// A student's first PiPath lesson in the browser: profile, setup, picker, an activity, Run,
// the checklist, the Coach, Watch the goal, and the on-screen board.
import { test, expect } from "@playwright/test";

const SIZE = { width: 1366, height: 768 };

async function newStudent(page, name) {
  await page.goto("/pipath/");
  const newBtn = page.getByRole("button", { name: "I'm new here" });
  await expect(newBtn.or(page.getByLabel("Your first name"))).toBeVisible({ timeout: 15_000 });
  if (await newBtn.isVisible().catch(() => false)) await newBtn.click();
  await page.getByLabel("Your first name").fill(name);
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText(`Nice to meet you, ${name}!`)).toBeVisible();
}

test("a student's first PiPath activity", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push(m.text()); });
  await page.setViewportSize(SIZE);

  await newStudent(page, "Mia");
  await page.getByText("Beginner", { exact: true }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();

  // the picker: Free Play first, then the activities
  await expect(page.locator(".card").first()).toHaveClass(/free/);
  await expect(page.locator(".card[data-id]")).toHaveCount(28);
  await expect(page.locator('.card[data-id="m2_turtle"]')).toBeDisabled();
  await page.screenshot({ path: "test-results/screenshots/pipath-picker.png" });

  // Hello, Pi!
  await page.locator('.card[data-id="s1_hello"]').click();
  await expect(page.getByRole("heading", { name: /Welcome to your first program/ })).toBeVisible();
  await page.getByRole("button", { name: /Start step 1/ }).click();
  await expect(page.locator("#guide-title")).toContainText("Step 1 of");
  await expect(page.locator("#status-level")).toContainText("Beginner");
  await expect(page.locator("#code")).toHaveValue(/print\("Hello, Pi!"\)/);
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("Hello, Pi!", { timeout: 60_000 });
  await expect(page.locator(".checklist li.ok")).toHaveCount(2, { timeout: 10_000 });
  await expect(page.locator("#step-done")).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/pipath-step1.png" });
  await page.getByRole("button", { name: "Next step" }).click();

  // step 2 has a blank: running it first gives the Coach's clue, not a crash
  await expect(page.locator("#guide-title")).toContainText("Step 2 of");
  await page.locator("#run").click();
  await expect(page.locator("#clue")).toContainText(/blank/i);
  await expect(page.locator("#clue")).toContainText("line");

  // a real error is explained in plain English, and Show me a hint reveals tiers
  await page.locator("#code").fill('print("Hello, " + 5)\n');
  await page.locator("#run").click();
  await expect(page.locator("#clue")).toBeVisible();
  await expect(page.locator(".console-out")).toContainText("TypeError", { timeout: 10_000 });
  await page.locator("#clue-hint").click();
  await expect(page.locator("#clue ol li").first()).toBeVisible();

  // Watch the goal plays the model answer without touching the student's code
  await page.locator("#goal").click();
  await expect(page.locator(".console-out")).toContainText("That's the goal", { timeout: 30_000 });
  await expect(page.locator("#code")).toHaveValue('print("Hello, " + 5)\n');
  expect(problems).toEqual([]);
});

test("a hardware activity: the board shows the program's LEDs and a button works", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.setViewportSize(SIZE);
  await newStudent(page, "Noor");
  await page.getByRole("button", { name: "Let's go!" }).click();
  await page.locator('.card[data-id="a1_traffic"]').click();
  await page.getByRole("button", { name: /Start step 1/ }).click();
  // Watch the goal: the Red LED glows on the board
  await page.locator("#goal").click();
  await expect(page.locator(".board .part").first()).toBeVisible();
  await expect.poll(async () => page.locator(".board svg circle[fill='#ff3b30']").first().evaluate((c) => c.style.opacity), { timeout: 30_000 }).toBe("1");
  await expect(page.locator(".console-out")).toContainText("That's the goal", { timeout: 60_000 });
  await page.screenshot({ path: "test-results/screenshots/pipath-board.png" });
  expect(problems).toEqual([]);
});

test("typing an answer to input(), Advanced shows just the goal, and Free Play adds a part", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.setViewportSize(SIZE);
  await newStudent(page, "Omar");
  await page.getByText("Advanced", { exact: true }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();

  // Advanced: "Jump to the challenge" is offered, and the step shows the goal first
  await page.locator('.card[data-id="s2_pibot"]').click();
  await expect(page.getByRole("button", { name: "Jump to the challenge" })).toBeVisible();
  await page.getByRole("button", { name: /Start step 1/ }).click();
  await expect(page.getByRole("button", { name: /Show the full explanation/ })).toBeVisible();

  // a program that asks a question: the answer box is lit, and typing the answer carries on
  await page.locator("#code").fill('name = input("What is your name? ")\nprint(f"Hello, {name}!")\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("What is your name?", { timeout: 60_000 });
  await expect(page.locator(".console-in")).toHaveClass(/waiting/);
  await page.getByLabel("Type your answer here").fill("Omar");
  await page.getByLabel("Type your answer here").press("Enter");
  await expect(page.locator(".console-out")).toContainText("Hello, Omar!");

  // Free Play: add an LED and run it; the board shows it
  await page.getByRole("button", { name: "◂ Activities" }).click();
  await page.locator("#free-play").click();
  await page.getByRole("button", { name: "LED", exact: true }).click();
  await expect(page.locator("#code")).toHaveValue(/LED\(17\)/);
  await page.locator("#run").click();
  await expect(page.locator(".board .part", { hasText: "GPIO17" })).toHaveCount(1, { timeout: 30_000 });
  expect(problems).toEqual([]);
});

test("a runaway loop is stopped and explained, the button works, and work can be saved and opened", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.setViewportSize(SIZE);
  await newStudent(page, "Lena");
  await page.getByRole("button", { name: "Let's go!" }).click();
  await page.locator("#free-play").click();

  // Button: pressing it on the board runs the program's when_pressed
  await page.locator("#code").fill('from gpiozero import Button\nfrom signal import pause\nb = Button(23)\nb.when_pressed = lambda: print("Pressed!")\nprint("Ready")\npause()\n');
  await page.locator("#run").click();
  await expect(page.locator(".console-out")).toContainText("Ready", { timeout: 60_000 });
  const press = page.getByRole("button", { name: /Press and hold/ });
  await press.dispatchEvent("pointerdown", { pointerId: 1 });
  await press.dispatchEvent("pointerup", { pointerId: 1 });
  await expect(page.locator(".console-out")).toContainText("Pressed!");
  await page.locator("#run").click(); // Stop
  await expect(page.locator("#run")).toContainText("Run");

  // a loop with nothing in it
  await page.locator("#code").fill("x = 0\nwhile True:\n    x += 1\n");
  await page.evaluate(() => { /* the page's runner is shared; make the wait short for the test */ });
  await page.locator("#run").click();
  await expect(page.locator("#clue")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#clue")).toContainText(/runs? (flat out|without|forever)|busy|loop|never/i);

  // save my work, then open it again
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "My work" }).click();
  const dl = page.waitForEvent("download");
  await page.locator("#save-work").click();
  const download = await dl;
  expect(download.suggestedFilename()).toMatch(/^Lena_PiPath_\d{4}-\d{2}-\d{2}\.pipath$/);
  const path = await download.path();
  await page.locator("#open-work").setInputFiles(path);
  await expect(page.getByText("Nothing new in that file")).toBeVisible();
  expect(problems).toEqual([]);
});
