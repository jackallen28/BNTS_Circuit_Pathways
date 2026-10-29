package pirelay

import (
	"encoding/json"
	"fmt"
)

// A Command is what the browser may ask a Pi to do. The relay checks it, and
// the Pi app checks it again: nothing else can reach the pins, and nothing is
// ever run as a program or a shell command.
type Command struct {
	Op    string  `json:"op"`              // mode | write | pwm | release | all_off | ping | read
	Pin   int     `json:"pin,omitempty"`   // GPIO (BCM) number, 2 to 27
	Mode  string  `json:"mode,omitempty"`  // out | in | in_up | in_down | pwm
	Value int     `json:"value,omitempty"` // 0 or 1
	Duty  float64 `json:"duty,omitempty"`  // 0 to 1
	Freq  int     `json:"freq,omitempty"`  // PWM frequency in Hz, 1 to 10000
	ID    int     `json:"id,omitempty"`    // echoed back, so the browser can match replies
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
