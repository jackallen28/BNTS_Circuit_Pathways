package server

import (
	"net"
	"net/http"
	"sync"
	"time"
)

// limiter allows n requests per window from one address. It lives only in
// memory and forgets an address once its window has passed.
type limiter struct {
	n      int
	window time.Duration
	mu     sync.Mutex
	hits   map[string][]time.Time
}

func newLimiter(n int, window time.Duration) *limiter {
	return &limiter{n: n, window: window, hits: map[string][]time.Time{}}
}

func (l *limiter) allow(key string, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	cut := now.Add(-l.window)
	kept := l.hits[key][:0]
	for _, t := range l.hits[key] {
		if t.After(cut) {
			kept = append(kept, t)
		}
	}
	if len(kept) >= l.n {
		l.hits[key] = kept
		return false
	}
	l.hits[key] = append(kept, now)
	if len(l.hits) > 5000 { // tidy away old addresses
		for k, ts := range l.hits {
			if len(ts) == 0 || ts[len(ts)-1].Before(cut) {
				delete(l.hits, k)
			}
		}
	}
	return true
}

// clientKey is the address to rate-limit by: the computer asking, on the school's network. (No proxy
// header is trusted: on a school network a student could make one up.) It is only kept in memory, never logged.
func clientKey(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func (s *Server) limited(w http.ResponseWriter, r *http.Request, l *limiter) bool {
	if l.allow(clientKey(r), s.Now()) {
		return false
	}
	w.Header().Set("Retry-After", "60")
	writeError(w, http.StatusTooManyRequests, "slow_down", "That was a lot of tries. Wait a minute and try again.")
	return true
}
