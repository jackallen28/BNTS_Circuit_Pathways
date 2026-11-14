package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// self-update keeps Circuit Pathways up to date. It runs as a service each time a Pi starts up (before Circuit
// Pathways itself), and never stops the Pi starting: if there's nothing to update from, it says so and finishes.
//
//   - a student Pi updates from the school server (over https, trusting only its certificate), so every student Pi
//     runs the same version as the school server, and its Pi Link app is refreshed too;
//   - the school server updates from the newest GitHub release (the Release workflow publishes the program and its
//     SHA256SUMS). The repository is private, so it needs a read-only token in /etc/circuitpathways/update-token.
//
// A new program is only put in place when its SHA-256 matches, and it replaces the old one in one step.

type updateOptions struct {
	from, school, schoolCA, repo, tokenFile, target, piApp, piServer, api string
	timeout                                                               time.Duration
}

func updateCommand(args []string) error {
	fs := flag.NewFlagSet("self-update", flag.ContinueOnError)
	o := updateOptions{}
	fs.StringVar(&o.from, "from", "school", "school (a student Pi: from the school server) or github (the school server: from the newest release)")
	fs.StringVar(&o.school, "school", "", "the school server's address (from school)")
	fs.StringVar(&o.schoolCA, "school-ca", "/etc/circuitpathways/school-ca.crt", "the school server's certificate authority (from school)")
	fs.StringVar(&o.repo, "repo", "jackallen28/BNTS_Circuit_Pathways", "the GitHub repository (from github)")
	fs.StringVar(&o.tokenFile, "token-file", "/etc/circuitpathways/update-token", "a read-only GitHub token, for a private repository (from github)")
	fs.StringVar(&o.target, "target", "", "the program to replace (default: this one)")
	fs.StringVar(&o.piApp, "pi-app", "", "a student Pi: also refresh the Pi Link app at this path")
	fs.StringVar(&o.piServer, "pi-server", "http://localhost:8080", "the address written into the Pi Link app")
	fs.DurationVar(&o.timeout, "timeout", 3*time.Minute, "give up after this long")
	fs.StringVar(&o.api, "github-api", "https://api.github.com", "GitHub's API (tests use a pretend one)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if o.target == "" {
		exe, err := os.Executable()
		if err != nil {
			return err
		}
		if o.target, err = filepath.EvalSymlinks(exe); err != nil {
			return err
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), o.timeout)
	defer cancel()
	changed, err := selfUpdate(ctx, o)
	if err != nil {
		// never stop the Pi starting: say why, and carry on with the version it has
		fmt.Fprintln(os.Stderr, "Not updated:", err)
		return nil
	}
	if !changed {
		fmt.Println("Circuit Pathways is up to date.")
	}
	if o.piApp != "" {
		if err := refreshPiApp(o.target, o.piApp, o.piServer); err != nil {
			fmt.Fprintln(os.Stderr, "Pi Link app not refreshed:", err)
		}
	}
	return nil
}

func fileSHA(path string) string {
	f, err := os.Open(path)
	if err != nil {
		return ""
	}
	defer f.Close()
	h := sha256.New()
	io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil))
}

