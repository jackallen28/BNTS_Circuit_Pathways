// Package auth signs and checks who is asking: a teacher (signed in with one of the school's teacher
// codes) or a student in a class. Tokens are signed with the server's own secret, so they can be checked
// without a lookup, and they are the same shape as the first (Cloudflare) version's, so a browser that
// joined a class there is simply asked to join again.
package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"regexp"
	"strconv"
	"time"
)

// Signer makes and checks tokens.
type Signer struct{ secret []byte }

// New returns a Signer. The secret must be long and random (at least 16 bytes).
func New(secret string) (*Signer, error) {
	if len(secret) < 16 {
		return nil, errors.New("the server secret must be at least 16 characters")
	}
	return &Signer{secret: []byte(secret)}, nil
}

// sign is a short signature as hex: the first n bytes of HMAC-SHA256.
func (s *Signer) sign(msg string, n int) string {
	h := hmac.New(sha256.New, s.secret)
	h.Write([]byte(msg))
	return hex.EncodeToString(h.Sum(nil))[:n*2]
}

func same(a, b string) bool { return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1 }

// TeacherID is a teacher's identity: a one-way fingerprint of their code (the code itself is never stored).
func (s *Signer) TeacherID(code string) string { return s.sign("teacher:"+code, 12) }

// TeacherToken signs a teacher in until expires.
func (s *Signer) TeacherToken(code string, expires time.Time) string {
	body := "t2." + s.TeacherID(code) + "." + strconv.FormatInt(expires.UnixMilli(), 10)
	return body + "." + s.sign(body, 16)
}

var teacherRe = regexp.MustCompile(`^t2\.([0-9a-f]{24})\.(\d{10,15})\.([0-9a-f]{32})$`)
var studentRe = regexp.MustCompile(`^s2\.([0-9a-f]{32})\.([0-9a-f]{32})$`)

// Teacher is the teacher's id from a token that hasn't expired, or "".
func (s *Signer) Teacher(token string, now time.Time) string {
	m := teacherRe.FindStringSubmatch(token)
	if m == nil {
		return ""
	}
	exp, err := strconv.ParseInt(m[2], 10, 64)
	if err != nil || exp < now.UnixMilli() {
		return ""
	}
	if !same(s.sign("t2."+m[1]+"."+m[2], 16), m[3]) {
		return ""
	}
	return m[1]
}

// StudentToken is a student's token (it lasts as long as they are in a class that is running).
func (s *Signer) StudentToken(id string) string { return "s2." + id + "." + s.sign("s2."+id, 16) }

// Student is the student id from a token (still to be looked up in the class list), or "".
func (s *Signer) Student(token string) string {
	m := studentRe.FindStringSubmatch(token)
	if m == nil || !same(s.sign("s2."+m[1], 16), m[2]) {
		return ""
	}
	return m[1]
}
