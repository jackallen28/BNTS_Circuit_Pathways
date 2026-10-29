package pirelay

import (
	"errors"
	"testing"
	"time"
)

type clock struct{ t time.Time }

func (c *clock) now() time.Time { return c.t }

func TestCommandsAreChecked(t *testing.T) {
	good := []Command{
		{Op: "mode", Pin: 17, Mode: "out"}, {Op: "mode", Pin: 4, Mode: "in_up"}, {Op: "write", Pin: 27, Value: 1},
		{Op: "pwm", Pin: 18, Duty: 0.5, Freq: 100}, {Op: "release", Pin: 2}, {Op: "all_off"}, {Op: "ping"}, {Op: "read"},
	}
	for _, c := range good {
		if err := c.Check(); err != nil {
			t.Errorf("%+v refused: %v", c, err)
		}
	}
	bad := []Command{
		{}, {Op: "shell"}, {Op: "mode", Pin: 17, Mode: "wat"}, {Op: "mode", Pin: 1, Mode: "out"}, {Op: "mode", Pin: 28, Mode: "out"},
		{Op: "write", Pin: 17, Value: 2}, {Op: "write", Pin: 0, Value: 1}, {Op: "pwm", Pin: 18, Duty: 1.5}, {Op: "pwm", Pin: 18, Duty: -1},
		{Op: "pwm", Pin: 18, Duty: 0.5, Freq: 99999}, {Op: "release", Pin: 99},
	}
	for _, c := range bad {
		if err := c.Check(); !errors.Is(err, ErrBadCommand) {
			t.Errorf("%+v should be refused, got %v", c, err)
		}
	}
}

func TestPairingCodes(t *testing.T) {
	r := New(nil)
	code, secret, err := r.Register("Pi 4", "1.2.3.4", 3)
	if err != nil || len(code) != 7 || code[3] != '-' || len(secret) < 20 {
		t.Fatalf("Register = %q %q %v", code, secret, err)
	}
	if NormaliseCode("abc-d1e") != "ABCD1E" || NormaliseCode(" o i l ") != "011" {
		t.Error("typed codes should be tidied")
	}
	if _, _, err := r.PiConnected(code, "wrong"); !errors.Is(err, ErrBadSecret) {
		t.Errorf("wrong secret: %v", err)
	}
	if _, _, err := r.PiConnected("ZZZ-ZZZ", secret); !errors.Is(err, ErrNotFound) {
		t.Errorf("unknown code: %v", err)
	}
	if _, _, err := r.PiConnected(code, secret); err != nil {
		t.Errorf("right secret: %v", err)
	}
}

func TestLabelNeverBecomesAHostName(t *testing.T) {
	for in, want := range map[string]string{"": "Raspberry Pi", "Pi 4": "Pi 4", "<b>x</b>": "bxb", "Mia's-pi": "Mias-pi", "!!!": "Raspberry Pi"} {
		if got := CleanName(in); got != want {
			t.Errorf("CleanName(%q) = %q, want %q", in, got, want)
		}
	}
	if len(CleanName("a123456789012345678901234567890")) > 24 {
		t.Error("labels are limited to 24 characters")
	}
}

