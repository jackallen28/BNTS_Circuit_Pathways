// Package pilink makes and checks the keys that Raspberry Pis use to connect
// to the site, and writes the installer a Pi runs once to start Pi Link at boot.
//
// Each Pi has its own key, which looks like CPK1-K7M2QX9P-AB12CD34EF. The middle
// part (K7M2-QX9P) is the Pi's ID: it is printed on the Pi's label and is what
// a student types into the PiPath page to link to that Pi. The last part is a
// signature made with a secret only the server knows, so the server can tell a
// real key from a made-up one without storing a list of keys. Keys can be
// switched off (revoked) by their ID, or all at once by changing the secret.
package pilink

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"errors"
	"strings"
)

const (
	alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
	idLen    = 8
	macLen   = 10
	prefix   = "CPK1"
)

// Keys makes and checks Pi keys.
type Keys struct {
	secret  []byte
	revoked map[string]bool
}

// NewKeys returns Keys using secret (at least 16 characters) and a list of revoked IDs.
func NewKeys(secret string, revoked []string) (*Keys, error) {
	if len(secret) < 16 {
		return nil, errors.New("the Pi key secret must be at least 16 characters")
	}
	k := &Keys{secret: []byte(secret), revoked: map[string]bool{}}
	for _, id := range revoked {
		if id = NormaliseID(id); id != "" {
			k.revoked[id] = true
		}
	}
	return k, nil
}

// NormaliseID tidies a typed Pi ID: upper case, no spaces or dashes, look-alikes fixed.
func NormaliseID(s string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(s) {
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

// DisplayID writes an ID as K7M2-QX9P.
func DisplayID(id string) string {
	id = NormaliseID(id)
	if len(id) != idLen {
		return id
	}
	return id[:4] + "-" + id[4:]
}

func (k *Keys) mac(id string) string {
	h := hmac.New(sha256.New, k.secret)
	h.Write([]byte("pikey1:" + id))
	sum := h.Sum(nil)
	out := make([]byte, macLen)
	for i := range out { // 5 bits per character, from the first 50 bits
		bit := i * 5
		v := (uint16(sum[bit/8]) << 8) | uint16(sum[bit/8+1])
		out[i] = alphabet[(v>>(11-uint(bit%8)))&31]
	}
	return string(out)
}

// New makes a key for a new Pi: its ID and the full key.
func (k *Keys) New() (id, key string, err error) {
	var r [idLen]byte
	if _, err := rand.Read(r[:]); err != nil {
		return "", "", err
	}
	b := make([]byte, idLen)
	for i, v := range r {
		b[i] = alphabet[int(v)&31]
	}
	id = string(b)
	return id, k.KeyFor(id), nil
}

// KeyFor makes the key for an ID (so a lost key can be made again from the ID).
func (k *Keys) KeyFor(id string) string {
	id = NormaliseID(id)
	return prefix + "-" + id + "-" + k.mac(id)
}

// Verify checks a key. It returns the Pi's ID if the key is real and hasn't been revoked.
func (k *Keys) Verify(key string) (id string, ok bool) {
	parts := strings.Split(strings.ToUpper(strings.TrimSpace(key)), "-")
	if len(parts) != 3 || parts[0] != prefix || len(parts[1]) != idLen || len(parts[2]) != macLen {
		return "", false
	}
	id = parts[1]
	for _, r := range id {
		if !strings.ContainsRune(alphabet, r) {
			return "", false
		}
	}
	if subtle.ConstantTimeCompare([]byte(parts[2]), []byte(k.mac(id))) != 1 || k.revoked[id] {
		return "", false
	}
	return id, true
}
