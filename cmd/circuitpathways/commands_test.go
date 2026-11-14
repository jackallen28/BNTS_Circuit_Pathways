package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"circuitpathways/internal/auth"
	"circuitpathways/internal/pilink"
)

func TestTheCommandsLookAfterTheDataFolder(t *testing.T) {
	data := t.TempDir()
	if err := command("teacher", []string{"add", "Ms Lee", "-data", data}); err != nil {
		t.Fatal(err)
	}
	if err := command("teacher", []string{"add", "-data", data, "chosen-code-12", "Mr Tan"}); err != nil {
		t.Fatal(err)
	}
	list, _ := auth.ReadCodes(filepath.Join(data, "teacher-codes.txt"))
	if len(list) != 2 || list[0].Label != "Ms Lee" || list[1].Code != "chosen-code-12" {
		t.Fatalf("codes: %+v", list)
	}
	if err := command("teacher", []string{"remove", "chosen-code-12", "-data", data}); err != nil {
		t.Fatal(err)
	}
	if err := command("teacher", []string{"remove", "nobody", "-data", data}); err == nil {
		t.Fatal("removing a code that isn't there should say so")
	}
	if err := command("status", []string{"-data", data}); err != nil {
		t.Fatal(err)
	}
	backup := filepath.Join(t.TempDir(), "b.db")
	if err := command("backup", []string{backup, "-data", data}); err != nil {
		t.Fatal(err)
	}
	if err := command("backup", []string{backup, "-data", data}); err == nil {
		t.Fatal("a backup over an old one")
	}
	if err := command("certificate", []string{"-data", data}); err != nil {
		t.Fatal(err)
	}
	if err := command("nonsense", nil); err == nil {
		t.Fatal("an unknown command")
	}
}

func TestAStudentPiKeepsItsOwnKey(t *testing.T) {
	data := t.TempDir()
	k1, err := thisPiKey(data)
	if err != nil {
		t.Fatal(err)
	}
	k2, _ := thisPiKey(data)
	if k1 != k2 {
		t.Fatal("the key changed")
	}
	secret, _ := os.ReadFile(filepath.Join(data, "pi-key-secret"))
	keys, _ := pilink.NewKeys(strings.TrimSpace(string(secret)), nil)
	if _, ok := keys.Verify(k1); !ok {
		t.Fatal("the key isn't signed with the Pi's own secret")
	}
	script, err := piInstaller("http://localhost:8080", k1)
	if err != nil || !strings.Contains(script, k1) || !strings.Contains(script, "class Runner") {
		t.Fatalf("the Pi Link installer: %v", err)
	}
}
