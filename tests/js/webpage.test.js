// The Web Page Designer's sketches run in the simulator: the page comes back with today's numbers,
// buttons switch pins, and sliders set values.
import { test } from "node:test";
import assert from "node:assert/strict";
import { boards } from "./circuit/helpers.js";
import { generateSketch, pageHTML, starterDesign, cName, namedItems } from "../../site/arduinopath/js/webpage.js";
import { runHeadless } from "../../site/arduinopath/js/sim/headless.js";

const esp32 = boards().find((b) => b.id === "esp32");
const nodemcu = boards().find((b) => b.id === "nodemcu");

const design = {
  title: "Plant <Page>", theme: "purple", wifi: { mode: "hotspot", name: "PlantPage", password: "circuit123" }, refresh: 3,
  items: [
    { kind: "heading", text: "My plant" },
    { kind: "button", label: "Light on", action: "on", pin: "LED_PIN" },
    { kind: "button", label: "Light on", action: "toggle", pin: "LED_PIN" },
    { kind: "button", label: "Feed the fish!", action: "custom" },
    { kind: "slider", label: "Speed", min: 0, max: 10, start: 5 },
    { kind: "reading", label: "Time", unit: "s", source: "millis() / 1000" },
  ],
};

test("names are C names and unique; the page escapes text and puts in the numbers", () => {
  assert.equal(cName("Feed the fish!"), "feedTheFish");
  assert.equal(cName("3 lights"), "item3Lights");
  assert.deepEqual(namedItems(design).map((i) => i.cname), ["myPlant", "lightOn", "lightOn2", "feedTheFish", "speed", "timeValue"]);
  const page = pageHTML(design);
  assert.match(page, /<title>Plant &lt;Page&gt;<\/title>/);
  assert.match(page, /href="\/light-on2"/);
  assert.match(page, /%timeValue%/);
  assert.match(page, /http-equiv="refresh" content="3"/);
});

for (const board of [esp32, nodemcu]) {
  test(`the sketch runs on ${board.id}: the page, a button, a slider and a reading`, () => {
    const code = generateSketch(design, board);
    assert.match(code, board.family === "esp8266" ? /ESP8266WebServer server\(80\);/ : /WebServer server\(80\);/);
    const r = runHeadless(code, {
      board, ms: 4000,
      events: [
        { at_ms: 500, http: { path: "/" } },
        { at_ms: 1000, http: { path: "/light-on" } },
        { at_ms: 1500, http: { path: "/speed", query: { value: "7" } } },
        { at_ms: 2500, http: { path: "/" } },
      ],
    });
    assert.equal(r.ok, true, JSON.stringify(r.errors ?? r.message));
    const pages = r.http.map((x) => x.response?.body ?? "");
    assert.match(pages[0], /<h1>Plant &lt;Page&gt;<\/h1>/);
    assert.match(pages[3], /Speed <b>7<\/b>/, "the slider's value is on the page");
    assert.match(pages[3], /Time: <b>2<\/b> s/, "the reading is on the page");
    const pin = Number(board.pin_plan.LED_PIN.replace(/\D/g, "")) || null;
    assert.ok(r.events.some((e) => e.type === "digital" && e.value === 1), "the button turned the pin on");
    assert.match(r.serial, /Light on was pressed/);
    assert.match(r.serial, /Speed: 7/);
    void pin;
  });
}

test("joining the school WiFi instead, and the starter design", () => {
  const code = generateSketch({ ...starterDesign(), wifi: { mode: "join", name: "BNTS-Guest", password: "secret12" } }, esp32);
  assert.match(code, /WiFi\.begin\(WIFI_NAME, WIFI_PASSWORD\);/);
  const r = runHeadless(code, { board: esp32, ms: 6000, events: [{ at_ms: 4500, http: { path: "/turn-it-on" } }] });
  assert.equal(r.ok, true, JSON.stringify(r.errors ?? r.message));
  assert.match(r.serial, /Turn it on was pressed/);
});

// ---- the interactive designer's elements, model and helpers ----
import { connections, connectionText, pinClashes, defaultItem, moveItem, insertItem, dropIndex, tryIt, TEMPLATES, ELEMENTS, onVar } from "../../site/arduinopath/js/webpage.js";

