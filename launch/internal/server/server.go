// Package server is the Circuit Pathways website. It serves the pages and
// does only two jobs that a browser can't do alone: it checks class codes
// and teacher sign-ins, and it compiles Arduino code for real boards.
//
// It never stores anything about students: no names, no school, no work, no
// code. Compiled code lives in a temporary folder for the length of one
// compile. Nothing it logs includes a request body.
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
	"circuitpathways/internal/classes"
	"circuitpathways/internal/content"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/pirelay"
)

// Compiler compiles a sketch (arduino.Tools; tests use a fake).
type Compiler interface {
	Compile(ctx context.Context, code, fqbn string, props []string) (arduino.CompileResult, []arduino.Artifact, error)
}

// Config is everything the server needs.
type Config struct {
	Site      fs.FS
	Catalogue *content.Catalogue
	Signer    *classes.Signer
	Teachers  classes.TeacherCodes
	Compiler  Compiler // nil: compiling is off
	Version   string
	Log       *slog.Logger
	Now       func() time.Time // nil: time.Now
	// MaxCompiles is how many compiles can run at once (default 2).
	MaxCompiles int
	// Relay connects browsers to Raspberry Pis (nil: a new one).
	Relay *pirelay.Relay
	// PiKeys checks Raspberry Pi keys (nil: Pi Link is off).
	PiKeys *pilink.Keys
	// Beta is the TEST version: no class codes or teacher pages, the apps are open to anyone with
	// the link, and the page says nothing is saved. Pi Link is off.
	Beta bool
}

// Server is the http.Handler.
type Server struct {
	Config
	static  http.Handler
	handler http.Handler
	slots   chan struct{}
	limits  struct{ signin, join, class, compile, piCommand *limiter }
}

const (
	maxBody       = 128 << 10 // a sketch is limited to 100 KB
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
	if cfg.MaxCompiles < 1 {
		cfg.MaxCompiles = defaultSlots
	}
	s := &Server{Config: cfg, static: http.FileServerFS(cfg.Site), slots: make(chan struct{}, cfg.MaxCompiles)}
	s.limits.signin = newLimiter(5, time.Minute)
	s.limits.join = newLimiter(20, time.Minute)
	s.limits.class = newLimiter(30, time.Minute)
	s.limits.compile = newLimiter(15, time.Minute)
	s.limits.piCommand = newLimiter(900, time.Minute)
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
	mux.HandleFunc("POST /api/teacher/signin", s.handleSignIn)
	mux.HandleFunc("POST /api/teacher/class", s.handleNewClass)
	mux.HandleFunc("POST /api/class/join", s.handleJoin)
	mux.HandleFunc("POST /api/compile", s.handleCompile)
	s.piRoutes(mux)
	mux.HandleFunc("GET /api/info", s.handleInfo)
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
		if s.Beta {
			h.Set("X-Robots-Tag", "noindex, nofollow") // a link to share, not a page for search engines
			if betaHidden(r.URL.Path) {
				http.NotFound(w, r)
				return
			}
		}
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
		h.Set("Permissions-Policy", "serial=(self), camera=(), microphone=(), geolocation=(), interest-cohort=()")
		h.Set("Strict-Transport-Security", "max-age=31536000")
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

// betaHidden are the parts of the site the TEST version doesn't have: classes, teachers and Raspberry Pi linking.
func betaHidden(path string) bool {
	switch path {
	case "/pipath/remote", "/pipath/remote/", "/pipath/remote/index.html", "/pipath/remote/circuitpathways_pi.py", "/pipath/remote/install.sh":
		return true // (pi-remote.js stays: PiPath's page loads it, and it does nothing without a Pi)
	}
	for _, p := range []string{"/teacher", "/api/teacher/", "/api/class/", "/api/pi/"} {
		if path == p || strings.HasPrefix(path, strings.TrimSuffix(p, "/")+"/") {
			return true
		}
	}
	return false
}

func hostOnly(h string) string {
	if i := strings.LastIndex(h, ":"); i > 0 && !strings.Contains(h[i:], "]") {
		h = h[:i]
	}
	return strings.ToLower(h)
}

// allowedHost lets any host name through except a bare IP-like or empty one
// (Render serves us under its own name and the school's domain).
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
	writeJSON(w, http.StatusOK, map[string]any{
		"app": "Circuit Pathways", "version": s.Version, "compile": s.Compiler != nil, "beta": s.Beta,
	})
}

func (s *Server) handleCatalogue(w http.ResponseWriter, r *http.Request) {
	c := s.Catalogue
	boards := make([]json.RawMessage, 0, len(c.Boards))
	for _, b := range c.Boards {
		boards = append(boards, b.Raw)
	}
	projects := make([]any, 0, len(c.Projects))
	for _, p := range c.Projects {
		projects = append(projects, p.ProjectSummary)
	}
	w.Header().Set("Cache-Control", "public, max-age=300")
	writeJSON(w, http.StatusOK, map[string]any{
		"tiers": c.Tiers, "parts": c.Parts, "kit": c.Kit, "boards": boards,
		"projects": projects, "errors": c.Errors, "curriculum": c.Curriculum,
	})
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
