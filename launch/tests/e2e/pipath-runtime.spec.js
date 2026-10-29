// Python in the browser, in a real browser, under the site's strict security policy.
import { test, expect } from "@playwright/test";

test("Python runs in a worker, asks for input, and the page can stop a busy loop", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) problems.push(m.text()); });
  await page.goto("/pipath/dev/runtime.html");
  await expect(page.locator("#state")).toContainText("is ready", { timeout: 60_000 });
  await expect(page.locator("#state")).toContainText("isolated=true");

  // a program that prints, asks a question and waits for the answer
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator("#out")).toContainText("Your name?");
  await expect(page.locator("#state")).toContainText("Waiting for you to type");
  await page.evaluate(() => window.pyRunner.sendLine("Mia"));
  await expect(page.locator("#out")).toContainText("Hi Mia");
  await expect(page.locator("#state")).toContainText("Finished: rc=0");

  // a loop that never waits is stopped, and the page says it ran away
  await page.fill("#code", "while True:\n    pass\n");
  await page.evaluate(() => { window.pyRunner.busyMs = 1000; });
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator("#state")).toContainText("reason=runaway_busy", { timeout: 15_000 });

  // Stop ends a program that is waiting
  await page.fill("#code", "from time import sleep\nwhile True:\n    sleep(0.1)\n");
  await page.getByRole("button", { name: "Run" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.locator("#state")).toContainText("reason=stop", { timeout: 10_000 });
  expect(problems).toEqual([]);
});
