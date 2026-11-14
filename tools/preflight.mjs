#!/usr/bin/env node
// Is this Circuit Pathways server ready for a test day with real Raspberry Pis and Arduinos?
//
//   node tools/preflight.mjs https://pathways.local --teacher-code "comet-maple-reef-42"     the school server
//   node tools/preflight.mjs http://localhost:8080 --pi K7M2-QX9P                            on a student Pi
//
// It only needs Node 18 or newer (no packages). It checks the things that fail quietly on the day: which server and
// build it is, whether Python can run (the isolation headers), whether uploading to a board can work (USB
// permissions, a real compile), whether teachers can make classes, whether a student Pi can reach the school
// server, and whether its Pi Link is connected. Each failure says what to do about it.
//
// The school server's https certificate is its own: to check it over https from a computer that doesn't trust it
// yet, run with NODE_EXTRA_CA_CERTS=ca.crt (download it from http://pathways.local/ca.crt), or check http://.
//
// Options:
//   --teacher-code CODE  a teacher code (sudo circuitpathways teacher list): checks signing in and making a class
//   --pi ID              (a student Pi) also check that this Pi's Pi Link is connected right now
//   --expect KIND        school | student-pi: fail if the server is the other kind
//   --no-compile         skip the real compile (it can take half a minute the first time)
//
// Exit status: 0 if nothing blocks the test day, 1 if something does.

const BLINK = "void setup() { pinMode(LED_BUILTIN, OUTPUT); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); delay(500); digitalWrite(LED_BUILTIN, LOW); delay(500); }\n";
const KINDS = { school: "school server", "student-pi": "student Pi" };

/**
 * @param {{ url: string, pi?: string, teacherCode?: string, expect?: string, compile?: boolean, fetch?: typeof fetch }} o
 * @returns {Promise<{ results: {state: "ok"|"fail"|"warn"|"info", title: string, detail?: string, fix?: string}[], ok: boolean, info: object|null }>}
 */
