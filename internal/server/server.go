// Package server is Circuit Pathways: PiPath and ArduinoPath in the browser, served by the school's own
// Raspberry Pi on the school network. It does what a browser can't do alone: it keeps classes (teachers'
// classes, the work they set, and students' first names, school and work, until the class ends), it
// compiles Arduino code for real boards, and it relays a Raspberry Pi's pins to the browser.
//
// The same program runs in two ways:
//
//   - the school server (the main Pi): the site, the classes and the compiler, for every computer on the network;
//   - a student Pi: the site on the Pi itself (so it works with no network), its own Pi Link, and classes and
//     compiling passed on to the school server whenever it can be reached.
//
// Nothing it logs includes a request body, a name or an address.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"circuitpathways/internal/arduino"
	"circuitpathways/internal/auth"
	"circuitpathways/internal/content"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/pirelay"
	"circuitpathways/internal/store"
)

// Compiler compiles a sketch (arduino.Tools; tests use a fake).
type Compiler interface {
	Compile(ctx context.Context, code, fqbn string, props []string) (arduino.CompileResult, []arduino.Artifact, error)
}

// The two ways the server runs.
const (
	ModeSchool    = "school"     // the main Pi: classes, the compiler, the site for the whole network
	ModeStudentPi = "student-pi" // a student's Pi: the site and Pi Link for this Pi, the rest from the school server
)

// Config is everything the server needs.
type Config struct {
	Site      fs.FS
	Catalogue *content.Catalogue
	// Mode is ModeSchool (the default) or ModeStudentPi.
	Mode string
	// Store keeps the classes (the school server). Nil on a student Pi.
	Store *store.Store
	// Auth signs teacher and student tokens (the school server).
	Auth *auth.Signer
	// Teachers are the school's teacher codes (the school server).
	Teachers *auth.Teachers
	// School is the school's name, filled in for new classes.
	School   string
	Compiler Compiler // nil: compiling is off (a student Pi then passes compiles on to the school server)
	Version  string
	Commit   string
	Log      *slog.Logger
	Now      func() time.Time // nil: time.Now
	// MaxCompiles is how many compiles can run at once (default 2).
	MaxCompiles int
	// Relay connects browsers to Raspberry Pis (nil: a new one).
	Relay *pirelay.Relay
	// PiKeys checks Raspberry Pi keys (nil: Pi Link is off).
	PiKeys *pilink.Keys
	// Upstream is the school server, for a student Pi (nil on the school server).
	Upstream *Upstream
	// Name is what the server calls itself (its address on the network, for the pages).
	Name string
	// Install serves the student-Pi installer and this program for it (the school server).
	Install *Installer
	// TLS says the school server also answers on https (for the start page's advice).
	TLS bool
}

// Server is the http.Handler.
type Server struct {
	Config
	static  http.Handler
	handler http.Handler
	slots   chan struct{}
	limits  struct{ signin, join, class, compile, piCommand, work *limiter }
}

const (
	maxBody       = 640 << 10 // a sketch is limited to 100 KB; 25 pieces of work at a time
	teacherTTL    = 12 * time.Hour
	compileWait   = 90 * time.Second
	headerName    = "X-Circuit-Pathways"
	accessHeader  = "X-Access"
	defaultSlots  = 2
	maxSketchSize = 100 << 10
)

