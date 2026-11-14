package server

import (
	"crypto/tls"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"circuitpathways/internal/pilink"
	"circuitpathways/internal/tlsca"
)

// A student Pi serves the site itself and passes classes on to the school server over https (trusting only
// the school server's own certificate authority). When the school server can't be reached, the page is told
// it is offline, and everything that doesn't need the school server keeps working.
func TestAStudentPiUsesTheSchoolServerAndCopesWithoutIt(t *testing.T) {
	school, _ := newTest(t)
	authority, err := tlsca.Open(t.TempDir(), func() ([]string, []net.IP) {
		return []string{"localhost"}, []net.IP{net.ParseIP("127.0.0.1")}
	})
	if err != nil {
		t.Fatal(err)
	}
	ts := httptest.NewUnstartedServer(school)
	ts.Listener = tls.NewListener(ts.Listener, authority.TLSConfig())
	ts.Start()
	ts.URL = strings.Replace(ts.URL, "http://", "https://", 1)
	caFile := filepath.Join(t.TempDir(), "school-ca.crt")
	os.WriteFile(caFile, authority.CAPEM(), 0o644)

	// a student Pi that only trusts the system's certificates can't reach it...
	wrong, _ := NewUpstream(ts.URL, "", nil)
	if wrong.Check(t.Context()) {
		t.Fatal("a student Pi trusted the school server without its certificate")
	}
	// ...one with the school's certificate can
	up, err := NewUpstream(ts.URL, caFile, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !up.Check(t.Context()) {
		t.Fatal("the student Pi couldn't reach the school server")
	}
	piKeys, _ := pilink.NewKeys("this-pi-secret-0123456789", nil)
	site := school.Site
	pi := New(Config{Site: site, Catalogue: school.Catalogue, Mode: ModeStudentPi, Upstream: up, PiKeys: piKeys})
	c := caller{t, pi}

	_, info := c.do("GET", "/api/info", "", nil)
	if info["edition"] != ModeStudentPi || info["online"] != true || info["relay"] != "sse" {
		t.Fatalf("info: %v", info)
	}
	// the teacher and the student both go through the Pi to the school server
	tok := c.teacher("teacher-code-1234")
	_, made := c.do("POST", "/api/teacher/class", tok, map[string]any{"name": "Pi room"})
	code := made["code"].(string)
	st, joined := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"Kai"}})
	if st != 200 {
		t.Fatalf("join through the Pi: %d %v", st, joined)
	}
	stu := joined["token"].(string)
	if st, _ := c.do("POST", "/api/student/work", stu, map[string]any{"items": []any{map[string]any{"app": "pipath", "item": "s1_hello", "kind": "sketch", "body": "print('hi')"}}}); st != 200 {
		t.Fatalf("save work through the Pi: %d", st)
	}
	work, _ := school.Store.ClassWork(t.Context(), code)
	if len(work) != 1 || len(work[0].Work) != 1 {
		t.Fatalf("the school server has %v", work)
	}
	// with no board tools of its own, the Pi passes compiles on too
	if st, m := c.do("POST", "/api/compile", stu, map[string]string{"code": "void setup(){}\nvoid loop(){}", "board": "uno"}); st != 200 || m["ok"] != true {
		t.Fatalf("compile through the Pi: %d %v", st, m)
	}

	// the school server goes away
	ts.Close()
	st, m := c.do("POST", "/api/student/work", stu, map[string]any{"items": []any{map[string]any{"app": "pipath", "item": "s1_hello", "kind": "sketch", "body": "print('offline')"}}})
	if st != http.StatusServiceUnavailable || m["error"] != "offline" {
		t.Fatalf("offline: %d %v", st, m)
	}
	_, info = c.do("GET", "/api/info", "", nil)
	if info["online"] != false || info["compile"] != false {
		t.Fatalf("info when offline: %v", info)
	}
	// the site itself still works
	w := httptest.NewRecorder()
	pi.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Code != 200 {
		t.Fatalf("the home page offline: %d", w.Code)
	}
}

func TestTheSchoolServerHandsOutTheStudentPiInstaller(t *testing.T) {
	s, _ := newTest(t)
	authority, _ := tlsca.Open(t.TempDir(), func() ([]string, []net.IP) { return []string{"pathways.local"}, nil })
	prog := filepath.Join(t.TempDir(), "circuitpathways")
	os.WriteFile(prog, []byte("pretend program"), 0o755)
	s2 := New(Config{Site: s.Site, Catalogue: s.Catalogue, Store: s.Store, Auth: s.Auth, Teachers: s.Teachers, Install: &Installer{Program: prog, CAPEM: authority.CAPEM(), HTTPSPort: "443"}})

	r := httptest.NewRequest("GET", "/install/student-pi.sh", nil)
	r.Host = "pathways.local"
	w := httptest.NewRecorder()
	s2.ServeHTTP(w, r)
	body := w.Body.String()
	if w.Code != 200 {
		t.Fatalf("installer: %d %s", w.Code, body)
	}
	for _, want := range []string{`SCHOOL="https://pathways.local"`, `HTTP_BASE="http://pathways.local"`, "-----BEGIN CERTIFICATE-----", "-mode student-pi", "SHA256=\"", "pi-installer -server"} {
		if !strings.Contains(body, want) {
			t.Errorf("the installer doesn't have %q", want)
		}
	}
	// a host name that isn't safe in a script is refused
	r = httptest.NewRequest("GET", "/install/student-pi.sh", nil)
	r.Host = "evil;rm -rf"
	w = httptest.NewRecorder()
	s2.ServeHTTP(w, r)
	if w.Code == 200 {
		t.Fatal("made an installer for a strange host name")
	}
	// the certificate, for laptops
	w = httptest.NewRecorder()
	s2.ServeHTTP(w, httptest.NewRequest("GET", "/ca.crt", nil))
	if w.Code != 200 || w.Header().Get("Content-Type") != "application/x-x509-ca-cert" || !strings.Contains(w.Body.String(), "BEGIN CERTIFICATE") {
		t.Fatalf("ca.crt: %d %s", w.Code, w.Header())
	}
	// the info says https is there
	w = httptest.NewRecorder()
	s2.Config.TLS = true
	s2.ServeHTTP(w, httptest.NewRequest("GET", "/api/info", nil))
	var info map[string]any
	json.Unmarshal(w.Body.Bytes(), &info)
	if info["edition"] != ModeSchool || info["classes"] != true || info["class_optional"] != true {
		t.Fatalf("info: %v", info)
	}
}
