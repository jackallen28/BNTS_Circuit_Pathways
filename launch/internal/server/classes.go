package server

import (
	"net/http"
	"strings"
	"time"
)

func (s *Server) handleSignIn(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.signin) {
		return
	}
	var req struct {
		Code string `json:"code"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	if !s.Teachers.Check(req.Code) {
		// The same pause for every wrong code, so timing says nothing.
		time.Sleep(400 * time.Millisecond)
		writeError(w, http.StatusUnauthorized, "bad_teacher_code", "That teacher code isn't right. Check it and try again.")
		return
	}
	token, exp := s.Signer.NewTeacherToken(s.Now(), teacherTTL)
	writeJSON(w, http.StatusOK, map[string]any{"token": token, "expires_at": exp.UnixMilli()})
}

func (s *Server) teacherToken(r *http.Request) bool {
	tok := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	return tok != "" && s.Signer.VerifyTeacherToken(tok, s.Now())
}

func (s *Server) handleNewClass(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.class) {
		return
	}
	if !s.teacherToken(r) {
		writeError(w, http.StatusUnauthorized, "teacher_only", "Sign in with your teacher code first.")
		return
	}
	var req struct {
		Days int `json:"days"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	code, exp, err := s.Signer.NewClass(s.Now(), req.Days)
	if err != nil {
		writeError(w, http.StatusBadRequest, "bad_days", "Pick how many days the class code should work (1 to 366).")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"code": code, "expires_at": exp.UnixMilli()})
}

func (s *Server) handleJoin(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.join) {
		return
	}
	var req struct {
		Code string `json:"code"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	exp, ok := s.Signer.Verify(req.Code, s.Now())
	if !ok {
		time.Sleep(300 * time.Millisecond)
		if !exp.IsZero() {
			writeError(w, http.StatusGone, "class_over", "That class code has finished. Ask your teacher for a new one.")
			return
		}
		writeError(w, http.StatusNotFound, "bad_class_code", "That class code isn't right. Check it with your teacher.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "expires_at": exp.UnixMilli()})
}