// selfUpdate returns true if it put a new program in place.
func selfUpdate(ctx context.Context, o updateOptions) (bool, error) {
	have := fileSHA(o.target)
	var want, url string
	var client *http.Client
	var header http.Header
	switch o.from {
	case "school":
		if o.school == "" {
			return false, errors.New("no school server given (-school)")
		}
		tr := http.DefaultTransport.(*http.Transport).Clone()
		tr.Proxy = nil
		if pem, err := os.ReadFile(o.schoolCA); err == nil {
			pool := x509.NewCertPool()
			pool.AppendCertsFromPEM(pem)
			tr.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
		}
		client = &http.Client{Transport: tr, Timeout: 2 * time.Minute}
		base := strings.TrimRight(o.school, "/")
		var v struct {
			SHA256 string `json:"sha256"`
			Arch   string `json:"arch"`
		}
		// just after the Pi starts, its WiFi may take a little while: try for up to a minute
		var err error
		for wait := time.Now().Add(time.Minute); ; {
			if err = getJSON(ctx, client, base+"/install/version", nil, &v); err == nil || time.Now().After(wait) || ctx.Err() != nil {
				break
			}
			time.Sleep(5 * time.Second)
		}
		if err != nil {
			return false, fmt.Errorf("the school server can't be reached (%v)", err)
		}
		if v.Arch != runtime.GOARCH {
			return false, fmt.Errorf("the school server has the %s version, and this Pi needs %s", v.Arch, runtime.GOARCH)
		}
		want, url = v.SHA256, base+"/install/circuitpathways-linux-"+runtime.GOARCH
	case "github":
		client = &http.Client{Timeout: 2 * time.Minute}
		header = http.Header{"Accept": {"application/vnd.github+json"}, "X-GitHub-Api-Version": {"2022-11-28"}}
		if b, err := os.ReadFile(o.tokenFile); err == nil && strings.TrimSpace(string(b)) != "" {
			header.Set("Authorization", "Bearer "+strings.TrimSpace(string(b)))
		}
		var rel struct {
			Tag    string `json:"tag_name"`
			Assets []struct {
				Name string `json:"name"`
				URL  string `json:"url"`
			} `json:"assets"`
		}
		if err := getJSON(ctx, client, strings.TrimRight(o.api, "/")+"/repos/"+o.repo+"/releases/latest", header, &rel); err != nil {
			return false, fmt.Errorf("the newest release couldn't be read (%v). A private repository needs a read-only token in %s", err, o.tokenFile)
		}
		asset := func(name string) string {
			for _, a := range rel.Assets {
				if a.Name == name {
					return a.URL
				}
			}
			return ""
		}
		sums, bin := asset("SHA256SUMS"), asset("circuitpathways-linux-"+runtime.GOARCH)
		if sums == "" || bin == "" {
			return false, fmt.Errorf("release %s doesn't have the program for %s", rel.Tag, runtime.GOARCH)
		}
		dl := header.Clone()
		dl.Set("Accept", "application/octet-stream")
		body, err := get(ctx, client, sums, dl, 1<<16)
		if err != nil {
			return false, err
		}
		sc := bufio.NewScanner(strings.NewReader(string(body)))
		for sc.Scan() {
			f := strings.Fields(sc.Text())
			if len(f) == 2 && strings.TrimPrefix(f[1], "*") == "circuitpathways-linux-"+runtime.GOARCH {
				want = f[0]
			}
		}
		url, header = bin, dl
	default:
		return false, errors.New("-from must be school or github")
	}
	if len(want) != 64 {
		return false, errors.New("the new version's checksum is missing")
	}
	if want == have {
		return false, nil
	}
	data, err := get(ctx, client, url, header, 200<<20)
	if err != nil {
		return false, err
	}
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != want {
		return false, errors.New("the download didn't match its checksum, so it wasn't used")
	}
	tmp := o.target + ".new"
	if err := os.WriteFile(tmp, data, 0o755); err != nil {
		return false, err
	}
	if err := os.Rename(tmp, o.target); err != nil {
		os.Remove(tmp)
		return false, err
	}
	fmt.Println("Circuit Pathways has been updated.")
	return true, nil
}

func get(ctx context.Context, c *http.Client, url string, h http.Header, max int64) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	for k, v := range h {
		req.Header[k] = v
	}
	res, err := c.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s gave %s", url, res.Status)
	}
	b, err := io.ReadAll(io.LimitReader(res.Body, max+1))
	if int64(len(b)) > max {
		return nil, errors.New("the download is too big")
	}
	return b, err
}

func getJSON(ctx context.Context, c *http.Client, url string, h http.Header, v any) error {
	b, err := get(ctx, c, url, h, 4<<20)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

// refreshPiApp writes the Pi Link app from the (new) program, and restarts Pi Link if it changed.
func refreshPiApp(program, path, server string) error {
	out, err := exec.Command(program, "pi-app", "-server", server).Output()
	if err != nil {
		return err
	}
	old, _ := os.ReadFile(path)
	if string(old) == string(out) {
		return nil
	}
	if err := os.WriteFile(path+".new", out, 0o644); err != nil {
		return err
	}
	if err := os.Rename(path+".new", path); err != nil {
		return err
	}
	fmt.Println("Pi Link has been updated.")
	exec.Command("systemctl", "try-restart", "circuitpathways-pi").Run()
	return nil
}
