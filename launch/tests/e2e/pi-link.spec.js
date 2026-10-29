// The Pi Link prototype with all three real parts: this site's server, the
// Pi app (in --mock mode, so no Pi is needed) and the browser page.
import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";

let pi;
let piOut = "";

test.beforeEach(async ({ baseURL }) => {
  pi = spawn("python3", ["site/pipath/remote/circuitpathways_pi.py", "--mock", "--server", baseURL], { stdio: ["pipe", "pipe", "pipe"] });
  piOut = "";
  pi.stdout.on("data", (d) => { piOut += d; });
  pi.stderr.on("data", (d) => { piOut += d; });
});

test.afterEach(() => { pi?.kill(); });

async function pairingCode() {
  await expect.poll(() => /\b([0-9A-Z]{3}-[0-9A-Z]{3})\b/.exec(piOut)?.[1] ?? "", { timeout: 15_000 }).not.toBe("");
  return /\b([0-9A-Z]{3}-[0-9A-Z]{3})\b/.exec(piOut)[1];
}

test("a browser pairs with a Pi and controls its pins", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) problems.push(m.text()); });

  const code = await pairingCode();
  await page.goto("/pipath/remote/");
  await expect(page.locator("#cmd")).toContainText("circuitpathways_pi.py");

  // a wrong code is explained, a right one connects
  await page.fill("#code", "ZZZ-ZZZ");
  await page.getByRole("button", { name: /Connect/ }).click();
  await expect(page.locator("#status")).toContainText("isn't connected");
  await page.fill("#code", code.toLowerCase());
  await page.getByRole("button", { name: /Connect/ }).click();
  await expect(page.locator("#panel")).toBeVisible();
  await expect(page.locator("#pi-info")).toContainText("Pretend Pi");
  await expect(page.locator("#pi-name")).toHaveText("Raspberry Pi");

  // an output pin: set it up, turn it on and off, and the page shows what the Pi really reports
  const gpio17 = page.getByRole("button", { name: "GPIO 17, physical pin 11" });
  await gpio17.click();
  await expect(page.locator("#pin-title")).toContainText("GPIO 17 (physical pin 11)");
  await page.getByLabel("Output (LED, buzzer)").check();
  await page.getByRole("button", { name: "Turn ON" }).click();
  await expect(gpio17.locator(".dot")).toHaveClass(/out-on/);
  await expect(page.getByRole("button", { name: "Turn OFF" })).toBeVisible();
  await page.getByRole("button", { name: "Turn OFF" }).click();
  await expect(gpio17.locator(".dot")).toHaveClass(/out-off/);
  await page.screenshot({ path: "test-results/screenshots/pi-link.png" });

  // PWM
  const gpio18 = page.getByRole("button", { name: "GPIO 18, physical pin 12" });
  await gpio18.click();
  await page.getByLabel("PWM (dim an LED)").check();
  await page.locator("#duty").fill("40");
  await expect(gpio18.locator(".dot")).toHaveClass(/pwm/);
  await expect.poll(() => page.evaluate(() => window.piRemote.pins["18"]?.duty)).toBe(0.4);

  // an input: the pretend button is pressed from the Pi's own keyboard
  const gpio4 = page.getByRole("button", { name: "GPIO 4, physical pin 7" });
  await gpio4.click();
  await page.getByLabel("Input, pull-up (button to GND)").check();
  await expect(page.locator("#reading")).toHaveText("HIGH");
  pi.stdin.write("set 4 0\n"); // pressed: a pull-up input goes low
  await expect(page.locator("#reading")).toHaveText("LOW");
  await expect(gpio4.locator(".dot")).toHaveClass(/in-lo/);
  pi.stdin.write("set 4 1\n");
  await expect(page.locator("#reading")).toHaveText("HIGH");

  // Blink, then Turn everything off
  await page.getByRole("button", { name: /Blink an LED/ }).click();
  const seen = new Set();
  await expect.poll(async () => { seen.add(await page.evaluate(() => window.piRemote.pins["17"]?.value)); return seen.size; }, { timeout: 8000, intervals: [100] }).toBe(2);
  await page.getByRole("button", { name: "Turn everything off" }).click();
  await expect.poll(() => page.evaluate(() => window.piRemote.pins["17"]?.value)).toBe(0);
  await expect.poll(() => page.evaluate(() => window.piRemote.pins["18"]?.duty)).toBe(0);

  // (the browser logs the 404 for the deliberately wrong pairing code; nothing else may appear)
  expect(problems.filter((p) => !/404/.test(p))).toEqual([]);
});

test("the page says so when the Pi app stops, and a second browser takes over", async ({ page, browser, baseURL }) => {
  const code = await pairingCode();
  await page.goto("/pipath/remote/");
  await page.fill("#code", code);
  await page.getByRole("button", { name: /Connect/ }).click();
  await expect(page.locator("#panel")).toBeVisible();

  // a second browser (another student with the same class code) connects: the first is told
  const other = await browser.newContext({ storageState: "test-results/student.json" });
  const page2 = await other.newPage();
  await page2.goto("/pipath/remote/");
  await page2.fill("#code", code);
  await page2.getByRole("button", { name: /Connect/ }).click();
  await expect(page2.locator("#panel")).toBeVisible();
  await expect(page.locator("#status")).toContainText("Someone else connected");

  // the Pi app is stopped
  pi.kill("SIGINT");
  await expect(page2.locator("#pi-info")).toContainText("isn't running", { timeout: 10_000 });
  await other.close();
  void baseURL;
});

test("the Pi app can be downloaded with this website's address filled in", async ({ request, baseURL }) => {
  const res = await request.get("/pipath/remote/circuitpathways_pi.py");
  expect(res.status()).toBe(200);
  const src = await res.text();
  expect(src).toContain(`CIRCUITPATHWAYS_URL", "${baseURL}"`);
  expect(src).not.toContain("onrender.com");
  expect(res.headers()["content-disposition"]).toContain("circuitpathways_pi.py");
});

test("the Pi page needs a class code", async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.goto("/pipath/remote/");
  await page.waitForURL("**/?need=class");
  const res = await ctx.request.post("/api/pi/command", { headers: { "X-Circuit-Pathways": "1" }, data: { code: "ABC-123", cmd: { op: "all_off" } } });
  expect(res.status()).toBe(401);
  await ctx.close();
});
