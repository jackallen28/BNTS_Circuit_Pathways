package server

import (
	"io"
	"io/fs"
	"net/http"
	"regexp"
	"strconv"
	"strings"
)

var prefixFile = regexp.MustCompile(`^[a-z0-9_/-]+\.js$`)

// handlePrefix is a tool for the TEST version only. If a school or office web filter blocks one of
// the site's files, /pipath/dev/blocktest.html asks for the first 1, 2, 3... lines of that file
// (and the whole file as plain text) to find which line the filter objects to.
func (s *Server) handlePrefix(w http.ResponseWriter, r *http.Request) {
	if !s.Beta {
		http.NotFound(w, r)
		return
	}
	name := r.URL.Query().Get("file")
	if !prefixFile.MatchString(name) || strings.Contains(name, "..") {
		http.Error(w, "no such file", http.StatusBadRequest)
		return
	}
	f, err := s.Site.Open("pipath/js/" + name)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	if st, err := fs.Stat(s.Site, "pipath/js/"+name); err != nil || st.Size() > 200<<10 {
		http.Error(w, "too big", http.StatusBadRequest)
		return
	}
	raw, err := io.ReadAll(f)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	lines := strings.SplitAfter(string(raw), "\n")
	n, err := strconv.Atoi(r.URL.Query().Get("n"))
	if err != nil || n < 0 || n > len(lines) {
		n = len(lines)
	}
	w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
	if r.URL.Query().Get("plain") == "1" {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	}
	w.Header().Set("Cache-Control", "no-store")
	io.WriteString(w, strings.Join(lines[:n], ""))
}
