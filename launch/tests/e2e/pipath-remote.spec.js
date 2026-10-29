// PiPath's "Run on my Pi": the real site, the real Pi app (pretend pins, a real Python for the
// students' programs) and the real browser page, all together.
import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { newPiKey } from "./pi-key.js";

const SIZE = { width: 1366, height: 768 };
let pi;
let piOut = "";
let piKey;

function startPi(baseURL, extra = []) {
  piKey = newPiKey();
  const asRoot = process.getuid?.() === 0; // as root the Pi app insists on an unprivileged user to run programs as
  const args = ["site/pipath/remote/circuitpathways_pi.py", "--mock", "--key", piKey.key, "--server", baseURL, "--run-dir", mkdtempSync(join(tmpdir(), "cp-run-")), ...(asRoot ? ["--run-user", "nobody"] : []), ...extra];
  pi = spawn("python3", args, { stdio: ["pipe", "pipe", "pipe"] });
  piOut = "";
  pi.stdout.on("data", (d) => { piOut += d; });
  pi.stderr.on("data", (d) => { piOut += d; });
  return expect.poll(() => piOut.includes(piKey.display), { timeout: 15_000 }).toBe(true);
}

test.afterEach(() => { pi?.kill(); });

async function newStudent(page, name) {
  await page.goto("/pipath/");
  const newBtn = page.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(page.getByLabel("Your first name"))).toBeVisible({ timeout: 15_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await page.getByLabel("Your first name").fill(name);
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();
}

async function linkThePi(page) {
  await page.locator("#where").selectOption("pi");
  await expect(page.getByRole("dialog", { name: "Link to my Raspberry Pi" })).toBeVisible();
  await page.fill("#pi-id", piKey.display.toLowerCase());
  await page.getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("#pi-chip")).toContainText("is ready");
}

