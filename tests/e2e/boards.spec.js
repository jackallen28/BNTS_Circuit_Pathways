// The school's ESP boards: a teacher sets one up (the flashing itself needs a real board, so the test records its
// chip as the teacher portal would), a student claims it in ArduinoPath with the sticker code, and their WiFi
// project uses that board's own WiFi name and password. The teacher portal shows who has it.
import { test, expect } from "@playwright/test";

test("a student claims their school ESP board, and their WiFi project uses its own WiFi", async ({ browser, baseURL, request }) => {
  const post = async (path, data, token) => {
    const r = await request.post(path, { headers: { "X-Circuit-Pathways": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, data });
    expect(r.ok(), `${path}: ${r.status()}`).toBe(true);
    return r.json();
  };
  const { token: teacher } = await post("/api/teacher/signin", { code: "teacher-code-dev" });
  const board = await post("/api/teacher/boards", { label: "ESP-21", kind: "nodemcu" }, teacher);
  await post(`/api/teacher/boards/${board.id}/flashed`, { mac: "a4:cf:12:0b:9e:21" }, teacher);
  const cls = await post("/api/teacher/class", { name: "Board test" }, teacher);

  // the student joins on the home page, then makes an ArduinoPath profile for a NodeMCU
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] }, baseURL });
  const page = await ctx.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await page.locator("#join-form").getByLabel("Class code").fill(cls.code);
  await page.getByRole("button", { name: "Join class ▸" }).click();
  await page.locator("#join-form").getByLabel(/Your first name/).fill("Lena");
  await page.getByRole("button", { name: "Join ▸" }).click();
  await expect(page.locator("#session-in-text")).toContainText("as Lena");
  await page.goto("/arduinopath/");
  const newTile = page.locator(".new-tile");
  await expect(newTile.or(page.getByLabel("First name", { exact: true }))).toBeVisible();
  if (await newTile.isVisible().catch(() => false)) await newTile.click();
  await page.getByLabel("First name", { exact: true }).fill("Lena");
  await page.getByLabel("Your school").fill("Test School");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Beginner", { exact: true }).click();
  await page.getByText("NodeMCU", { exact: false }).first().click();
  await page.getByRole("button", { name: "Let's go!" }).click();

  // Settings > My ESP board: before claiming, a WiFi made just for this computer; then the school board
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "My ESP board" }).click();
  await expect(page.getByText("Your WiFi", { exact: true })).toBeVisible();
  await page.getByLabel("Board code").fill(board.code.toLowerCase());
  await page.getByRole("button", { name: "Use this board" }).click();
  await expect(page.getByText("Your board: ESP-21")).toBeVisible();
  await expect(page.locator(".kv")).toContainText(board.ssid);
  await expect(page.locator(".kv")).toContainText(board.password);
  await page.screenshot({ path: "test-results/screenshots/my-esp-board.png" });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tab", { name: "My ESP board" })).toBeHidden();

  // Phone-controlled LED: Run puts the board's own WiFi at the top of the code
  await page.locator(".project-card", { hasText: "Phone-controlled LED" }).click();
  const wizard = page.getByRole("dialog", { name: /Wiring Wizard/ });
  await expect(wizard).toBeVisible();
  await wizard.getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".editor-text")).toHaveValue(/WiFi\.softAP\(MY_WIFI_NAME, MY_WIFI_PASSWORD\)/);
  await page.locator("#tool-run").click();
  await expect(page.locator(".editor-text")).toHaveValue(new RegExp(`#define MY_WIFI_NAME "${board.ssid}"`));
  await expect(page.locator(".editor-text")).toHaveValue(new RegExp(`#define MY_WIFI_PASSWORD "${board.password}"`));

  // the teacher sees who has it
  const list = await (await request.get("/api/teacher/boards", { headers: { Authorization: `Bearer ${teacher}` } })).json();
  expect(list.boards.find((b) => b.id === board.id).student).toBe("Lena");
  expect(problems).toEqual([]);
  await ctx.close();
});

test("the teacher portal lists the boards, with their WiFi and sticker codes", async ({ browser, baseURL }) => {
  const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] }, baseURL });
  const page = await ctx.newPage();
  await page.goto("/");
  await page.getByLabel("Teacher code").fill("teacher-code-dev");
  await page.getByRole("button", { name: /Teacher sign in/ }).click();
  await page.waitForURL("**/teacher/");
  await expect(page.getByRole("heading", { name: "3. ESP boards" })).toBeVisible();
  await expect(page.locator("#b-kind option")).not.toHaveCount(0);
  await expect(page.locator("#b-table")).toContainText("ESP-21");
  await expect(page.locator("#b-table")).toContainText("Lena");
  await expect(page.locator("#b-label")).not.toHaveValue("ESP-21"); // the next free label
  await expect(page.locator("#b-print")).toBeVisible();
  await page.locator("#boards-card").screenshot({ path: "test-results/screenshots/teacher-boards.png" });
  await ctx.close();
});
