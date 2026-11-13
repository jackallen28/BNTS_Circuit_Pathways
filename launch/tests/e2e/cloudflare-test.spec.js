// The TEST version on Cloudflare (a local Worker with BETA=1): nothing is saved on the computer, but it has
// beta teacher mode. A teacher makes up a code and makes a class, a student joins, and their work is saved to
// the class, so it survives a reload even though the browser keeps nothing.
import { test, expect } from "@playwright/test";

const TEST = `http://localhost:${Number(process.env.E2E_CFTEST_PORT) || 8547}`;
test.use({ baseURL: TEST, storageState: { cookies: [], origins: [] } });

test("TEST version: beta teacher mode, a student joins, and their work is saved to the class", async ({ page, browser }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));

  // the TEST home page: labelled, with the class and teacher boxes
  await page.goto("/");
  await expect(page.locator("h1 .beta-badge")).toHaveText("BETA");
  await expect(page.locator("#teacher-hint")).toBeVisible();
  await expect(page.locator("#optional-note")).toContainText("saved to the class");
  await expect(page.locator("#test-tag")).toHaveAttribute("aria-label", /Join a class to save your work/);
  await page.screenshot({ path: "test-results/screenshots/cf-test-home.png" });

  // a teacher makes up a code and makes a class
  await page.locator("#teacher-form input[name=teacher]").fill("made up by a tester");
  await page.getByRole("button", { name: /Teacher sign in/ }).click();
  await page.waitForURL("**/teacher/");
  await page.locator("#c-name").fill("Beta class");
  await page.locator("#c-school").fill("Eltham High");
  await page.getByRole("button", { name: "Make class ▸" }).click();
  await expect(page.locator("#roster")).toBeVisible();
  const code = (await page.locator("#r-code").textContent()).trim();

  // a student joins with first name and school, and writes some code in PiPath
  const sctx = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const sp = await sctx.newPage();
  sp.on("pageerror", (e) => problems.push(e.message));
  await sp.goto(`${TEST}/`);
  await sp.locator("#join-form input[name=code]").fill(code);
  await sp.getByRole("button", { name: /Join class/ }).click();
  await expect(sp.locator("#join-class")).toContainText("Beta class");
  await sp.locator("#join-form input[name=names]").fill("Ari");
  await sp.getByRole("button", { name: /^Join/ }).click();
  await expect(sp.locator("#session-in-text")).toContainText("as Ari");

  await sp.goto(`${TEST}/pipath/`);
  const newBtn = sp.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(sp.getByLabel("Your first name"))).toBeVisible({ timeout: 20_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await expect(sp.locator("#name1")).toHaveValue("Ari"); // filled in from the class
  await sp.getByRole("button", { name: "Next" }).click();
  await sp.getByText("Beginner", { exact: true }).first().click();
  await sp.getByRole("button", { name: "Let's go!" }).click();
  await sp.locator(".card.free").click();
  await sp.locator("#code").fill('print("kept by the class")\n');
  await sp.locator("#run").click();
  await expect(sp.locator(".console-out")).toContainText("kept by the class", { timeout: 60_000 });

  // the teacher sees Ari's work
  await expect.poll(async () => {
    await page.getByRole("button", { name: "Refresh" }).click();
    await page.getByRole("button", { name: "See work" }).first().click();
    return page.locator("#r-work").textContent();
  }, { timeout: 30_000 }).toContain("kept by the class");

  // the TEST version keeps nothing on the computer, but the class has it: after a reload, joining back in brings it back
  await sp.reload();
  await expect(newBtn.or(sp.getByLabel("Your first name"))).toBeVisible({ timeout: 20_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await sp.getByRole("button", { name: "Next" }).click();
  await sp.getByText("Beginner", { exact: true }).first().click();
  await sp.getByRole("button", { name: "Let's go!" }).click();
  await sp.locator(".card.free").click();
  await expect(sp.locator("#code")).toHaveValue(/kept by the class/, { timeout: 20_000 });
  await sctx.close();
  expect(problems).toEqual([]);
});
