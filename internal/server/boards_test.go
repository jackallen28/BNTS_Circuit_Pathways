package server

import (
	"strings"
	"testing"
)

// A teacher sets up the school's ESP boards; a student claims one with its sticker code and gets its own WiFi;
// nobody else can claim it, and it is free again when the student leaves.
func TestTheSchoolsESPBoards(t *testing.T) {
	s, _ := newTest(t)
	c := caller{t, s}
	t1, t2 := c.teacher("teacher-code-1234"), c.teacher("teacher-code-5678")

	st, b := c.do("POST", "/api/teacher/boards", t1, map[string]string{"label": "ESP-07", "kind": "nodemcu"})
	if st != 200 {
		t.Fatalf("set up a board: %d %v", st, b)
	}
	ssid, pass, code, id := b["ssid"].(string), b["password"].(string), b["code"].(string), b["id"].(string)
	if !strings.HasPrefix(ssid, "CP-ESP07-") || len(pass) != 10 || len(code) != 9 || code[4] != '-' {
		t.Fatalf("the board's WiFi and code: %v", b)
	}
	_, b2 := c.do("POST", "/api/teacher/boards", t1, map[string]string{"label": "ESP-08", "kind": "esp32"})
	if b2["ssid"] == ssid || b2["password"] == pass || b2["code"] == code {
		t.Fatal("two boards share a WiFi name, password or code")
	}
	for _, bad := range []map[string]string{{"label": "ESP-07", "kind": "nodemcu"}, {"label": "x", "kind": "uno"}, {"label": "<b>", "kind": "esp32"}} {
		if st, _ := c.do("POST", "/api/teacher/boards", t1, bad); st == 200 {
			t.Errorf("%v was allowed", bad)
		}
	}
	// the sketch the teacher portal flashes, and the chip it records
	_, sk := c.do("GET", "/api/teacher/boards/"+id+"/sketch", t1, nil)
	if !strings.Contains(sk["code"].(string), `"`+ssid+`"`) || !strings.Contains(sk["code"].(string), `"`+pass+`"`) {
		t.Fatal("the set-up sketch doesn't have the board's WiFi")
	}
	if st, _ := c.do("POST", "/api/teacher/boards/"+id+"/flashed", t1, map[string]string{"mac": "nonsense"}); st != 400 {
		t.Fatalf("a made-up MAC: %d", st)
	}
	if st, _ := c.do("POST", "/api/teacher/boards/"+id+"/flashed", t1, map[string]string{"mac": "A4:CF:12:0B:9E:01"}); st != 200 {
		t.Fatalf("record the chip: %d", st)
	}
	// another teacher can't see or touch it
	_, other := c.do("GET", "/api/teacher/boards", t2, nil)
	if len(other["boards"].([]any)) != 0 {
		t.Fatal("another teacher sees the boards")
	}
	if st, _ := c.do("GET", "/api/teacher/boards/"+id+"/sketch", t2, nil); st != 404 {
		t.Fatalf("another teacher gets the WiFi password: %d", st)
	}

	// students: in the teacher's class
	_, cls := c.do("POST", "/api/teacher/class", t1, map[string]any{"name": "8C"})
	_, mia := c.do("POST", "/api/class/join", "", map[string]any{"code": cls["code"], "names": []string{"Mia"}})
	_, sam := c.do("POST", "/api/class/join", "", map[string]any{"code": cls["code"], "names": []string{"Sam"}})
	miaTok, samTok := mia["token"].(string), sam["token"].(string)
	if _, m := c.do("GET", "/api/student/board", miaTok, nil); m["board"] != nil {
		t.Fatal("a board before claiming one")
	}
	if st, _ := c.do("POST", "/api/student/board", miaTok, map[string]string{"code": "ZZZZ-ZZZZ"}); st != 404 {
		t.Fatalf("a made-up code: %d", st)
	}
	st, got := c.do("POST", "/api/student/board", miaTok, map[string]string{"code": strings.ToLower(code)})
	if st != 200 {
		t.Fatalf("claim: %d %v", st, got)
	}
	mb := got["board"].(map[string]any)
	if mb["ssid"] != ssid || mb["password"] != pass || mb["mac"] != "a4:cf:12:0b:9e:01" || mb["label"] != "ESP-07" {
		t.Fatalf("Mia's board: %v", mb)
	}
	if st, _ := c.do("POST", "/api/student/board", samTok, map[string]string{"code": code}); st != 409 {
		t.Fatalf("Sam took Mia's board: %d", st)
	}
	// the teacher sees who has it
	_, list := c.do("GET", "/api/teacher/boards", t1, nil)
	if list["boards"].([]any)[0].(map[string]any)["student"] != "Mia" {
		t.Fatalf("who has it: %v", list["boards"])
	}
	// a student in another teacher's class can't claim it
	_, cls2 := c.do("POST", "/api/teacher/class", t2, map[string]any{"name": "Other"})
	_, ari := c.do("POST", "/api/class/join", "", map[string]any{"code": cls2["code"], "names": []string{"Ari"}})
	if st, _ := c.do("POST", "/api/student/board", ari["token"].(string), map[string]string{"code": b2["code"].(string)}); st != 404 {
		t.Fatalf("a board from another teacher: %d", st)
	}
	// claiming another gives the first back
	c.do("POST", "/api/student/board", miaTok, map[string]string{"code": b2["code"].(string)})
	if st, _ := c.do("POST", "/api/student/board", samTok, map[string]string{"code": code}); st != 200 {
		t.Fatalf("Sam couldn't claim the board Mia gave back: %d", st)
	}
	// when Sam leaves the class, his board is free again
	c.do("DELETE", "/api/student/me", samTok, nil)
	_, list = c.do("GET", "/api/teacher/boards", t1, nil)
	for _, x := range list["boards"].([]any) {
		if bb := x.(map[string]any); bb["id"] == id && bb["student"] != nil {
			t.Fatalf("a board still held by a student who left: %v", bb)
		}
	}
	// the teacher can free a board, and delete one
	if st, _ := c.do("POST", "/api/teacher/boards/"+b2["id"].(string)+"/release", t1, nil); st != 204 {
		t.Fatalf("free it: %d", st)
	}
	if _, m := c.do("GET", "/api/student/board", miaTok, nil); m["board"] != nil {
		t.Fatal("Mia still has a board the teacher freed")
	}
	if st, _ := c.do("DELETE", "/api/teacher/boards/"+id, t1, nil); st != 204 {
		t.Fatalf("delete: %d", st)
	}
}
