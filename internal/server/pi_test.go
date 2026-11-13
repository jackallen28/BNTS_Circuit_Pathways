package server

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"circuitpathways/internal/pilink"
)

// sseReader reads "data:" lines from a streaming response.
type sseReader struct {
	resp *http.Response
	ch   chan string
}

func openSSE(t *testing.T, ctx context.Context, url string, hdr map[string]string) *sseReader {
	t.Helper()
	req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	r := &sseReader{resp: resp, ch: make(chan string, 64)}
	go func() {
		defer close(r.ch)
		sc := bufio.NewScanner(resp.Body)
		for sc.Scan() {
			if d, ok := strings.CutPrefix(sc.Text(), "data: "); ok {
				r.ch <- d
			}
		}
	}()
	return r
}

func (r *sseReader) next(t *testing.T) string {
	t.Helper()
	select {
	case d, ok := <-r.ch:
		if !ok {
			t.Fatal("the stream ended")
		}
		return d
	case <-time.After(3 * time.Second):
		t.Fatal("nothing arrived")
		return ""
	}
}

func jsonPost(t *testing.T, url string, body any, hdr map[string]string) *http.Response {
	t.Helper()
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST", url, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set(headerName, "1")
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func TestPiOverTheRelay(t *testing.T) {
	s, _ := newTest(t)
	ts := httptest.NewServer(s)
	defer ts.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	class, _, _ := s.Signer.NewClass(time.Now(), 2)

	// a made-up key is turned away; a real one opens the Pi's command stream
	if resp, _ := http.Get(ts.URL + "/api/pi/pi/events"); resp.StatusCode != 403 {
		t.Fatalf("no key: %d", resp.StatusCode)
	}
	id, key, _ := s.PiKeys.New()
	reg := struct{ Code string }{Code: pilink.DisplayID(id)}
	piAuth := map[string]string{piKeyHeader: key}
	bogus := map[string]string{piKeyHeader: "CPK1-K7M2QX9P-AAAAAAAAAA"}
	if r := jsonPost(t, ts.URL+"/api/pi/pi/send", map[string]any{"event": map[string]any{"type": "hello", "data": map[string]string{}}}, bogus); r.StatusCode != 403 {
		t.Fatalf("a made-up key: %d", r.StatusCode)
	}
	pi := openSSE(t, ctx, ts.URL+"/api/pi/pi/events", piAuth)
	if pi.resp.StatusCode != 200 {
		t.Fatalf("Pi stream: %d", pi.resp.StatusCode)
	}
	// the Pi says hello
	if r := jsonPost(t, ts.URL+"/api/pi/pi/send", map[string]any{"event": map[string]any{"type": "hello", "data": map[string]string{"model": "Pi 4", "name": "Pi 4"}}}, piAuth); r.StatusCode != 204 {
		t.Fatalf("send: %d", r.StatusCode)
	}

	// a browser without a class code is turned away; the wrong code isn't found
	if r, _ := http.Get(ts.URL + "/api/pi/events?code=" + reg.Code); r.StatusCode != 401 {
		t.Fatalf("no class code: %d", r.StatusCode)
	}
	if r, _ := http.NewRequest("GET", ts.URL+"/api/pi/events?code=ZZZZ-ZZZZ", nil); r != nil {
		r.Header.Set(accessHeader, class)
		if resp, _ := http.DefaultClient.Do(r); resp.StatusCode != 404 {
			t.Fatalf("wrong pairing code: %d", resp.StatusCode)
		}
	}

	browser := openSSE(t, ctx, ts.URL+"/api/pi/events?code="+strings.ToLower(reg.Code), map[string]string{accessHeader: class})
	if got := browser.next(t); !strings.Contains(got, `"connected"`) || !strings.Contains(got, `"name":"Pi 4"`) {
		t.Fatalf("first event: %s", got)
	}
	if got := browser.next(t); !strings.Contains(got, `"hello"`) {
		t.Fatalf("second event: %s", got)
	}

	// browser -> Pi
	cmd := map[string]any{"code": reg.Code, "cmd": map[string]any{"op": "write", "pin": 17, "value": 1}}
	if r := jsonPost(t, ts.URL+"/api/pi/command", cmd, nil); r.StatusCode != 401 {
		t.Fatalf("command without class: %d", r.StatusCode)
	}
	if r := jsonPost(t, ts.URL+"/api/pi/command", cmd, map[string]string{accessHeader: class}); r.StatusCode != 204 {
		t.Fatalf("command: %d", r.StatusCode)
	}
	if got := pi.next(t); got != `{"op":"write","pin":17,"value":1}` {
		t.Fatalf("the Pi got %s", got)
	}
	bad := map[string]any{"code": reg.Code, "cmd": map[string]any{"op": "write", "pin": 40, "value": 1}}
	if r := jsonPost(t, ts.URL+"/api/pi/command", bad, map[string]string{accessHeader: class}); r.StatusCode != 400 {
		t.Fatalf("a bad pin: %d", r.StatusCode)
	}

	// Pi -> browser, and only with the Pi's own secret
	state := map[string]any{"event": map[string]any{"type": "state", "data": map[string]any{"pins": map[string]any{"17": map[string]any{"mode": "out", "value": 1}}}}}
	if r := jsonPost(t, ts.URL+"/api/pi/pi/send", state, bogus); r.StatusCode != 403 {
		t.Fatalf("wrong key: %d", r.StatusCode)
	}
	jsonPost(t, ts.URL+"/api/pi/pi/send", state, piAuth)
	if got := browser.next(t); !strings.Contains(got, `"state"`) || !strings.Contains(got, `"17"`) {
		t.Fatalf("the browser got %s", got)
	}

	// the Pi drops: the browser is told
	pi.resp.Body.Close()
	if got := browser.next(t); !strings.Contains(got, "pi-offline") {
		t.Fatalf("after the Pi dropped: %s", got)
	}
}

func TestRevokedPiKeyIsRefused(t *testing.T) {
	s, _ := newTest(t)
	id, key, _ := s.PiKeys.New()
	revoked, _ := pilink.NewKeys("test-pi-secret-0123456789", []string{id})
	s.PiKeys = revoked
	w := post(s, "/api/pi/pi/send", map[string]any{"event": map[string]any{"type": "hello", "data": map[string]string{}}}, map[string]string{piKeyHeader: key})
	if w.Code != 403 {
		t.Fatalf("a revoked key got %d", w.Code)
	}
}

func TestPiLinkIsOffWithoutKeys(t *testing.T) {
	s, _ := newTest(t)
	s.PiKeys = nil
	if w := post(s, "/api/pi/pi/send", map[string]any{"event": map[string]any{}}, nil); w.Code != 503 {
		t.Fatalf("got %d", w.Code)
	}
}

func TestPiEndpointsNeedOurHeader(t *testing.T) {
	s, _ := newTest(t)
	r := httptest.NewRequest("POST", "/api/pi/command", strings.NewReader(`{}`))
	r.Header.Set("Content-Type", "text/plain")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatalf("got %d", w.Code)
	}
}

