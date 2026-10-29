package server

import (
	"net/http"
	"strings"
)

// staticHandler serves the website: pages are never cached (so a new
// release shows up at once), everything else for an hour. Pages without a
// file name open their index.html, and PiPath / ArduinoPath live in their own folders.
func (s *Server) staticHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Path
		// /arduinopath -> /arduinopath/ so relative links work
		if p == "/arduinopath" || p == "/pipath" || p == "/teacher" {
			http.Redirect(w, r, p+"/", http.StatusMovedPermanently)
			return
		}
		if strings.HasSuffix(p, "/") || strings.HasSuffix(p, ".html") || p == "" {
			w.Header().Set("Cache-Control", "no-cache")
		} else {
			w.Header().Set("Cache-Control", "public, max-age=3600")
		}
		s.static.ServeHTTP(w, r)
	})
}
