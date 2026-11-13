package arduino

import (
	"testing"
)

func TestParseDiagnostics(t *testing.T) {
	out := `C:\Users\ava\AppData\Local\ArduinoPath\arduino-x\sketches\ab\sketch\sketch.ino: In function 'void loop()':
C:\Users\ava\AppData\Local\ArduinoPath\arduino-x\sketches\ab\sketch\sketch.ino:7:3: error: expected ';' before '}' token
   }
   ^
/tmp/sketch/sketch.ino:3:10: fatal error: Servo2.h: No such file or directory
/tmp/sketch/sketch.ino:9:5: warning: unused variable 'x' [-Wunused-variable]
/tmp/sketch/sketch.ino:7:3: error: expected ';' before '}' token
(.text.startup.main+0x84): undefined reference to ` + "`setup'" + `
collect2.exe: error: ld returned 1 exit status`
	got := ParseDiagnostics(out)
	want := []Diagnostic{
		{File: "sketch.ino", Line: 7, Col: 3, Severity: "error", Message: "expected ';' before '}' token"},
		{File: "sketch.ino", Line: 3, Col: 10, Severity: "error", Message: "fatal error: Servo2.h: No such file or directory"},
		{File: "sketch.ino", Line: 9, Col: 5, Severity: "warning", Message: "unused variable 'x' [-Wunused-variable]"},
		{File: "sketch.ino", Severity: "error", Message: "undefined reference to `setup'"},
	}
	if len(got) != len(want) {
		t.Fatalf("got %+v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("%d: got %+v, want %+v", i, got[i], want[i])
		}
	}
}

func TestParseCompileJSON(t *testing.T) {
	ok := parseCompileJSON(`{"compiler_out":"Sketch uses 924 bytes","compiler_err":"","builder_result":{"executable_sections_size":[{"name":"text","size":924,"max_size":32256},{"name":"data","size":9,"max_size":2048}]},"success":true}`)
	if !ok.OK || ok.Size == nil || ok.Size.Flash != 924 || ok.Size.RAMMax != 2048 {
		t.Fatalf("ok = %+v %+v", ok, ok.Size)
	}
	bad := parseCompileJSON(`{"compiler_out":"","compiler_err":"/x/sketch.ino:2:1: error: 'foo' was not declared in this scope","success":false}`)
	if bad.OK || len(bad.Diagnostics) != 1 || bad.Diagnostics[0].Line != 2 {
		t.Fatalf("bad = %+v", bad)
	}
	text := parseCompileJSON(`{"compiler_out":"Sketch uses 265413 bytes (25%) of program storage space. Maximum is 1044464 bytes.\nGlobal variables use 28104 bytes (34%) of dynamic memory, leaving 53816 bytes for local variables. Maximum is 81920 bytes.","success":true}`)
	if text.Size == nil || text.Size.Flash != 265413 || text.Size.RAMMax != 81920 {
		t.Fatalf("size from text = %+v", text.Size)
	}
	junk := parseCompileJSON("Error: no JSON here")
	if junk.OK || junk.Output != "Error: no JSON here" {
		t.Fatalf("junk = %+v", junk)
	}
}

func TestCoachText(t *testing.T) {
	ds := []Diagnostic{
		{File: "Servo.cpp", Severity: "error", Message: "in a library"},
		{File: "sketch.ino", Line: 6, Severity: "warning", Message: "unused"},
		{File: "sketch.ino", Line: 7, Severity: "error", Message: "'digitalwrite' was not declared in this scope"},
		{File: "sketch.ino", Line: 7, Severity: "note", Message: "suggested alternative: 'digitalWrite'"},
		{File: "sketch.ino", Line: 9, Severity: "error", Message: "expected ';' before '}' token"},
	}
	want := "'digitalwrite' was not declared in this scope\nsuggested alternative: 'digitalWrite'"
	if got := CoachText(ds); got != want {
		t.Fatalf("got %q", got)
	}
	if got := CoachText(ds[:1]); got != "in a library" {
		t.Fatalf("library only: %q", got)
	}
	if CoachText(nil) != "" {
		t.Fatal("empty")
	}
}
