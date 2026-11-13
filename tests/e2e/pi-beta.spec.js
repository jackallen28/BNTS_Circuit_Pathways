// The Pi beta (a local Worker with PI_BETA=1): students on a Raspberry Pi start with no class code and
// their work is saved on the device; if they join a class, the same work syncs to the class database.
import { test, expect } from "@playwright/test";

const PI = `http://localhost:${Number(process.env.E2E_PI_PORT) || 8546}`;
test.use({ baseURL: PI, storageState: { cookies: [], origins: [] } });

async function newStudent(page, name, school = "Eltham High") {
  await page.goto("/pipath/");
  const newBtn = page.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(page.getByLabel("Your first name"))).toBeVisible({ timeout: 20_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await page.getByLabel("Your first name").fill(name);
  await page.getByLabel("Your school").fill(school);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();
}

test("no class code needed: work is saved on the device, and the home page says so", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await expect(page.locator("#beta-badge")).toBeVisible();
  await expect(page.locator("#optional-note")).toBeVisible();
  await expect(page.locator("#optional-note")).toContainText("saved on this device");
  await expect(page.locator("#privacy")).toContainText("device only");
  await expect(page.locator("#build")).toContainText("Pi beta, Cloudflare"); // which build this is, for bug reports
  await expect(page.locator("#test-tag")).toHaveCount(0); // it saves, so no TEST ticker
  await expect(page.locator("#session-forms")).toBeVisible(); // the class code is optional, not hidden
  await expect(page.locator("#teacher-hint")).toContainText("make up a teacher code"); // beta teacher mode
  await page.screenshot({ path: "test-results/screenshots/pi-beta-home.png" });

  // straight into PiPath, no code
  await page.getByRole("link", { name: /Open PiPath/ }).first().click();
  await expect(page).toHaveURL(/\/pipath\//);
  await newStudent(page, "Ben");
  await page.locator(".card.free").click();
  await page.locator("#code").fill('print("saved on this Pi")\n');
  await expect(page.locator("#save-status")).toContainText("Saved", { timeout: 10_000 });
  await page.reload();
  // the same device a moment later: the session resumes and the code is still here
  await expect(page.locator("#code")).toHaveValue(/saved on this Pi/);
  // nothing was sent to a class
  const access = await page.evaluate(() => localStorage.getItem("circuitpathways.access"));
  expect(access).toBeNull();
  expect(problems).toEqual([]);
});

test("ArduinoPath opens with no class code too", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/arduinopath/");
  await expect(page).toHaveURL(/\/arduinopath\//); // not sent back to the home page
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible({ timeout: 20_000 });
  expect(problems).toEqual([]);
});

test("joining a class later saves the work to the class database", async ({ page, browser }) => {
  // a teacher makes a class
  const tctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const tp = await tctx.newPage();
  await tp.goto(`${PI}/`);
  await tp.locator("#teacher-form input[name=teacher]").fill("teacher-code-dev");
  await tp.getByRole("button", { name: /Teacher sign in/ }).click();
  await tp.waitForURL("**/teacher/");
  await tp.locator("#c-name").fill("9C Pi class");
  await tp.locator("#c-school").fill("Eltham High");
  await tp.getByRole("button", { name: "Make class ▸" }).click();
  await expect(tp.locator("#roster")).toBeVisible();
  const code = (await tp.locator("#r-code").textContent()).trim();

  // the student starts with no class and writes some code
  await newStudent(page, "Cleo");
  await page.locator(".card.free").click();
  await page.locator("#code").fill('print("before the class")\n');
  await expect(page.locator("#save-status")).toContainText("Saved", { timeout: 10_000 });

  // ...then joins the class on the home page (first name and school)
  await page.goto("/");
  await page.locator("#join-form input[name=code]").fill(code);
  await page.getByRole("button", { name: /Join class/ }).click();
  await expect(page.locator("#join-class")).toContainText("9C Pi class");
  await page.locator("#join-form input[name=names]").fill("Cleo");
  await page.getByRole("button", { name: /^Join/ }).click();
  await expect(page.locator("#session-in-text")).toContainText("as Cleo");
  await expect(page.locator("#optional-note")).toBeHidden();

  // back in PiPath her local profile is linked to the class, and what she wrote is sent up
  await page.goto("/pipath/");
  await page.locator(".card.free").click();
  await expect(page.locator("#code")).toHaveValue(/before the class/);

  // the teacher sees Cleo and her code
  await expect.poll(async () => {
    await tp.getByRole("button", { name: "Refresh" }).click();
    return tp.locator("#r-table").textContent();
  }, { timeout: 30_000 }).toContain("Cleo");
  await expect.poll(async () => {
    await tp.getByRole("button", { name: "Refresh" }).click();
    await tp.getByRole("button", { name: "See work" }).first().click();
    return tp.locator("#r-work").textContent();
  }, { timeout: 30_000 }).toContain("before the class");

  // leaving the class goes back to this-device saving, with the work still here
  await page.goto("/");
  await page.getByRole("button", { name: "Leave this class" }).click();
  await expect(page.locator("#optional-note")).toBeVisible();
  await tctx.close();
});
