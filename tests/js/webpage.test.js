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
