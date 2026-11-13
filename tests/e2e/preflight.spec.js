// The test-day preflight against the real servers, with the real Pi app on pretend pins: it must see the Pi
// come online, and notice when it goes away. (Both the Go site and the Cloudflare Pi beta.)
import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { newPiKey } from "./pi-key.js";
import { runPreflight } from "../../tools/preflight.mjs";

const SITES = {
  "the Go site (real, dev mode)": { url: `http://localhost:${Number(process.env.E2E_PORT) || 8543}`, expect: "real", teacherCode: "teacher-code-dev" },
  "the Cloudflare Pi beta": { url: `http://localhost:${Number(process.env.E2E_PI_PORT) || 8546}`, expect: "pi-beta", teacherCode: "teacher-code-dev" },
  "the Cloudflare TEST version": { url: `http://localhost:${Number(process.env.E2E_CFTEST_PORT) || 8547}`, expect: "test", teacherCode: "a code I made up" },
};

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

for (const [name, site] of Object.entries(SITES)) {
  test(`preflight: ${name} is ready apart from the compiler, and sees the Pi come and go`, async () => {
    const isTest = site.expect === "test";
    const quiet = await runPreflight({ url: site.url, expect: site.expect, teacherCode: site.teacherCode, compile: false });
    const fails = quiet.results.filter((r) => r.state === "fail").map((r) => r.title);
    // a local dev server has no compiler: that is the only thing that may be wrong
    expect(fails.filter((t) => !/no compiler/.test(t)), JSON.stringify(quiet.results)).toEqual([]);
    expect(quiet.results.some((r) => /Beta teacher mode|A teacher can sign in/.test(r.title))).toBe(true);
    if (isTest) return; // the TEST version has no Pi linking

    const p = startPi(site.url);
    await p.up();
    await expect.poll(async () => {
      const online = await runPreflight({ url: site.url, pi: p.key.display, teacherCode: site.teacherCode, compile: false });
      return online.results.some((r) => r.state === "ok" && r.title.includes(`${p.key.display} is connected`));
    }, { timeout: 20_000 }).toBe(true);

    pi.kill();
    await expect.poll(async () => {
      const gone = await runPreflight({ url: site.url, pi: p.key.display, teacherCode: site.teacherCode, compile: false });
      return gone.results.some((r) => r.state === "fail" && r.title.includes("isn't connected"));
    }, { timeout: 20_000 }).toBe(true);
  });
}
