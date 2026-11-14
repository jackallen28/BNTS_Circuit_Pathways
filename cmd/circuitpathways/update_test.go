package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func sumOf(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }

func TestAStudentPiUpdatesFromTheSchoolServer(t *testing.T) {
	newProg := []byte("#!/bin/sh\necho new version\n")
	served := newProg
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/install/version":
			json.NewEncoder(w).Encode(map[string]string{"sha256": sumOf(newProg), "arch": runtime.GOARCH})
		case "/install/circuitpathways-linux-" + runtime.GOARCH:
			w.Write(served)
		default:
			http.NotFound(w, r)
		}
	}))
	defer ts.Close()
	ca := filepath.Join(t.TempDir(), "ca.crt")
	os.WriteFile(ca, certPEM(ts), 0o644)
	target := filepath.Join(t.TempDir(), "circuitpathways")
	os.WriteFile(target, []byte("old version"), 0o755)
	o := updateOptions{from: "school", school: ts.URL, schoolCA: ca, target: target}

	// a download that doesn't match its checksum is never used
	served = []byte("tampered")
	if changed, err := selfUpdate(context.Background(), o); changed || err == nil {
		t.Fatal("used a download that didn't match")
	}
	if b, _ := os.ReadFile(target); string(b) != "old version" {
		t.Fatal("the program was changed by a bad download")
	}
	served = newProg
	if changed, err := selfUpdate(context.Background(), o); !changed || err != nil {
		t.Fatalf("update: %v %v", changed, err)
	}
	if b, _ := os.ReadFile(target); string(b) != string(newProg) {
		t.Fatal("not updated")
	}
	if changed, _ := selfUpdate(context.Background(), o); changed {
		t.Fatal("updated again although it was up to date")
	}
	// no school server: no update, and no error that would stop the Pi starting
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	o.school = "https://127.0.0.1:1"
	if changed, err := selfUpdate(ctx, o); changed || err == nil {
		t.Fatal("no school server should mean no update, with a reason")
	}
	if err := updateCommand([]string{"-from", "school", "-school", "https://127.0.0.1:1", "-target", target, "-timeout", "1s"}); err != nil {
		t.Fatal("the command must not fail (it would stop the Pi starting)")
	}
}

func TestTheSchoolServerUpdatesFromTheNewestRelease(t *testing.T) {
	newProg := []byte("new school server")
	name := "circuitpathways-linux-" + runtime.GOARCH
	var gotAuth string
	var ts *httptest.Server
	ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		switch r.URL.Path {
		case "/repos/school/cp/releases/latest":
			json.NewEncoder(w).Encode(map[string]any{"tag_name": "v2.1.0", "assets": []map[string]string{
				{"name": "SHA256SUMS", "url": ts.URL + "/assets/1"}, {"name": name, "url": ts.URL + "/assets/2"},
			}})
		case "/assets/1":
			fmt.Fprintf(w, "%s  %s\n%s  circuitpathways-linux-other\n", sumOf(newProg), name, sumOf([]byte("x")))
		case "/assets/2":
			if r.Header.Get("Accept") != "application/octet-stream" {
				http.Error(w, "want the file", 400)
				return
			}
			w.Write(newProg)
		default:
			http.NotFound(w, r)
		}
	}))
	defer ts.Close()
	dir := t.TempDir()
	token := filepath.Join(dir, "update-token")
	os.WriteFile(token, []byte("github_pat_readonly\n"), 0o600)
	target := filepath.Join(dir, "circuitpathways")
	os.WriteFile(target, []byte("old"), 0o755)
	changed, err := selfUpdate(context.Background(), updateOptions{from: "github", repo: "school/cp", api: ts.URL, tokenFile: token, target: target})
	if !changed || err != nil {
		t.Fatalf("update: %v %v", changed, err)
	}
	if b, _ := os.ReadFile(target); string(b) != string(newProg) || gotAuth != "Bearer github_pat_readonly" {
		t.Fatalf("not updated (or the token wasn't sent): %q %q", b, gotAuth)
	}
}

func certPEM(ts *httptest.Server) []byte {
	return pemEncode(ts.Certificate().Raw)
}
