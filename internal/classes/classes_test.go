package classes

import (
	"strings"
	"testing"
	"time"
)

func signer(t *testing.T) *Signer {
	s, err := New("0123456789abcdef-test-secret")
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestClassCodeRoundTrip(t *testing.T) {
	s := signer(t)
	now := time.Date(2026, 10, 29, 3, 0, 0, 0, time.UTC)
	code, exp, err := s.NewClass(now, 7)
	if err != nil {
		t.Fatal(err)
	}
	if len(code) != 11 || code[5] != '-' {
		t.Fatalf("code %q isn't ABCDE-FGHJK", code)
	}
	got, ok := s.Verify(code, now)
	if !ok || !got.Equal(exp) {
		t.Fatalf("Verify(%q) = %v, %v; want %v", code, got, ok, exp)
	}
	// typed sloppily
	sloppy := strings.ToLower(strings.ReplaceAll(code, "-", " "))
	if _, ok := s.Verify(sloppy, now); !ok {
		t.Errorf("%q should still work", sloppy)
	}
	// works through its last day in Melbourne (29 Oct + 6 days = 4 Nov), then stops
	if _, ok := s.Verify(code, time.Date(2026, 11, 4, 12, 0, 0, 0, time.UTC)); !ok {
		t.Error("should still work on its last day")
	}
	if _, ok := s.Verify(code, time.Date(2026, 11, 4, 13, 0, 0, 0, time.UTC)); ok {
		t.Error("should have expired at midnight in Melbourne")
	}
}

func TestClassCodeRejectsGuessesAndOtherSecrets(t *testing.T) {
	s := signer(t)
	now := time.Date(2026, 10, 29, 0, 0, 0, 0, time.UTC)
	code, _, _ := s.NewClass(now, 30)
	other, _ := New("a-completely-different-secret")
	if _, ok := other.Verify(code, now); ok {
		t.Error("a code from another secret was accepted")
	}
	for _, bad := range []string{"", "ABCDE-FGHJK", "1234567890", code[:10], code + "A", "UUUUU-UUUUU"} {
		if _, ok := s.Verify(bad, now); ok {
			t.Errorf("%q was accepted", bad)
		}
	}
	// changing any character breaks it
	flipped := []byte(code)
	flipped[0] = alphabet[(strings.IndexByte(alphabet, flipped[0])+1)%32]
	if _, ok := s.Verify(string(flipped), now); ok {
		t.Error("a changed code was accepted")
	}
}

func TestDaysLimits(t *testing.T) {
	s := signer(t)
	now := time.Now()
	for _, d := range []int{0, -1, MaxDays + 1} {
		if _, _, err := s.NewClass(now, d); err == nil {
			t.Errorf("%d days should be refused", d)
		}
	}
}

func TestTeacherToken(t *testing.T) {
	s := signer(t)
	now := time.Now()
	tok, _ := s.NewTeacherToken(now, time.Hour)
	if !s.VerifyTeacherToken(tok, now) || !s.CheckAccess(tok, now) {
		t.Error("fresh token refused")
	}
	if s.VerifyTeacherToken(tok, now.Add(2*time.Hour)) {
		t.Error("expired token accepted")
	}
	if s.VerifyTeacherToken(tok+"x", now) || s.VerifyTeacherToken("t1.9999999999.abc", now) {
		t.Error("forged token accepted")
	}
}

func TestTeacherCodes(t *testing.T) {
	tc := ParseTeacherCodes("short, correct-horse-battery , another-good-code\n")
	if tc.Len() != 2 {
		t.Fatalf("got %d codes, want 2 (short ones are ignored)", tc.Len())
	}
	if !tc.Check(" correct-horse-battery ") || !tc.Check("another-good-code") {
		t.Error("real code refused")
	}
	if tc.Check("short") || tc.Check("") || tc.Check("correct-horse") {
		t.Error("wrong code accepted")
	}
	if ParseTeacherCodes("").Check("") {
		t.Error("with no codes set, nothing should work")
	}
}