// New makes the server.
func New(cfg Config) *Server {
	if cfg.Log == nil {
		cfg.Log = slog.Default()
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	if cfg.Mode == "" {
		cfg.Mode = ModeSchool
	}
	if cfg.School == "" {
		cfg.School = defaultSchool
	}
	if cfg.Teachers == nil {
		cfg.Teachers = auth.NewTeachers("", "")
	}
	if cfg.MaxCompiles < 1 {
		cfg.MaxCompiles = defaultSlots
	}
	s := &Server{Config: cfg, static: http.FileServerFS(cfg.Site), slots: make(chan struct{}, cfg.MaxCompiles)}
	s.limits.signin = newLimiter(5, time.Minute)
	s.limits.join = newLimiter(20, time.Minute)
	s.limits.class = newLimiter(30, time.Minute)
	s.limits.compile = newLimiter(15, time.Minute)
	s.limits.piCommand = newLimiter(900, time.Minute)
	s.limits.work = newLimiter(240, time.Minute)
	if s.Relay == nil {
		s.Relay = pirelay.New(cfg.Now)
	}
	go func() {
		for range time.Tick(30 * time.Second) {
			s.Relay.Sweep()
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok\n")) })
	mux.HandleFunc("GET /api/info", s.handleInfo)
	if s.Upstream != nil {
		// a student Pi: classes (and compiling, without tools of its own) are the school server's
		for _, p := range []string{"/api/teacher/", "/api/class/", "/api/student/"} {
			mux.Handle(p, s.Upstream)
		}
		if s.Compiler == nil {
			mux.Handle("POST /api/compile", s.Upstream)
		} else {
			mux.HandleFunc("POST /api/compile", s.handleCompile)
		}
	} else {
		mux.HandleFunc("POST /api/teacher/signin", s.handleSignIn)
		mux.HandleFunc("GET /api/teacher/classes", s.handleTeacherClasses)
		mux.HandleFunc("POST /api/teacher/class", s.handleNewClass)
		mux.HandleFunc("/api/teacher/class/", s.handleTeacherClass)
		mux.HandleFunc("/api/teacher/boards", s.handleTeacherBoards)
		mux.HandleFunc("/api/teacher/boards/", s.handleTeacherBoard)
		mux.HandleFunc("POST /api/class/join", s.handleJoin)
		mux.HandleFunc("/api/student/", s.handleStudent)
		mux.HandleFunc("POST /api/compile", s.handleCompile)
	}
	s.piRoutes(mux)
	if s.Install != nil {
		s.Install.routes(mux)
	}
	mux.HandleFunc("GET /arduinopath/data/catalogue.json", s.handleCatalogue)
	mux.HandleFunc("GET /arduinopath/data/projects/{id}", s.handleProject)
	mux.HandleFunc("/api/", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, http.StatusNotFound, "not_found", "There's nothing here.")
	})
	mux.Handle("/", s.staticHandler())
	s.handler = s.guard(mux)
	return s
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) { s.handler.ServeHTTP(w, r) }

// guard adds the security headers, a body limit, the "writes need our
// header" rule, and logging that leaves out everything personal.
func (s *Server) guard(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		h := w.Header()
		h.Set("Content-Security-Policy", cspFor(r.URL.Path))
		h.Set("X-Robots-Tag", "noindex, nofollow") // a school's own server, not a page for search engines
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "SAMEORIGIN")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("Cross-Origin-Opener-Policy", "same-origin")
		h.Set("Cross-Origin-Resource-Policy", "same-origin")
		if strings.HasPrefix(r.URL.Path, "/pipath/") {
			// Python in the browser runs a student's program in a worker that waits for button
			// presses in shared memory, which the browser only allows on an isolated page.
			h.Set("Cross-Origin-Embedder-Policy", "require-corp")
		}
		// Web Serial (uploading to a board) only on our own pages; nothing else is needed.
		h.Set("Permissions-Policy", permissionsPolicy)
		if strings.HasPrefix(r.URL.Path, "/api/") {
			h.Set("Cache-Control", "no-store")
			if r.Method != http.MethodGet && r.Method != http.MethodHead {
				if r.Header.Get(headerName) != "1" || !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
					writeError(w, http.StatusForbidden, "bad_request", "That request didn't come from the Circuit Pathways page.")
					return
				}
				r.Body = http.MaxBytesReader(w, r.Body, maxBody)
			}
		}
		if host := hostOnly(r.Host); !allowedHost(host) {
			http.Error(w, "unknown host", http.StatusMisdirectedRequest)
			return
		}
		rec := &statusRecorder{ResponseWriter: w, status: 200}
		next.ServeHTTP(rec, r)
		// Method, path, status and time only: never an address, a body or a header.
		if strings.HasPrefix(r.URL.Path, "/api/") {
			s.Log.Info("request", "method", r.Method, "path", r.URL.Path, "status", rec.status, "ms", time.Since(start).Milliseconds())
		}
	})
}

