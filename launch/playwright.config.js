// Playwright drives the real site (the real Go server in dev mode, its own
// port) in Chromium. Run: npm run e2e
import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT) || 8543;
const BETA_PORT = Number(process.env.E2E_BETA_PORT) || 8544; // the TEST version, for tests/e2e/test-version.spec.js
const CF_PORT = Number(process.env.E2E_CF_PORT) || 8545; // the Cloudflare Worker (local), for tests/e2e/cloudflare.spec.js

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
      command: `go run ./cmd/launch -dev -addr :${PORT}`,
      url: `http://localhost:${PORT}/healthz`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `go run ./cmd/launch -dev -beta -addr :${BETA_PORT}`,
      url: `http://localhost:${BETA_PORT}/healthz`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `sh cloudflare/test/serve.sh ${CF_PORT}`,
      url: `http://localhost:${CF_PORT}/api/info`,
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
