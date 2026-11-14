package server

import (
	"errors"
	"net/http"
	"regexp"
	"strings"
	"time"

	"circuitpathways/internal/store"
)

// The classes kept on the school's server: teachers sign in with a teacher code, make classes and set work;
// students join with a class code and their first name(s) and school, and their work is kept with the class
// until it ends. The same API as the first (Cloudflare) version, so the pages work unchanged.

const defaultSchool = "Banyule Nillumbik Tech School"

var (
	itemRe   = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,63}$`)
	apps     = map[string]bool{"arduinopath": true, "pipath": true}
	kinds    = map[string]int{"sketch": 100 << 10, "progress": 64 << 10, "settings": 8 << 10}
	classURL = regexp.MustCompile(`^/api/teacher/class/([0-9A-Za-z-]{10,12})(/.*)?$`)
	studURL  = regexp.MustCompile(`^/students/([0-9a-f]{32})$`)
)

func bearer(r *http.Request) string {
	if a := r.Header.Get("Authorization"); a != "" {
		if len(a) > 7 && strings.EqualFold(a[:7], "bearer ") {
			return strings.TrimSpace(a[7:])
		}
	}
	return r.Header.Get(accessHeader)
}

// classesOff answers when this server keeps no classes (a student Pi passes these on to the main server).
func (s *Server) classesOff(w http.ResponseWriter) bool {
	if s.Store == nil {
		writeError(w, http.StatusServiceUnavailable, "no_classes", "Classes are kept on the school's Circuit Pathways server, and it can't be reached.")
		return true
	}
	return false
}

func (s *Server) handleSignIn(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.signin) || s.classesOff(w) {
		return
	}
	var req struct {
		Code string `json:"code"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	code := s.Teachers.Match(req.Code)
	if code == "" {
		// The same pause for every wrong code, so timing says nothing.
		time.Sleep(400 * time.Millisecond)
		writeError(w, http.StatusUnauthorized, "bad_code", "That teacher code isn't right. Check it and try again.")
		return
	}
	exp := s.Now().Add(teacherTTL)
	writeJSON(w, http.StatusOK, map[string]any{"token": s.Auth.TeacherToken(code, exp), "expires_at": exp.UnixMilli()})
}

func (s *Server) needTeacher(w http.ResponseWriter, r *http.Request) (string, bool) {
	if s.classesOff(w) {
		return "", false
	}
	t := s.Auth.Teacher(bearer(r), s.Now())
	if t == "" {
		writeError(w, http.StatusUnauthorized, "no_teacher", "Please sign in as a teacher again.")
		return "", false
	}
	return t, true
}

// storeError turns a database problem into a message (never the details).
func (s *Server) storeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, "no_class", "That class isn't one of yours (or it has ended).")
	case errors.Is(err, store.ErrTooMany):
		writeError(w, http.StatusTooManyRequests, "too_many", "You have a lot of classes running. Delete one you don't need first.")
	case errors.Is(err, store.ErrClassFull):
		writeError(w, http.StatusConflict, "class_full", "This class is full. Ask your teacher.")
	case errors.Is(err, store.ErrTooMuchWork):
		writeError(w, http.StatusConflict, "too_much", "You've saved a lot of work in this class. Ask your teacher to tidy it up.")
	case errors.Is(err, store.ErrBadEnd):
		writeError(w, http.StatusBadRequest, "bad_days", "Pick an end date within 400 days.")
	case errors.Is(err, store.ErrBadTask):
		writeError(w, http.StatusBadRequest, "bad_task", "That list of work couldn't be saved.")
	default:
		s.Log.Error("database", "err", err.Error())
		writeError(w, http.StatusInternalServerError, "oops", "Something went wrong on the server. Try again.")
	}
}

func (s *Server) handleTeacherClasses(w http.ResponseWriter, r *http.Request) {
	t, ok := s.needTeacher(w, r)
	if !ok {
		return
	}
	list, err := s.Store.TeacherClasses(r.Context(), t, s.Now())
	if err != nil {
		s.storeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"classes": list})
}

