package auth

import (
	"bufio"
	"crypto/rand"
	"crypto/subtle"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// MinCode and MaxCode are how long a teacher code may be.
const (
	MinCode = 8
	MaxCode = 64
)

// Teachers is the list of teacher codes: the school's file on the server (one code per line, with an
// optional "# label" after it) plus any given when the server starts. The file is read again when it
// changes, so adding a teacher needs no restart.
type Teachers struct {
	path  string
	extra []string
	mu    sync.Mutex
	codes []string
	mod   time.Time
	size  int64
}

// NewTeachers reads the codes in path (it may not exist yet) and extra (a comma- or newline-separated list).
func NewTeachers(path, extra string) *Teachers {
	t := &Teachers{path: path}
	for _, c := range strings.FieldsFunc(extra, func(r rune) bool { return r == ',' || r == '\n' || r == ';' }) {
		if c = strings.TrimSpace(c); len(c) >= MinCode && len(c) <= MaxCode {
			t.extra = append(t.extra, c)
		}
	}
	t.reload()
	return t
}

func (t *Teachers) reload() {
	if t.path == "" {
		return
	}
	st, err := os.Stat(t.path)
	if err != nil {
		t.codes, t.mod, t.size = nil, time.Time{}, 0
		return
	}
	if st.ModTime().Equal(t.mod) && st.Size() == t.size {
		return
	}
	entries, err := ReadCodes(t.path)
	if err != nil {
		return
	}
	t.codes = t.codes[:0]
	for _, e := range entries {
		t.codes = append(t.codes, e.Code)
	}
	t.mod, t.size = st.ModTime(), st.Size()
}

// Len is how many teacher codes there are.
func (t *Teachers) Len() int {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.reload()
	return len(t.codes) + len(t.extra)
}

// Match returns the real code a typed one matches (comparing every code in constant time), or "".
func (t *Teachers) Match(typed string) string {
	typed = strings.TrimSpace(typed)
	t.mu.Lock()
	t.reload()
	all := append(append([]string{}, t.codes...), t.extra...)
	t.mu.Unlock()
	found := ""
	for _, c := range all {
		if subtle.ConstantTimeCompare([]byte(typed), []byte(c)) == 1 {
			found = c
		}
	}
	return found
}

// Entry is one line of the codes file.
type Entry struct {
	Code, Label string
}

// ReadCodes reads a codes file.
func ReadCodes(path string) ([]Entry, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []Entry
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		code, label, _ := strings.Cut(line, "#")
		code = strings.TrimSpace(code)
		if len(code) >= MinCode && len(code) <= MaxCode && !strings.ContainsAny(code, " \t") {
			out = append(out, Entry{Code: code, Label: strings.TrimSpace(label)})
		}
	}
	return out, sc.Err()
}

func writeCodes(path string, entries []Entry) error {
	var b strings.Builder
	b.WriteString("# Circuit Pathways teacher codes: one per line, with a label after # (no student names).\n")
	b.WriteString("# Add one with:  sudo circuitpathways teacher add \"Ms Lee\"     Remove:  sudo circuitpathways teacher remove CODE\n")
	for _, e := range entries {
		if e.Label != "" {
			fmt.Fprintf(&b, "%s  # %s\n", e.Code, e.Label)
		} else {
			fmt.Fprintf(&b, "%s\n", e.Code)
		}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, []byte(b.String()), 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// codeWords make teacher codes that are easy to read out and type: three words and a number.
var codeWords = strings.Fields(`amber anchor apple arrow aspen badge bamboo basil beacon berry blaze bloom breeze brick
cactus canyon cedar comet coral cosmic crystal dawn delta ember falcon fern flame forest fossil galaxy garnet glacier
harbour hazel honey indigo island jasper jungle kayak kelp koala lagoon lantern lemon lilac lotus lunar magnet maple
meadow meteor mint nebula nickel oasis ocean olive opal orbit orchid otter pebble pepper pixel planet plum prism quartz
quokka rain raven reef river rocket saffron sapphire shell sierra silver solar spark spruce storm summit sunset thunder
tiger topaz tulip tundra valley velvet violet volcano walnut wattle willow wombat zephyr`)

// NewCode makes a fresh teacher code such as "comet-maple-reef-42".
func NewCode() string {
	b := make([]byte, 4)
	rand.Read(b)
	n := len(codeWords)
	return fmt.Sprintf("%s-%s-%s-%02d", codeWords[int(b[0])%n], codeWords[int(b[1])%n], codeWords[int(b[2])%n], int(b[3])%100)
}

// AddCode adds a code (a new random one if code is "") with a label to the file, and returns it.
func AddCode(path, code, label string) (string, error) {
	entries, err := ReadCodes(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	if code == "" {
		code = NewCode()
	}
	code = strings.TrimSpace(code)
	if len(code) < MinCode || len(code) > MaxCode || strings.ContainsAny(code, " \t#") {
		return "", fmt.Errorf("a teacher code is %d to %d characters, with no spaces or #", MinCode, MaxCode)
	}
	label = strings.TrimSpace(strings.ReplaceAll(label, "\n", " "))
	for _, e := range entries {
		if e.Code == code {
			return "", errors.New("that code is already on the list")
		}
	}
	return code, writeCodes(path, append(entries, Entry{Code: code, Label: label}))
}

// RemoveCode takes a code (or every code with that label) off the file. It returns how many it removed.
func RemoveCode(path, codeOrLabel string) (int, error) {
	entries, err := ReadCodes(path)
	if err != nil {
		return 0, err
	}
	kept := entries[:0]
	n := 0
	for _, e := range entries {
		if e.Code == codeOrLabel || (e.Label != "" && strings.EqualFold(e.Label, codeOrLabel)) {
			n++
			continue
		}
		kept = append(kept, e)
	}
	if n == 0 {
		return 0, nil
	}
	return n, writeCodes(path, kept)
}
