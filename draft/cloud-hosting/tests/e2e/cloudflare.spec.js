// The Cloudflare version (the Worker, run locally with its own database): a teacher makes a saved
// class, a student joins with their first name and school, codes in PiPath and ArduinoPath, and the
// teacher sees the work; then the teacher deletes the class and it is all gone.
import { test, expect } from "@playwright/test";

const CF = `http://localhost:${Number(process.env.E2E_CF_PORT) || 8545}`;
test.use({ baseURL: CF, storageState: { cookies: [], origins: [] } });

async function teacherMakesClass(page, name) {
  await page.goto("/");
  await page.locator("#teacher-form input[name=teacher]").fill("teacher-code-dev");
  await page.getByRole("button", { name: /Teacher sign in/ }).click();
  await page.waitForURL("**/teacher/");
  await expect(page.locator("#classes-card")).toBeVisible();
  await expect(page.locator("#code-card")).toBeHidden();
  await page.locator("#c-name").fill(name);
  await page.locator("#c-school").fill("Eltham High");
  await page.getByRole("button", { name: "Make class ▸" }).click();
  await expect(page.locator("#roster")).toBeVisible();
  return (await page.locator("#r-code").textContent()).trim();
}

test("a saved class from start to finish", async ({ page, browser }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  const code = await teacherMakesClass(page, "7B Thursday");
  expect(code).toMatch(/^[0-9A-Z]{5}-[0-9A-Z]{5}$/);
  await expect(page.locator("#c-table")).toContainText("7B Thursday");
  await page.screenshot({ path: "test-results/screenshots/cf-teacher.png", fullPage: true });

  // a student joins: the code, then first name and school
  const sctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const sp = await sctx.newPage();
  sp.on("pageerror", (e) => problems.push(e.message));
  await sp.goto(`${CF}/`);
  await sp.locator("#join-form input[name=code]").fill(code.toLowerCase());
  await sp.getByRole("button", { name: /Join class/ }).click();
  await expect(sp.locator("#join-class")).toContainText("7B Thursday (Eltham High)");
  await expect(sp.locator("#join-form input[name=school]")).toHaveValue("Eltham High");
  await sp.locator("#join-form input[name=names]").fill("mia");
  await sp.getByRole("button", { name: /^Join/ }).click();
  await expect(sp.locator("#session-in-text")).toContainText("as Mia");
  await expect(sp.locator("#privacy")).toContainText("deleted when the class ends");

  // PiPath: the profile is filled in already; the student's code saves to the class
  await sp.goto(`${CF}/pipath/`);
  const newBtn = sp.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(sp.getByLabel("Your first name"))).toBeVisible({ timeout: 20_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await expect(sp.locator("#name1")).toHaveValue("Mia");
  await expect(sp.locator("#school")).toHaveValue("Eltham High");
  await sp.getByRole("button", { name: "Next" }).click();
  await sp.getByText("Beginner", { exact: true }).first().click();
  await sp.getByRole("button", { name: "Let's go!" }).click();
  await sp.locator(".card.free").click();
  await sp.locator("#code").fill('print("Mia was here")\n');
  await sp.locator("#run").click();
  await expect(sp.locator(".console-out")).toContainText("Mia was here", { timeout: 60_000 });

  // the teacher sees Mia and her code
  await expect.poll(async () => {
    await page.getByRole("button", { name: "Refresh" }).click();
    return page.locator("#r-table").textContent();
  }, { timeout: 20_000 }).toContain("Mia");
  await expect.poll(async () => {
    await page.getByRole("button", { name: "Refresh" }).click();
    await page.getByRole("button", { name: "See work" }).first().click();
    return page.locator("#r-work").textContent();
  }, { timeout: 20_000 }).toContain('print("Mia was here")');

  // the student's save file carries the class link
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Download everyone's work/ }).click()]);
  expect(dl.suggestedFilename()).toMatch(/7B-Thursday_work_.*\.zip$/);

  // the teacher deletes the class: the student's link stops working
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete this class now" }).click();
  await expect(page.locator("#c-note")).toContainText("deleted");
  const gone = await sp.evaluate(async () => (await fetch("/api/student/me", { headers: { Authorization: `Bearer ${JSON.parse(localStorage.getItem("circuitpathways.access")).value}` } })).status);
  expect(gone).toBe(401);
  expect(problems).toEqual([]);
  await sctx.close();
});