func TestProgramsAndOutputOverTheRelay(t *testing.T) {
	s, _ := newTest(t)
	ts := httptest.NewServer(s)
	defer ts.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	class, _, _ := s.Signer.NewClass(time.Now(), 2)
	classAuth := map[string]string{accessHeader: class}
	id, key, _ := s.PiKeys.New()
	code := pilink.DisplayID(id)
	piAuth := map[string]string{piKeyHeader: key}

	pi := openSSE(t, ctx, ts.URL+"/api/pi/pi/events", piAuth)
	jsonPost(t, ts.URL+"/api/pi/pi/send", map[string]any{"event": map[string]any{"type": "hello", "data": map[string]any{"name": "Pi", "can_run": true}}}, piAuth)
	browser := openSSE(t, ctx, ts.URL+"/api/pi/events?code="+code, classAuth)
	browser.next(t) // connected
	browser.next(t) // hello

	// a program goes to the Pi exactly as sent
	run := map[string]any{"op": "run", "rid": 3, "name": "program.py", "code": "name = input()\nprint('Hi', name)\n", "files": map[string]string{"words.txt": "aGk="}, "support": []string{"pipath_computer"}}
	if r := jsonPost(t, ts.URL+"/api/pi/command", map[string]any{"code": code, "cmd": run}, nil); r.StatusCode != 401 {
		t.Fatalf("a program without a class code: %d", r.StatusCode)
	}
	if r := jsonPost(t, ts.URL+"/api/pi/command", map[string]any{"code": code, "cmd": run}, classAuth); r.StatusCode != 204 {
		t.Fatalf("run: %d", r.StatusCode)
	}
	var got map[string]any
	if err := json.Unmarshal([]byte(pi.next(t)), &got); err != nil || got["op"] != "run" || got["rid"] != float64(3) || got["name"] != "program.py" ||
		got["code"] != "name = input()\nprint('Hi', name)\n" || got["files"].(map[string]any)["words.txt"] != "aGk=" || got["support"].([]any)[0] != "pipath_computer" {
		t.Fatalf("the Pi got %v (%v)", got, err)
	}
	jsonPost(t, ts.URL+"/api/pi/command", map[string]any{"code": code, "cmd": map[string]any{"op": "stdin", "rid": 3, "text": "Mia"}}, classAuth)
	if got := pi.next(t); got != `{"op":"stdin","rid":3,"text":"Mia"}` {
		t.Fatalf("stdin: %s", got)
	}
	jsonPost(t, ts.URL+"/api/pi/command", map[string]any{"code": code, "cmd": map[string]any{"op": "stop", "rid": 3}}, classAuth)
	if got := pi.next(t); got != `{"op":"stop","rid":3}` {
		t.Fatalf("stop: %s", got)
	}

	// the program's output and exit come back to the browser
	for _, ev := range []map[string]any{
		{"type": "run", "data": map[string]any{"rid": 3, "state": "started"}},
		{"type": "out", "data": map[string]any{"rid": 3, "stream": "out", "text": "Hi Mia\n"}},
		{"type": "exit", "data": map[string]any{"rid": 3, "rc": 0, "stopped": false, "files": map[string]any{}}},
	} {
		if r := jsonPost(t, ts.URL+"/api/pi/pi/send", map[string]any{"event": ev}, piAuth); r.StatusCode != 204 {
			t.Fatalf("send %v: %d", ev["type"], r.StatusCode)
		}
		if got := browser.next(t); !strings.Contains(got, `"type":"`+ev["type"].(string)+`"`) || !strings.Contains(got, `"rid":3`) {
			t.Fatalf("the browser got %s", got)
		}
	}

	// things a program may not contain or ask for never reach the Pi
	for name, cmd := range map[string]map[string]any{
		"a path out of the folder": {"op": "run", "rid": 4, "name": "program.py", "code": "x", "files": map[string]string{"../../etc/cron.d/x": "eA=="}},
		"a shell script":           {"op": "run", "rid": 4, "name": "program.sh", "code": "rm -rf /"},
		"an unknown helper":        {"op": "run", "rid": 4, "name": "program.py", "code": "x", "support": []string{"subprocess"}},
		"too much code":            {"op": "run", "rid": 4, "name": "program.py", "code": strings.Repeat("x", 41<<10)},
	} {
		if r := jsonPost(t, ts.URL+"/api/pi/command", map[string]any{"code": code, "cmd": cmd}, classAuth); r.StatusCode != 400 {
			t.Errorf("%s: %d", name, r.StatusCode)
		}
	}
}