func TestLimits(t *testing.T) {
	r := New(nil)
	for i := 0; i < 3; i++ {
		if _, _, err := r.Register("", "9.9.9.9", 3); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := r.Register("", "9.9.9.9", 3); !errors.Is(err, ErrFull) {
		t.Errorf("a fourth Pi from one address: %v", err)
	}
	if _, _, err := r.Register("", "8.8.8.8", 3); err != nil {
		t.Errorf("another address is fine: %v", err)
	}
}

func TestBrowserAndPiTalk(t *testing.T) {
	r := New(nil)
	code, secret, _ := r.Register("", "ip", 3)
	cmds, stream, _ := r.PiConnected(code, secret)

	if err := r.ToPi(code, Command{Op: "shell"}); !errors.Is(err, ErrBadCommand) {
		t.Fatalf("bad command: %v", err)
	}
	// the Pi says hello and shows its pins before any browser is there
	if err := r.FromPi(code, secret, []byte(`{"type":"hello","data":{"model":"Pi 4"}}`)); err != nil {
		t.Fatal(err)
	}
	if err := r.FromPi(code, secret, []byte(`{"type":"state","data":{"pins":{"17":{"mode":"out","value":1}}}}`)); err != nil {
		t.Fatal(err)
	}
	l, p, err := r.Watch(code)
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	for i := 0; i < 3; i++ {
		got = append(got, string((<-l.C)[:12]))
	}
	if got[0] != `{"type":"con` || got[1] != `{"type":"hel` || got[2] != `{"type":"sta` {
		t.Errorf("a new browser should get connected, hello, state: %q", got)
	}

	// browser -> Pi
	if err := r.ToPi(code, Command{Op: "write", Pin: 17, Value: 0}); err != nil {
		t.Fatal(err)
	}
	if c := <-cmds; string(c) != `{"op":"write","pin":17,"value":0}` {
		t.Errorf("the Pi got %s (a value of 0 must not be dropped)", c)
	}
	r.ToPi(code, Command{Op: "pwm", Pin: 18, Duty: 0})
	if c := <-cmds; string(c) != `{"duty":0,"op":"pwm","pin":18}` {
		t.Errorf("the Pi got %s", c)
	}
	// Pi -> browser
	r.FromPi(code, secret, []byte(`{"type":"state","data":{"pins":{}}}`))
	if ev := <-l.C; string(ev) != `{"type":"state","data":{"pins":{}}}` {
		t.Errorf("the browser got %s", ev)
	}
	// garbage from the Pi is refused
	for _, bad := range []string{`nope`, `{"type":"exec","data":{}}`, `{"type":"state"}`} {
		if err := r.FromPi(code, secret, []byte(bad)); !errors.Is(err, ErrBadCommand) {
			t.Errorf("%s: %v", bad, err)
		}
	}
	if err := r.FromPi(code, secret, make([]byte, 9000)); !errors.Is(err, ErrEventTooBig) {
		t.Errorf("a huge event: %v", err)
	}

	// a second browser takes over; the first is told why
	l2, _, _ := r.Watch(code)
	for range l.C { // drained until closed
	}
	if l.Reason != "Someone else connected to this Pi." {
		t.Errorf("reason = %q", l.Reason)
	}
	r.Unwatch(p, l) // the old one ending must not remove the new one
	r.FromPi(code, secret, []byte(`{"type":"pong","data":{}}`))
	select {
	case <-l2.C: // connected / hello / state arrive first; just check something flows
	default:
		t.Error("the new browser should still be connected")
	}

	// the Pi drops: the browser is told, and commands stop
	r.PiGone(code, stream)
	if err := r.ToPi(code, Command{Op: "ping"}); !errors.Is(err, ErrNotFound) {
		t.Errorf("an offline Pi can't be commanded: %v", err)
	}
}

func TestQuietPisAreForgotten(t *testing.T) {
	c := &clock{t: time.Date(2026, 10, 29, 9, 0, 0, 0, time.UTC)}
	r := New(c.now)
	never, _, _ := r.Register("", "a", 3)     // registered, never connected
	gone, secret, _ := r.Register("", "b", 3) // connected, then dropped
	_, stream, _ := r.PiConnected(gone, secret)
	live, ls, _ := r.Register("", "c", 3)
	r.PiConnected(live, ls)
	l, _, _ := r.Watch(gone)
	r.PiGone(gone, stream)

	c.t = c.t.Add(OfflineGrace + time.Second)
	r.Sweep()
	if _, err := r.authed(gone, secret); !errors.Is(err, ErrNotFound) {
		t.Error("a Pi that stayed offline should be forgotten")
	}
	var last []byte
	for ev := range l.C {
		last = ev
	}
	_ = last
	if l.Reason != "The Pi disconnected." {
		t.Errorf("the browser should be told: %q", l.Reason)
	}
	if r.find(live) == nil {
		t.Error("a connected Pi must stay")
	}
	c.t = c.t.Add(RegisterTTL)
	r.Sweep()
	if r.find(never) != nil {
		t.Error("a code that was never used should expire")
	}
	if r.find(live) == nil {
		t.Error("a connected Pi must stay")
	}
	if r.Count() != 1 {
		t.Errorf("Count = %d", r.Count())
	}
}
