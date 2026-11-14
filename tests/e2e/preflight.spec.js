// The test-day preflight against the real servers: the school server (dev mode), and a student Pi passing classes
// on to it, with the real Pi app on pretend pins: it must see the Pi come online, and notice when it goes away.
import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { newPiKey } from "./pi-key.js";
import { runPreflight } from "../../tools/preflight.mjs";

const SCHOOL = `http://localhost:${Number(process.env.E2E_PORT) || 8543}`;
const PI = `http://localhost:${Number(process.env.E2E_PI_PORT) || 8546}`;

let pi;
test.afterEach(() => { pi?.kill(); pi = null; });

function startPi(url) {
  const key = newPiKey();
  const asRoot = process.getuid?.() === 0;
  pi = spawn("python3", ["site/pipath/remote/circuitpathways_pi.py", "--mock", "--key", key.key, "--server", url, "--run-dir", mkdtempSync(join(tmpdir(), "cp-run-")), ...(asRoot ? ["--run-user", "nobody"] : [])], { stdio: ["pipe", "pipe", "pipe"] });
  let out = "";
  pi.stdout.on("data", (d) => { out += d; });
  pi.stderr.on("data", (d) => { out += d; });
  return { key, up: () => expect.poll(() => out.includes(key.display), { timeout: 15_000 }).toBe(true) };
}

test("preflight: the school server is ready apart from the compiler, and a teacher can make a class", async () => {
  const r = await runPreflight({ url: SCHOOL, expect: "school", teacherCode: "teacher-code-dev", compile: false });
  const fails = r.results.filter((x) => x.state === "fail").map((x) => x.title);
  // a dev server has no board tools: that is the only thing that may be wrong
  expect(fails.filter((t) => !/no compiler/.test(t)), JSON.stringify(r.results)).toEqual([]);
  expect(r.results.some((x) => /A teacher can make a class/.test(x.title))).toBe(true);
});

test("preflight: a student Pi reaches the school server, and sees its Pi Link come and go", async () => {
  const quiet = await runPreflight({ url: PI, expect: "student-pi", teacherCode: "teacher-code-dev", compile: false });
  expect(quiet.results.filter((x) => x.state === "fail" && !/no compiler/.test(x.title)), JSON.stringify(quiet.results)).toEqual([]);
  expect(quiet.results.some((x) => x.state === "ok" && /can reach the school server/.test(x.title))).toBe(true);
  expect(quiet.results.some((x) => /A teacher can make a class/.test(x.title))).toBe(true); // through the Pi

  const p = startPi(PI);
  await p.up();
  await expect.poll(async () => {
    const online = await runPreflight({ url: PI, pi: p.key.display, compile: false });
    return online.results.some((x) => x.state === "ok" && x.title.includes(`${p.key.display}'s Pi Link is connected`));
  }, { timeout: 20_000 }).toBe(true);

  pi.kill();
  await expect.poll(async () => {
    const gone = await runPreflight({ url: PI, pi: p.key.display, compile: false });
    return gone.results.some((x) => x.state === "fail" && x.title.includes("isn't connected"));
  }, { timeout: 20_000 }).toBe(true);
});