// The apps run under a strict policy: everything from our own address, no
// inline styles or scripts, nothing from anywhere else. Only the home page
// and teacher page need inline styles (the spinning logo is drawn with them).
const cspBase = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; img-src 'self' data: blob:; media-src 'self' blob:; " +
	"font-src 'self'; connect-src 'self'; worker-src 'self' blob:; frame-src 'self'; frame-ancestors 'self'; " +
	"object-src 'none'; base-uri 'none'; form-action 'self'"

func cspFor(path string) string {
	if strings.HasPrefix(path, "/arduinopath/") || strings.HasPrefix(path, "/pipath/") {
		return cspBase + "; style-src 'self'"
	}
	return cspBase + "; style-src 'self' 'unsafe-inline'"
}

func hostOnly(h string) string {
	if i := strings.LastIndex(h, ":"); i > 0 && !strings.Contains(h[i:], "]") {
		h = h[:i]
	}
	return strings.ToLower(h)
}

// allowedHost: on the school's network the server is reached by its name (pathways.local), its address,
// or (on a student Pi) localhost. Any of them is fine; a request with no host isn't.
func allowedHost(h string) bool { return h != "" }

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) { r.status = code; r.ResponseWriter.WriteHeader(code) }

// Unwrap lets http.ResponseController reach the real writer (for streaming).
func (r *statusRecorder) Unwrap() http.ResponseWriter { return r.ResponseWriter }

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"error": code, "message": message})
}

func readJSON(w http.ResponseWriter, r *http.Request, v any) bool {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil || dec.More() {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			writeError(w, http.StatusRequestEntityTooLarge, "too_big", "That is too big to send. Sketches can be up to 100 KB.")
			return false
		}
		if err == io.EOF || err != nil {
			writeError(w, http.StatusBadRequest, "bad_json", "That request wasn't understood.")
			return false
		}
	}
	return true
}

func (s *Server) handleInfo(w http.ResponseWriter, r *http.Request) {
	relay := "off"
	if s.PiKeys != nil {
		relay = "sse"
	}
	info := map[string]any{
		"app": "Circuit Pathways", "version": s.Version, "commit": s.Commit, "host": "pi", "edition": s.Mode,
		"compile": s.Compiler != nil, "classes": true, "class_optional": true, "teacher_mode": false, "relay": relay,
		"name": s.Name, "secure": r.TLS != nil, "tls": s.TLS,
	}
	if s.Install != nil && len(s.Install.CAPEM) > 0 {
		info["ca_fingerprint"] = s.Install.Fingerprint()
	}
	if s.Upstream != nil {
		up := s.Upstream.Status()
		info["online"] = up.Online
		info["school_server"] = up.Name
		info["compile"] = s.Compiler != nil || up.Compile
	} else {
		info["online"] = true
	}
	writeJSON(w, http.StatusOK, info)
}

func (s *Server) handleCatalogue(w http.ResponseWriter, r *http.Request) {
	b, err := CatalogueJSON(s.Catalogue)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "oops", "The catalogue couldn't be made.")
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "public, max-age=300")
	w.Write(b)
}

func (s *Server) handleProject(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimSuffix(r.PathValue("id"), ".json")
	p, ok := s.Catalogue.Project(id)
	if !ok {
		writeError(w, http.StatusNotFound, "not_found", "That project isn't here.")
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "public, max-age=300")
	w.Write(p.Raw)
}
