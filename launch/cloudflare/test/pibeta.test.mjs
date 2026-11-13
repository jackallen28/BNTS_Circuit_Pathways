// The Pi beta (PI_BETA=1): students on Raspberry Pis start with no class code (work stays on the device),
// or join a class and sync to the database. This checks the Worker's side: what "local" may do.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { startWorker, api } from "./harness.mjs";

let pi;
let normal;
let onPi;
let onNormal;

before(async () => {
  [pi, normal] = await Promise.all([startWorker({ env: "pi" }), startWorker()]);
  onPi = api(pi.url);
  onNormal = api(normal.url);
});
after(() => { pi?.stop(); normal?.stop(); });

test("/api/info says it's the Pi beta and that a class code is optional", async () => {
  const { data } = await onPi("GET", "/api/info");
  assert.equal(data.edition, "pi-beta");
  assert.equal(data.class_optional, true);
  assert.equal(data.classes, true, "classes still work");
  assert.equal(data.beta, false, "it saves, unlike the TEST version");
  const plain = (await onNormal("GET", "/api/info")).data;
  assert.equal(plain.edition, "");
  assert.equal(plain.class_optional, false);
});

test("a student with no class ('local') may compile and link a Pi; a made-up word may not", async () => {
  const body = { code: "void setup(){}\nvoid loop(){}", board: "uno" };
  const local = await onPi("POST", "/api/compile", { body, headers: { "X-Access": "local" } });
  assert.notEqual(local.status, 401, "local is let in (503 just means no compiler is set up here)");
  assert.equal((await onPi("POST", "/api/compile", { body, headers: { "X-Access": "made-up" } })).status, 401);
  const cmd = await onPi("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "local" } });
  assert.notEqual(cmd.status, 401);
  assert.equal((await onPi("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "made-up" } })).status, 401);
});

test("the normal site still needs a class: 'local' means nothing there", async () => {
  const body = { code: "void setup(){}\nvoid loop(){}", board: "uno" };
  assert.equal((await onNormal("POST", "/api/compile", { body, headers: { "X-Access": "local" } })).status, 401);
  assert.equal((await onNormal("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "local" } })).status, 401);
});

test("classes, teachers and the Pi installer are all there (unlike the TEST version)", async () => {
  assert.equal((await onPi("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).status, 200);
  const res = await fetch(`${pi.url}/pipath/remote/install.sh`);
  assert.equal(res.status, 200);
  assert.match(await res.text(), /Circuit Pathways Pi Link/);
});
