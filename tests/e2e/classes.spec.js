// Classes on the school server, from start to finish in real browsers: a teacher signs in, makes a class and sets
// work; a student joins on the home page, sees the work, opens it, and their progress shows on the teacher portal.
// Then the same through a student Pi, which passes everything on to the school server.
import { test, expect } from "@playwright/test";

const PI = `http://localhost:${Number(process.env.E2E_PI_PORT) || 8546}`;
const fresh = { storageState: { cookies: [], origins: [] } };

async function teacherMakesAClass(browser, base, name) {
  const ctx = await browser.newContext({ ...fresh, baseURL: base });
  const page = await ctx.newPage();
  await page.goto("/");
  await page.getByLabel("Teacher code").fill("teacher-code-dev");
  await page.getByRole("button", { name: /Teacher sign in/ }).click();
  await page.waitForURL("**/teacher/");
  await expect(page.getByRole("heading", { name: "1. My classes" })).toBeVisible();
  await page.locator("#c-name").fill(name);
  await page.getByRole("button", { name: "Make class ▸" }).click();
  await expect(page.locator("#c-note")).toContainText(`Made ${name}`);
  await expect(page.locator("#r-code")).toHaveText(/^[0-9A-Z]{5}-[0-9A-Z]{5}$/);
  const code = (await page.locator("#r-code").textContent()).trim();
  return { ctx, page, code };
}

async function studentJoins(browser, base, code, name) {
  const ctx = await browser.newContext({ ...fresh, baseURL: base });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.locator("#optional-note")).toBeVisible(); // no class is needed to start
  await page.locator("#join-form").getByLabel("Class code").fill(code.toLowerCase());
  await page.getByRole("button", { name: "Join class ▸" }).click();
  await page.locator("#join-form").getByLabel(/Your first name/).fill(name);
  await page.getByRole("button", { name: "Join ▸" }).click();
  await expect(page.locator("#session-in-text")).toContainText(`as ${name}`);
  return { ctx, page };
}

test("a teacher sets work, a student joins and opens it, and the teacher sees their progress", async ({ browser, baseURL }) => {
  const problems = [];
  const t = await teacherMakesAClass(browser, baseURL, "8C Robotics");
  t.page.on("pageerror", (e) => problems.push(e.message));

  // set work: an ArduinoPath project with a note, and a PiPath activity
  await t.page.getByLabel("ArduinoPath project").selectOption({ label: "Blink & Traffic Lights" });
  await t.page.getByLabel("Note (optional)").fill("Steps 1 and 2 today");
  await t.page.getByRole("button", { name: "Add ▸" }).click();
  await t.page.getByLabel("PiPath activity").selectOption("s1_hello");
  await t.page.getByRole("button", { name: "Add ▸" }).click();
  await expect(t.page.locator("#w-list li")).toHaveCount(2);
  await t.page.getByRole("button", { name: "Save the work for this class" }).click();
  await expect(t.page.locator("#w-note-msg")).toContainText("Saved");
  await expect(t.page.locator("#p-table thead th")).toHaveCount(3);

  // the student joins, and sees the work with links that open it
  const s = await studentJoins(browser, baseURL, t.code, "Ava");
  s.page.on("pageerror", (e) => problems.push(e.message));
  const tasks = s.page.locator("#task-list li");
  await expect(tasks).toHaveCount(2);
  await expect(tasks.first()).toContainText("Blink & Traffic Lights");
  await expect(tasks.first()).toContainText("Steps 1 and 2 today");
  await expect(tasks.nth(1).getByRole("link")).toHaveAttribute("href", "/pipath/#/activity/s1_hello");
  await s.page.screenshot({ path: "test-results/screenshots/home-set-work.png" });

  // the link opens ArduinoPath: a new profile with the same name, then straight to the project
  await tasks.first().getByRole("link").click();
  await s.page.waitForURL("**/arduinopath/**");
  const newTile = s.page.locator(".new-tile");
  await expect(newTile.or(s.page.getByLabel("First name", { exact: true }))).toBeVisible();
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await s.page.getByLabel("First name", { exact: true }).fill("Ava");
  await s.page.getByLabel("Your school").fill("Test School");
  await s.page.getByRole("button", { name: "Next" }).click();
  await s.page.getByText("Beginner", { exact: true }).click();
  await s.page.getByText("Arduino Uno R3").click();
  await s.page.getByRole("button", { name: "Let's go!" }).click();
  await expect(s.page.getByRole("dialog", { name: /Wiring Wizard/ })).toBeVisible();
  await expect(s.page).toHaveURL(/#\/project\/blink-traffic-lights$/);
  await s.page.getByRole("dialog", { name: /Wiring Wizard/ }).getByRole("button", { name: "Close" }).click();
  await expect(s.page.locator(".editor-text")).toBeVisible();

  // the teacher sees Ava, and that she has opened the project
  await expect.poll(async () => {
    await t.page.getByRole("button", { name: "Refresh" }).click();
    return (await t.page.locator("#p-table tbody tr").first().textContent()) ?? "";
  }, { timeout: 20_000 }).toMatch(/Ava\s*·/);
  await expect(t.page.locator("#r-table tbody tr")).toHaveCount(1);
  await t.page.screenshot({ path: "test-results/screenshots/teacher-progress.png", fullPage: true });

  expect(problems).toEqual([]);
  await t.ctx.close();
  await s.ctx.close();
});

test("on a student Pi, joining a class and the teacher portal go through to the school server", async ({ browser, request }) => {
  const info = await (await request.get(`${PI}/api/info`)).json();
  expect(info.edition).toBe("student-pi");
  expect(info.online).toBe(true);
  const t = await teacherMakesAClass(browser, PI, "Pi room");
  const s = await studentJoins(browser, PI, t.code, "Kai");
  await expect(s.page.locator("#offline-note")).toBeHidden();
  // the school server has Kai
  await t.page.getByRole("button", { name: "Refresh" }).click();
  await expect(t.page.locator("#r-table tbody tr")).toContainText("Kai");
  await t.ctx.close();
  await s.ctx.close();
});
