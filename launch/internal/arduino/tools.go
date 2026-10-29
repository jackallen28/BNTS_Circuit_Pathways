package arduino

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Tools compiles sketches with the pinned arduino-cli installed by Env.Setup.
// It serves the hosted site: it never keeps a student's code. Each sketch is
// written to a temporary folder that is deleted as soon as the compile ends.
type Tools struct {
	env *Env
	log *slog.Logger

	// One compile at a time per board, because a board's build folder is
	// shared (so its core is only compiled once).
	mu    sync.Mutex
	locks map[string]*sync.Mutex
}

// InstalledTools uses tools already installed by Env.Setup in dir.
func InstalledTools(dir string, log *slog.Logger) (*Tools, error) {
	if log == nil {
		log = slog.Default()
	}
	env := &Env{Dir: dir, Log: log}
	if !env.Ready() {
		return nil, fmt.Errorf("no board tools in %s (run the setup first)", dir)
	}
	return &Tools{env: env, log: log, locks: map[string]*sync.Mutex{}}, nil
}

func (t *Tools) lockFor(fqbn string) *sync.Mutex {
	t.mu.Lock()
	defer t.mu.Unlock()
	m := t.locks[fqbn]
	if m == nil {
		m = &sync.Mutex{}
		t.locks[fqbn] = m
	}
	return m
}

// FamilyOf says which family an FQBN belongs to.
func FamilyOf(fqbn string) string {
	switch {
	case strings.HasPrefix(fqbn, "arduino:avr:"):
		return "avr"
	case strings.HasPrefix(fqbn, "esp8266:"):
		return "esp8266"
	case strings.HasPrefix(fqbn, "esp32:"):
		return "esp32"
	}
	return ""
}

// Diagnostic is one compiler message.
type Diagnostic struct {
	File     string `json:"file"` // "sketch.ino", or a library / core file name
	Line     int    `json:"line,omitempty"`
	Col      int    `json:"col,omitempty"`
	Severity string `json:"severity"` // error | warning | note
	Message  string `json:"message"`
}

// Size is how much of the board's memory a compiled sketch uses.
type Size struct {
	Flash    int64 `json:"flash"`
	FlashMax int64 `json:"flash_max"`
	RAM      int64 `json:"ram"`
	RAMMax   int64 `json:"ram_max"`
}

// CompileResult is the outcome of a compile.
type CompileResult struct {
	OK          bool         `json:"ok"`
	Output      string       `json:"output"`
	Diagnostics []Diagnostic `json:"errors"`
	Size        *Size        `json:"size,omitempty"`
	BuildPath   string       `json:"-"`
}

const sketchName = "sketch"

// Artifact is a file the browser flashes to the board.
type Artifact struct {
	Offset int    `json:"offset"` // where it goes in flash (ESP boards)
	Name   string `json:"name"`
	Data   []byte `json:"data"`
}

// Compile compiles code for a board, with extra build properties (from the
// board's file, such as defining LED_BUILTIN). On success it also returns
// what the browser needs to flash the board: the .hex for an Arduino, or the
// merged .bin for an ESP board.
func (t *Tools) Compile(ctx context.Context, code, fqbn string, props []string) (CompileResult, []Artifact, error) {
	family := FamilyOf(fqbn)
	if family == "" {
		return CompileResult{}, nil, fmt.Errorf("unknown board %q", fqbn)
	}
	lock := t.lockFor(fqbn)
	lock.Lock()
	defer lock.Unlock()
	work := filepath.Join(t.env.Dir, "sketches", randomName())
	sketchDir := filepath.Join(work, sketchName)
	if err := os.MkdirAll(sketchDir, 0o755); err != nil {
		return CompileResult{}, nil, err
	}
	defer os.RemoveAll(work)
	if err := os.WriteFile(filepath.Join(sketchDir, sketchName+".ino"), []byte(code), 0o644); err != nil {
		return CompileResult{}, nil, err
	}
	build := filepath.Join(t.env.Dir, "build", safeName(fqbn))
	if err := os.MkdirAll(build, 0o755); err != nil {
		return CompileResult{}, nil, err
	}
	// A previous sketch's files must never end up in this student's upload.
	for _, stale := range []string{"sketch.ino.hex", "sketch.ino.bin", "sketch.ino.merged.bin", "sketch.ino.elf"} {
		os.Remove(filepath.Join(build, stale))
	}
	ctx, cancel := context.WithTimeout(ctx, 4*time.Minute)
	defer cancel()
	args := []string{"compile", "--fqbn", fqbn, "--build-path", build, "--warnings", "default", "--format", "json"}
	for _, p := range props {
		args = append(args, "--build-property", p)
	}
	text, err := t.stream(ctx, nil, append(args, sketchDir)...)
	if err != nil && strings.TrimSpace(text) == "" {
		return CompileResult{}, nil, fmt.Errorf("the compiler didn't run: %w", err)
	}
	res := parseCompileJSON(text)
	if ctx.Err() == context.DeadlineExceeded {
		return res, nil, errors.New("compiling took too long and was stopped")
	}
	if err != nil && res.OK {
		res.OK = false
	}
	if !res.OK && len(res.Diagnostics) == 0 {
		res.Diagnostics = ParseDiagnostics(res.Output)
	}
	if !res.OK {
		return res, nil, nil
	}
	arts, err := t.artifacts(family, build)
	if err != nil {
		return res, nil, err
	}
	return res, arts, nil
}

