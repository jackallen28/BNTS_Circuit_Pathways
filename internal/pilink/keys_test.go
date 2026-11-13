package pilink

import (
	"strings"
	"testing"
)

func TestKeysRoundTrip(t *testing.T) {
	k, err := NewKeys("0123456789abcdef-pi-secret", nil)
	if err != nil {
		t.Fatal(err)
	}
	id, key, err := k.New()
	if err != nil {
		t.Fatal(err)
	}
	if len(id) != 8 || !strings.HasPrefix(key, "CPK1-"+id+"-") || len(key) != 5+8+1+10 {
		t.Fatalf("id %q key %q", id, key)
	}
	got, ok := k.Verify(key)
	if !ok || got != id {
		t.Fatalf("Verify(%q) = %q %v", key, got, ok)
	}
	if got, ok := k.Verify("  " + strings.ToLower(key) + " "); !ok || got != id {
		t.Error("a key typed in lower case with spaces should still work")
	}
	if k.KeyFor(DisplayID(id)) != key {
		t.Error("a key can be made again from the ID on the label")
	}
	if DisplayID(id) != id[:4]+"-"+id[4:] || NormaliseID("k7m2-qx9p") != "K7M2QX9P" || NormaliseID("o-i-l") != "011" {
		t.Error("IDs are shown with a dash and typed forgivingly")
	}
}

func TestKeysRejectGuessesAndOtherSecrets(t *testing.T) {
	k, _ := NewKeys("0123456789abcdef-pi-secret", nil)
	other, _ := NewKeys("another-secret-entirely", nil)
	_, key, _ := k.New()
	for _, bad := range []string{"", "CPK1", "CPK1-K7M2QX9P-AAAAAAAAAA", "CPK2" + key[4:], key[:len(key)-1], key + "A", "CPK1-UUUUUUUU-AAAAAAAAAA"} {
		if _, ok := k.Verify(bad); ok {
			t.Errorf("%q was accepted", bad)
		}
	}
	if _, ok := other.Verify(key); ok {
		t.Error("a key from another secret was accepted")
	}
	flipped := []byte(key)
	flipped[len(flipped)-1] ^= 1
	if _, ok := k.Verify(string(flipped)); ok {
		t.Error("a changed key was accepted")
	}
}

func TestRevokedKeys(t *testing.T) {
	k, _ := NewKeys("0123456789abcdef-pi-secret", nil)
	id, key, _ := k.New()
	r, _ := NewKeys("0123456789abcdef-pi-secret", []string{DisplayID(id)})
	if _, ok := r.Verify(key); ok {
		t.Error("a revoked key was accepted")
	}
	if _, ok := k.Verify(key); !ok {
		t.Error("the same key without revocation should work")
	}
}

func TestShortSecretsAreRefused(t *testing.T) {
	if _, err := NewKeys("short", nil); err == nil {
		t.Error("a short secret should be refused")
	}
}
