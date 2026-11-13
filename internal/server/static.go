package server

import (
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"net/http"
	"path"
	"strings"
)

// etags maps every file in the site to a short hash of its contents. Browsers
// keep a copy but must ask "has it changed?" each time, and get a tiny 304
// answer when it hasn't. That way a new release shows up at once and a page
// never mixes old and new script files.
func etags(site fs.FS) map[string]string {
	out := map[string]string{}
	fs.WalkDir(site, ".", func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if b, err := fs.ReadFile(site, p); err == nil {
			sum := sha256.Sum256(b)
			out[p] = `"` + hex.EncodeToString(sum[:8]) + `"`
		}
		return nil
	})
	return out
}

// staticHandler serves the website. Folders open their index.html, and
// /arduinopath, /pipath and /teacher get a trailing slash so relative links work.
func (s *Server) staticHandler() http.Handler {
	tags := etags(s.Site)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Path
		if p == "/arduinopath" || p == "/pipath" || p == "/teacher" {
			http.Redirect(w, r, p+"/", http.StatusMovedPermanently)
			return
		}
		file := strings.TrimPrefix(path.Clean("/"+p), "/")
		if strings.HasSuffix(p, "/") || file == "" {
			file = path.Join(file, "index.html")
		}
		w.Header().Set("Cache-Control", cacheControlFor(file))
		if tag, ok := tags[file]; ok {
			w.Header().Set("ETag", tag)
			if r.Header.Get("If-None-Match") == tag {
				w.WriteHeader(http.StatusNotModified)
				return
			}
		}
		s.static.ServeHTTP(w, r)
	})
}
