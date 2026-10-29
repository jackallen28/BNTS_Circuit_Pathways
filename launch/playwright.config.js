// Playwright drives the real site (the real Go server in dev mode, its own
// port) in Chromium. Run: npm run e2e
import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT) || 8543;

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./tests/e2e/global-setup.js",
  use: {
    baseURL: `http://localhost:${PORT}`,
    storageState: "test-results/student.json",
    trace: "retain-on-failure",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: `go run ./cmd/launch -dev -addr :${PORT}`,
    url: `http://localhost:${PORT}/healthz`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
