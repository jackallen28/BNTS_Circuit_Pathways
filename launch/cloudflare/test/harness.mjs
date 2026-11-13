// Starts the Worker locally (workerd, with a fresh local D1 and Durable Objects) for the tests.
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));
const wrangler = join(here, "node_modules", ".bin", "wrangler");

export const VARS = {
  CLASS_SECRET: "test-class-secret-0123456789",
  TEACHER_CODES: "teacher-code-one,teacher-code-two",
  PI_KEY_SECRET: "dev-pi-key-secret-do-not-use-in-production",
};

/** @returns {Promise<{url: string, stop: () => void, out: () => string}>} */
export async function startWorker({ port = 8700 + Math.floor(Math.random() * 200), vars = {}, env } = {}) {
  const persist = mkdtempSync(join(tmpdir(), "cp-cf-"));
  const envArgs = env ? ["--env", env] : [];
  execFileSync(wrangler, ["d1", "migrations", "apply", "DB", "--local", "--persist-to", persist, ...envArgs], { cwd: here, stdio: "pipe" });
  const all = { ...VARS, ...vars };
  const args = ["dev", "--local", "--port", String(port), "--persist-to", persist, "--show-interactive-dev-session=false", ...envArgs,
    ...Object.entries(all).flatMap(([k, v]) => ["--var", `${k}:${v}`])];
  const child = spawn(wrangler, args, { cwd: here, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, NO_COLOR: "1" } });
  let out = "";
  child.stdout.on("data", (d) => { out += d; });
  child.stderr.on("data", (d) => { out += d; });
  const url = `http://localhost:${port}`;
  for (let i = 0; i < 120; i++) {
    if (/Ready on/.test(out)) break;
    if (child.exitCode !== null) throw new Error(`wrangler dev stopped:\n${out}`);
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!/Ready on/.test(out)) { child.kill(); throw new Error(`wrangler dev didn't start:\n${out}`); }
  return { url, stop: () => child.kill(), out: () => out, persist };
}

export function api(url) {
  return async (method, path, { body, token, headers = {} } = {}) => {
    const res = await fetch(url + path, {
      method,
      headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...(method !== "GET" ? { "X-Circuit-Pathways": "1" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...headers },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    return { status: res.status, data, headers: res.headers };
  };
}