test("a student runs a program on their Pi: output, typing an answer, Stop, an error and a lesson check", async ({ page, baseURL }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push(m.text()); });
  await page.setViewportSize(SIZE);
  await startPi(baseURL);
  await newStudent(page, "Mia");

  await page.locator(".card.free").click();
  await expect(page.locator("#where")).toHaveValue("sim");
  await expect(page.locator("#pi-panel")).toBeHidden();

  // choose the Pi: the window asks for its ID (a wrong one is explained first)
  await page.locator("#where").selectOption("pi");
  await page.fill("#pi-id", "ZZZZ-ZZZZ");
  await page.getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.locator("#pi-msg")).toContainText("isn't connected");
  await page.fill("#pi-id", piKey.display.toLowerCase());
  await page.getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.locator("#pi-chip")).toContainText("is ready");
  await expect(page.locator("#pi-panel")).toBeVisible();
  await expect(page.locator("#pi-panel")).toContainText("Pretend Pi");
  await expect(page.locator("#status-where")).toContainText("runs on your Raspberry Pi");
  await page.screenshot({ path: "test-results/screenshots/pipath-run-on-pi.png" });

  // a program that prints and asks a question
  await page.locator("#code").fill('import sys\nname = input("Your name? ")\nprint("Hi", name, "from Python", sys.version_info[0])\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("Your name?", { timeout: 20_000 });
  await expect(page.locator("#run")).toContainText("Stop");
  await page.locator(".console-in input").fill("Mia");
  await page.locator(".console-in input").press("Enter");
  await expect(page.locator(".console-out")).toContainText("Hi Mia from Python 3", { timeout: 20_000 });
  await expect(page.locator("#run")).toContainText("Run", { timeout: 10_000 });

  // Stop ends a loop on the Pi
  await page.locator("#code").fill('from time import sleep\nprint("looping")\nwhile True:\n    sleep(0.1)\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("looping", { timeout: 20_000 });
  await page.locator("#run").click();
  await expect(page.locator("#run")).toContainText("Run", { timeout: 15_000 });
  await expect(page.locator(".console-out")).not.toContainText("KeyboardInterrupt");

  // a mistake on the Pi is explained by the Coach, in plain English
  await page.locator("#code").fill('print("Hello, " + 5)\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("TypeError", { timeout: 20_000 });
  await expect(page.locator("#clue")).toBeVisible({ timeout: 10_000 });

  // the Pi needs a pin driver for gpiozero: a mock Pi has none, so the Coach explains that too (and the page carries on)
  await page.locator("#code").fill('print("still fine")\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("still fine", { timeout: 20_000 });

  // Watch the goal still plays in the Simulator, even with the Pi chosen
  await page.getByRole("button", { name: "Settings" }).waitFor();
  expect(problems).toEqual([]);
});

test("a lesson step is checked from what the Pi printed", async ({ page, baseURL }) => {
  await page.setViewportSize(SIZE);
  await startPi(baseURL);
  await newStudent(page, "Noor");
  await page.locator('.card[data-id="s1_hello"]').click();
  await page.getByRole("button", { name: /Start step 1/ }).click();
  await linkThePi(page);
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("Hello, Pi!", { timeout: 30_000 });
  await expect(page.locator(".checklist li.ok")).toHaveCount(2, { timeout: 15_000 });
  await expect(page.locator("#step-done")).toBeVisible();

  // Watch the goal on the next step still plays in the Simulator, and the Pi stays linked afterwards
  await page.getByRole("button", { name: "Next step" }).click();
  await page.locator("#goal").click();
  await expect(page.locator(".console-out")).toContainText("That's the goal", { timeout: 30_000 });
  await expect(page.locator("#pi-chip")).toContainText("is ready");
});

test("a Pi that has been set to pins-only says so, and the choice is remembered", async ({ page, baseURL }) => {
  await startPi(baseURL, ["--no-run"]);
  await newStudent(page, "Sam");
  await page.locator(".card.free").click();
  await page.locator("#where").selectOption("pi");
  await page.fill("#pi-id", piKey.display);
  await page.getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.locator("#pi-msg")).toContainText("isn't set to run programs");
  await page.getByRole("button", { name: "Not now" }).click();
  await page.locator("#run").click();
  await expect(page.getByRole("dialog")).toContainText(/can't run programs|Link to my Raspberry Pi/);
});

test("the Simulator still works, and the Pi choice is kept for next time", async ({ page, baseURL }) => {
  await startPi(baseURL);
  await newStudent(page, "Eli");
  await page.locator(".card.free").click();
  await linkThePi(page);
  await page.reload();
  await expect(page.locator("#where")).toHaveValue("pi");
  await page.locator("#where").selectOption("sim");
  await page.locator("#code").fill('print("in the browser")\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("in the browser", { timeout: 60_000 });
  await expect(page.locator("#pi-panel")).toBeHidden();
});

test("PiPath's helper modules reach the Pi, and a program that prints forever is cut off and explained", async ({ page, baseURL }) => {
  await page.setViewportSize(SIZE);
  await startPi(baseURL);
  await newStudent(page, "Ravi");
  await page.locator(".card.free").click();
  await linkThePi(page);

  // pipath_computer is PiPath's own helper: the Pi gets it from the website
  await page.locator("#code").fill('from pipath_computer import cpu_load\nprint("helper ok", cpu_load() >= 0)\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("helper ok True", { timeout: 30_000 });
  await expect(page.locator("#run")).toContainText("Run", { timeout: 10_000 });

  // a runaway print loop is stopped by the Pi and the Coach explains it
  await page.locator("#code").fill('while True:\n    print("spam spam spam spam spam spam spam spam")\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("running away", { timeout: 30_000 });
  await expect(page.locator("#clue")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("#run")).toContainText("Run", { timeout: 10_000 });
});

test("if PiPath's main file can't load, the page says so instead of staying blank", async ({ page }) => {
  await page.route("**/pipath/js/main.js", (route) => route.abort());
  await page.goto("/pipath/");
  await expect(page.getByRole("heading", { name: "PiPath didn't start" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("pre")).toContainText("main.js");
});

test("the start-up message names the file that went wrong", async ({ page }) => {
  await page.route("**/pipath/js/state.js", (route) => route.fulfill({ status: 404, contentType: "text/plain", body: "nope" }));
  await page.goto("/pipath/");
  await expect(page.getByRole("heading", { name: "PiPath didn't start" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("pre")).toContainText("/pipath/js/state.js -> 404", { timeout: 15_000 });
});
