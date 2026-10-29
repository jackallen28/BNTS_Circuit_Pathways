// Package classes makes and checks class codes and teacher sign-ins without
// storing anything. A class code carries its own expiry and a signature, so
// the server can tell a real code from a guess without a database. It holds
// no names, no school and no class label: those stay on the teacher's and
// students' own computers.
//
// A class code is 10 letters and digits shown as ABCDE-FGHJK:
//
//	first five characters  12 bits: the last day it works (days after 1 Jan 2026)
//	                       13 bits: random, so two classes never get the same code
//	last five characters   25 bits: the first 25 bits of HMAC-SHA256(secret, first five)
package classes

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"strconv"
	"strings"
	"time"
)

// alphabet is Crockford's base 32: no I, L, O or U, so codes are easy to read and type.
const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

var epoch = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

// Melbourne is UTC+11 in daylight saving time; a code works until the end of its last day there.
const melbourneOffset = 11 * time.Hour

// MaxDays is the longest a class code can last.
const MaxDays = 366

// Signer makes and checks codes with a secret.
type Signer struct {
	secret []byte
}

// New returns a Signer. The secret must be long and random (at least 16 bytes).
func New(secret string) (*Signer, error) {
	if len(secret) < 16 {
		return nil, errors.New("the class secret must be at least 16 characters")
	}
	return &Signer{secret: []byte(secret)}, nil
}

func (s *Signer) mac(msg string) []byte {
	h := hmac.New(sha256.New, s.secret)
	h.Write([]byte(msg))
	return h.Sum(nil)
}

func encode5(v uint32) string {
	var b [5]byte
	for i := 4; i >= 0; i-- {
		b[i] = alphabet[v&31]
		v >>= 5
	}
	return string(b[:])
}

func decode5(s string) (uint32, bool) {
	var v uint32
	for _, r := range s {
		i := strings.IndexRune(alphabet, r)
		if i < 0 {
			return 0, false
		}
		v = v<<5 | uint32(i)
	}
	return v, len(s) == 5
}

// Normalise tidies what a student typed: upper case, no spaces or dashes,
// and the look-alikes (I, L, O) read as the digits they were meant to be.
func Normalise(code string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(code) {
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

// NewClass makes a class code that works for days more days (1 to MaxDays),
// counting today. It returns the code and the moment it stops working.
func (s *Signer) NewClass(now time.Time, days int) (code string, expires time.Time, err error) {
	if days < 1 || days > MaxDays {
		return "", time.Time{}, errors.New("pick between 1 and " + strconv.Itoa(MaxDays) + " days")
	}
	last := dayNumber(now.Add(melbourneOffset)) + days - 1
	if last >= 1<<12 {
		return "", time.Time{}, errors.New("that is too far in the future")
	}
	var r [2]byte
	if _, err := rand.Read(r[:]); err != nil {
		return "", time.Time{}, err
	}
	payload := uint32(last)<<13 | uint32(uint16(r[0])<<8|uint16(r[1]))&(1<<13-1)
	head := encode5(payload)
	m := s.mac("class1:" + head)
	tag := (uint32(m[0])<<24 | uint32(m[1])<<16 | uint32(m[2])<<8 | uint32(m[3])) >> 7 // 25 bits
	full := head + encode5(tag)
	return full[:5] + "-" + full[5:], endOfDay(last), nil
}

func dayNumber(t time.Time) int { return int(t.Sub(epoch).Hours() / 24) }

func endOfDay(day int) time.Time {
	return epoch.AddDate(0, 0, day+1).Add(-melbourneOffset)
}

// Verify checks a class code a student typed. ok is true only for a real
// code that hasn't expired.
func (s *Signer) Verify(code string, now time.Time) (expires time.Time, ok bool) {
	c := Normalise(code)
	if len(c) != 10 {
		return time.Time{}, false
	}
	payload, ok1 := decode5(c[:5])
	tag, ok2 := decode5(c[5:])
	if !ok1 || !ok2 {
		return time.Time{}, false
	}
	m := s.mac("class1:" + c[:5])
	want := (uint32(m[0])<<24 | uint32(m[1])<<16 | uint32(m[2])<<8 | uint32(m[3])) >> 7
	if subtle.ConstantTimeEq(int32(want), int32(tag)) != 1 {
		return time.Time{}, false
	}
	exp := endOfDay(int(payload >> 13))
	if !now.Before(exp) {
		return exp, false
	}
	return exp, true
}

// NewTeacherToken makes a sign-in token that lasts for ttl.
func (s *Signer) NewTeacherToken(now time.Time, ttl time.Duration) (token string, expires time.Time) {
	expires = now.Add(ttl)
	body := "t1." + strconv.FormatInt(expires.Unix(), 10)
	sig := base64.RawURLEncoding.EncodeToString(s.mac(body))
	return body + "." + sig, expires
}

// VerifyTeacherToken checks a token from NewTeacherToken.
func (s *Signer) VerifyTeacherToken(token string, now time.Time) bool {
	i := strings.LastIndex(token, ".")
	if i < 0 {
		return false
	}
	body, sig := token[:i], token[i+1:]
	want := base64.RawURLEncoding.EncodeToString(s.mac(body))
	if subtle.ConstantTimeCompare([]byte(sig), []byte(want)) != 1 {
		return false
	}
	parts := strings.Split(body, ".")
	if len(parts) != 2 || parts[0] != "t1" {
		return false
	}
	exp, err := strconv.ParseInt(parts[1], 10, 64)
	return err == nil && now.Unix() < exp
}

// CheckAccess accepts either a class code or a teacher token.
func (s *Signer) CheckAccess(access string, now time.Time) bool {
	if strings.HasPrefix(access, "t1.") {
		return s.VerifyTeacherToken(access, now)
	}
	_, ok := s.Verify(access, now)
	return ok
}

// TeacherCodes holds the teacher codes set by the school (never stored in code or files).
type TeacherCodes struct{ codes [][]byte }

// ParseTeacherCodes reads a comma- or newline-separated list of teacher codes.
func ParseTeacherCodes(list string) TeacherCodes {
	var t TeacherCodes
	for _, c := range strings.FieldsFunc(list, func(r rune) bool { return r == ',' || r == '\n' || r == ';' }) {
		if c = strings.TrimSpace(c); len(c) >= 8 {
			t.codes = append(t.codes, []byte(c))
		}
	}
	return t
}

// Len is how many valid teacher codes are set.
func (t TeacherCodes) Len() int { return len(t.codes) }

// Check compares a typed teacher code with every real one, in constant time per code.
func (t TeacherCodes) Check(typed string) bool {
	typed = strings.TrimSpace(typed)
	ok := 0
	for _, c := range t.codes {
		ok |= subtle.ConstantTimeCompare([]byte(typed), c)
	}
	return ok == 1
}