func (t *Tools) artifacts(family, build string) ([]Artifact, error) {
	read := func(name string, offset int) (Artifact, error) {
		b, err := os.ReadFile(filepath.Join(build, name))
		if err != nil {
			return Artifact{}, fmt.Errorf("the compiler didn't make %s: %w", name, err)
		}
		return Artifact{Name: name, Offset: offset, Data: b}, nil
	}
	var a Artifact
	var err error
	switch family {
	case "avr":
		a, err = read("sketch.ino.hex", 0)
	case "esp8266":
		a, err = read("sketch.ino.bin", 0)
	default: // esp32: one merged image, written at the start of flash
		a, err = read("sketch.ino.merged.bin", 0)
	}
	if err != nil {
		return nil, err
	}
	return []Artifact{a}, nil
}

// parseCompileJSON reads arduino-cli's --format json result.
func parseCompileJSON(text string) (res CompileResult) {
	var j struct {
		CompilerOut   string `json:"compiler_out"`
		CompilerErr   string `json:"compiler_err"`
		Success       bool   `json:"success"`
		Error         string `json:"error"`
		BuilderResult struct {
			Sections []struct {
				Name    string `json:"name"`
				Size    int64  `json:"size"`
				MaxSize int64  `json:"max_size"`
			} `json:"executable_sections_size"`
		} `json:"builder_result"`
	}
	start := strings.Index(text, "{")
	if start < 0 || json.Unmarshal([]byte(text[start:]), &j) != nil {
		res.Output = text
		return res
	}
	res.OK = j.Success
	res.Output = strings.TrimSpace(j.CompilerOut + "\n" + j.CompilerErr + "\n" + j.Error)
	res.Diagnostics = ParseDiagnostics(j.CompilerErr + "\n" + j.Error)
	defer func() {
		if res.Size == nil && res.OK {
			res.Size = sizeFromText(res.Output)
		}
	}()
	for _, s := range j.BuilderResult.Sections {
		if res.Size == nil {
			res.Size = &Size{}
		}
		switch s.Name {
		case "text":
			res.Size.Flash, res.Size.FlashMax = s.Size, s.MaxSize
		case "data":
			res.Size.RAM, res.Size.RAMMax = s.Size, s.MaxSize
		}
	}
	return res
}

var (
	flashRe = regexp.MustCompile(`Sketch uses (\d+) bytes .*?Maximum is (\d+) bytes`)
	ramRe   = regexp.MustCompile(`Global variables use (\d+) bytes .*?Maximum is (\d+) bytes`)

	esp8266FlashRe = regexp.MustCompile(`Code in flash \(default, ICACHE_FLASH_ATTR\), used (\d+) / (\d+) bytes`)
	esp8266RAMRe   = regexp.MustCompile(`Variables and constants in RAM \(global, static\), used (\d+) / (\d+) bytes`)
)

