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
    if (path === "/install/student-pi.sh") return res(200);
    return res(404);
  };
}
const school = { edition: "school", name: "pathways.local", commit: "5e86a54", compile: true, classes: true, relay: "off", class_optional: true, tls: true };
const studentPi = { edition: "student-pi", name: "pi-07.local", commit: "5e86a54", compile: true, classes: true, relay: "sse", online: true, school_server: "pathways.local" };
const states = (r) => r.results.map((x) => `${x.state}:${x.title}`);

test("a healthy school server with a compiler is ready, and a teacher can make a class", async () => {
  const r = await runPreflight({ url: "https://pathways.local", teacherCode: "comet-maple-reef-42", expect: "school", fetch: site({ info: school }) });
  assert.equal(r.ok, true, JSON.stringify(states(r)));
  assert.ok(r.results.some((x) => /real compile worked/.test(x.title)));
  assert.ok(r.results.some((x) => /school server \(pathways.local\), build 5e86a54/.test(x.title)));
  assert.ok(r.results.some((x) => /A teacher can make a class/.test(x.title)));
});

test("a student Pi with its Pi Link connected is ready", async () => {
  const r = await runPreflight({ url: "http://localhost:8080", pi: "K7M2-QX9P", expect: "student-pi", fetch: site({ info: studentPi }) });
  assert.equal(r.ok, true, JSON.stringify(states(r)));
  assert.ok(r.results.some((x) => /Pi K7M2-QX9P's Pi Link is connected/.test(x.title)));
  assert.ok(r.results.some((x) => /can reach the school server/.test(x.title)));
});

test("a student Pi that can't reach the school server is only a warning (students can still work)", async () => {
  const r = await runPreflight({ url: "http://localhost:8080", compile: false, fetch: site({ info: { ...studentPi, online: false } }) });
  assert.equal(r.ok, true, JSON.stringify(states(r)));
  assert.ok(r.results.some((x) => x.state === "warn" && /can't reach the school server/.test(x.title)));
});

test("no compiler is not ready, and says how to fix it", async () => {
  const r = await runPreflight({ url: "https://pathways.local", fetch: site({ info: { ...school, compile: false } }) });
  assert.equal(r.ok, false);
  const bad = r.results.find((x) => x.state === "fail");
  assert.match(bad.title, /no compiler/);
  assert.match(bad.fix, /-setup -warm/);
});

test("a compiler that is there but fails is not ready", async () => {
  const r = await runPreflight({ url: "https://pathways.local", fetch: site({ info: school, compile: "broken" }) });
  assert.equal(r.ok, false);
  assert.ok(r.results.some((x) => x.state === "fail" && /real compile failed/.test(x.title)));
});

test("--no-compile skips the compile but still checks everything else", async () => {
  const r = await runPreflight({ url: "https://pathways.local", compile: false, fetch: site({ info: school }) });
  assert.equal(r.ok, true);
  assert.ok(!r.results.some((x) => /real compile/.test(x.title)));
});

test("a Pi Link that isn't connected is not ready, and the fix names its commands", async () => {
  const r = await runPreflight({ url: "http://localhost:8080", pi: "K7M2-QX9P", fetch: site({ info: studentPi, pi: "offline" }) });
  assert.equal(r.ok, false);
  const bad = r.results.find((x) => /isn't connected/.test(x.title));
  assert.match(bad.fix, /pilink status/);
});

test("missing isolation headers mean Python can't run, and USB headers mean uploads can't", async () => {
  const r = await runPreflight({ url: "https://pathways.local", fetch: site({ info: school, headers: false }) });
  assert.equal(r.ok, false);
  assert.ok(r.results.some((x) => x.state === "fail" && /Python/.test(x.title)));
  assert.ok(r.results.some((x) => x.state === "fail" && /USB/.test(x.title)));
});

test("the wrong kind of server is caught, and an uncached Python engine is only a warning", async () => {
  const r = await runPreflight({ url: "https://pathways.local", expect: "student-pi", fetch: site({ info: school, wasmCache: "no-cache" }) });
  assert.ok(r.results.some((x) => x.state === "fail" && /Expected a student Pi, but this is a school server/.test(x.title)));
  assert.ok(r.results.some((x) => x.state === "warn" && /isn't cached/.test(x.title)));
});

test("a server that doesn't answer is not ready; one with a certificate this computer doesn't trust says so", async () => {
  const r = await runPreflight({ url: "https://nope.local", fetch: async () => { throw Object.assign(new Error("fetch failed"), { cause: { code: "ENOTFOUND" } }); } });
  assert.equal(r.ok, false);
  assert.match(r.results[0].title, /didn't answer/);
  assert.match(r.results[0].detail, /ENOTFOUND/);
  const cert = await runPreflight({ url: "https://pathways.local", fetch: async () => { throw Object.assign(new Error("fetch failed"), { cause: { code: "SELF_SIGNED_CERT_IN_CHAIN" } }); } });
  assert.match(cert.results[0].fix, /NODE_EXTRA_CA_CERTS/);
});
