package main

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"circuitpathways"
	"circuitpathways/internal/pilink"
)

// devPiKeySecret is the Pi key secret in -dev mode only (the tests' pretend Pis use it).
const devPiKeySecret = "dev-pi-key-secret-do-not-use-in-production"

// piAppSource is the Pi app that goes inside every Pi Link installer.
func piAppSource() ([]byte, error) {
	return fs.ReadFile(circuitpathways.Site(), "pipath/remote/circuitpathways_pi.py")
}

// secretIn reads a secret kept in the data folder, making it the first time.
func secretIn(dir, name string) (string, error) {
	p := filepath.Join(dir, name)
	if b, err := os.ReadFile(p); err == nil {
		if s := strings.TrimSpace(string(b)); len(s) >= 32 {
			return s, nil
		}
		return "", errors.New(p + " is too short: delete it to make a new one")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	s := hex.EncodeToString(b)
	return s, os.WriteFile(p, []byte(s+"\n"), 0o600)
}

// thisPiKey is a student Pi's own Pi Link key, made and kept in its data folder (the same key every time).
func thisPiKey(dir string) (string, error) {
	secret, err := secretIn(dir, "pi-key-secret")
	if err != nil {
		return "", err
	}
	keys, err := pilink.NewKeys(secret, nil)
	if err != nil {
		return "", err
	}
	idFile := filepath.Join(dir, "this-pi-id")
	if b, err := os.ReadFile(idFile); err == nil {
		if id := pilink.NormaliseID(strings.TrimSpace(string(b))); len(id) == 8 {
			return keys.KeyFor(id), nil
		}
	}
	id, key, err := keys.New()
	if err != nil {
		return "", err
	}
	return key, os.WriteFile(idFile, []byte(pilink.DisplayID(id)+"\n"), 0o600)
}

// piInstaller is the Pi Link installer for a key and the server it links to.
func piInstaller(server, key string) (string, error) {
	src, err := piAppSource()
	if err != nil {
		return "", err
	}
	return pilink.Installer(server, key, src)
}
