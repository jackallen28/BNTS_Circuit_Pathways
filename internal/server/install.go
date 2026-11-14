package server

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/pem"
	"io"
	"net"
	"net/http"
	"os"
	"runtime"
	"strings"
	"sync"

	"circuitpathways/internal/setup"
)

// Installer hands student Pis what they need from the school server: the installer script, this very
// program (a student Pi runs the same one), and the server's certificate authority.
type Installer struct {
	Program   string // the path of this program (os.Executable)
	CAPEM     []byte
	HTTPSPort string // "443" or another port

	once sync.Once
	sum  string
	err  error
}

func (in *Installer) routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /install/student-pi.sh", in.handleScript)
	mux.HandleFunc("GET /install/{file}", in.handleProgram)
	mux.HandleFunc("GET /ca.crt", in.handleCA)
	mux.HandleFunc("GET /install/school-ca.crt", in.handleCA)
}

func (in *Installer) checksum() (string, error) {
	in.once.Do(func() {
		f, err := os.Open(in.Program)
		if err != nil {
			in.err = err
			return
		}
		defer f.Close()
		h := sha256.New()
		if _, err := io.Copy(h, f); err != nil {
			in.err = err
			return
		}
		in.sum = hex.EncodeToString(h.Sum(nil))
	})
	return in.sum, in.err
}

func (in *Installer) handleCA(w http.ResponseWriter, r *http.Request) {
	if len(in.CAPEM) == 0 {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "application/x-x509-ca-cert")
	w.Header().Set("Content-Disposition", `attachment; filename="circuit-pathways-school.crt"`)
	w.Header().Set("Cache-Control", "no-cache")
	w.Write(in.CAPEM)
}

func (in *Installer) handleProgram(w http.ResponseWriter, r *http.Request) {
	arch, ok := strings.CutPrefix(r.PathValue("file"), "circuitpathways-linux-")
	if !ok {
		http.NotFound(w, r)
		return
	}
	if runtime.GOOS != "linux" || arch != runtime.GOARCH {
		writeError(w, http.StatusNotFound, "no_program", "The school server only has the "+runtime.GOOS+"/"+runtime.GOARCH+" version of Circuit Pathways.")
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Cache-Control", "no-cache")
	http.ServeFile(w, r, in.Program)
}

func (in *Installer) handleScript(w http.ResponseWriter, r *http.Request) {
	sum, err := in.checksum()
	if err != nil || runtime.GOOS != "linux" || len(in.CAPEM) == 0 {
		writeError(w, http.StatusServiceUnavailable, "no_installer", "This server can't set up student Pis (it isn't the school server on a Pi).")
		return
	}
	host := hostOnly(r.Host)
	if strings.Contains(host, ":") && net.ParseIP(host) != nil { // an IPv6 address
		host = "[" + host + "]"
	}
	school := "https://" + host
	if in.HTTPSPort != "" && in.HTTPSPort != "443" {
		school += ":" + in.HTTPSPort
	}
	httpBase := "http://" + r.Host
	if r.TLS != nil {
		httpBase = school // (fetched over https: the Pi's curl must trust the server already)
	}
	script, err := setup.StudentPiScript(setup.StudentPi{School: school, HTTP: httpBase, SHA256: sum, Arch: runtime.GOARCH, CA: string(in.CAPEM)})
	if err != nil {
		writeError(w, http.StatusBadRequest, "bad_address", "Open this with the school server's name or address, such as http://pathways.local/install/student-pi.sh.")
		return
	}
	w.Header().Set("Content-Type", "text/x-shellscript; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	io.WriteString(w, script)
}

// Fingerprint is the SHA-256 fingerprint of the school server's certificate authority, as browsers show it.
func (in *Installer) Fingerprint() string {
	blk, _ := pem.Decode(in.CAPEM)
	if blk == nil {
		return ""
	}
	sum := sha256.Sum256(blk.Bytes)
	h := strings.ToUpper(hex.EncodeToString(sum[:]))
	var parts []string
	for i := 0; i < len(h); i += 2 {
		parts = append(parts, h[i:i+2])
	}
	return strings.Join(parts, ":")
}
