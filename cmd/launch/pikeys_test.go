package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRefreshedInstallersKeepTheKeysAndCarryTheCurrentApp(t *testing.T) {
	t.Setenv("PI_KEY_SECRET", "0123456789abcdef-pi-secret")
	dir := t.TempDir()
	if err := makePiKeys(2, dir, "https://school.example.org"); err != nil {
		t.Fatal(err)
	}
	csv := filepath.Join(dir, "pi-keys.csv")
	out := filepath.Join(dir, "new")
	if err := refreshPiInstallers(csv, out, "https://school.example.org"); err != nil {
		t.Fatal(err)
	}
	files, _ := filepath.Glob(filepath.Join(dir, "install-pi-*.sh"))
	if len(files) != 2 {
		t.Fatalf("expected 2 installers, found %d", len(files))
	}
	for _, f := range files {
		before, _ := os.ReadFile(f)
		after, err := os.ReadFile(filepath.Join(out, filepath.Base(f)))
		if err != nil {
			t.Fatal(err)
		}
		if string(before) != string(after) {
			t.Errorf("%s: a refreshed installer should match the original while the app is unchanged", filepath.Base(f))
		}
		if !strings.Contains(string(after), "class Runner") {
			t.Errorf("%s doesn't carry the program-running Pi app", filepath.Base(f))
		}
	}
}
