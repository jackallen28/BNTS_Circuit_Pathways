package server

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"
)

type caller struct {
	t *testing.T
	s http.Handler
}

func (c caller) do(method, path, token string, body any) (int, map[string]any) {
	c.t.Helper()
	var rd *bytes.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	} else {
		rd = bytes.NewReader(nil)
	}
	r := httptest.NewRequest(method, path, rd)
	if method != http.MethodGet {
		r.Header.Set(headerName, "1")
		r.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	c.s.ServeHTTP(w, r)
	var m map[string]any
	json.Unmarshal(w.Body.Bytes(), &m)
	return w.Code, m
}

func (c caller) teacher(code string) string {
	c.t.Helper()
	st, m := c.do("POST", "/api/teacher/signin", "", map[string]string{"code": code})
	if st != 200 {
		c.t.Fatalf("sign in: %d %v", st, m)
	}
	return m["token"].(string)
}

func names(list []any) [][]string {
	var out [][]string
	for _, s := range list {
		var n []string
		for _, x := range s.(map[string]any)["names"].([]any) {
			n = append(n, x.(string))
		}
		out = append(out, n)
	}
	return out
}

// The same story as the first (Cloudflare) version's test: a teacher makes a class, students join with first
// names and a school, work is saved, newer work wins, and deleting removes everything.
func TestAClassFromStartToFinish(t *testing.T) {
	s, _ := newTest(t)
	c := caller{t, s}
	if st, _ := c.do("POST", "/api/teacher/signin", "", map[string]string{"code": "wrong-code-xx"}); st != 401 {
		t.Fatalf("a wrong teacher code: %d", st)
	}
	t1, t2 := c.teacher("teacher-code-1234"), c.teacher("teacher-code-5678")

	st, made := c.do("POST", "/api/teacher/class", t1, map[string]any{"name": "7B Thursday", "school": "Eltham High", "days": 30})
	if st != 200 {
		t.Fatalf("make a class: %d %v", st, made)
	}
	code := made["code"].(string)
	if len(code) != 11 || code[5] != '-' {
		t.Fatalf("class code %q", code)
	}
	for _, bad := range []map[string]any{{"name": "Mia's class <b>", "days": 3}, {"name": "x", "days": 999}, {"name": "x", "days": 0}} {
		if st, _ := c.do("POST", "/api/teacher/class", t1, bad); st != 400 {
			t.Errorf("%v: %d", bad, st)
		}
	}
	if st, _ := c.do("POST", "/api/teacher/class", "", map[string]any{"days": 3}); st != 401 {
		t.Fatalf("a class with no sign-in: %d", st)
	}

	// only the teacher who made it sees it
	_, l1 := c.do("GET", "/api/teacher/classes", t1, nil)
	_, l2 := c.do("GET", "/api/teacher/classes", t2, nil)
	if len(l1["classes"].([]any)) != 1 || len(l2["classes"].([]any)) != 0 {
		t.Fatalf("classes: %v %v", l1, l2)
	}
	if st, _ := c.do("GET", "/api/teacher/class/"+code, t2, nil); st != 404 {
		t.Fatalf("another teacher's class: %d", st)
	}

	// joining: the code alone says the class is real; then first names + school
	if st, _ := c.do("POST", "/api/class/join", "", map[string]any{"code": "ZZZZZ-ZZZZZ"}); st != 404 {
		t.Fatalf("a made-up code: %d", st)
	}
	_, peek := c.do("POST", "/api/class/join", "", map[string]any{"code": strings.ToLower(code)})
	if peek["needs_names"] != true || peek["class"].(map[string]any)["school"] != "Eltham High" {
		t.Fatalf("peek: %v", peek)
	}
	if st, _ := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"Mia Smith-Jones!"}}); st != 400 {
		t.Fatalf("a name with ! in it: %d", st)
	}
	st, mia := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"mia"}})
	if st != 200 || !reflect.DeepEqual(mia["student"], map[string]any{"names": []any{"Mia"}, "school": "Eltham High"}) {
		t.Fatalf("Mia joins: %d %v", st, mia)
	}
	_, noor := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"Noor", "Sam"}, "school": "Diamond Valley College"})
	miaTok, noorTok := mia["token"].(string), noor["token"].(string)

	// work is saved, and newer work is never replaced by older
	push := func(tok string, items ...map[string]any) int {
		st, _ := c.do("POST", "/api/student/work", tok, map[string]any{"items": items})
		return st
	}
	if st := push(miaTok, map[string]any{"app": "arduinopath", "item": "blink", "kind": "sketch", "body": "void setup(){}", "updated_at": 2000}); st != 200 {
		t.Fatalf("save work: %d", st)
	}
	push(miaTok, map[string]any{"app": "arduinopath", "item": "blink", "kind": "sketch", "body": "OLD", "updated_at": 1000})
	push(miaTok, map[string]any{"app": "pipath", "item": "s1_hello", "kind": "progress", "body": `{"step":2}`, "updated_at": 3000})
	_, mine := c.do("GET", "/api/student/work", miaTok, nil)
	work := mine["work"].([]any)
	if len(work) != 2 || work[0].(map[string]any)["body"] != "void setup(){}" {
		t.Fatalf("Mia's work: %v", work)
	}
	for _, bad := range []map[string]any{
		{"app": "evil", "item": "x", "kind": "sketch", "body": ""},
		{"app": "pipath", "item": "../x", "kind": "sketch", "body": ""},
		{"app": "pipath", "item": "x", "kind": "photo", "body": ""},
		{"app": "pipath", "item": "x", "kind": "sketch", "body": strings.Repeat("x", 101*1024)},
	} {
		if st := push(miaTok, bad); st != 400 && st != 413 {
			t.Errorf("%v: %d", bad["item"], st)
		}
	}
	if st := push("s2.nonsense", map[string]any{"app": "pipath", "item": "x", "kind": "sketch", "body": ""}); st != 401 {
		t.Fatalf("a made-up student token: %d", st)
	}

	// the teacher sees first names, school and work; nothing else is kept about a student
	_, roster := c.do("GET", "/api/teacher/class/"+code, t1, nil)
	students := roster["students"].([]any)
	if got := names(students); !reflect.DeepEqual(got, [][]string{{"Mia"}, {"Noor", "Sam"}}) {
		t.Fatalf("roster: %v", got)
	}
	var keys []string
	for k := range students[0].(map[string]any) {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	if strings.Join(keys, ",") != "id,items,joined_at,last_work,names,school,seen_at" {
		t.Fatalf("what is kept about a student: %v", keys)
	}
	_, all := c.do("GET", "/api/teacher/class/"+code+"/work", t1, nil)
	if n := len(all["students"].([]any)[0].(map[string]any)["work"].([]any)); n != 2 {
		t.Fatalf("Mia's work as the teacher sees it: %d pieces", n)
	}

	// a student can take themselves off; the teacher can remove a student
	if st, _ := c.do("DELETE", "/api/student/me", noorTok, nil); st != 204 {
		t.Fatalf("take my name off: %d", st)
	}
	if st, _ := c.do("GET", "/api/student/me", noorTok, nil); st != 401 {
		t.Fatalf("after taking their name off: %d", st)
	}

	// deleting the class removes everything, and the student's token stops working
	if st, _ := c.do("DELETE", "/api/teacher/class/"+code, t1, nil); st != 204 {
		t.Fatalf("delete the class: %d", st)
	}
	if st, _ := c.do("GET", "/api/student/work", miaTok, nil); st != 401 {
		t.Fatalf("work after the class was deleted: %d", st)
	}
	if st, _ := c.do("POST", "/api/class/join", "", map[string]any{"code": code}); st != 404 {
		t.Fatalf("joining a deleted class: %d", st)
	}
	totals, _ := s.Store.Totals(t.Context())
	if totals.Students != 0 || totals.Work != 0 {
		t.Fatalf("left behind: %+v", totals)
	}
}

