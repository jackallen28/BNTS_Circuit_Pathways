// The TEST version (BETA=1): the same home page with PiPath and ArduinoPath, labelled TEST, no
// class codes or teacher sign-in, and nothing saved.
import { test, expect } from "@playwright/test";

const BETA = `http://localhost:${Number(process.env.E2E_BETA_PORT) || 8544}`;
test.use({ baseURL: BETA, storageState: { cookies: [], origins: [] } });

test("the home page says TEST and has no class or teacher boxes", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/^TEST: /);
  await expect(page.locator("#test-tag")).toBeVisible();
  await expect(page.locator("#test-tag")).toHaveAttribute("aria-label", /Nothing is saved/);
  await expect(page.locator("#test-ribbon")).toHaveCount(0);
  await expect(page.locator("h1 .beta-badge")).toHaveText("BETA");
  await expect(page.getByRole("link", { name: /Open PiPath/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open ArduinoPath/ })).toBeVisible();
  for (const gone of ["#session", "#join-form", "#teacher-form", ".scroll-hint"]) await expect(page.locator(gone)).toBeHidden();
  expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/class code|teacher code|teacher sign/i); // (innerText leaves out hidden parts)
  expect((await page.request.get("/teacher/")).status()).toBe(404);
  expect((await page.request.get("/api/pi/events?code=X")).status()).toBe(404);
  expect((await page.request.get("/api/info")).headers()["x-robots-tag"]).toContain("noindex");
  await page.screenshot({ path: "test-results/screenshots/test-home.png" });
});

test("PiPath opens with no class code, runs Python, offers no saving, and forgets on reload", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push(m.text()); });
  await page.goto("/pipath/");
  await expect(page).toHaveURL(/\/pipath\/$/); // no redirect to a class-code page
  const newBtn = page.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(page.getByLabel("Your first name"))).toBeVisible({ timeout: 15_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await page.getByLabel("Your first name").fill("Colleague");
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();
  await expect(page.locator("#test-tag")).toBeVisible();
  await expect(page.getByText("Your browser isn't keeping your work")).toHaveCount(0);

  await page.locator(".card.free").click();
  await expect(page.locator("#where")).toHaveCount(0); // no "Run on my Raspberry Pi" here
  await page.locator("#code").fill('print("hello from the test")\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("hello from the test", { timeout: 60_000 });
  await expect(page.locator("#save-status")).toHaveText("");

  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "My work" }).or(page.getByText("My work", { exact: true })).first().click();
  await expect(page.getByRole("dialog")).toContainText("TEST version");
  await expect(page.locator("#save-work")).toHaveCount(0);
  await expect(page.locator("#open-work")).toHaveCount(0);
  await page.getByRole("button", { name: "OK" }).click();

  // nothing was kept: a reload starts again
  await page.reload();
  await expect(page.getByRole("button", { name: "I'm new here" }).or(page.getByLabel("Your first name"))).toBeVisible();
  await expect(page.getByText("Colleague", { exact: true })).toHaveCount(0);
  expect(problems).toEqual([]);
});

test("ArduinoPath opens with no class code, and has no save or download buttons", async ({ page }) => {
  await page.goto("/arduinopath/");
  await expect(page).toHaveURL(/\/arduinopath\/$/);
  await expect(page.getByRole("button", { name: /Wipe this browser/ })).toHaveCount(0);
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible({ timeout: 15_000 });
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await page.getByLabel("First name", { exact: true }).fill("Colleague");
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).click();
  await page.getByText("Arduino Uno R3").click();
  await page.getByRole("button", { name: "Let's go!" }).click();
  await expect(page.getByRole("heading", { name: /Hi Colleague!/ })).toBeVisible();
  await expect(page.locator("#test-tag")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save my work" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open my work" })).toHaveCount(0);
  await expect(page.getByText("Your browser isn't keeping your work")).toHaveCount(0);

  // into a project: no Download .ino, and the save note stays empty
  await page.locator(".project-card, .card").filter({ hasText: "Blink" }).first().click();
  const wizard = page.getByRole("dialog", { name: /Wiring Wizard/ });
  if (await wizard.isVisible({ timeout: 5000 }).catch(() => false)) await wizard.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("button", { name: "Download .ino" })).toHaveCount(0);
  await expect(page.getByText("Saved ✓")).toHaveCount(0);
  await page.screenshot({ path: "test-results/screenshots/test-arduinopath.png" });
});