const everything = {
  title: "Everything", theme: "sunset", wifi: { mode: "hotspot", name: "Everything", password: "circuit123" }, refresh: 2,
  items: [
    { kind: "switch", label: "Lamp", pin: "LED_PIN" },
    { kind: "status", label: "Lamp", source: "light", pin: "LED_PIN", onText: "Shining", offText: "Dark" },
    { kind: "colour", label: "Mood", start: "#000000" },
    { kind: "slider", label: "Pitch", min: 0, max: 2000, start: 0, pin: "BUZZER_PIN" },
    { kind: "button", label: "Beep", action: "beep" },
    { kind: "status", label: "Doorbell", source: "button", onText: "Ringing", offText: "Quiet" },
    { kind: "reading", label: "Knob", source: "analogRead(POT_PIN)", style: "bar", max: 4095 },
  ],
};

for (const board of [esp32, nodemcu]) {
  test(`every new element works in the simulator on ${board.id}: switch, status lights, colour, pitch, beep, a bar`, () => {
    const code = generateSketch(everything, board);
    const btn = board.pin_plan.BUTTON_PIN;
    const r = runHeadless(code, {
      board, ms: 5000,
      events: [
        { at_ms: 400, http: { path: "/" } },
        { at_ms: 800, http: { path: "/toggle-lamp" } },
        { at_ms: 1200, http: { path: "/set-mood", query: { value: "#ff8000" } } },
        { at_ms: 1600, http: { path: "/pitch", query: { value: "440" } } },
        { at_ms: 2000, http: { path: "/beep" } },
        { at_ms: 2400, set: { digital: { BUTTON_PIN: 0 }, analog: { POT_PIN: 1000 } } },
        { at_ms: 3000, http: { path: "/" } },
      ],
    });
    assert.equal(r.ok, true, JSON.stringify(r.errors ?? r.message));
    void btn;
    const [before, , , , , after] = r.http.map((x) => x.response?.body ?? "");
    assert.match(before, /class="switch sw-off"/, "the switch starts off");
    assert.match(before, /Lamp: <b>Dark<\/b>/);
    assert.match(after, /class="switch sw-on"/, "pressing it switched it on, and the page shows it");
    assert.match(after, /status st-on"><span class="dot"><\/span> Lamp: <b>Shining<\/b>/, "the status light follows the switch");
    assert.match(after, /value="#ff8000"/, "the colour picker remembers the colour");
    assert.match(after, /Pitch <b>440<\/b>/);
    assert.match(after, /Doorbell: <b>Ringing<\/b>/, "holding the button lights its status light");
    assert.match(after, /<meter min="0" max="4095" value="1000"><\/meter>/, "the knob is a bar");
    assert.match(r.serial, /Lamp: on/);
    assert.match(r.serial, /Mood: #ff8000/);
    assert.match(r.serial, /Beep was pressed/);
    assert.ok(r.events.some((e) => e.type === "tone"), "the buzzer beeped");
    assert.match(code, /pinMode\(BUTTON_PIN, INPUT_PULLUP\);/);
    assert.match(code, new RegExp(`bool ${onVar("LED_PIN")} = false;`));
  });
}

test("a toggle remembers its own state (an ESP32 can't read back an output pin)", () => {
  const code = generateSketch({ ...design, items: [{ kind: "button", label: "Flip", action: "toggle", pin: "LED_PIN" }] }, esp32);
  assert.doesNotMatch(code, /digitalRead\(LED_PIN\)/);
  assert.match(code, /ledPinOn = !ledPinOn;/);
});

test("each element says what it's wired to, and clashing pins are found", () => {
  assert.equal(connectionText(connections({ kind: "switch", pin: "LED_PIN" }, esp32)[0]), "→ LED_PIN (pin 25)");
  assert.equal(connectionText(connections({ kind: "reading", source: "analogRead(POT_PIN)" }, esp32)[0]), "← Knob (pin 34)");
  assert.deepEqual(connections({ kind: "colour" }, esp32).map((c) => c.role), ["RGB_RED", "RGB_GREEN", "RGB_BLUE"]);
  assert.deepEqual(connections({ kind: "button", action: "custom" }, esp32), []);
  // a NodeMCU has one analog pin: a knob and a light sensor can't share it
  const two = { items: [{ kind: "reading", source: "analogRead(POT_PIN)" }, { kind: "reading", source: "analogRead(LDR_PIN)" }] };
  assert.deepEqual(pinClashes(two, nodemcu).map((c) => c.pin), ["A0"]);
  assert.deepEqual(pinClashes(two, esp32), [], "an ESP32 has separate pins for them");
  // the same output twice is not a clash
  assert.deepEqual(pinClashes({ items: [{ kind: "switch", pin: "LED_PIN" }, { kind: "button", action: "on", pin: "LED_PIN" }] }, esp32), []);
});

test("drag and drop as list changes: insert, move up and down, and where a drop lands", () => {
  const list = ["a", "b", "c", "d"];
  assert.deepEqual(insertItem(list, 1, "x"), ["a", "x", "b", "c", "d"]);
  assert.deepEqual(insertItem(list, 99, "x"), ["a", "b", "c", "d", "x"]);
  assert.deepEqual(moveItem(list, 0, 2), ["b", "c", "a", "d"]);
  assert.deepEqual(moveItem(list, 3, 0), ["d", "a", "b", "c"]);
  assert.deepEqual(list, ["a", "b", "c", "d"], "the original isn't changed (so Undo can keep it)");
  assert.equal(dropIndex([10, 30, 50], 5), 0);
  assert.equal(dropIndex([10, 30, 50], 31), 2);
  assert.equal(dropIndex([10, 30, 50], 99), 3);
  for (const kind of Object.keys(ELEMENTS)) assert.equal(defaultItem(kind, esp32).kind, kind);
});

test("Try it: the pretend board does what the real sketch would", () => {
  const t = tryIt(everything, esp32);
  assert.equal(t.show(0), "off");
  t.use(0); // the switch
  assert.equal(t.state.outputs.LED_PIN, 1);
  assert.equal(t.show(0), "on");
  assert.equal(t.show(1), "on", "the status light follows it");
  t.use(2, "#ff8000");
  assert.deepEqual(t.state.rgb, { r: 255, g: 128, b: 0 });
  t.use(3, 5000); // past the end of the slider
  assert.equal(t.show(3), 2000);
  assert.equal(t.state.pitch, 2000);
  t.use(4);
  assert.equal(t.state.beep, 1);
  assert.equal(t.show(5), "off");
  t.setInput("BUTTON_PIN", true);
  assert.equal(t.show(5), "on");
  t.setInput("POT_PIN", 1234);
  assert.equal(t.show(6), 1234);
  const s = tryIt({ items: [{ kind: "reading", source: "millis() / 1000" }, { kind: "slider", min: 0, max: 100, pin: "LED_PIN" }] }, esp32);
  s.tick(3);
  assert.equal(s.show(0), 3);
  s.use(1, 25);
  assert.equal(s.state.outputs.LED_PIN, 0.25, "a slider dims the LED");
});

for (const [id, tpl] of Object.entries(TEMPLATES)) {
  for (const board of [esp32, nodemcu]) {
    test(`the "${tpl.name}" idea runs on ${board.id}`, () => {
      const r = runHeadless(generateSketch(tpl.design, board), { board, ms: 1500, events: [{ at_ms: 500, http: { path: "/" } }] });
      assert.equal(r.ok, true, `${id}: ${JSON.stringify(r.errors ?? r.message)}`);
      assert.match(r.http[0].response.body, new RegExp(`<h1>${tpl.design.title}</h1>`));
    });
  }
}

// The Web Page Designer's sketches are compiled for real in CI from internal/arduino/testdata/webpage/.
test("the sketches CI compiles for real are up to date, and each runs in the simulator", async () => {
  const { fixtures } = await import("../../tools/make_compile_fixtures.mjs");
  const { readFileSync, existsSync } = await import("node:fs");
  const want = fixtures();
  assert.ok(Object.keys(want).length >= 16);
  for (const [name, code] of Object.entries(want)) {
    const file = new URL(`../../internal/arduino/testdata/webpage/${name}`, import.meta.url);
    assert.ok(existsSync(file) && readFileSync(file, "utf8") === code, `${name} is out of date: run node tools/make_compile_fixtures.mjs`);
    const board = boards().find((b) => b.id === name.split("--")[0]);
    const r = runHeadless(code, { board, ms: 800 });
    assert.equal(r.ok, true, `${name}: ${JSON.stringify(r.errors)}`);
  }
});
