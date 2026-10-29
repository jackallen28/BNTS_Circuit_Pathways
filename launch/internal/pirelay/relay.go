// Package pirelay lets a student's browser control a Raspberry Pi's GPIO pins
// over the school WiFi, through the Circuit Pathways site.
//
// Both sides only ever make outgoing connections, so it works on school
// networks that stop laptops talking to other devices:
//
//	Pi app   --POST /api/pi/pi/send-->  relay  --stream-->  browser
//	Pi app   <--stream----------------  relay  <--POST /api/pi/command--  browser
//
// Each Pi has its own key (see package pilink). Its ID, such as K7M2-QX9P, is
// what the student types into the website to link to that Pi. The relay keeps
// everything in memory, only for as long as the Pi stays connected, and only
// passes pin commands and pin states. It never stores them, and knows
// nothing about the student.
package pirelay

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"
)

const (
	// MaxPis is how many Pis can be connected at once.
	MaxPis = 400
	// OfflineGrace is how long a Pi may be disconnected before it is forgotten.
	OfflineGrace = 90 * time.Second

	maxEventBytes = 8 << 10
	queueSize     = 64
)

var (
	ErrFull        = errors.New("too many Pis are connected right now")
	ErrNotFound    = errors.New("that code isn't connected")
	ErrBadCommand  = errors.New("that isn't a command a Pi understands")
	ErrPiBusy      = errors.New("the Pi can't keep up")
	ErrEventTooBig = errors.New("event too big")
)

// Relay holds every registered Pi.
type Relay struct {
	now func() time.Time

	mu    sync.Mutex
	pis   map[string]*Pi
	perIP map[string]int
}

// New makes a Relay. now may be nil.
func New(now func() time.Time) *Relay {
	if now == nil {
		now = time.Now
	}
	return &Relay{now: now, pis: map[string]*Pi{}}
}

// Pi is one registered Raspberry Pi and the browser that is controlling it.
type Pi struct {
	ID   string
	Name string

	mu        sync.Mutex
	lastSeen  time.Time
	cmds      chan []byte // browser -> Pi
	piOnline  bool
	piStream  int // which Pi connection is current
	browser   *Listener
	lastState []byte
	hello     []byte
}

// Listener is a browser watching a Pi. Events arrive on C; it is closed when
// the browser is replaced by a newer one, or the Pi goes for good.
type Listener struct {
	C      chan []byte
	closed bool
	Reason string
}

// NormaliseCode tidies a typed pairing code: upper case, no spaces or dashes, look-alikes fixed.
func NormaliseCode(s string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(s) {
		switch r {
		case ' ', '-', '_', '\t':
			continue
		case 'I', 'L':
			r = '1'
		case 'O':
			r = '0'
		}
		b.WriteRune(r)
	}
	return b.String()
}

// ensure finds the Pi with this ID, adding it if it isn't known yet.
func (r *Relay) ensure(id string) (*Pi, error) {
	id = NormaliseCode(id)
	r.mu.Lock()
	defer r.mu.Unlock()
	if p := r.pis[id]; p != nil {
		return p, nil
	}
	r.sweepLocked()
	if len(r.pis) >= MaxPis {
		return nil, ErrFull
	}
	p := &Pi{ID: id, Name: "Raspberry Pi", lastSeen: r.now(), cmds: make(chan []byte, queueSize)}
	r.pis[id] = p
	return p, nil
}

// CleanName keeps a Pi's label to a few plain characters. It is shown on the
// website, so it never defaults to the Pi's host name (which can hold a student's name).
func CleanName(s string) string {
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == ' ' || r == '-' {
			b.WriteRune(r)
		}
		if b.Len() >= 24 {
			break
		}
	}
	if n := strings.TrimSpace(b.String()); n != "" {
		return n
	}
	return "Raspberry Pi"
}

// sweepLocked forgets Pis that have gone quiet.
func (r *Relay) sweepLocked() {
	now := r.now()
	for code, p := range r.pis {
		p.mu.Lock()
		stale := !p.piOnline && now.Sub(p.lastSeen) > OfflineGrace
		p.mu.Unlock()
		if stale {
			r.removeLocked(code, p, "The Pi disconnected.")
		}
	}
}

// Sweep forgets Pis that have gone quiet (called every so often).
func (r *Relay) Sweep() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.sweepLocked()
}

func (r *Relay) removeLocked(code string, p *Pi, reason string) {
	delete(r.pis, code)
	p.mu.Lock()
	p.closeBrowserLocked(reason)
	p.mu.Unlock()
}

