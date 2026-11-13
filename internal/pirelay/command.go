package pirelay

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"
)

// A Command is what the browser may ask a Pi to do. The relay checks it, and
// the Pi app checks it again. A command either works one pin, or (run, stdin,
// stop) runs the student's own Python program on a Pi that has agreed to. It is
// never a shell command, and the Pi app decides what a program may touch.
type Command struct {
	Op    string  `json:"op"`              // mode | write | pwm | release | all_off | ping | read | run | stdin | stop
	Pin   int     `json:"pin,omitempty"`   // GPIO (BCM) number, 2 to 27
	Mode  string  `json:"mode,omitempty"`  // out | in | in_up | in_down | pwm
	Value int     `json:"value,omitempty"` // 0 or 1
	Duty  float64 `json:"duty,omitempty"`  // 0 to 1
	Freq  int     `json:"freq,omitempty"`  // PWM frequency in Hz, 1 to 10000
	ID    int     `json:"id,omitempty"`    // echoed back, so the browser can match replies

	// run, stdin and stop (a program on the Pi)
	RunID        int               `json:"rid,omitempty"`     // which run this is about (from the browser)
	Name         string            `json:"name,omitempty"`    // the program's file name, such as program.py
	Code         string            `json:"code,omitempty"`    // the program
	Files        map[string]string `json:"files,omitempty"`   // data files the program reads: name -> base64
	Support      []string          `json:"support,omitempty"` // PiPath's helper modules the program imports
	CameraObject string            `json:"camera_object,omitempty"`
	Text         string            `json:"text,omitempty"` // a line for input()
}

// What a program sent to a Pi may hold. The request has to stay under the site's body limit.
const (
	MaxCodeBytes  = 40 << 10
	MaxFilesBytes = 40 << 10 // all data files together, as base64
	MaxFiles      = 8
	MaxStdinBytes = 1000
)

var (
	programName = regexp.MustCompile(`^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}\.py$`)
	fileSegment = regexp.MustCompile(`^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}$`)
	cameraName  = regexp.MustCompile(`^[a-z ]{0,30}$`)
	supportMods = map[string]bool{"pipath_camera": true, "pipath_computer": true}
)

func (c Command) checkRun() error {
	bad := func(why string) error { return fmt.Errorf("%w: %s", ErrBadCommand, why) }
	if c.RunID <= 0 || !programName.MatchString(c.Name) {
		return bad("run needs an id and a .py file name")
	}
	if c.Code == "" || len(c.Code) > MaxCodeBytes || !utf8.ValidString(c.Code) || strings.ContainsRune(c.Code, 0) {
		return bad("the program is empty or too big")
	}
	if len(c.Files) > MaxFiles {
		return bad("too many data files")
	}
	total := 0
	for name, data := range c.Files {
		segs := strings.Split(name, "/")
		if len(segs) > 3 {
			return bad("data file path")
		}
		for _, seg := range segs {
			if !fileSegment.MatchString(seg) || seg == ".." {
				return bad("data file name")
			}
		}
		total += len(data)
	}
	if total > MaxFilesBytes {
		return bad("the data files are too big")
	}
	for _, m := range c.Support {
		if !supportMods[m] {
			return bad("unknown helper module")
		}
	}
	if !cameraName.MatchString(c.CameraObject) {
		return bad("camera object")
	}
	return nil
}

// Pins are the GPIO (BCM) numbers on the 40-pin header that a student may use.
const (
	MinPin = 2
	MaxPin = 27
)

// Check says whether the command is well formed.
func (c Command) Check() error {
	pin := func() error {
		if c.Pin < MinPin || c.Pin > MaxPin {
			return fmt.Errorf("%w: GPIO %d", ErrBadCommand, c.Pin)
		}
		return nil
	}
	switch c.Op {
	case "all_off", "ping", "read":
		return nil
	case "run":
		return c.checkRun()
	case "stdin":
		if c.RunID <= 0 || len(c.Text) > MaxStdinBytes || !utf8.ValidString(c.Text) || strings.ContainsRune(c.Text, 0) {
			return ErrBadCommand
		}
		return nil
	case "stop":
		if c.RunID < 0 {
			return ErrBadCommand
		}
		return nil
	case "release":
		return pin()
	case "mode":
		switch c.Mode {
		case "out", "in", "in_up", "in_down", "pwm":
			return pin()
		}
		return ErrBadCommand
	case "write":
		if c.Value != 0 && c.Value != 1 {
			return ErrBadCommand
		}
		return pin()
	case "pwm":
		if c.Duty < 0 || c.Duty > 1 || c.Freq < 0 || c.Freq > 10000 {
			return ErrBadCommand
		}
		return pin()
	}
	return ErrBadCommand
}

// MarshalJSON writes exactly the fields each operation needs. (A plain
// "omitempty" would drop a value of 0, and "turn off" would arrive without one.)
func (c Command) MarshalJSON() ([]byte, error) {
	m := map[string]any{"op": c.Op}
	if c.ID != 0 {
		m["id"] = c.ID
	}
	switch c.Op {
	case "run":
		m["rid"], m["name"], m["code"] = c.RunID, c.Name, c.Code
		if len(c.Files) > 0 {
			m["files"] = c.Files
		}
		if len(c.Support) > 0 {
			m["support"] = c.Support
		}
		if c.CameraObject != "" {
			m["camera_object"] = c.CameraObject
		}
	case "stdin":
		m["rid"], m["text"] = c.RunID, c.Text
	case "stop":
		m["rid"] = c.RunID
	case "release":
		m["pin"] = c.Pin
	case "mode":
		m["pin"], m["mode"] = c.Pin, c.Mode
	case "write":
		m["pin"], m["value"] = c.Pin, c.Value
	case "pwm":
		m["pin"], m["duty"] = c.Pin, c.Duty
		if c.Freq > 0 {
			m["freq"] = c.Freq
		}
	}
	return json.Marshal(m)
}
