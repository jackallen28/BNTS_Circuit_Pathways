package server

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/fstest"
	"time"

	"circuitpathways"
	"circuitpathways/internal/arduino"
	"circuitpathways/internal/classes"
	"circuitpathways/internal/content"
)

type fakeCompiler struct {
	last string
	ok   bool
}

func (f *fakeCompiler) Compile(ctx context.Context, code, fqbn string, props []string) (arduino.CompileResult, []arduino.Artifact, error) {
	f.last = fqbn
	if !f.ok {
		return arduino.CompileResult{OK: false, Output: "sketch.ino:1:1: error: boom", Diagnostics: []arduino.Diagnostic{{File: "sketch.ino", Line: 1, Severity: "error", Message: "boom"}}}, nil, nil
	}
	return arduino.CompileResult{OK: true}, []arduino.Artifact{{Name: "sketch.ino.hex", Data: []byte(":00000001FF\n")}}, nil
}

func newTest(t *testing.T) (*Server, *fakeCompiler) {
	t.Helper()
	cat, problems := content.Load(launch.Content())
	if len(problems) > 0 {
		t.Fatal(problems[0])
	}
	signer, _ := classes.New("test-secret-0123456789")
	fc := &fakeCompiler{ok: true}
	site := fstest.MapFS{
		"index.html":             {Data: []byte("<h1>home</h1>")},
		"arduinopath/index.html": {Data: []byte("<h1>ap</h1>")},
	}
	return New(Config{Site: site, Catalogue: cat, Signer: signer, Teachers: classes.ParseTeacherCodes("teacher-code-1234"), Compiler: fc, Log: nil}), fc
}

func post(s *Server, path string, body any, hdr map[string]string) *httptest.ResponseRecorder {
	b, _ := json.Marshal(body)
	r := httptest.NewRequest("POST", path, bytes.NewReader(b))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set(headerName, "1")
	for k, v := range hdr {
		r.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}

func decode(t *testing.T, w *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &m); err != nil {
		t.Fatalf("not json: %q", w.Body.String())
	}
	return m
}

func TestTeacherMakesAClassAndStudentsJoin(t *testing.T) {
	s, _ := newTest(t)
	if w := post(s, "/api/teacher/signin", map[string]string{"code": "wrong-code-here"}, nil); w.Code != 401 {
		t.Fatalf("wrong teacher code: %d", w.Code)
	}
	w := post(s, "/api/teacher/signin", map[string]string{"code": "teacher-code-1234"}, nil)
	if w.Code != 200 {
		t.Fatalf("signin: %d %s", w.Code, w.Body)
	}
	token := decode(t, w)["token"].(string)

	// no token, no class
	if w := post(s, "/api/teacher/class", map[string]int{"days": 7}, nil); w.Code != 401 {
		t.Fatalf("class without sign-in: %d", w.Code)
	}
	w = post(s, "/api/teacher/class", map[string]int{"days": 7}, map[string]string{"Authorization": "Bearer " + token})
	if w.Code != 200 {
		t.Fatalf("class: %d %s", w.Code, w.Body)
	}
	code := decode(t, w)["code"].(string)

	if w := post(s, "/api/class/join", map[string]string{"code": strings.ToLower(code)}, nil); w.Code != 200 {
		t.Fatalf("join: %d %s", w.Code, w.Body)
	}
	if w := post(s, "/api/class/join", map[string]string{"code": "ZZZZZ-ZZZZZ"}, nil); w.Code != 404 {
		t.Fatalf("bad code: %d", w.Code)
	}
	if w := post(s, "/api/teacher/class", map[string]int{"days": 0}, map[string]string{"Authorization": "Bearer " + token}); w.Code != 400 {
		t.Fatalf("0 days: %d", w.Code)
	}
}

func TestExpiredClassCode(t *testing.T) {
	s, _ := newTest(t)
	code, _, _ := s.Signer.NewClass(time.Now().AddDate(0, 0, -10), 3)
	if w := post(s, "/api/class/join", map[string]string{"code": code}, nil); w.Code != 410 {
		t.Fatalf("expired code: %d %s", w.Code, w.Body)
	}
}

