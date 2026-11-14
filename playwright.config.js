// Playwright drives the real site in Chromium: the real Go server in dev mode as the school server, and a second
// copy as a student Pi that passes classes on to it. Run: npm run e2e
import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT) || 8543;
const PI_PORT = Number(process.env.E2E_PI_PORT) || 8546; // a student Pi, for tests/e2e/student-pi.spec.js

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
  webServer: [
    {
      command: `go run ./cmd/circuitpathways -dev -addr :${PORT}`,
      url: `http://localhost:${PORT}/healthz`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `go run ./cmd/circuitpathways -dev -mode student-pi -addr :${PI_PORT} -school http://localhost:${PORT}`,
      url: `http://localhost:${PI_PORT}/healthz`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
