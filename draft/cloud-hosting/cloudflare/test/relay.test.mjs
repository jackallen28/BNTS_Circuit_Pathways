// The Pi relay on Cloudflare: the real Pi app (pretend pins) and a browser-like WebSocket, through a
// real local Worker and Durable Object.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { startWorker, api, VARS } from "./harness.mjs";
import { keyFor } from "../src/pikeys.js";

const here = dirname(dirname(fileURLToPath(import.meta.url)));
let w;
let call;
let pi;
let piOut = "";
const ID = "K7M2QX9P";

before(async () => {
  w = await startWorker();
  call = api(w.url);
  const key = await keyFor(VARS.PI_KEY_SECRET, ID);
  const runDir = mkdtempSync(join(tmpdir(), "cp-run-"));
  chmodSync(runDir, 0o755); // the unprivileged user that programs run as has to reach its own folder
  pi = spawn("python3", [join(here, "..", "site", "pipath", "remote", "circuitpathways_pi.py"), "--mock", "--key", key, "--server", w.url, "--run-dir", runDir, ...(process.getuid?.() === 0 ? ["--run-user", "nobody"] : [])], { stdio: ["pipe", "pipe", "pipe"] });
  pi.stdout.on("data", (d) => { piOut += d; });
  pi.stderr.on("data", (d) => { piOut += d; });
});
after(() => { pi?.kill(); w?.stop(); });

function browser(token, code) {
  const ws = new WebSocket(`${w.url.replace("http", "ws")}/api/pi/ws?code=${code}`, ["cp-access", token]);
  const events = [];
  ws.onmessage = (e) => events.push(JSON.parse(e.data));
  const opened = new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("the WebSocket didn't open")); });
  const until = async (pred, ms = 8000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const hit = events.find(pred);
      if (hit) return hit;
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error(`waited for an event; got ${JSON.stringify(events).slice(-900)}\nPi said: ${piOut.slice(-800)}`);
  };
  return { ws, events, opened, until };
}

test("a teacher's browser links to the Pi, switches a pin, and runs a program on it", async () => {
  const token = (await call("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).data.token;
  const b = browser(token, "k7m2-qx9p");
  await b.opened;
  await b.until((e) => e.type === "connected");
  await b.until((e) => e.type === "hello" || (e.type === "pi-online"), 15000);
  const hello = await b.until((e) => e.type === "hello", 15000);
  assert.equal(hello.data.backend, "mock");

  const cmd = (c) => call("POST", "/api/pi/command", { headers: { "X-Access": token }, body: { code: ID, cmd: c } });
  assert.equal((await cmd({ op: "mode", pin: 17, mode: "out" })).status, 204);
  assert.equal((await cmd({ op: "write", pin: 17, value: 1 })).status, 204);
  await b.until((e) => e.type === "state" && e.data.pins["17"]?.value === 1);
  assert.equal((await cmd({ op: "write", pin: 40, value: 1 })).status, 400, "a pin a Pi doesn't have is refused by the Worker");

  assert.equal((await cmd({ op: "run", rid: 1, name: "program.py", code: "print('hello from the Pi', 6 * 7)\n" })).status, 204);
  await b.until((e) => e.type === "out" && /hello from the Pi 42/.test(e.data.text), 15000);
  const exit = await b.until((e) => e.type === "exit");
  assert.equal(exit.data.rc, 0);
  b.ws.close();
});

test("without a class or teacher sign-in, a browser can't reach a Pi", async () => {
  const b = browser("s2.nope.nope", ID);
  await assert.rejects(b.opened);
  const r = await call("POST", "/api/pi/command", { headers: { "X-Access": "nope" }, body: { code: ID, cmd: { op: "all_off" } } });
  assert.equal(r.status, 401);
});

test("a second browser takes over, and the first is told why", async () => {
  const token = (await call("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).data.token;
  const a = browser(token, ID);
  await a.opened;
  await a.until((e) => e.type === "connected");
  const b = browser(token, ID);
  await b.opened;
  await a.until((e) => e.type === "closed" && /Someone else/.test(e.data.reason));
  a.ws.close();
  b.ws.close();
});