func TestCompileNeedsAClassAndPassesTheBoard(t *testing.T) {
	s, fc := newTest(t)
	body := map[string]string{"code": "void setup(){}\nvoid loop(){}", "board": "uno"}
	if w := post(s, "/api/compile", body, nil); w.Code != 401 {
		t.Fatalf("no class code: %d", w.Code)
	}
	code, _, _ := s.Signer.NewClass(time.Now(), 2)
	w := post(s, "/api/compile", body, map[string]string{accessHeader: code})
	if w.Code != 200 {
		t.Fatalf("compile: %d %s", w.Code, w.Body)
	}
	m := decode(t, w)
	if m["ok"] != true || len(m["artifacts"].([]any)) != 1 {
		t.Fatalf("response: %v", m)
	}
	if fc.last != "arduino:avr:uno" {
		t.Errorf("compiled for %q", fc.last)
	}
	// a teacher token works too
	tok, _ := s.Signer.NewTeacherToken(time.Now(), time.Hour)
	if w := post(s, "/api/compile", body, map[string]string{accessHeader: tok}); w.Code != 200 {
		t.Fatalf("teacher compile: %d", w.Code)
	}
	// errors come back for the Coach, with no artifacts
	fc.ok = false
	m = decode(t, post(s, "/api/compile", body, map[string]string{accessHeader: code}))
	if m["ok"] != false || m["artifacts"] != nil || len(m["errors"].([]any)) != 1 {
		t.Fatalf("failed compile response: %v", m)
	}
	for _, bad := range []map[string]string{{"code": "", "board": "uno"}, {"code": "x", "board": "nope"}, {"code": "x", "board": "uno", "variant": "nope"}} {
		if w := post(s, "/api/compile", bad, map[string]string{accessHeader: code}); w.Code != 400 {
			t.Errorf("%v: %d", bad, w.Code)
		}
	}
}

func TestWritesNeedOurHeaderAndJSON(t *testing.T) {
	s, _ := newTest(t)
	r := httptest.NewRequest("POST", "/api/class/join", strings.NewReader(`{"code":"x"}`))
	r.Header.Set("Content-Type", "text/plain")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatalf("a cross-site style request got %d", w.Code)
	}
	r = httptest.NewRequest("POST", "/api/class/join", strings.NewReader(`{"code":"x"}`))
	r.Header.Set("Content-Type", "application/json")
	w = httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatalf("a request without our header got %d", w.Code)
	}
}

func TestTooBigSketch(t *testing.T) {
	s, _ := newTest(t)
	code, _, _ := s.Signer.NewClass(time.Now(), 2)
	w := post(s, "/api/compile", map[string]string{"code": strings.Repeat("a", 200<<10), "board": "uno"}, map[string]string{accessHeader: code})
	if w.Code != 413 {
		t.Fatalf("a 200 KB sketch got %d", w.Code)
	}
}

func TestRateLimitOnTeacherSignIn(t *testing.T) {
	s, _ := newTest(t)
	var last int
	for i := 0; i < 8; i++ {
		last = post(s, "/api/teacher/signin", map[string]string{"code": "guess-guess-guess"}, nil).Code
	}
	if last != http.StatusTooManyRequests {
		t.Fatalf("8 wrong guesses ended with %d, want 429", last)
	}
}

func TestPagesAndHeaders(t *testing.T) {
	s, _ := newTest(t)
	for path, want := range map[string]string{"/": "home", "/arduinopath/": "ap"} {
		w := httptest.NewRecorder()
		s.ServeHTTP(w, httptest.NewRequest("GET", path, nil))
		if w.Code != 200 || !strings.Contains(w.Body.String(), want) {
			t.Errorf("%s: %d %q", path, w.Code, w.Body)
		}
		h := w.Header()
		if !strings.Contains(h.Get("Content-Security-Policy"), "default-src 'self'") || h.Get("X-Content-Type-Options") != "nosniff" ||
			!strings.Contains(h.Get("Permissions-Policy"), "serial=(self)") {
			t.Errorf("%s: security headers missing: %v", path, h)
		}
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/arduinopath", nil))
	if w.Code != 301 {
		t.Errorf("/arduinopath should redirect to /arduinopath/, got %d", w.Code)
	}
}

func TestCatalogueAndProjects(t *testing.T) {
	s, _ := newTest(t)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/arduinopath/data/catalogue.json", nil))
	m := decode(t, w)
	if len(m["boards"].([]any)) < 5 || len(m["projects"].([]any)) < 20 {
		t.Fatalf("catalogue looks empty: %d bytes", w.Body.Len())
	}
	w = httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/arduinopath/data/projects/smart-bin.json", nil))
	if w.Code != 200 || decode(t, w)["id"] != "smart-bin" {
		t.Fatalf("smart-bin: %d", w.Code)
	}
	w = httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/arduinopath/data/projects/nope.json", nil))
	if w.Code != 404 {
		t.Fatalf("unknown project: %d", w.Code)
	}
}