func TestTeachersSetWorkAndStudentsSeeIt(t *testing.T) {
	s, _ := newTest(t)
	c := caller{t, s}
	tok := c.teacher("teacher-code-1234")
	_, made := c.do("POST", "/api/teacher/class", tok, map[string]any{"name": "8C Robotics"})
	code := made["code"].(string)
	_, joined := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"Ava"}})
	stu := joined["token"].(string)

	tasks := []map[string]any{
		{"app": "arduinopath", "item": "blink-traffic-lights", "note": "Steps 1 to 3 by Friday"},
		{"app": "pipath", "item": "s1_hello"},
		{"app": "arduinopath", "item": "freeplay", "note": "Your own idea"},
	}
	if st, m := c.do("PUT", "/api/teacher/class/"+code+"/tasks", tok, map[string]any{"tasks": tasks}); st != 200 || len(m["tasks"].([]any)) != 3 {
		t.Fatalf("set work: %d %v", st, m)
	}
	for _, bad := range []map[string]any{{"app": "arduinopath", "item": "not-a-project"}, {"app": "evil", "item": "x"}, {"app": "pipath", "item": "s1_hello", "note": "<script>"}} {
		if st, _ := c.do("PUT", "/api/teacher/class/"+code+"/tasks", tok, map[string]any{"tasks": []any{bad}}); st != 400 {
			t.Errorf("%v: %d", bad, st)
		}
	}
	_, me := c.do("GET", "/api/student/me", stu, nil)
	got := me["tasks"].([]any)
	if len(got) != 3 || got[0].(map[string]any)["note"] != "Steps 1 to 3 by Friday" || got[2].(map[string]any)["item"] != "freeplay" {
		t.Fatalf("the student sees: %v", got)
	}
	_, roster := c.do("GET", "/api/teacher/class/"+code, tok, nil)
	if len(roster["tasks"].([]any)) != 3 {
		t.Fatalf("the teacher sees: %v", roster["tasks"])
	}
	// reordering keeps when each was first set; taking one off removes it
	first := got[0].(map[string]any)["set_at"]
	c.do("PUT", "/api/teacher/class/"+code+"/tasks", tok, map[string]any{"tasks": []any{tasks[1], tasks[0]}})
	_, me = c.do("GET", "/api/student/me", stu, nil)
	got = me["tasks"].([]any)
	if len(got) != 2 || got[0].(map[string]any)["item"] != "s1_hello" || got[1].(map[string]any)["set_at"] != first {
		t.Fatalf("after reordering: %v", got)
	}
	// another teacher can't change it
	other := c.teacher("teacher-code-5678")
	if st, _ := c.do("PUT", "/api/teacher/class/"+code+"/tasks", other, map[string]any{"tasks": []any{}}); st != 404 {
		t.Fatalf("another teacher: %d", st)
	}
}

