package server

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

// Upstream is the school server, as a student Pi sees it. A student Pi serves the site itself, so it
// works with no network at all; what only the school server can do (classes, a student's saved work,
// the teacher's portal, and compiling when this Pi has no board tools) is passed on to it. When it
// can't be reached, the page is told so ("offline") and keeps the student's work on this Pi until it can.
type Upstream struct {
	URL   *url.URL
	proxy *httputil.ReverseProxy
	check *http.Client
	log   *slog.Logger

	mu      sync.Mutex
	online  bool
	compile bool
	name    string
	last    time.Time
}

// UpstreamStatus is what the page is told about the school server.
type UpstreamStatus struct {
	Online  bool
	Compile bool // the school server can compile for boards
	Name    string
}

// NewUpstream connects to the school server at rawURL. caFile is the school server's own certificate
// authority (from its installer), so https works without trusting anything else; "" uses the system's.
func NewUpstream(rawURL, caFile string, log *slog.Logger) (*Upstream, error) {
	u, err := url.Parse(strings.TrimRight(rawURL, "/"))
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return nil, errors.New("the school server's address must look like https://pathways.local")
	}
	tr := http.DefaultTransport.(*http.Transport).Clone()
	tr.Proxy = nil // the school server is on this network
	tr.ResponseHeaderTimeout = 6 * time.Minute
	if caFile != "" {
		pem, err := os.ReadFile(caFile)
		if err != nil {
			return nil, err
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(pem) {
			return nil, errors.New("the school server's certificate file isn't right")
		}
		tr.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	}
	if log == nil {
		log = slog.Default()
	}
	up := &Upstream{URL: u, log: log, check: &http.Client{Transport: tr, Timeout: 4 * time.Second}, name: u.Host}
	up.proxy = &httputil.ReverseProxy{
		Transport: tr,
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(u)
			pr.Out.Host = u.Host
			// what the school server sees is this Pi asking (no forwarded addresses)
			pr.Out.Header.Del("X-Forwarded-For")
			pr.Out.Header.Del("Forwarded")
			pr.Out.Header.Del("Cookie")
			pr.Out.Header.Del("Origin")
			pr.Out.Header.Del("Referer")
		},
		ModifyResponse: func(res *http.Response) error {
			up.setOnline(true)
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			up.setOnline(false)
			if r.URL.Path == "/api/compile" {
				writeError(w, http.StatusServiceUnavailable, "offline", "Uploading to a board needs the school's Circuit Pathways server, and it can't be reached right now. The simulator still works, and your work is saved on this Pi.")
				return
			}
			writeError(w, http.StatusServiceUnavailable, "offline", "The school's Circuit Pathways server can't be reached right now. Your work is saved on this Pi, and goes to your class when the server is back.")
		},
	}
	return up, nil
}

func (u *Upstream) setOnline(on bool) {
	u.mu.Lock()
	if on != u.online {
		u.log.Info("school server", "online", on)
	}
	u.online = on
	u.last = time.Now()
	u.mu.Unlock()
}

// Status is the last thing known about the school server.
func (u *Upstream) Status() UpstreamStatus {
	u.mu.Lock()
	defer u.mu.Unlock()
	return UpstreamStatus{Online: u.online, Compile: u.online && u.compile, Name: u.name}
}

// Check asks the school server if it is there, and whether it can compile.
func (u *Upstream) Check(ctx context.Context) bool {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u.URL.String()+"/api/info", nil)
	res, err := u.check.Do(req)
	ok := err == nil && res.StatusCode == http.StatusOK
	var info struct {
		Compile bool   `json:"compile"`
		Name    string `json:"name"`
	}
	if res != nil {
		if ok {
			ok = json.NewDecoder(io.LimitReader(res.Body, 16<<10)).Decode(&info) == nil
		}
		io.Copy(io.Discard, io.LimitReader(res.Body, 16<<10))
		res.Body.Close()
	}
	u.mu.Lock()
	u.compile = ok && info.Compile
	u.mu.Unlock()
	u.setOnline(ok)
	return ok
}

// Watch checks the school server every so often until ctx ends.
func (u *Upstream) Watch(ctx context.Context, every time.Duration) {
	u.Check(ctx)
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			u.Check(ctx)
		}
	}
}

func (u *Upstream) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	u.proxy.ServeHTTP(w, r)
}
