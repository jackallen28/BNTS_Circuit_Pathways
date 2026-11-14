package arduino_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"circuitpathways"
	"circuitpathways/internal/arduino"
	"circuitpathways/internal/content"
	"circuitpathways/internal/setup"
)

// A real compile for every board, with the real compilers. It runs only when
// CIRCUITPATHWAYS_TOOLS points at a folder made by `circuitpathways -setup` (CI does this).
func TestCompileEveryBoardForReal(t *testing.T) {
	dir := os.Getenv("CIRCUITPATHWAYS_TOOLS")
	if dir == "" {
		t.Skip("set CIRCUITPATHWAYS_TOOLS to a folder made by `circuitpathways -setup` to run this")
	}
	tools, err := arduino.InstalledTools(dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	cat, problems := content.Load(circuitpathways.Content())
	if len(problems) > 0 {
		t.Fatal(problems[0])
	}
	const blink = "void setup() { pinMode(LED_BUILTIN, OUTPUT); Serial.begin(115200); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); delay(500); digitalWrite(LED_BUILTIN, LOW); delay(500); Serial.println(\"hi\"); }\n"
	for _, b := range cat.Boards {
		t.Run(b.ID, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
			defer cancel()
			res, arts, err := tools.Compile(ctx, blink, b.FQBN, b.BuildProperties)
			if err != nil || !res.OK {
				t.Fatalf("compile failed: %v\n%s", err, res.Output)
			}
			if len(arts) != 1 || len(arts[0].Data) == 0 {
				t.Fatalf("want one non-empty file to upload, got %+v", arts)
			}
			data := arts[0].Data
			switch b.Family {
			case "avr":
				if data[0] != ':' {
					t.Errorf("an Arduino upload is an Intel HEX file, got %q...", data[:8])
				}
			case "esp8266":
				if data[0] != 0xE9 {
					t.Errorf("an ESP8266 image starts with 0xE9, got %#x", data[0])
				}
			case "esp32":
				if len(data) < 0x10000 {
					t.Errorf("an ESP32 merged image is bootloader + partitions + app, got only %d bytes", len(data))
				}
			}
			// the Web Page Designer's sketches for this board (written by tools/make_compile_fixtures.mjs)
			pages, _ := filepath.Glob(filepath.Join("testdata", "webpage", b.ID+"--*.ino"))
			if b.Family != "avr" && len(pages) == 0 {
				t.Errorf("no Web Page Designer sketches for %s: run node tools/make_compile_fixtures.mjs", b.ID)
			}
			for _, f := range pages {
				code, err := os.ReadFile(f)
				if err != nil {
					t.Fatal(err)
				}
				res, arts, err := tools.Compile(ctx, string(code), b.FQBN, b.BuildProperties)
				if err != nil || !res.OK || len(arts) == 0 {
					t.Errorf("%s doesn't compile: %v\n%s", filepath.Base(f), err, res.Output)
				}
			}
			// the set-up sketch the teacher portal flashes onto each of the school's ESP boards
			if b.Family != "avr" {
				code := setup.BoardSketch("ESP-07", "CP-ESP07-K3QX", "abcdefgh23")
				if res, arts, err := tools.Compile(ctx, code, b.FQBN, b.BuildProperties); err != nil || !res.OK || len(arts) == 0 {
					t.Errorf("the board set-up sketch doesn't compile: %v\n%s", err, res.Output)
				}
			}
			// a student's sketch with a mistake comes back as an error with a line number, and no file
			bad, none, err := tools.Compile(ctx, "void setup() { digitalWrite(13 HIGH) }\nvoid loop() {}\n", b.FQBN, b.BuildProperties)
			if err != nil || bad.OK || none != nil || len(bad.Diagnostics) == 0 || bad.Diagnostics[0].Line == 0 {
				t.Fatalf("a broken sketch should fail with a diagnostic: err=%v ok=%v diags=%+v", err, bad.OK, bad.Diagnostics)
			}
		})
	}
}