func (s *Server) handleNewClass(w http.ResponseWriter, r *http.Request) {
	t, ok := s.needTeacher(w, r)
	if !ok || s.limited(w, r, s.limits.class) {
		return
	}
	var req struct {
		Name   string `json:"name"`
		School string `json:"school"`
		Days   *int   `json:"days"`
		EndsAt *int64 `json:"ends_at"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	name, err := cleanLabel(req.Name)
	if err != nil {
		writeError(w, http.StatusBadRequest, "bad_name", err.Error())
		return
	}
	school := req.School
	if strings.TrimSpace(school) == "" {
		school = s.School
	}
	if school, err = cleanSchool(school); err != nil {
		writeError(w, http.StatusBadRequest, "bad_school", err.Error())
		return
	}
	ends, err := store.EndsAt(s.Now(), req.EndsAt, req.Days)
	if err != nil {
		s.storeError(w, err)
		return
	}
	c, err := s.Store.NewClass(r.Context(), t, name, school, s.Now(), ends)
	if err != nil {
		s.storeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, classOut(c))
}

func classOut(c store.Class) map[string]any {
	out := map[string]any{"code": c.Code, "name": c.Name, "school": c.School, "created_at": c.CreatedAt, "ends_at": c.EndsAt, "expires_at": c.EndsAt}
	if c.Students != nil {
		out["students"] = *c.Students
	}
	return out
}

// handleTeacherClass is everything under /api/teacher/class/<code>.
func (s *Server) handleTeacherClass(w http.ResponseWriter, r *http.Request) {
	m := classURL.FindStringSubmatch(r.URL.Path)
	if m == nil {
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
		return
	}
	t, ok := s.needTeacher(w, r)
	if !ok {
		return
	}
	ctx := r.Context()
	c, err := s.Store.TeacherClass(ctx, t, m[1], s.Now())
	if err != nil {
		s.storeError(w, err)
		return
	}
	rest := m[2]
	switch {
	case rest == "" && r.Method == http.MethodGet:
		list, err := s.Store.Students(ctx, c.Code)
		if err != nil {
			s.storeError(w, err)
			return
		}
		tasks, err := s.Store.Tasks(ctx, c.Code)
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"class": classOut(c), "students": list, "tasks": tasks})
	case rest == "/work" && r.Method == http.MethodGet:
		list, err := s.Store.ClassWork(ctx, c.Code)
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"class": classOut(c), "students": list})
	case rest == "/end" && r.Method == http.MethodPost:
		var req struct {
			Days   *int   `json:"days"`
			EndsAt *int64 `json:"ends_at"`
		}
		if !readJSON(w, r, &req) {
			return
		}
		ends, err := store.EndsAt(s.Now(), req.EndsAt, req.Days)
		if err == nil {
			err = s.Store.SetEnd(ctx, c.Code, ends)
		}
		if err != nil {
			s.storeError(w, err)
			return
		}
		c.EndsAt = ends
		writeJSON(w, http.StatusOK, classOut(c))
	case rest == "/tasks" && r.Method == http.MethodGet:
		tasks, err := s.Store.Tasks(ctx, c.Code)
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"tasks": tasks})
	case rest == "/tasks" && r.Method == http.MethodPut:
		var req struct {
			Tasks []store.Task `json:"tasks"`
		}
		if !readJSON(w, r, &req) {
			return
		}
		for i, t := range req.Tasks {
			t.Note = strings.TrimSpace(t.Note)
			if !apps[t.App] || !itemRe.MatchString(t.Item) || !store.TaskNoteOK(t.Note) || (t.App == "arduinopath" && t.Item != "freeplay" && s.Catalogue != nil && !s.hasProject(t.Item)) {
				writeError(w, http.StatusBadRequest, "bad_task", "One of those pieces of work isn't a project or activity on this server.")
				return
			}
			req.Tasks[i] = t
		}
		if err := s.Store.SetTasks(ctx, c.Code, req.Tasks, s.Now()); err != nil {
			s.storeError(w, err)
			return
		}
		tasks, _ := s.Store.Tasks(ctx, c.Code)
		writeJSON(w, http.StatusOK, map[string]any{"tasks": tasks})
	case rest == "" && r.Method == http.MethodDelete:
		if err := s.Store.DeleteClass(ctx, c.Code); err != nil {
			s.storeError(w, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		if sm := studURL.FindStringSubmatch(rest); sm != nil && r.Method == http.MethodDelete {
			if err := s.Store.RemoveStudent(ctx, c.Code, sm[1]); err != nil {
				s.storeError(w, err)
				return
			}
			w.WriteHeader(http.StatusNoContent)
			return
		}
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
	}
}

func (s *Server) hasProject(id string) bool {
	_, ok := s.Catalogue.Project(id)
	return ok
}

func (s *Server) handleJoin(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.join) || s.classesOff(w) {
		return
	}
	var req struct {
		Code   string    `json:"code"`
		Names  *[]string `json:"names"`
		School string    `json:"school"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	ctx := r.Context()
	c, err := s.Store.RunningClass(ctx, req.Code, s.Now())
	if err != nil {
		time.Sleep(300 * time.Millisecond)
		writeError(w, http.StatusNotFound, "no_class", "That class code isn't right, or the class has ended. Check it with your teacher.")
		return
	}
	if req.Names == nil {
		writeJSON(w, http.StatusOK, map[string]any{"needs_names": true, "class": classOut(c), "expires_at": c.EndsAt})
		return
	}
	names, err := cleanNames(*req.Names)
	if err != nil {
		writeError(w, http.StatusBadRequest, "bad_names", err.Error())
		return
	}
	school := req.School
	if strings.TrimSpace(school) == "" {
		school = c.School
	}
	if school, err = cleanSchool(school); err != nil {
		writeError(w, http.StatusBadRequest, "bad_school", err.Error())
		return
	}
	id, err := s.Store.Join(ctx, c.Code, names, school, s.Now())
	if err != nil {
		s.storeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"token": s.Auth.StudentToken(id), "expires_at": c.EndsAt, "class": classOut(c),
		"student": map[string]any{"names": names, "school": school},
	})
}

