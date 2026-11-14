package server

import (
	"errors"
	"net/http"
	"regexp"
	"strings"

	"circuitpathways/internal/setup"
	"circuitpathways/internal/store"
)

// The school's ESP boards (see internal/store/boards.go): teachers set them up from the teacher portal, students
// claim one with the code on its sticker, and ArduinoPath uses that board's own WiFi name and password and only
// uploads to it.

var (
	labelRe    = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9 -]{0,15}$`)
	macRe      = regexp.MustCompile(`^([0-9a-f]{2}:){5}[0-9a-f]{2}$`)
	boardURL   = regexp.MustCompile(`^/api/teacher/boards/([0-9a-f]{32})(/[a-z]+)?$`)
	espFamilyS = []string{"esp8266:", "esp32:"}
)

func (s *Server) isESP(kind string) bool {
	if s.Catalogue == nil {
		return false
	}
	b, ok := s.Catalogue.Board(kind)
	if !ok {
		return false
	}
	for _, f := range espFamilyS {
		if strings.HasPrefix(b.FQBN, f) {
			return true
		}
	}
	return false
}

func (s *Server) boardError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, "no_board", "There's no board with that code in your class. Check the code on its sticker.")
	case errors.Is(err, store.ErrBoardTaken):
		writeError(w, http.StatusConflict, "board_taken", "Someone else has that board. Check the code, or ask your teacher.")
	case errors.Is(err, store.ErrSameLabel):
		writeError(w, http.StatusConflict, "same_label", "You already have a board with that label. Pick another.")
	case errors.Is(err, store.ErrTooMany):
		writeError(w, http.StatusTooManyRequests, "too_many", "That's a lot of boards. Delete ones you no longer use first.")
	default:
		s.storeError(w, err)
	}
}

// handleTeacherBoards: GET the teacher's boards, POST a new one.
func (s *Server) handleTeacherBoards(w http.ResponseWriter, r *http.Request) {
	t, ok := s.needTeacher(w, r)
	if !ok {
		return
	}
	if r.Method == http.MethodGet {
		list, err := s.Store.TeacherBoards(r.Context(), t)
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"boards": list})
		return
	}
	if s.limited(w, r, s.limits.class) {
		return
	}
	var req struct {
		Label string `json:"label"`
		Kind  string `json:"kind"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	req.Label = strings.TrimSpace(req.Label)
	if !labelRe.MatchString(req.Label) {
		writeError(w, http.StatusBadRequest, "bad_label", "A board's label is up to 16 letters, numbers, spaces or dashes, like ESP-07. No student names.")
		return
	}
	if !s.isESP(req.Kind) {
		writeError(w, http.StatusBadRequest, "bad_board", "Pick an ESP board (NodeMCU, D1 mini, ESP32...).")
		return
	}
	b, err := s.Store.NewBoard(r.Context(), t, req.Label, req.Kind, s.Now())
	if err != nil {
		s.boardError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, b)
}

// handleTeacherBoard is everything under /api/teacher/boards/<id>.
func (s *Server) handleTeacherBoard(w http.ResponseWriter, r *http.Request) {
	m := boardURL.FindStringSubmatch(r.URL.Path)
	if m == nil {
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
		return
	}
	t, ok := s.needTeacher(w, r)
	if !ok {
		return
	}
	ctx := r.Context()
	b, err := s.Store.TeacherBoard(ctx, t, m[1])
	if err != nil {
		writeError(w, http.StatusNotFound, "no_board", "That board isn't one of yours.")
		return
	}
	switch {
	case m[2] == "/sketch" && r.Method == http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{"code": setup.BoardSketch(b.Label, b.SSID, b.Password), "board": b.Kind})
	case m[2] == "/flashed" && r.Method == http.MethodPost:
		var req struct {
			MAC string `json:"mac"`
		}
		if !readJSON(w, r, &req) {
			return
		}
		mac := strings.ToLower(strings.TrimSpace(req.MAC))
		if !macRe.MatchString(mac) {
			writeError(w, http.StatusBadRequest, "bad_mac", "That isn't a board's MAC address.")
			return
		}
		if err := s.Store.BoardFlashed(ctx, t, b.ID, mac, s.Now()); err != nil {
			s.boardError(w, err)
			return
		}
		b, _ = s.Store.TeacherBoard(ctx, t, b.ID)
		writeJSON(w, http.StatusOK, b)
	case m[2] == "/release" && r.Method == http.MethodPost:
		if err := s.Store.ReleaseBoard(ctx, t, b.ID); err != nil {
			s.boardError(w, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	case m[2] == "" && r.Method == http.MethodDelete:
		if err := s.Store.DeleteBoard(ctx, t, b.ID); err != nil {
			s.boardError(w, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
	}
}

// handleStudentBoard: a student's own board (GET), claiming one with its code (POST), giving it back (DELETE).
func (s *Server) handleStudentBoard(w http.ResponseWriter, r *http.Request, st store.Member) {
	ctx := r.Context()
	switch r.Method {
	case http.MethodGet:
		b, err := s.Store.StudentBoard(ctx, st.ID)
		if errors.Is(err, store.ErrNotFound) {
			writeJSON(w, http.StatusOK, map[string]any{"board": nil})
			return
		}
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"board": b})
	case http.MethodPost:
		if s.limited(w, r, s.limits.join) {
			return
		}
		var req struct {
			Code string `json:"code"`
		}
		if !readJSON(w, r, &req) {
			return
		}
		b, err := s.Store.ClaimBoard(ctx, st.ID, st.ClassCode, req.Code)
		if err != nil {
			s.boardError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"board": b})
	case http.MethodDelete:
		if err := s.Store.GiveBackBoard(ctx, st.ID); err != nil {
			s.storeError(w, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		writeError(w, http.StatusMethodNotAllowed, "not_found", "There's nothing here.")
	}
}
