// The programming workspace: a student opens Blink & Traffic Lights, runs
// the starter code in the simulator, watches the checklist tick, makes a
// mistake and gets the Coach's clue, fixes it, finishes the step and moves
// on; Watch the goal plays the model answer.
import { test, expect } from "@playwright/test";
import { installFakeBoard } from "./fake-serial.js";

async function newStudent(page, name) {
  await page.goto("/arduinopath/");
  const logOut = page.getByRole("button", { name: "Log out" });
  if (await logOut.isVisible({ timeout: 2000 }).catch(() => false)) await logOut.click();
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible();
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await page.getByLabel("First name", { exact: true }).fill(name);
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).click();
  await page.getByText("Arduino Uno R3").click();
  await page.getByRole("button", { name: "Let's go!" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Hi ${name}!`) })).toBeVisible();
}

// A project with parts opens the Wiring Wizard first (its own test goes through it).
async function closeWizard(page) {
  const wizard = page.getByRole("dialog", { name: /Wiring Wizard/ });
  await expect(wizard).toBeVisible();
  await wizard.getByRole("button", { name: "Close" }).click();
  await expect(wizard).toBeHidden();
}

test("a project, one step at a time", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await newStudent(page, "Zara");

  await page.locator(".project-card", { hasText: "Blink & Traffic Lights" }).click();
  await closeWizard(page);
  const guide = page.locator(".side-panel.guide");
  await expect(guide.getByRole("heading", { name: /Step 1 of 4/ })).toBeVisible();
  const editor = page.locator(".editor-text");
  await expect(editor).toHaveValue(/Pins for your Arduino Uno/);
  await expect(editor).toHaveValue(/#define LED_RED 12/);

  // Running with the blank left in asks for the blank first.
  await page.locator("#tool-run").click();
  await expect(guide.locator(".clue")).toContainText("Fill in the blanks first");

  // Fill it in and Run: the simulator ticks the checklist by itself.
  await editor.fill((await editor.inputValue()).replace("___", "LOW"));
  await page.locator("#tool-run").click();
  const rows = guide.locator(".check-row");
  await expect(rows.filter({ hasText: "The red LED turns on" })).toHaveClass(/ok/, { timeout: 15_000 });
  await expect(rows.filter({ hasText: "The red LED turns off" })).toHaveClass(/ok/, { timeout: 15_000 });
  await expect(page.locator("#tool-run")).toContainText("Stop");
  await page.locator("#tool-run").click();
  await expect(page.locator("#tool-run")).toContainText("Run");

  // "I saw it happen" finishes the step, with stars.
  await guide.getByLabel(/I saw the red LED blink/).check();
  await expect(guide.locator(".step-done")).toBeVisible();
  await expect(guide.locator(".stars-line")).toContainText("★★★");
  await page.screenshot({ path: "test-results/screenshots/09-workspace-step-done-1366x768.png" });

  // Step 2: a mistake gives a clue in plain English.
  await guide.getByRole("button", { name: "Next step ▶" }).click();
  await expect(guide.getByRole("heading", { name: /Step 2 of 4/ })).toBeVisible();
  const code = await editor.inputValue();
  await editor.fill(code.replace(/digitalWrite\(LED_RED, HIGH\);/, "digitalWrite(LED_RED, HIGH)"));
  await page.locator("#tool-run").click();
  const clue = guide.locator(".clue");
  await expect(clue).toBeVisible();
  await expect(clue).toContainText(/semicolon|;/i);
  await expect(clue).toContainText("Hint 1"); // beginners see the first hint straight away
  await page.screenshot({ path: "test-results/screenshots/10-workspace-clue-1366x768.png" });

  // Watch the goal plays the model answer, and doesn't tick anything.
  await page.locator("#tool-goal").click();
  await expect(page.locator(".rp-banner")).toContainText("Watching the goal");

  // Progress is saved: reopening the project comes back to step 2.
  await page.getByRole("button", { name: "Projects" }).click();
  await page.locator(".project-card", { hasText: "Blink & Traffic Lights" }).click();
  await closeWizard(page);
  await expect(guide.getByRole("heading", { name: /Step 2 of 4/ })).toBeVisible();
  await expect(guide.locator(".step-dot.done")).toHaveCount(1);

  expect(problems).toEqual([]);
});

test("a screen-only project with the Serial Monitor", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await newStudent(page, "Omar");
  await page.locator(".project-card", { hasText: "Serial Chatbot" }).click();
  await expect(page.getByRole("dialog", { name: /Wiring Wizard/ })).toHaveCount(0); // no parts, no wiring
  const editor = page.locator(".editor-text");
  await expect(editor).toHaveValue(/___/);
  await editor.fill((await editor.inputValue()).replace("___", '"Hello from Omar!"'));
  await page.locator("#tool-run").click();
  await expect(page.locator(".console-out").first()).toContainText("Hello from Omar!", { timeout: 10_000 });
  const rows = page.locator(".side-panel.guide .check-row");
  await expect(rows.first()).toHaveClass(/ok/, { timeout: 10_000 });
  expect(problems).toEqual([]);
});

// Upload, the real Serial Monitor and Send: a pretend Uno on a pretend Web
// Serial port, and a pretend compiler (the real one is checked in CI).
test("uploading to a real board", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await installFakeBoard(page, { silentFirst: 1, programSays: ["Hello from my real board!\r\n"] });
  const serial = () => page.evaluate(() => window.__serial);

  await newStudent(page, "Lena");
  await page.locator(".project-card", { hasText: "Serial Chatbot" }).click();
  const editor = page.locator(".editor-text");
  await expect(editor).toHaveValue(/___/);
  await editor.fill((await editor.inputValue()).replace("___", '"Hello from my real board!"'));

  // No board chosen yet: the student is asked to pick it in the browser's own box.
  await page.locator("#tool-upload").click();
  await page.getByRole("button", { name: "OK" }).click();
  // The first try fails like a wrong board setting; the Coach explains.
  const guide = page.locator(".side-panel.guide");
  await expect(guide.locator(".clue")).toContainText("The board didn't answer", { timeout: 15_000 });
  expect((await serial()).requested).toBe(1);

  // The board is remembered, so the second try just works.
  await page.locator("#tool-upload").click();
  const monitor = page.locator(".console-out").first();
  await expect(monitor).toContainText("Hello from my real board!", { timeout: 15_000 });
  const s = await serial();
  expect(s.requested).toBe(1);
  expect(s.uploads).toBe(1);
  expect(s.opens.at(-1)).toBe(9600); // the speed in Serial.begin()
  await expect(guide.locator(".checklist legend")).toContainText("on your board");
  await expect(guide.locator(".check-row").first()).toHaveClass(/ok/);

  // Send goes to the real board, not the simulator.
  await page.getByLabel("Text to send").fill("hi board");
  await page.getByLabel("Text to send").press("Enter");
  await expect.poll(async () => (await serial()).writes).toEqual(["hi board\n"]);

  // Changing the speed reconnects at the new speed.
  await page.getByLabel("Speed (baud)").selectOption("115200");
  await expect.poll(async () => (await serial()).opens.includes(115200)).toBe(true);

  // Run goes back to the simulator, and Send with it.
  await page.locator("#tool-run").click();
  await expect(guide.locator(".checklist legend")).toHaveText("Checklist");
  expect(problems).toEqual([]);
});

// A board Web Serial can't see (no driver on this computer): the student
// closes the empty box, gets the Can't see your board? help, and uploads the
// USB way (WebUSB talking to the CH340 chip itself).
test("uploading the USB way when the computer has no driver for the board", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await installFakeBoard(page, { usb: true, programSays: ["Hello the USB way!\r\n"] });
  const serial = () => page.evaluate(() => window.__serial);

  await newStudent(page, "Ari");
  await page.locator(".project-card", { hasText: "Serial Chatbot" }).click();
  const editor = page.locator(".editor-text");
  await expect(editor).toHaveValue(/___/);
  await editor.fill((await editor.inputValue()).replace("___", '"Hello the USB way!"'));

  await page.locator("#tool-upload").click();
  await page.getByRole("button", { name: "OK" }).click();
  const help = page.getByRole("dialog", { name: "Can't see your board?" });
  await expect(help).toContainText("Some cables only charge");
  await page.screenshot({ path: "test-results/screenshots/board-help.png" });
  await help.getByRole("button", { name: "Try the USB way" }).click();

  const monitor = page.locator(".console-out").first();
  await expect(monitor).toContainText("Hello the USB way!", { timeout: 15_000 });
  const s = await serial();
  expect(s.requested).toBe(1);
  expect(s.usbRequested).toBe(1);
  expect(s.uploads).toBe(1);
  expect(s.opens.at(-1)).toBe(9600);
  // the port list names the board as connected the USB way
  await expect.poll(() => page.evaluate(() => {
    const sel = document.querySelector(".port-select");
    return sel?.selectedOptions[0]?.textContent ?? "";
  })).toContain("the USB way");

  // Send reaches the board the USB way too.
  await page.getByLabel("Text to send").fill("hi chip");
  await page.getByLabel("Text to send").press("Enter");
  await expect.poll(async () => (await serial()).writes).toEqual(["hi chip\n"]);
  expect(problems).toEqual([]);
});

test("a compile error from the real compiler is explained by the Coach", async ({ page }) => {
  await installFakeBoard(page, { compile: { ok: false, output: "sketch.ino:3:1: error: expected ';' before '}' token", errors: [{ file: "sketch.ino", line: 3, col: 1, severity: "error", message: "expected ';' before '}' token" }] } });
  await newStudent(page, "Noor");
  await page.locator(".project-card", { hasText: "Serial Chatbot" }).click();
  await expect(page.locator(".editor-text")).toBeVisible();
  await page.locator(".editor-text").fill("void setup() {\n  Serial.begin(9600)\n}\nvoid loop() {}\n");
  await page.locator("#tool-check").click();
  await expect(page.locator(".side-panel.guide .clue")).toContainText("semicolon", { timeout: 10_000 });
});

test("Upload is for everyone on the school network, but a made-up class token is refused", async ({ request }) => {
  const res = await request.post("/api/compile", {
    headers: { "X-Circuit-Pathways": "1", "X-Access": "s2.made-up" },
    data: { code: "void setup(){}\nvoid loop(){}", board: "uno" },
  });
  expect(res.status()).toBe(401);
  const none = await request.post("/api/compile", { headers: { "X-Circuit-Pathways": "1" }, data: { code: "void setup(){}\nvoid loop(){}", board: "uno" } });
  expect(none.status()).toBe(503); // (the dev server has no board tools)
});

test("Free Play with a Grove kit: add a module, its code goes in, it's in the simulator, and it comes back next time", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await newStudent(page, "Gus");
  await page.locator(".freeplay-card").click();
  const box = page.locator(".grove-box");
  await expect(box).toContainText("Grove Base Shield V2");
  await box.getByLabel("Grove module").selectOption("grove-led");
  await expect(box.getByLabel("Port")).toHaveValue("D2");
  await box.getByLabel("Port").selectOption("D4");
  await box.getByRole("button", { name: "Add" }).click();
  // the mini wizard opens for it
  const wiz = page.getByRole("dialog", { name: /Wiring Wizard/ });
  await expect(wiz.getByRole("heading", { name: /Meet the Grove LED/ })).toBeVisible();
  await wiz.getByRole("button", { name: "Next ▶" }).click();
  await expect(wiz).toContainText("into port D4");
  await wiz.getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".editor-text")).toHaveValue(/#define LED_PIN 4 .*port D4/);
  await expect(box).toContainText("Grove LED → port D4 (LED_PIN)");
  await expect(page.locator(".run-holder .cp-grove-shield")).toBeVisible();
  // come back: it's still there
  await page.reload();
  await expect(page.locator(".grove-box")).toContainText("Grove LED → port D4", { timeout: 15_000 });
  await expect(page.locator(".run-holder .cp-grove-shield")).toBeVisible();
  expect(problems).toEqual([]);
});

/** Drags with the real mouse, in small steps, from one element to a point (like a student would). */
async function dragTo(page, from, x, y) {
  const b = await from.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) await page.mouse.move(b.x + b.width / 2 + ((x - b.x - b.width / 2) * i) / 12, b.y + b.height / 2 + ((y - b.y - b.height / 2) * i) / 12);
  await page.mouse.up();
}

test("the Web Page Designer on a NodeMCU: ideas, a pin clash warning, and a colour and beep to try", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto("/arduinopath/");
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible();
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await page.getByLabel("First name", { exact: true }).fill("Kai");
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).click();
  await page.getByText("NodeMCU", { exact: false }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();
  await page.locator(".freeplay-card").click();
  await page.getByRole("button", { name: "Web page", exact: true }).click();
  const dlg = page.getByRole("dialog", { name: "Web Page Designer" });

  // start from the plant idea: its soil reading is on A0, the NodeMCU's only analog pin
  await dlg.getByLabel("Start from an idea").selectOption("plant");
  await page.getByRole("button", { name: "Start from it" }).click();
  await expect(dlg.locator(".wp-phone h1")).toHaveText("Plant Buddy");
  await expect(dlg.locator(".wp-el-reading meter")).toHaveAttribute("max", "1023"); // the board's own analog range
  // a knob is on A0 too: both say so, and the inspector explains
  await dlg.getByRole("button", { name: "Add Reading" }).click();
  await expect(dlg.locator(".wp-badge.warn")).toHaveCount(2);
  await expect(dlg.locator(".wp-badge.warn").first()).toHaveText("⚠ pin A0 is shared");
  await expect(dlg.locator(".wp-warn")).toContainText("SOIL_PIN and POT_PIN are both on pin A0");
  await dlg.getByRole("button", { name: "Undo" }).click();
  await expect(dlg.locator(".wp-badge.warn")).toHaveCount(0);

  // party lights: the colour picker lights the pretend RGB LED, and the beep button beeps
  await dlg.getByLabel("Start from an idea").selectOption("party");
  await page.getByRole("button", { name: "Start from it" }).click();
  await dlg.getByRole("tab", { name: /Try it/ }).click();
  const bench = dlg.locator(".wp-bench");
  await expect(bench).toContainText("RGB LED");
  await dlg.getByLabel("Light colour", { exact: true }).fill("#00ff00");
  await expect(bench).toContainText("rgb 0, 255, 0");
  await dlg.getByRole("button", { name: "Beep!" }).click();
  await expect(bench.locator(".wp-buzz")).toHaveClass(/beep/);
  await dlg.getByLabel("Beep pitch", { exact: true }).fill("440");
  await expect(bench).toContainText("playing 440 Hz");
  expect(problems).toEqual([]);
});

test("the Web Page Designer on an ESP: drag, drop, wire, try it, then the phone shows it", async ({ page }) => {
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  // The phone is a sandboxed frame with no scripts: Chromium notes that
  // whenever the test looks inside it, which isn't a fault in the page.
  page.on("console", (m) => { if (m.type() === "error" && !/Blocked script execution in 'about:srcdoc'/.test(m.text())) problems.push(m.text()); });
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto("/arduinopath/");
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible();
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await page.getByLabel("First name", { exact: true }).fill("Wren");
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).click();
  await page.getByText("ESP32 DevKit", { exact: false }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();
  await expect(page.getByRole("heading", { name: /Hi Wren!/ })).toBeVisible();
  await page.locator(".freeplay-card").click();
  await page.waitForURL(/#\/freeplay/);
  await expect(page.getByRole("button", { name: "Web page", exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Web page", exact: true }).click();
  const dlg = page.getByRole("dialog", { name: "Web Page Designer" });
  const els = dlg.locator(".wp-el");
  await expect(dlg.locator(".wp-phone")).toContainText("My Smart Light");
  await expect(els).toHaveCount(4); // the starting idea: some text, two buttons and a reading

  // the page's settings: the title
  await dlg.getByLabel("Title").fill("Fish Feeder");
  await expect(dlg.locator(".wp-phone h1")).toHaveText("Fish Feeder");

  // drag a switch from the palette into the gap after the first element
  const second = await els.nth(1).boundingBox();
  await dragTo(page, dlg.getByRole("button", { name: "Add Switch" }), second.x + second.width / 2, second.y + 3);
  await expect(els).toHaveCount(5);
  await expect(els.nth(1)).toHaveClass(/wp-el-switch/);
  await expect(els.nth(1)).toHaveClass(/selected/);
  await expect(els.nth(1).locator(".wp-badge")).toHaveText("→ LED_PIN (pin 25)");
  await expect(dlg.locator(".wp-does")).toContainText("turns LED_PIN (pin 25) on or off");

  // drag the first element (the text) to the bottom of the page
  const phone = await dlg.locator(".wp-phone").boundingBox();
  await dragTo(page, els.nth(0), phone.x + phone.width / 2, phone.y + phone.height - 20);
  await expect(els.last()).toHaveClass(/wp-el-text/);

  // drag a button onto the bin to remove it; Undo brings it back
  const bin = await dlg.locator(".wp-bin").boundingBox();
  await dragTo(page, dlg.locator(".wp-el-button").first(), bin.x + bin.width / 2, bin.y + bin.height / 2);
  await expect(els).toHaveCount(4);
  await dlg.getByRole("button", { name: "Undo" }).click();
  await expect(els).toHaveCount(5);

  // a knob reading, added with a click, and changed in the inspector
  await dlg.getByRole("button", { name: "Add Reading" }).click();
  await expect(els).toHaveCount(6);
  await expect(dlg.locator(".wp-el-reading .wp-badge")).toHaveText("← Knob (pin 34)");
  await expect(dlg.locator(".wp-does")).toHaveText("Shows a knob (POT_PIN) as a bar. The page updates every 5 seconds.");
  await expect(dlg.locator(".wp-inspector")).not.toContainText("null");
  await dlg.getByLabel("Name", { exact: true }).fill("Water level");
  const water = dlg.locator(".wp-el-reading", { hasText: "Water level" });
  await expect(water).toHaveCount(1);

  // the keyboard: Alt+Up moves an element up
  const at = Number(await water.getAttribute("data-index"));
  expect(at).toBeGreaterThan(0);
  await water.focus();
  await page.keyboard.press("Alt+ArrowUp");
  await expect(els.nth(at - 1)).toContainText("Water level");
  await page.screenshot({ path: "test-results/screenshots/webpage-designer.png" });

  // Try it: the page works on the pretend board
  await dlg.getByRole("tab", { name: /Try it/ }).click();
  const bench = dlg.locator(".wp-bench");
  await expect(bench).toContainText("LED_PIN (pin 25)");
  await expect(bench.locator(".wp-part").first()).toContainText("off");
  await dlg.getByRole("switch").click();
  await expect(dlg.getByRole("switch")).toContainText("ON");
  await expect(bench.locator(".wp-part").first()).toContainText("on");
  await dlg.getByRole("button", { name: "Turn it off" }).click();
  await expect(dlg.getByRole("switch")).toContainText("OFF", { timeout: 2000 });
  await dlg.getByLabel("Pretend knob").fill("3000");
  await expect(water.locator("b")).toHaveText("3000");
  await page.screenshot({ path: "test-results/screenshots/webpage-designer-try.png" });

  // the code is right there to look at
  await dlg.locator(".wp-code-box summary").click();
  await expect(dlg.locator(".wp-code")).toContainText("void toggleLight()");

  await dlg.getByRole("button", { name: "Put it in my code" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Replace it" }).click();
  await expect(page.locator(".editor-text")).toHaveValue(/Fish Feeder: a web page made with ArduinoPath's Web Page Designer/);
  await expect(page.locator(".editor-text")).toHaveValue(/void toggleLight\(\) \{/);
  // run it: the phone shows the page, and its switch works
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator(".rp-phone")).toBeVisible({ timeout: 20_000 });
  await page.locator(".rp-phone").getByRole("button", { name: "Go" }).click();
  const phoneFrame = page.frameLocator(".rp-phone-screen");
  await expect(phoneFrame.locator("h1")).toHaveText("Fish Feeder", { timeout: 15_000 });
  await phoneFrame.locator("a.switch").click();
  await expect(phoneFrame.locator("a.switch")).toHaveClass(/sw-on/, { timeout: 10_000 });
  // the design is kept for next time
  await page.reload();
  await page.getByRole("button", { name: "Web page", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Web Page Designer" }).locator(".wp-phone h1")).toHaveText("Fish Feeder");
  await expect(page.getByRole("dialog", { name: "Web Page Designer" }).locator(".wp-el")).toHaveCount(6);
  expect(problems).toEqual([]);
});

