package pirelay

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
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

func TestPisAreFoundByTheirIDEvenWhenTypedSloppily(t *testing.T) {
	r := New(nil)
	if _, _, err := r.PiConnected("K7M2QX9P"); err != nil {
		t.Fatal(err)
	}
	if l, _, err := r.Watch(" k7m2-qx9p "); err != nil || l == nil {
		t.Errorf("a typed ID should find the Pi: %v", err)
	}
	if _, _, err := r.Watch("ZZZZ-ZZZZ"); !errors.Is(err, ErrNotFound) {
		t.Errorf("an unknown ID: %v", err)
	}
	if NormaliseCode("abc-d1e") != "ABCD1E" || NormaliseCode(" o i l ") != "011" {
		t.Error("typed codes should be tidied")
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

func TestTooManyPis(t *testing.T) {
	r := New(nil)
	for i := 0; i < MaxPis; i++ {
		if _, _, err := r.PiConnected(fmt.Sprintf("PI%06d", i)); err != nil {
			t.Fatalf("Pi %d: %v", i, err)
		}
	}
	if _, _, err := r.PiConnected("ONEMORE00"); !errors.Is(err, ErrFull) {
		t.Errorf("one more than the limit: %v", err)
	}
	if _, _, err := r.PiConnected("PI000000"); err != nil {
		t.Errorf("a Pi that is already connected can reconnect: %v", err)
	}
}

func TestBrowserAndPiTalk(t *testing.T) {
	r := New(nil)
	code := "K7M2QX9P"
	cmds, stream, _ := r.PiConnected(code)

	if err := r.ToPi(code, Command{Op: "shell"}); !errors.Is(err, ErrBadCommand) {
		t.Fatalf("bad command: %v", err)
	}
	// the Pi says hello and shows its pins before any browser is there
	if err := r.FromPi(code, []byte(`{"type":"hello","data":{"model":"Pi 4","name":"Pi 4"}}`)); err != nil {
		t.Fatal(err)
	}
	if err := r.FromPi(code, []byte(`{"type":"state","data":{"pins":{"17":{"mode":"out","value":1}}}}`)); err != nil {
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
	r.FromPi(code, []byte(`{"type":"state","data":{"pins":{}}}`))
	if ev := <-l.C; string(ev) != `{"type":"state","data":{"pins":{}}}` {
		t.Errorf("the browser got %s", ev)
	}
	// garbage from the Pi is refused
	for _, bad := range []string{`nope`, `{"type":"exec","data":{}}`, `{"type":"state"}`} {
		if err := r.FromPi(code, []byte(bad)); !errors.Is(err, ErrBadCommand) {
			t.Errorf("%s: %v", bad, err)
		}
	}
	if err := r.FromPi(code, make([]byte, maxEventBytes+1)); !errors.Is(err, ErrEventTooBig) {
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
	r.FromPi(code, []byte(`{"type":"pong","data":{}}`))
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
	_, stream, _ := r.PiConnected("GONEGONE") // connected, then dropped
	r.PiConnected("STAYSTAY")                 // still connected
	l, _, _ := r.Watch("GONEGONE")
	r.PiGone("GONEGONE", stream)

	c.t = c.t.Add(OfflineGrace + time.Second)
	r.Sweep()
	if r.find("GONEGONE") != nil {
		t.Error("a Pi that stayed offline should be forgotten")
	}
	for range l.C { // the browser is told, then its stream ends
	}
	if l.Reason != "The Pi disconnected." {
		t.Errorf("the browser should be told: %q", l.Reason)
	}
	if r.find("STAYSTAY") == nil {
		t.Error("a connected Pi must stay")
	}
	if r.Count() != 1 {
		t.Errorf("Count = %d", r.Count())
	}
}

func TestProgramCommandsAreChecked(t *testing.T) {
	run := func(mod func(*Command)) Command {
		c := Command{Op: "run", RunID: 1, Name: "program.py", Code: "print('hi')\n"}
		if mod != nil {
			mod(&c)
		}
		return c
	}
	good := []Command{
		run(nil),
		run(func(c *Command) {
			c.Files = map[string]string{"words.txt": "aGk=", "data/a.csv": "MQ=="}
			c.Support = []string{"pipath_camera"}
			c.CameraObject = "red ball"
		}),
		{Op: "stdin", RunID: 1, Text: "Mia"}, {Op: "stdin", RunID: 2}, {Op: "stop", RunID: 1}, {Op: "stop"},
	}
	for _, c := range good {
		if err := c.Check(); err != nil {
			t.Errorf("%+v refused: %v", c, err)
		}
	}
	bad := []Command{
		run(func(c *Command) { c.RunID = 0 }),
		run(func(c *Command) { c.Name = "../x.py" }),
		run(func(c *Command) { c.Name = "program.sh" }),
		run(func(c *Command) { c.Code = "" }),
		run(func(c *Command) { c.Code = strings.Repeat("x", MaxCodeBytes+1) }),
		run(func(c *Command) { c.Code = "a\x00b" }),
		run(func(c *Command) { c.Files = map[string]string{"../etc/passwd": "eA=="} }),
		run(func(c *Command) { c.Files = map[string]string{"/etc/passwd": "eA=="} }),
		run(func(c *Command) { c.Files = map[string]string{"a/b/c/d": "eA=="} }),
		run(func(c *Command) { c.Files = map[string]string{"big": strings.Repeat("A", MaxFilesBytes+1)} }),
		run(func(c *Command) { c.Support = []string{"os"} }),
		run(func(c *Command) { c.CameraObject = "x; rm -rf /" }),
		{Op: "stdin", Text: "no run id"}, {Op: "stdin", RunID: 1, Text: strings.Repeat("a", MaxStdinBytes+1)}, {Op: "stop", RunID: -1},
	}
	for i, c := range bad {
		if err := c.Check(); !errors.Is(err, ErrBadCommand) {
			t.Errorf("bad command %d should be refused, got %v", i, err)
		}
	}
	many := run(func(c *Command) {
		c.Files = map[string]string{}
		for i := 0; i <= MaxFiles; i++ {
			c.Files[fmt.Sprintf("f%d", i)] = "eA=="
		}
	})
	if err := many.Check(); !errors.Is(err, ErrBadCommand) {
		t.Errorf("too many files: %v", err)
	}
}

func TestProgramReachesThePiAndOutputComesBack(t *testing.T) {
	r := New(nil)
	cmds, _, err := r.PiConnected("K7M2QX9P")
	if err != nil {
		t.Fatal(err)
	}
	l, p, err := r.Watch("K7M2-QX9P")
	if err != nil {
		t.Fatal(err)
	}
	defer r.Unwatch(p, l)
	<-l.C // connected
	if err := r.ToPi("K7M2-QX9P", Command{Op: "run", RunID: 7, Name: "program.py", Code: "print(0)\n"}); err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	if err := json.Unmarshal(<-cmds, &got); err != nil || got["op"] != "run" || got["rid"] != float64(7) || got["code"] != "print(0)\n" {
		t.Errorf("the Pi should get the program: %v %v", got, err)
	}
	for _, ev := range []string{
		`{"type":"run","data":{"rid":7,"state":"started"}}`,
		`{"type":"out","data":{"rid":7,"stream":"out","text":"0\n","seq":1}}`,
		`{"type":"exit","data":{"rid":7,"rc":0}}`,
	} {
		if err := r.FromPi("K7M2QX9P", []byte(ev)); err != nil {
			t.Fatalf("%s: %v", ev, err)
		}
		if !strings.Contains(string(<-l.C), `"rid":7`) {
			t.Errorf("the browser should get %s", ev)
		}
	}
	if err := r.FromPi("K7M2QX9P", []byte(`{"type":"shell","data":{}}`)); !errors.Is(err, ErrBadCommand) {
		t.Errorf("an unknown event type: %v", err)
	}
	// a lot of output is kept, not dropped
	for i := 0; i < 300; i++ {
		r.FromPi("K7M2QX9P", []byte(fmt.Sprintf(`{"type":"out","data":{"rid":7,"stream":"out","text":"x","seq":%d}}`, i)))
	}
	if len(l.C) != 300 {
		t.Errorf("all 300 output events should be waiting, got %d", len(l.C))
	}
}
