package pilink

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func app(t *testing.T) []byte {
	b, err := os.ReadFile("../../site/pipath/remote/circuitpathways_pi.py")
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestInstallerForOnePi(t *testing.T) {
	k, _ := NewKeys("0123456789abcdef-pi-secret", nil)
	id, key, _ := k.New()
	script, err := Installer("https://school.example.org/", key, app(t))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{key, DisplayID(id), "https://school.example.org", "systemctl enable --now circuitpathways-pi", "PYTHON_APP_END"} {
		if !strings.Contains(script, want) {
			t.Errorf("the installer should contain %q", want)
		}
	}
	if strings.Contains(script, PlaceholderServer) || strings.Contains(script, "<%") {
		t.Error("the installer still has placeholders in it")
	}
	if strings.Count(script, "#!/usr/bin/env bash") != 2 {
		t.Error("expected the installer and the pilink helper")
	}
}

func TestInstallerRefusesBadInput(t *testing.T) {
	for _, server := range []string{"", "ftp://x", "https://x y", "https://x\"; rm -rf /", "https://x$(id)", "https://x`id`"} {
		if _, err := Installer(server, "", app(t)); err == nil {
			t.Errorf("server %q should be refused", server)
		}
	}
	if _, err := Installer("https://x", "not-a-key", app(t)); err == nil {
		t.Error("a bad key should be refused")
	}
}

// The installer is run for real, into a temporary folder: it must write every
// file, and the config it writes must be one the Pi app accepts.
func TestInstallerRunsAndMakesWorkingFiles(t *testing.T) {
	if _, err := exec.LookPath("bash"); err != nil {
		t.Skip("no bash")
	}
	k, _ := NewKeys("0123456789abcdef-pi-secret", nil)
	_, key, _ := k.New()
	script, err := Installer("https://school.example.org", key, app(t))
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	file := filepath.Join(dir, "install.sh")
	os.WriteFile(file, []byte(script), 0o755)
	if out, err := exec.Command("bash", "-n", file).CombinedOutput(); err != nil {
		t.Fatalf("the installer has a syntax error: %v\n%s", err, out)
	}
	root := filepath.Join(dir, "root")
	os.MkdirAll(filepath.Join(root, "boot", "firmware"), 0o755)
	cmd := exec.Command("bash", file)
	cmd.Env = append(os.Environ(), "CP_PREFIX="+root)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("installer failed: %v\n%s", err, out)
	}
	for _, f := range []string{"opt/circuitpathways-pi/circuitpathways_pi.py", "etc/circuitpathways-pi.conf", "etc/circuitpathways-pi.id", "usr/local/bin/pilink", "boot/firmware/PI-LINK-ID.txt"} {
		if _, err := os.Stat(filepath.Join(root, f)); err != nil {
			t.Errorf("missing %s", f)
		}
	}
	conf, _ := os.ReadFile(filepath.Join(root, "etc/circuitpathways-pi.conf"))
	if !strings.Contains(string(conf), "KEY="+key) || !strings.Contains(string(conf), "SERVER=https://school.example.org") {
		t.Errorf("config:\n%s", conf)
	}
	for _, want := range []string{"RUN=yes", "RUN_USER=cprun"} {
		if !strings.Contains(string(conf), want) {
			t.Errorf("config should say %s:\n%s", want, conf)
		}
	}
	if info, _ := os.Stat(filepath.Join(root, "etc/circuitpathways-pi.conf")); info.Mode().Perm() != 0o600 {
		t.Errorf("the key file should be private, got %v", info.Mode().Perm())
	}
	installed, _ := os.ReadFile(filepath.Join(root, "opt/circuitpathways-pi/circuitpathways_pi.py"))
	if string(installed) != strings.TrimRight(strings.ReplaceAll(string(app(t)), PlaceholderServer, "https://school.example.org"), "\n")+"\n" {
		t.Error("the installed app isn't the app that was embedded")
	}
	if !strings.Contains(string(out), "Pi Link is installed") {
		t.Errorf("no summary:\n%s", out)
	}
	if py, err := exec.LookPath("python3"); err == nil {
		// the installed app reads the installed config and refuses nothing about it
		c := exec.Command(py, filepath.Join(root, "opt/circuitpathways-pi/circuitpathways_pi.py"), "--config", filepath.Join(root, "etc/circuitpathways-pi.conf"), "--mock", "--server", "http://127.0.0.1:1")
		done := make(chan error, 1)
		if err := c.Start(); err != nil {
			t.Fatal(err)
		}
		go func() { done <- c.Wait() }()
		select {
		case err := <-done:
			t.Fatalf("the app should keep running (retrying) with the installed config, but exited: %v", err)
		case <-timeAfterMillis(1500):
			c.Process.Kill()
		}
	}
}

func TestGenericInstallerTakesTheKeyAsAnArgument(t *testing.T) {
	script, err := Installer("https://school.example.org", "", app(t))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(script, `KEY="${1:-${CP_KEY:-}}"`) {
		t.Error("the generic installer should read the key from its first argument")
	}
	dir := t.TempDir()
	file := filepath.Join(dir, "install.sh")
	os.WriteFile(file, []byte(script), 0o755)
	cmd := exec.Command("bash", file) // no key
	cmd.Env = append(os.Environ(), "CP_PREFIX="+filepath.Join(dir, "root"))
	out, err := cmd.CombinedOutput()
	if err == nil || !strings.Contains(string(out), "needs its key") {
		t.Errorf("without a key it should explain: %v\n%s", err, out)
	}
}

func timeAfterMillis(ms int) <-chan time.Time {
	return time.After(time.Duration(ms) * time.Millisecond)
}