func TestAClassThatHasEndedIsGoneAndCleanedUp(t *testing.T) {
	s, _ := newTest(t)
	now := time.Now()
	s.Now = func() time.Time { return now }
	c := caller{t, s}
	tok := c.teacher("teacher-code-1234")
	_, made := c.do("POST", "/api/teacher/class", tok, map[string]any{"name": "Short", "ends_at": now.Add(time.Hour).UnixMilli()})
	code := made["code"].(string)
	_, joined := c.do("POST", "/api/class/join", "", map[string]any{"code": code, "names": []string{"Ava"}})
	stu := joined["token"].(string)
	c.do("POST", "/api/student/work", stu, map[string]any{"items": []any{map[string]any{"app": "pipath", "item": "x", "kind": "sketch", "body": "print(1)"}}})

	now = now.Add(2 * time.Hour)
	if st, _ := c.do("GET", "/api/student/work", stu, nil); st != 401 {
		t.Fatalf("an ended class still works: %d", st)
	}
	if st, _ := c.do("POST", "/api/compile", stu, map[string]string{"code": "x", "board": "uno"}); st != 401 {
		t.Fatalf("an ended class's token still compiles: %d", st)
	}
	n, err := s.Store.CleanUp(t.Context(), now)
	if err != nil || n != 1 {
		t.Fatalf("clean-up: %d %v", n, err)
	}
	totals, _ := s.Store.Totals(t.Context())
	if totals.Classes+totals.Students+totals.Work != 0 {
		t.Fatalf("left behind: %+v", totals)
	}
}

func TestATeacherCodeAddedToTheFileWorksAtOnce(t *testing.T) {
	s, _ := newTest(t)
	c := caller{t, s}
	if st, _ := c.do("POST", "/api/teacher/signin", "", map[string]string{"code": "teacher-code-1234 "}); st != 200 {
		t.Fatalf("a code with a space after it: %d", st)
	}
	if fmt.Sprint(s.Teachers.Len()) != "2" {
		t.Fatalf("codes: %d", s.Teachers.Len())
	}
}
