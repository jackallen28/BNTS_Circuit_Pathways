// "My ESP board": each board's own WiFi goes into the student's code, and a school board is remembered offline.
import { test } from "node:test";
import assert from "node:assert/strict";

const mem = new Map();
const ls = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
globalThis.localStorage = ls;
const { applyWifi, localIdentity, myBoard, isEspBoard, notYourBoard, DEFAULT_WIFI } = await import("../../site/arduinopath/js/myboard.js");
const { expandPins } = await import("../../site/arduinopath/js/sim/pins.js");

const school = { source: "school", label: "ESP-07", ssid: "CP-ESP07-K3QX", password: "abcdefgh23", mac: "a4:cf:12:0b:9e:01" };

test("a starter's #define lines get the board's own WiFi name and password", () => {
  const project = { parts: [] };
  const board = { name: "NodeMCU", pins: [], fqbn: "esp8266:esp8266:nodemcuv2" };
  const starter = expandPins("{{pins}}\n#include <WiFi.h>\nvoid setup() { WiFi.softAP(MY_WIFI_NAME, MY_WIFI_PASSWORD); }\nvoid loop() {}\n", project, board);
  assert.match(starter, new RegExp(`#define MY_WIFI_NAME "${DEFAULT_WIFI.name}"`));
  const mine = applyWifi(starter, school);
  assert.match(mine, /#define MY_WIFI_NAME "CP-ESP07-K3QX"/);
  assert.match(mine, /#define MY_WIFI_PASSWORD "abcdefgh23"/);
  assert.equal(applyWifi(mine, school), mine, "doing it again changes nothing");
});

test("with a school board, a hotspot with any other name uses the board's", () => {
  const code = 'void setup() {\n  WiFi.softAP("Sams-Net", "password1");\n}\n';
  const out = applyWifi(code, school);
  assert.match(out, /WiFi\.softAP\(MY_WIFI_NAME, MY_WIFI_PASSWORD\)/);
  assert.match(out, /^#define MY_WIFI_NAME "CP-ESP07-K3QX"/m);
  // the Web Page Designer's hotspot too
  const page = 'const char* WIFI_NAME = "MySmartLight";\nconst char* WIFI_PASSWORD = "circuit123";  // at least 8 characters\nvoid setup() { WiFi.softAP(WIFI_NAME, WIFI_PASSWORD); }\n';
  const fixed = applyWifi(page, school);
  assert.match(fixed, /WIFI_NAME = "CP-ESP07-K3QX"/);
  assert.match(fixed, /WIFI_PASSWORD = "abcdefgh23";  \/\/ at least 8/);
  // joining the school's WiFi (not a hotspot) is left alone
  const join = 'const char* WIFI_NAME = "SchoolWiFi";\nconst char* WIFI_PASSWORD = "secret";\nvoid setup() { WiFi.begin(WIFI_NAME, WIFI_PASSWORD); }\n';
  assert.equal(applyWifi(join, school), join);
  // without a school board, a student's own hotspot name is theirs to choose
  assert.equal(applyWifi(code, { source: "local", ssid: "ArduinoPath-ab12", password: "x".repeat(10) }), code);
});

test("this browser's own WiFi is made once and kept", () => {
  mem.clear();
  const a = localIdentity(ls);
  assert.match(a.ssid, /^ArduinoPath-[a-z0-9]{4}$/);
  assert.match(a.password, /^[a-z0-9]{10}$/);
  assert.deepEqual(localIdentity(ls), a);
});

test("a student's school board comes from the server, and is remembered for when it can't be reached", async () => {
  mem.clear();
  const access = { kind: "student", value: "s2.token" };
  const ok = async () => ({ ok: true, status: 200, json: async () => ({ board: { ...school, code: "K7M2-QX9P", kind: "nodemcu" } }) });
  const b = await myBoard({ access, fetchImpl: ok, ls });
  assert.equal(b.source, "school");
  assert.equal(b.mac, school.mac);
  const offline = async () => { throw new TypeError("Failed to fetch"); };
  assert.equal((await myBoard({ access, fetchImpl: offline, ls })).label, "ESP-07");
  // no board (or no class): this browser's own WiFi
  const none = async () => ({ ok: true, status: 200, json: async () => ({ board: null }) });
  assert.equal((await myBoard({ access, fetchImpl: none, ls })).source, "local");
  assert.equal((await myBoard({ access: { kind: "local", value: "local" }, ls })).source, "local");
});

test("only ESP boards are checked, and the message names the student's own board", () => {
  assert.equal(isEspBoard({ fqbn: "esp32:esp32:esp32" }), true);
  assert.equal(isEspBoard({ fqbn: "arduino:avr:uno" }), false);
  assert.match(notYourBoard(school), /isn't your board.*ESP-07.*CP-ESP07-K3QX/);
});
