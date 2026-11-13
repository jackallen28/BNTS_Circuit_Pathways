package server

import (
	"net/http/httptest"
	"strings"
	"testing"

	"circuitpathways"
	"circuitpathways/internal/classes"
	"circuitpathways/internal/content"
)

func TestCacheControlFor(t *testing.T) {
	for file, want := range map[string]string{
		"pipath/vendor/pyodide/pyodide.asm.wasm":  vendorCacheControl,
		"arduinopath/vendor/esptool-js/bundle.js": vendorCacheControl,
		"img/bnts-logo.png":                       vendorCacheControl,
		"pipath/js/main.js":                       "no-cache", // our own code: always asked about
		"index.html":                              "no-cache",
		"arduinopath/data/catalogue.json":         "no-cache",
	} {
		if got := cacheControlFor(file); got != want {
			t.Errorf("%s: got %q, want %q", file, got, want)
		}
	}
}

// The big, rarely changing files are cached for a week by both the Go site and Cloudflare's _headers.
func TestVendoredFilesAreCachedLongOnBothSites(t *testing.T) {
	cat, problems := content.Load(circuitpathways.Content())
	if len(problems) > 0 {
		t.Fatal(problems[0])
	}
	signer, _ := classes.New("test-secret-0123456789")
	s := New(Config{Site: circuitpathways.Site(), Catalogue: cat, Signer: signer, Teachers: classes.ParseTeacherCodes("teacher-code-1234")})
	w := httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/pipath/vendor/pyodide/pyodide.asm.wasm", nil))
	if got := w.Header().Get("Cache-Control"); got != vendorCacheControl {
		t.Errorf("Go site: wasm Cache-Control %q", got)
	}
	w = httptest.NewRecorder()
	s.ServeHTTP(w, httptest.NewRequest("GET", "/pipath/js/main.js", nil))
	if got := w.Header().Get("Cache-Control"); got != "no-cache" {
		t.Errorf("Go site: our own code should stay no-cache, got %q", got)
	}

	h := HeadersFile(false)
	for _, want := range []string{"/pipath/vendor/*\n  ! Cache-Control\n  Cache-Control: " + vendorCacheControl, "/arduinopath/vendor/*\n  ! Cache-Control", "/img/*\n  ! Cache-Control"} {
		if !strings.Contains(h, want) {
			t.Errorf("_headers should contain %q", want)
		}
	}
	if !strings.Contains(h, "/*\n") || !strings.Contains(h, "Cache-Control: no-cache") {
		t.Error("_headers should still say no-cache for everything else")
	}
}