// Count is how many Pis are registered.
func (r *Relay) Count() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.pis)
}

func (r *Relay) find(code string) *Pi {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.pis[NormaliseCode(code)]
}

func (p *Pi) closeBrowserLocked(reason string) {
	if p.browser != nil && !p.browser.closed {
		p.browser.Reason = reason
		p.browser.closed = true
		close(p.browser.C)
	}
	p.browser = nil
}

// PiConnected marks the Pi's stream as open. It returns the Pi's command
// channel and a stream number; call PiGone with the number when the stream ends.
func (r *Relay) PiConnected(id string) (cmds <-chan []byte, stream int, err error) {
	p, err := r.ensure(id)
	if err != nil {
		return nil, 0, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.piStream++
	p.piOnline = true
	p.lastSeen = r.now()
	// commands queued for an earlier connection are stale
	for len(p.cmds) > 0 {
		<-p.cmds
	}
	if p.browser != nil {
		p.pushLocked(p.browser, event("pi-online", nil))
	}
	return p.cmds, p.piStream, nil
}

// PiGone says a Pi's stream ended. Stale streams (replaced by a newer one) are ignored.
func (r *Relay) PiGone(code string, stream int) {
	if p := r.find(code); p != nil {
		p.mu.Lock()
		defer p.mu.Unlock()
		if p.piStream == stream {
			p.piOnline = false
			p.lastSeen = r.now()
			if p.browser != nil {
				p.pushLocked(p.browser, event("pi-offline", nil))
			}
		}
	}
}

func event(kind string, data json.RawMessage) []byte {
	if data == nil {
		return []byte(fmt.Sprintf(`{"type":%q}`, kind))
	}
	return []byte(fmt.Sprintf(`{"type":%q,"data":%s}`, kind, data))
}

func (p *Pi) pushLocked(l *Listener, ev []byte) {
	if l == nil || l.closed {
		return
	}
	select {
	case l.C <- ev:
	default: // a slow browser misses an event; the next state catches it up
	}
}

// FromPi passes an event from the Pi (a hello or a pin state) on to the browser.
func (r *Relay) FromPi(id string, raw []byte) error {
	if len(raw) > maxEventBytes {
		return ErrEventTooBig
	}
	p, err := r.ensure(id)
	if err != nil {
		return err
	}
	var ev struct {
		Type string          `json:"type"`
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(raw, &ev); err != nil || (ev.Type != "hello" && ev.Type != "state" && ev.Type != "error" && ev.Type != "pong") || len(ev.Data) == 0 {
		return ErrBadCommand
	}
	out := event(ev.Type, ev.Data)
	p.mu.Lock()
	defer p.mu.Unlock()
	p.lastSeen = r.now()
	switch ev.Type {
	case "state":
		p.lastState = out
	case "hello":
		p.hello = out
		var h struct {
			Name string `json:"name"`
		}
		if json.Unmarshal(ev.Data, &h) == nil {
			p.Name = CleanName(h.Name)
		}
	}
	p.pushLocked(p.browser, out)
	return nil
}

// Watch connects a browser to the Pi with this code, replacing any browser
// already watching. The listener first gets the Pi's hello and latest state.
func (r *Relay) Watch(code string) (*Listener, *Pi, error) {
	p := r.find(code)
	if p == nil {
		return nil, nil, ErrNotFound
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.closeBrowserLocked("Someone else connected to this Pi.")
	l := &Listener{C: make(chan []byte, queueSize)}
	p.browser = l
	p.pushLocked(l, event("connected", json.RawMessage(fmt.Sprintf(`{"name":%q,"pi_online":%t}`, p.Name, p.piOnline))))
	if p.hello != nil {
		p.pushLocked(l, p.hello)
	}
	if p.lastState != nil {
		p.pushLocked(l, p.lastState)
	}
	return l, p, nil
}

// Unwatch removes a browser's listener (when its stream ends).
func (r *Relay) Unwatch(p *Pi, l *Listener) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.browser == l {
		p.browser = nil
	}
}

// ToPi sends a checked command from the browser to the Pi.
func (r *Relay) ToPi(code string, cmd Command) error {
	p := r.find(code)
	if p == nil {
		return ErrNotFound
	}
	if err := cmd.Check(); err != nil {
		return err
	}
	raw, _ := json.Marshal(cmd)
	p.mu.Lock()
	online := p.piOnline
	p.mu.Unlock()
	if !online {
		return ErrNotFound
	}
	select {
	case p.cmds <- raw:
		return nil
	default:
		return ErrPiBusy
	}
}
