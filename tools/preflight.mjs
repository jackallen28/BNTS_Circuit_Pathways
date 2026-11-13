#!/usr/bin/env node
// Is this site ready for a test day with a real Raspberry Pi and Arduino?
//
//   node tools/preflight.mjs https://your-site.example
//   node tools/preflight.mjs https://your-site.example --pi K7M2-QX9P --teacher-code "my teacher code"
//
// It only needs Node 18 or newer (no packages). It checks the things that fail quietly on the day:
// which edition and build is live, whether Python can run (the isolation headers), whether uploading to a board can
// work (USB permissions, a real compile), whether the Pi app points at this site, whether a Pi is connected, and
// whether teachers can make classes. Each failure says what to do about it.
//
// Options:
//   --pi ID              also check that the Pi with this ID is connected right now
//   --teacher-code CODE  a teacher code (or on the TEST / Pi beta, any code you make up: 8+ characters).
//                        It lets the checks that need a class (the compile, the Pi) run on the real site
//   --access TOKEN       or a class token / class code, if you have one instead
//   --expect EDITION     real | pi-beta | test: fail if the site is a different edition
//   --no-compile         skip the real compile (it can take half a minute the first time)
//
// Exit status: 0 if nothing blocks the test day, 1 if something does.

const BLINK = "void setup() { pinMode(LED_BUILTIN, OUTPUT); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); delay(500); digitalWrite(LED_BUILTIN, LOW); delay(500); }\n";
const EDITION_NAMES = { "": "real site", "pi-beta": "Pi beta", test: "TEST version" };

/**
 * @param {{ url: string, pi?: string, teacherCode?: string, access?: string, expect?: string, compile?: boolean, fetch?: typeof fetch }} o
 * @returns {Promise<{ results: {state: "ok"|"fail"|"warn"|"info", title: string, detail?: string, fix?: string}[], ok: boolean, info: object|null }>}
 */
