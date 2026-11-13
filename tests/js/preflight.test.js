import { test } from "node:test";
import assert from "node:assert/strict";
import { runPreflight } from "../../tools/preflight.mjs";

/** A pretend site: path → response. Each site says what its /api/info is and which parts work. */
function site({ info, compile = "ok", pi = "online", piApp = true, wasmCache = "public, max-age=604800", headers = true }) {
  const origin = "https://cp.example";
  const res = (status, body = "", h = {}) => ({
    status, headers: new Headers(h),
    json: async () => (typeof body === "string" ? JSON.parse(body || "null") : body),
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  });
  const isolation = headers ? { "cross-origin-opener-policy": "same-origin", "cross-origin-embedder-policy": "require-corp" } : {};
  const usb = headers ? { "permissions-policy": "serial=(self), usb=(self), camera=()" } : {};
  return async (url, init = {}) => {
    const path = new URL(url).pathname;
    if (path === "/api/info") return res(200, { app: "Circuit Pathways", ...info });
    if (path === "/") return res(200);
    if (path === "/pipath/") return res(200, "", isolation);
    if (path === "/arduinopath/") return res(200, "", usb);
    if (path === "/pipath/vendor/pyodide/pyodide.asm.wasm") return res(200, "", { "content-type": "application/wasm", "cache-control": wasmCache });
    if (path === "/arduinopath/vendor/esptool-js/bundle.js") return res(200);
    if (path === "/api/teacher/signin") return res(200, { token: "t2.x" });
    if (path === "/api/teacher/class" && init.method === "POST") return res(200, { code: "ABCDE-FGHJK" });
    if (path === "/api/class/join") return res(200, { needs_names: true });
    if (path.startsWith("/api/teacher/class/")) return res(204);
    if (path === "/api/compile") return compile === "ok" ? res(200, { ok: true, artifacts: [{ name: "x.hex" }] }) : res(502, { message: "The compiler can't be reached" });
    if (path === "/pipath/remote/circuitpathways_pi.py") return piApp ? res(200, `SERVER = "${origin}"`) : res(404);
    if (path === "/api/pi/command") return pi === "online" ? res(204) : pi === "denied" ? res(401, { message: "no" }) : res(404, { error: "pi_not_found" });
    return res(404);
  };
}
const piBeta = { edition: "pi-beta", host: "cloudflare", commit: "5e86a54", compile: true, classes: true, relay: "ws", teacher_mode: true, class_optional: true };
const states = (r) => r.results.map((x) => `${x.state}:${x.title}`);

test("a healthy Pi beta with a compiler and a connected Pi is ready", async () => {
  const r = await runPreflight({ url: "https://cp.example", pi: "K7M2-QX9P", expect: "pi-beta", fetch: site({ info: piBeta }) });
  assert.equal(r.ok, true, JSON.stringify(states(r)));
  assert.ok(r.results.some((x) => /real compile worked/.test(x.title)));
  assert.ok(r.results.some((x) => /Pi K7M2-QX9P is connected/.test(x.title)));
  assert.ok(r.results.some((x) => /Pi beta, on cloudflare, build 5e86a54/.test(x.title)));
});

test("no compiler is not ready, and says how to fix it", async () => {
  const r = await runPreflight({ url: "https://cp.example", fetch: site({ info: { ...piBeta, compile: false } }) });
  assert.equal(r.ok, false);
  const bad = r.results.find((x) => x.state === "fail");
  assert.match(bad.title, /no compiler/);
  assert.match(bad.fix, /COMPILE_URL/);
});

test("a compiler that is set up but fails is not ready", async () => {
  const r = await runPreflight({ url: "https://cp.example", fetch: site({ info: piBeta, compile: "broken" }) });
  assert.equal(r.ok, false);
  assert.ok(r.results.some((x) => x.state === "fail" && /real compile failed/.test(x.title)));
});

test("--no-compile skips the compile but still checks everything else", async () => {
  const r = await runPreflight({ url: "https://cp.example", compile: false, fetch: site({ info: piBeta }) });
  assert.equal(r.ok, true);
  assert.ok(!r.results.some((x) => /real compile/.test(x.title)));
});

test("a Pi that isn't connected is not ready, and the fix names its commands", async () => {
  const r = await runPreflight({ url: "https://cp.example", pi: "K7M2-QX9P", fetch: site({ info: piBeta, pi: "offline" }) });
  assert.equal(r.ok, false);
  const bad = r.results.find((x) => /isn't connected/.test(x.title));
  assert.match(bad.fix, /pilink status/);
  assert.match(bad.fix, /pilink server https:\/\/cp\.example/);
});

test("missing isolation headers mean Python can't run, and USB headers mean uploads can't", async () => {
  const r = await runPreflight({ url: "https://cp.example", fetch: site({ info: piBeta, headers: false }) });
  assert.equal(r.ok, false);
  assert.ok(r.results.some((x) => x.state === "fail" && /Python/.test(x.title)));
  assert.ok(r.results.some((x) => x.state === "fail" && /USB/.test(x.title)));
});

test("the wrong edition is caught, and an uncached Python engine is only a warning", async () => {
  const r = await runPreflight({ url: "https://cp.example", expect: "real", fetch: site({ info: piBeta, wasmCache: "no-cache" }) });
  assert.ok(r.results.some((x) => x.state === "fail" && /Expected the real site, but this is the Pi beta/.test(x.title)));
  assert.ok(r.results.some((x) => x.state === "warn" && /isn't cached/.test(x.title)));
});

test("the TEST version has no Pi linking, and that's fine unless a Pi was asked for", async () => {
  const testInfo = { edition: "test", beta: true, host: "render", compile: true, teacher_mode: true };
  const r = await runPreflight({ url: "https://cp.example", fetch: site({ info: testInfo, piApp: false }) });
  assert.equal(r.ok, true, JSON.stringify(states(r)));
  const asked = await runPreflight({ url: "https://cp.example", pi: "K7M2-QX9P", fetch: site({ info: testInfo, piApp: false }) });
  assert.equal(asked.ok, false);
});

test("a site that doesn't answer is not ready", async () => {
  const r = await runPreflight({ url: "https://nope.example", fetch: async () => { throw Object.assign(new Error("fetch failed"), { cause: { code: "ENOTFOUND" } }); } });
  assert.equal(r.ok, false);
  assert.match(r.results[0].title, /didn't answer/);
  assert.match(r.results[0].detail, /ENOTFOUND/);
});