// member is the student asking, if their class is still running.
func (s *Server) member(r *http.Request) (store.Member, bool) {
	if s.Store == nil {
		return store.Member{}, false
	}
	id := s.Auth.Student(bearer(r))
	if id == "" {
		return store.Member{}, false
	}
	m, err := s.Store.Member(r.Context(), id, s.Now())
	return m, err == nil
}

func (s *Server) handleStudent(w http.ResponseWriter, r *http.Request) {
	if s.classesOff(w) {
		return
	}
	st, ok := s.member(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "no_class", "Your class has ended, or you've been taken off it. Join again with a class code.")
		return
	}
	ctx := r.Context()
	me := func() (map[string]any, error) {
		tasks, err := s.Store.Tasks(ctx, st.ClassCode)
		return map[string]any{
			"class":   map[string]any{"code": store.ShowCode(st.ClassCode), "name": st.ClassName, "school": st.ClassSchool, "ends_at": st.EndsAt},
			"student": map[string]any{"names": st.Names, "school": st.School},
			"tasks":   tasks,
		}, err
	}
	switch {
	case r.URL.Path == "/api/student/me" && r.Method == http.MethodGet:
		s.Store.Seen(ctx, st.ID, s.Now())
		out, err := me()
		if err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, out)
	case r.URL.Path == "/api/student/me" && r.Method == http.MethodDelete:
		if err := s.Store.DeleteStudent(ctx, st.ID); err != nil {
			s.storeError(w, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	case r.URL.Path == "/api/student/work" && r.Method == http.MethodGet:
		work, err := s.Store.MyWork(ctx, st.ID)
		if err != nil {
			s.storeError(w, err)
			return
		}
		out, err := me()
		if err != nil {
			s.storeError(w, err)
			return
		}
		out["work"] = work
		writeJSON(w, http.StatusOK, out)
	case r.URL.Path == "/api/student/work" && r.Method == http.MethodPost:
		if s.limited(w, r, s.limits.work) {
			return
		}
		var req struct {
			Items []struct {
				App       string   `json:"app"`
				Item      string   `json:"item"`
				Kind      string   `json:"kind"`
				Body      *string  `json:"body"`
				UpdatedAt *float64 `json:"updated_at"`
			} `json:"items"`
		}
		if !readJSON(w, r, &req) {
			return
		}
		if len(req.Items) == 0 || len(req.Items) > 25 {
			writeError(w, http.StatusBadRequest, "bad_items", "Send 1 to 25 pieces of work at a time.")
			return
		}
		now := s.Now().UnixMilli()
		items := make([]store.Work, 0, len(req.Items))
		for _, it := range req.Items {
			limit, kindOK := kinds[it.Kind]
			if !apps[it.App] || !itemRe.MatchString(it.Item) || !kindOK || it.Body == nil {
				writeError(w, http.StatusBadRequest, "bad_item", "That work couldn't be saved.")
				return
			}
			if len(*it.Body) > limit {
				writeError(w, http.StatusRequestEntityTooLarge, "too_big", "That work is too big to save.")
				return
			}
			at := now
			if it.UpdatedAt != nil && *it.UpdatedAt > 0 && int64(*it.UpdatedAt) < now {
				at = int64(*it.UpdatedAt)
			}
			items = append(items, store.Work{App: it.App, Item: it.Item, Kind: it.Kind, Body: *it.Body, UpdatedAt: at})
		}
		if err := s.Store.SaveWork(ctx, st.ID, items, s.Now()); err != nil {
			s.storeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"saved": len(items), "at": now})
	default:
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
	}
}

// accessOK: who may compile and use the Pi relay. On the school's network anyone may (the simulator and
// uploading don't need a class), but a token that is sent must be real: a teacher's, or a student's in a
// running class. "local" is the browser's word for a student who hasn't joined a class. A student Pi
// answers only its own Pi, so it lets everything through (it can't look classes up when it is offline).
func (s *Server) accessOK(r *http.Request, token string) bool {
	if s.Store == nil {
		return true
	}
	switch {
	case token == "" || token == "local":
		return true
	case strings.HasPrefix(token, "t2."):
		return s.Auth.Teacher(token, s.Now()) != ""
	case strings.HasPrefix(token, "s2."):
		id := s.Auth.Student(token)
		if id == "" {
			return false
		}
		_, err := s.Store.Member(r.Context(), id, s.Now())
		return err == nil
	}
	return false
}
