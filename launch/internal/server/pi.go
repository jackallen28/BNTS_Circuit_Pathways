package server

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"strings"
	"time"

	"circuitpathways/internal/pirelay"
)

const (
	piSecretHeader = "X-Pi-Secret"
	perOwnerPis    = 3
)

func (s *Server) piRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/pi/register", s.handlePiRegister)
	mux.HandleFunc("GET /api/pi/pi/events", s.handlePiEvents)
	mux.HandleFunc("POST /api/pi/pi/send", s.handlePiSend)
	mux.HandleFunc("GET /api/pi/events", s.handlePiWatch)
	mux.HandleFunc("POST /api/pi/command", s.handlePiCommand)
	mux.HandleFunc("GET /pipath/remote/circuitpathways_pi.py", s.handlePiApp)
}

// placeholderServer is the website address written into the Pi app's source.
const placeholderServer = "https://circuit-pathways.onrender.com"

// handlePiApp hands out the Pi app with this website's own address as its
// default, so a student only has to download and run it.
func (s *Server) handlePiApp(w http.ResponseWriter, r *http.Request) {
	src, err := fs.ReadFile(s.Site, "pipath/remote/circuitpathways_pi.py")
	if err != nil {
		http.NotFound(w, r)
		return
	}
	scheme := "https"
	if h := hostOnly(r.Host); h == "localhost" || h == "127.0.0.1" || h == "::1" {
		scheme = "http"
	}
	out := strings.Replace(string(src), placeholderServer, scheme+"://"+r.Host, 1)
	w.Header().Set("Content-Type", "text/x-python; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="circuitpathways_pi.py"`)
	w.Header().Set("Cache-Control", "no-cache")
	io.WriteString(w, out)
}

// handlePiRegister: a Pi asks for a pairing code. Nothing about the Pi is
// kept except a plain label and its secret, in memory, while it stays connected.
func (s *Server) handlePiRegister(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.piRegister) {
		return
	}
	var req struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	code, secret, err := s.Relay.Register(req.Name, clientKey(r), perOwnerPis)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "pi_full", "Too many Raspberry Pis are connected right now. Try again in a few minutes.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"code": code, "secret": secret, "register_ttl_s": int(pirelay.RegisterTTL.Seconds())})
}

// sse starts a server-sent-events stream that can last as long as the Pi or
// browser stays connected (the server's normal write limit doesn't apply).
func sse(w http.ResponseWriter) (flush func(), ok bool) {
	rc := http.NewResponseController(w)
	if err := rc.SetWriteDeadline(time.Time{}); err != nil {
		return nil, false
	}
	h := w.Header()
	h.Set("Content-Type", "text/event-stream")
	h.Set("Cache-Control", "no-store")
	h.Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	flush = func() { rc.Flush() }
	fmt.Fprint(w, "retry: 3000\n\n")
	flush()
	return flush, true
}

func piError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, pirelay.ErrNotFound):
		writeError(w, http.StatusNotFound, "pi_not_found", "That code isn't connected. Check the code on your Pi, and that the Pi app is still running.")
	case errors.Is(err, pirelay.ErrBadSecret):
		writeError(w, http.StatusForbidden, "pi_secret", "That Pi isn't allowed.")
	case errors.Is(err, pirelay.ErrPiBusy):
		writeError(w, http.StatusTooManyRequests, "pi_busy", "The Pi can't keep up. Slow down a little.")
	case errors.Is(err, pirelay.ErrEventTooBig):
		writeError(w, http.StatusRequestEntityTooLarge, "too_big", "That is too big.")
	default:
		writeError(w, http.StatusBadRequest, "bad_command", "That isn't something a Pi can do.")
	}
}

// handlePiEvents: the Pi's stream of commands from the browser.
func (s *Server) handlePiEvents(w http.ResponseWriter, r *http.Request) {
	code := r.URL.Query().Get("code")
	cmds, stream, err := s.Relay.PiConnected(code, r.Header.Get(piSecretHeader))
	if err != nil {
		piError(w, err)
		return
	}
	defer s.Relay.PiGone(code, stream)
	flush, ok := sse(w)
	if !ok {
		return
	}
	beat := time.NewTicker(15 * time.Second)
	defer beat.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case raw := <-cmds:
			fmt.Fprintf(w, "data: %s\n\n", raw)
			flush()
		case <-beat.C:
			fmt.Fprint(w, ": keep-alive\n\n")
			flush()
		}
	}
}

// handlePiSend: the Pi reports its pins.
func (s *Server) handlePiSend(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Code  string          `json:"code"`
		Event json.RawMessage `json:"event"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	if err := s.Relay.FromPi(req.Code, r.Header.Get(piSecretHeader), req.Event); err != nil {
		piError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) allowedBrowser(w http.ResponseWriter, r *http.Request) bool {
	if !s.Signer.CheckAccess(r.Header.Get(accessHeader), s.Now()) {
		writeError(w, http.StatusUnauthorized, "no_class", "Join a class with your class code to connect to a Pi.")
		return false
	}
	return true
}

// handlePiWatch: the browser's stream of what the Pi reports.
func (s *Server) handlePiWatch(w http.ResponseWriter, r *http.Request) {
	if !s.allowedBrowser(w, r) {
		return
	}
	if s.limited(w, r, s.limits.join) { // pairing codes can't be guessed quickly
		return
	}
	l, p, err := s.Relay.Watch(r.URL.Query().Get("code"))
	if err != nil {
		piError(w, err)
		return
	}
	defer s.Relay.Unwatch(p, l)
	flush, ok := sse(w)
	if !ok {
		return
	}
	beat := time.NewTicker(15 * time.Second)
	defer beat.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case ev, open := <-l.C:
			if !open {
				fmt.Fprintf(w, "data: {\"type\":\"closed\",\"data\":{\"reason\":%q}}\n\n", l.Reason)
				flush()
				return
			}
			fmt.Fprintf(w, "data: %s\n\n", ev)
			flush()
		case <-beat.C:
			fmt.Fprint(w, ": keep-alive\n\n")
			flush()
		}
	}
}

// handlePiCommand: the browser tells the Pi what to do with a pin.
func (s *Server) handlePiCommand(w http.ResponseWriter, r *http.Request) {
	if !s.allowedBrowser(w, r) {
		return
	}
	if s.limited(w, r, s.limits.piCommand) {
		return
	}
	var req struct {
		Code string          `json:"code"`
		Cmd  pirelay.Command `json:"cmd"`
	}
	if !readJSON(w, r, &req) {
		return
	}
	if err := s.Relay.ToPi(req.Code, req.Cmd); err != nil {
		piError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