export async function runPreflight({ url, pi = "", teacherCode = "", access = "", expect = "", compile = true, fetch: f = fetch }) {
  const base = new URL(url).origin;
  const results = [];
  const add = (state, title, detail, fix) => results.push({ state, title, ...(detail ? { detail } : {}), ...(fix ? { fix } : {}) });
  const get = async (path, init) => {
    try { return await f(base + path, { redirect: "manual", ...init }); } catch (e) { return { status: 0, error: e, headers: new Headers() }; }
  };
  const post = (path, body, headers = {}) => get(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", ...headers }, body: JSON.stringify(body) });
  const json = async (res) => { try { return await res.json(); } catch { return null; } };

  // 1. the site, and which edition and build it is
  const infoRes = await get("/api/info");
  const info = infoRes.status === 200 ? await json(infoRes) : null;
  if (!info || info.app !== "Circuit Pathways") {
    add("fail", `The site didn't answer at ${base}`, infoRes.error ? String(infoRes.error.cause?.code ?? infoRes.error.message) : `/api/info gave ${infoRes.status}`,
      "Check the address, and that the site is deployed (on Render a free site takes about a minute to wake up).");
    return { results, ok: false, info: null };
  }
  const edition = info.edition ?? (info.beta ? "test" : "");
  const name = EDITION_NAMES[edition] ?? edition;
  add("ok", `The site is up: ${name}${info.host ? `, on ${info.host}` : ""}${info.commit ? `, build ${info.commit}` : ""}`);
  if (expect) {
    const want = expect === "real" ? "" : expect;
    if (want === edition) add("ok", `It is the ${EDITION_NAMES[want]}, as expected`);
    else add("fail", `Expected the ${EDITION_NAMES[want] ?? expect}, but this is the ${name}`, undefined, "You may be testing the wrong site: check the address.");
  }
  if (!info.commit && ["cloudflare", "render"].includes(info.host)) add("warn", "The build number isn't shown", undefined, "Deploy with `npm run deploy:pi` (or deploy / deploy:test) so the About box says which build testers are on.");

  // 2. the pages, and the headers each app needs
  const home = await get("/");
  home.status === 200 ? add("ok", "The home page loads") : add("fail", `The home page gave ${home.status}`);
  const pipath = await get("/pipath/");
  const coop = pipath.headers.get("cross-origin-opener-policy");
  const coep = pipath.headers.get("cross-origin-embedder-policy");
  if (pipath.status !== 200) add("fail", `PiPath gave ${pipath.status}`);
  else if (coop !== "same-origin" || coep !== "require-corp") {
    add("fail", "PiPath can't run Python: the isolation headers are missing", `COOP=${coop} COEP=${coep}`,
      "Python in the browser needs `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` on /pipath/. Check a proxy or CDN in front isn't removing them.");
  } else add("ok", "PiPath has the headers Python needs (cross-origin isolation)");
  const arduino = await get("/arduinopath/");
  const perms = arduino.headers.get("permissions-policy") ?? "";
  if (arduino.status !== 200) add("fail", `ArduinoPath gave ${arduino.status}`);
  else if (!/serial=\(self\)/.test(perms) || !/usb=\(self\)/.test(perms)) {
    add("fail", "ArduinoPath can't use USB: the Permissions-Policy blocks it", perms || "(no header)",
      "It must allow `serial=(self)` and `usb=(self)`, or Chrome won't offer the boards.");
  } else add("ok", "ArduinoPath is allowed to use USB serial (Web Serial and WebUSB)");

  // 3. the big files, and that they are cached
  const wasm = await get("/pipath/vendor/pyodide/pyodide.asm.wasm", { method: "HEAD" });
  if (wasm.status !== 200) add("fail", `Python's engine (pyodide) is missing: ${wasm.status}`);
  else {
    const type = wasm.headers.get("content-type") ?? "";
    const cache = wasm.headers.get("cache-control") ?? "";
    if (!/wasm/.test(type)) add("fail", "Python's engine is served as the wrong type", type, "It must be `application/wasm`.");
    else if (!/max-age=\d{5,}/.test(cache)) add("warn", "Python's engine isn't cached for long", cache || "(no Cache-Control)", "A Pi on slow WiFi will download 12 MB on every visit. Check the site was deployed from `main`.");
    else add("ok", "Python's engine is served right and cached for a week (quick on a Pi after the first time)");
  }
  const esp = await get("/arduinopath/vendor/esptool-js/bundle.js", { method: "HEAD" });
  esp.status === 200 ? add("ok", "The ESP uploader (esptool-js) is there") : add("fail", `The ESP uploader is missing: ${esp.status}`);

  // 4. teachers and classes
  let teacherToken = "";
  {
    if (teacherCode) {
      const t = await post("/api/teacher/signin", { code: teacherCode });
      const body = await json(t);
      if (t.status === 200 && body?.token) {
        teacherToken = body.token;
        add("ok", "A teacher can sign in with that code");
      } else add("fail", `That teacher code didn't work (${t.status})`, body?.message, edition === "" ? "On the real site only the school's TEACHER_CODES work." : "Use 8 or more characters.");
    } else if (info.teacher_mode) {
      const made = `preflight-${Math.random().toString(36).slice(2, 12)}`;
      const t = await post("/api/teacher/signin", { code: made });
      const body = await json(t);
      if (t.status === 200 && body?.token) { teacherToken = body.token; add("ok", "Beta teacher mode works: a made-up teacher code signs in"); }
      else add("fail", `Beta teacher mode didn't work (${t.status})`, body?.message);
    } else add("info", "Teacher sign-in not checked (add --teacher-code)");
    if (teacherToken) {
      // (the Cloudflare site keeps classes, so they have a name and school; the Go site only makes a code)
      const made = await post("/api/teacher/class", info.classes ? { name: "Preflight", school: "Preflight", days: 1 } : { days: 1 }, { Authorization: `Bearer ${teacherToken}` });
      const body = await json(made);
      if (made.status === 200 && body?.code) {
        add("ok", "A teacher can make a class");
        const join = await post("/api/class/join", { code: body.code });
        join.status === 200 ? add("ok", "A student can find that class by its code") : add("fail", `A student couldn't join the class (${join.status})`);
        if (info.classes) {
          // tidy up: a class made by the check shouldn't linger (Cloudflare keeps classes; the Go site's codes keep nothing)
          await get(`/api/teacher/class/${body.code}`, { method: "DELETE", headers: { "X-Circuit-Pathways": "1", Authorization: `Bearer ${teacherToken}` } });
        }
      } else add("fail", `A teacher couldn't make a class (${made.status})`, body?.message, "On Cloudflare this needs the D1 database: check `wrangler d1 migrations apply` ran and CLASS_SECRET is set.");
    }
  }

  // 5. who may use the compiler and the Pi (the access the apps would send)
  const accessWord = access || teacherToken || (edition === "test" ? "beta" : edition === "pi-beta" ? "local" : "");

  // 6. uploading to a real board needs a compiler
  if (!info.compile) {
    add("fail", "Uploading to a board won't work: this site has no compiler", undefined,
      "Run the compiler somewhere (render.paid.yaml, or `circuitpathways -setup` on any computer) and give this site its address: `wrangler secret put COMPILE_URL` and `COMPILE_KEY`. The simulator still works.");
  } else if (!compile) {
    add("info", "The compiler is set up (not tried: --no-compile)");
  } else if (!accessWord) {
    add("warn", "The compiler is set up, but couldn't be tried without a class", undefined, "Add --teacher-code or --access.");
  } else {
    const t0 = Date.now();
    const c = await post("/api/compile", { code: BLINK, board: "uno" }, { "X-Access": accessWord });
    const body = await json(c);
    const secs = Math.round((Date.now() - t0) / 1000);
    if (c.status === 200 && body?.ok && body.artifacts?.length) add("ok", `A real compile worked (Blink for the Uno, ${secs} s)`);
    else add("fail", `The real compile failed (${c.status})`, body?.message || body?.output?.slice(0, 200), "Check the compiler's own log. On Render the image must finish building (the first build downloads about 1.5 GB).");
  }

  // 7. the Pi app and the Pi
  const piApp = await get("/pipath/remote/circuitpathways_pi.py");
  if (piApp.status !== 200 && edition === "test" && !pi) {
    add("info", "The TEST version has no Pi linking (use the Pi beta or the real site to test a Pi)");
  } else if (piApp.status !== 200) {
    add("fail", `The Pi app can't be downloaded (${piApp.status})`, undefined, edition === "test" ? "The TEST version has no Pi linking; use the Pi beta or the real site." : "Check the site was deployed from `main`.");
  } else {
    const text = await piApp.text();
    text.includes(base) ? add("ok", "The Pi app downloads and points at this site") : add("fail", "The Pi app points at a different site", undefined, "It should contain this site's address. Regenerate the Pi installers with `circuitpathways -pi-refresh ... -server " + base + "`.");
  }
  if (info.relay === "off") add("warn", "Pi linking is switched off on this site", undefined, "Set `PI_KEY_SECRET` (the same value the Pi keys were made with).");
  if (pi) {
    if (!accessWord) add("warn", "Couldn't check the Pi: it needs a class or a teacher code", undefined, "Add --teacher-code, or --access.");
    else {
      const p = await post("/api/pi/command", { code: pi, cmd: { op: "ping" } }, { "X-Access": accessWord });
      if (p.status === 204 || p.status === 200) add("ok", `The Pi ${pi} is connected right now`);
      else if (p.status === 404) add("fail", `The Pi ${pi} isn't connected`, undefined, "Is it switched on and on the network? On the Pi: `pilink status` and `pilink log`. Its server must be this site: `sudo pilink server " + base + "`.");
      else if (p.status === 401) add("fail", "The site wouldn't let the check talk to the Pi (401)", undefined, "Give --teacher-code or --access.");
      else add("fail", `Checking the Pi gave ${p.status}`, (await json(p))?.message);
    }
  } else add("info", "No Pi checked (add --pi K7M2-QX9P to check one is connected)");

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
    else if (a === "--access") o.access = argv[++i];
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
    console.log("Usage: node tools/preflight.mjs <site address> [--pi ID] [--teacher-code CODE] [--access TOKEN] [--expect real|pi-beta|test] [--no-compile]");
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
