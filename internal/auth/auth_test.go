package auth

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestTokens(t *testing.T) {
	s, _ := New("0123456789abcdef-secret")
	other, _ := New("another-secret-0123456789")
	now := time.Now()
	tok := s.TeacherToken("teacher-code-one", now.Add(time.Hour))
	if s.Teacher(tok, now) != s.TeacherID("teacher-code-one") {
		t.Fatal("a teacher's own token")
	}
	if s.Teacher(tok, now.Add(2*time.Hour)) != "" || other.Teacher(tok, now) != "" || s.Teacher(tok+"0", now) != "" {
		t.Fatal("an expired, foreign or changed token was accepted")
	}
	if s.TeacherID("a") == s.TeacherID("b") {
		t.Fatal("two codes, one teacher")
	}
	st := s.StudentToken(strings.Repeat("ab", 16))
	if s.Student(st) != strings.Repeat("ab", 16) || other.Student(st) != "" || s.Student("s2.x.y") != "" {
		t.Fatal("student tokens")
	}
	if _, err := New("short"); err == nil {
		t.Fatal("a short secret")
	}
}

func TestTeacherCodesFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "teacher-codes.txt")
	tc := NewTeachers(path, "env-code-1234, x")
	if tc.Len() != 1 || tc.Match("env-code-1234") == "" {
		t.Fatal("codes from the environment (too-short ones dropped)")
	}
	code, err := AddCode(path, "", "Ms Lee")
	if err != nil || len(code) < MinCode {
		t.Fatalf("a new code: %q %v", code, err)
	}
	if tc.Match(code) != code || tc.Match(" "+code+" ") != code {
		t.Fatal("a code added to the file works at once")
	}
	if _, err := AddCode(path, code, ""); err == nil {
		t.Fatal("the same code twice")
	}
	if _, err := AddCode(path, "has space x", ""); err == nil {
		t.Fatal("a code with a space")
	}
	mine, _ := AddCode(path, "my-own-code-99", "Mr Tan")
	if st, _ := os.Stat(path); st.Mode().Perm() != 0o600 {
		t.Fatalf("the file can be read by others: %v", st.Mode())
	}
	time.Sleep(10 * time.Millisecond)
	if n, _ := RemoveCode(path, "ms lee"); n != 1 {
		t.Fatal("removing by label")
	}
	if tc.Match(code) != "" || tc.Match(mine) != mine {
		t.Fatal("a removed code still works, or the other went")
	}
	list, _ := ReadCodes(path)
	if len(list) != 1 || list[0].Label != "Mr Tan" {
		t.Fatalf("the list: %v", list)
	}
}