// sizeFromText reads "Sketch uses 924 bytes (2%) of program storage space.
// Maximum is 32256 bytes." (and the same for RAM) from compiler output.
func sizeFromText(out string) *Size {
	m := flashRe.FindStringSubmatch(out)
	if m == nil {
		// ESP8266: ". Code in flash (default, ICACHE_FLASH_ATTR), used 231884 / 1048576 bytes"
		if e := esp8266FlashRe.FindStringSubmatch(out); e != nil {
			sz := &Size{}
			sz.Flash, _ = strconv.ParseInt(e[1], 10, 64)
			sz.FlashMax, _ = strconv.ParseInt(e[2], 10, 64)
			if r := esp8266RAMRe.FindStringSubmatch(out); r != nil {
				sz.RAM, _ = strconv.ParseInt(r[1], 10, 64)
				sz.RAMMax, _ = strconv.ParseInt(r[2], 10, 64)
			}
			return sz
		}
		return nil
	}
	sz := &Size{}
	sz.Flash, _ = strconv.ParseInt(m[1], 10, 64)
	sz.FlashMax, _ = strconv.ParseInt(m[2], 10, 64)
	if r := ramRe.FindStringSubmatch(out); r != nil {
		sz.RAM, _ = strconv.ParseInt(r[1], 10, 64)
		sz.RAMMax, _ = strconv.ParseInt(r[2], 10, 64)
	}
	return sz
}

var (
	diagRe   = regexp.MustCompile(`^(.*?):(\d+):(?:(\d+):)? (fatal error|error|warning|note): (.*)$`)
	linkerRe = regexp.MustCompile("undefined reference to `([^']+)'")
)

// ParseDiagnostics reads gcc-style messages ("file:line:col: error: msg")
// and linker errors out of compiler output. File names are shortened to
// their base name; the sketch is "sketch.ino".
func ParseDiagnostics(output string) []Diagnostic {
	var out []Diagnostic
	seen := map[string]bool{}
	sc := bufio.NewScanner(strings.NewReader(output))
	sc.Buffer(make([]byte, 64<<10), 1<<20)
	for sc.Scan() {
		line := strings.TrimRight(sc.Text(), "\r")
		var d Diagnostic
		if m := diagRe.FindStringSubmatch(line); m != nil {
			d.File = filepath.Base(strings.ReplaceAll(m[1], `\`, "/"))
			d.Line, _ = strconv.Atoi(m[2])
			d.Col, _ = strconv.Atoi(m[3])
			d.Severity = m[4]
			if d.Severity == "fatal error" {
				d.Severity = "error"
				d.Message = "fatal error: " + m[5]
			} else {
				d.Message = m[5]
			}
		} else if m := linkerRe.FindStringSubmatch(line); m != nil {
			d = Diagnostic{File: "sketch.ino", Severity: "error", Message: "undefined reference to `" + m[1] + "'"}
		} else {
			continue
		}
		key := fmt.Sprint(d.File, d.Line, d.Col, d.Severity, d.Message)
		if !seen[key] {
			seen[key] = true
			out = append(out, d)
		}
	}
	return out
}

// CoachText is what the Coach matches against the errors database: the
// first error in the sketch (or anywhere, if none is in the sketch) and the
// notes right after it ("suggested alternative: ..."). coach.js does the same.
func CoachText(ds []Diagnostic) string {
	first := -1
	for i, d := range ds {
		if d.Severity == "error" && d.File == "sketch.ino" {
			first = i
			break
		}
	}
	if first < 0 {
		for i, d := range ds {
			if d.Severity == "error" {
				first = i
				break
			}
		}
	}
	if first < 0 {
		return ""
	}
	parts := []string{ds[first].Message}
	for _, d := range ds[first+1:] {
		if d.Severity != "note" {
			break
		}
		parts = append(parts, d.Message)
	}
	return strings.Join(parts, "\n")
}

// stream runs arduino-cli, passing its output to out as it arrives, and
// returns all of it.
func (t *Tools) stream(ctx context.Context, out func(string), args ...string) (string, error) {
	args = append([]string{"--config-file", t.env.ConfigFile(), "--no-color"}, args...)
	cmd := exec.CommandContext(ctx, t.env.CLI(), args...)
	cmd.Env = append(os.Environ(), "HOME="+t.env.Dir)
	hideConsole(cmd)
	pr, pw := io.Pipe()
	cmd.Stdout, cmd.Stderr = pw, pw
	if err := cmd.Start(); err != nil {
		return "", err
	}
	var all strings.Builder
	done := make(chan struct{})
	go func() {
		defer close(done)
		buf := make([]byte, 4096)
		for {
			n, err := pr.Read(buf)
			if n > 0 {
				chunk := string(buf[:n])
				all.WriteString(chunk)
				if out != nil {
					out(chunk)
				}
			}
			if err != nil {
				return
			}
		}
	}()
	err := cmd.Wait()
	pw.Close()
	<-done
	return all.String(), err
}

func randomName() string {
	b := make([]byte, 8)
	rand.Read(b)
	return hex.EncodeToString(b)
}

var unsafeChars = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

func safeName(s string) string { return unsafeChars.ReplaceAllString(s, "_") }