export async function runPreflight({ url, pi = "", teacherCode = "", expect = "", compile = true, fetch: f = fetch }) {
  const base = new URL(url).origin;
  const results = [];
  const add = (state, title, detail, fix) => results.push({ state, title, ...(detail ? { detail } : {}), ...(fix ? { fix } : {}) });
  const get = async (path, init) => {
    try { return await f(base + path, { redirect: "manual", ...init }); } catch (e) { return { status: 0, error: e, headers: new Headers() }; }
  };
  const post = (path, body, headers = {}) => get(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", ...headers }, body: JSON.stringify(body) });
  const json = async (res) => { try { return await res.json(); } catch { return null; } };

  // 1. the server, and which kind and build it is
  const infoRes = await get("/api/info");
  const info = infoRes.status === 200 ? await json(infoRes) : null;
  if (!info || info.app !== "Circuit Pathways") {
    const why = infoRes.error ? String(infoRes.error.cause?.code ?? infoRes.error.message) : `/api/info gave ${infoRes.status}`;
    add("fail", `The server didn't answer at ${base}`, why, /CERT|SELF_SIGNED|UNABLE_TO_VERIFY/.test(why)
      ? "This computer doesn't trust the school server's certificate: run with NODE_EXTRA_CA_CERTS=ca.crt (from http://pathways.local/ca.crt), or use the http:// address."
      : "Check the address, that this computer is on the school network, and on the server Pi: `sudo systemctl status circuitpathways`.");
    return { results, ok: false, info: null };
  }
  const kind = info.edition === "student-pi" ? "student-pi" : "school";
  add("ok", `It's up: the ${KINDS[kind]}${info.name ? ` (${info.name})` : ""}${info.commit ? `, build ${info.commit}` : info.version ? `, version ${info.version}` : ""}`);
  if (expect) {
    if (expect === kind) add("ok", `It is a ${KINDS[expect]}, as expected`);
    else add("fail", `Expected a ${KINDS[expect] ?? expect}, but this is a ${KINDS[kind]}`, undefined, "You may be checking the wrong address.");
  }
  if (kind === "school" && info.tls === false) {
    add("warn", "The school server has no https address", undefined, "Laptops need https to upload to boards and for Python's input(). Start it with -https :443 (the installer does).");
  } else if (kind === "school" && base.startsWith("http:")) {
    add("info", "Checked over http. Laptops should use the https address (set each one up once at /trust)");
  }

  // 2. the pages, and the headers each app needs
  const home = await get("/");
  home.status === 200 ? add("ok", "The home page loads") : add("fail", `The home page gave ${home.status}`);
  const pipath = await get("/pipath/");
  const coop = pipath.headers.get("cross-origin-opener-policy");
  const coep = pipath.headers.get("cross-origin-embedder-policy");
  if (pipath.status !== 200) add("fail", `PiPath gave ${pipath.status}`);
  else if (coop !== "same-origin" || coep !== "require-corp") {
    add("fail", "PiPath can't run Python: the isolation headers are missing", `COOP=${coop} COEP=${coep}`,
      "Python in the browser needs `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` on /pipath/. Is something in between (a proxy) removing them?");
  } else add("ok", "PiPath has the headers Python needs (cross-origin isolation)");
  const arduino = await get("/arduinopath/");
  const perms = arduino.headers.get("permissions-policy") ?? "";
  if (arduino.status !== 200) add("fail", `ArduinoPath gave ${arduino.status}`);
  else if (!/serial=\(self\)/.test(perms) || !/usb=\(self\)/.test(perms)) {
    add("fail", "ArduinoPath can't use USB: the Permissions-Policy blocks it", perms || "(no header)", "It must allow `serial=(self)` and `usb=(self)`, or Chrome won't offer the boards.");
  } else add("ok", "ArduinoPath is allowed to use USB serial (Web Serial and WebUSB)");

  // 3. the big files, and that they are cached
  const wasm = await get("/pipath/vendor/pyodide/pyodide.asm.wasm", { method: "HEAD" });
  if (wasm.status !== 200) add("fail", `Python's engine (pyodide) is missing: ${wasm.status}`);
  else {
    const type = wasm.headers.get("content-type") ?? "";
    const cache = wasm.headers.get("cache-control") ?? "";
    if (!/wasm/.test(type)) add("fail", "Python's engine is served as the wrong type", type, "It must be `application/wasm`.");
    else if (!/max-age=\d{5,}/.test(cache)) add("warn", "Python's engine isn't cached for long", cache || "(no Cache-Control)", "Laptops will download 12 MB on every visit. Update Circuit Pathways on the server.");
    else add("ok", "Python's engine is served right and cached for a week");
  }
  const esp = await get("/arduinopath/vendor/esptool-js/bundle.js", { method: "HEAD" });
  esp.status === 200 ? add("ok", "The ESP uploader (esptool-js) is there") : add("fail", `The ESP uploader is missing: ${esp.status}`);

  // 4. a student Pi: can it reach the school server?
  if (kind === "student-pi") {
    if (info.online) add("ok", `This Pi can reach the school server (${info.school_server})`);
    else add("warn", `This Pi can't reach the school server (${info.school_server}) right now`, undefined,
      "Students can still work (it's saved on the Pi). For classes and uploads: check the Pi's network, and that the school server is on. On the Pi: `journalctl -u circuitpathways -n 30`.");
  }

  // 5. teachers and classes
  let teacherToken = "";
  if (teacherCode) {
    const t = await post("/api/teacher/signin", { code: teacherCode });
    const body = await json(t);
    if (t.status === 200 && body?.token) {
      teacherToken = body.token;
      add("ok", "A teacher can sign in with that code");
    } else if (t.status === 503) add("fail", "Signing in needs the school server, and it can't be reached from here", body?.message);
    else add("fail", `That teacher code didn't work (${t.status})`, body?.message, "On the school server: `sudo circuitpathways teacher list` shows the codes.");
    if (teacherToken) {
      const made = await post("/api/teacher/class", { name: "Preflight check", days: 1 }, { Authorization: `Bearer ${teacherToken}` });
      const body2 = await json(made);
      if (made.status === 200 && body2?.code) {
        add("ok", "A teacher can make a class");
        const join = await post("/api/class/join", { code: body2.code });
        join.status === 200 ? add("ok", "A student can find that class by its code") : add("fail", `A student couldn't find the class (${join.status})`);
        // tidy up: a class made by the check shouldn't linger
        await get(`/api/teacher/class/${body2.code}`, { method: "DELETE", headers: { "X-Circuit-Pathways": "1", Authorization: `Bearer ${teacherToken}` } });
      } else add("fail", `A teacher couldn't make a class (${made.status})`, body2?.message, "Look at the server's log: `journalctl -u circuitpathways -n 50`.");
    }
  } else add("info", "Teacher sign-in not checked (add --teacher-code)");

  // 6. uploading to a real board needs a compiler (on the school server, or on a student Pi with the board tools)
  if (!info.compile) {
    add("fail", "Uploading to a board won't work: there's no compiler", undefined, kind === "student-pi"
      ? "This Pi uses the school server's compiler: check the school server is on and has the board tools."
      : "Install the board tools on the school server (needs the internet once): `sudo -u circuitpathways circuitpathways -setup -warm -tools /opt/circuitpathways`, then `sudo systemctl restart circuitpathways`. The simulator still works.");
  } else if (!compile) {
    add("info", "The compiler is there (not tried: --no-compile)");
  } else {
    const t0 = Date.now();
    const c = await post("/api/compile", { code: BLINK, board: "uno" }, { "X-Access": teacherToken || "local" });
    const body = await json(c);
    const secs = Math.round((Date.now() - t0) / 1000);
    if (c.status === 200 && body?.ok && body.artifacts?.length) add("ok", `A real compile worked (Blink for the Uno, ${secs} s)`);
    else add("fail", `The real compile failed (${c.status})`, body?.message || body?.output?.slice(0, 200), "Look at the server's log: `journalctl -u circuitpathways -n 50`. The first compile after a restart is slow.");
  }

  // 7. Pi Link (a student Pi)
  if (kind === "student-pi" && info.relay === "off") add("fail", "Pi Link is switched off on this Pi", undefined, "Run the student Pi installer again.");
  if (kind === "school" && !pi) add("info", "Pi Link runs on each student Pi: check one with  node tools/preflight.mjs http://localhost:8080 --pi ID  on that Pi");
  if (pi) {
    const p = await post("/api/pi/command", { code: pi, cmd: { op: "ping" } }, { "X-Access": "local" });
    if (p.status === 204 || p.status === 200) add("ok", `The Pi ${pi}'s Pi Link is connected right now`);
    else if (p.status === 404) add("fail", `The Pi ${pi}'s Pi Link isn't connected`, undefined, "On the Pi: `pilink status` and `pilink log`. Its ID is in `pilink id`.");
    else if (p.status === 503) add("fail", "Pi Link is switched off here", (await json(p))?.message, "Check it on the student Pi itself (http://localhost:8080).");
    else add("fail", `Checking the Pi gave ${p.status}`, (await json(p))?.message);
  }

  // 8. the school server can set up student Pis
  if (kind === "school") {
    const inst = await get("/install/student-pi.sh", { method: "HEAD" });
    if (inst.status === 200) add("ok", "Student Pis can be set up from here (/install/student-pi.sh)");
    else add("warn", `The student Pi installer isn't available (${inst.status})`, undefined, "It is there when the school server runs on a 64-bit Pi with https (the installer sets that up).");
  }

  return { results, ok: !results.some((r) => r.state === "fail"), info };
}

const ICON = { ok: "✓", fail: "✗", warn: "!", info: "·" };

function print({ results, ok }) {
  const colour = process.stdout.isTTY ? { ok: "\x1b[32m", fail: "\x1b[31m", warn: "\x1b[33m", info: "\x1b[2m", off: "\x1b[0m" } : { ok: "", fail: "", warn: "", info: "", off: "" };
  console.log("");
  for (const r of results) {
    console.log(`  ${colour[r.state]}${ICON[r.state]}${colour.off} ${r.title}`);
    if (r.detail) console.log(`      ${colour.info}${r.detail}${colour.off}`);
    if (r.fix && r.state !== "ok") console.log(`      → ${r.fix}`);
  }
  const fails = results.filter((r) => r.state === "fail").length;
  const warns = results.filter((r) => r.state === "warn").length;
  console.log("");
  console.log(ok ? `  ${colour.ok}Ready for the test day${colour.off}${warns ? ` (with ${warns} thing${warns > 1 ? "s" : ""} to look at)` : ""}.` : `  ${colour.fail}Not ready: ${fails} thing${fails > 1 ? "s" : ""} to fix first.${colour.off}`);
  console.log("");
}

function parse(argv) {
  const o = { compile: true };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-compile") o.compile = false;
    else if (a === "--pi") o.pi = argv[++i];
    else if (a === "--teacher-code") o.teacherCode = argv[++i];
    else if (a === "--expect") o.expect = argv[++i];
    else if (a === "--help" || a === "-h") o.help = true;
    else rest.push(a);
  }
  o.url = rest[0];
  return o;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const o = parse(process.argv.slice(2));
  if (o.help || !o.url) {
    console.log("Usage: node tools/preflight.mjs <server address> [--teacher-code CODE] [--pi ID] [--expect school|student-pi] [--no-compile]");
    process.exit(o.help ? 0 : 2);
  }
  try {
    const r = await runPreflight(o);
    print(r);
    process.exit(r.ok ? 0 : 1);
  } catch (e) {
    console.error(`Sorry: ${e.message}`);
    process.exit(2);
  }
}
