// Gives the tests a student who has joined a class: a teacher makes a class
// code, the code is checked by the server, and the browser keeps it (what the
// home page does when a student types it in).
import { mkdirSync, writeFileSync } from "node:fs";

export default async function globalSetup(config) {
  const base = config.projects[0].use.baseURL ?? config.use.baseURL;
  const post = async (path, body, headers = {}) => {
    const r = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", ...headers }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
    return r.json();
  };
  const { token } = await post("/api/teacher/signin", { code: "teacher-code-dev" });
  const cls = await post("/api/teacher/class", { days: 3 }, { Authorization: `Bearer ${token}` });
  const joined = await post("/api/class/join", { code: cls.code });
  mkdirSync("test-results", { recursive: true });
  const access = JSON.stringify({ kind: "class", value: cls.code, expires_at: joined.expires_at });
  const state = { cookies: [], origins: [{ origin: base, localStorage: [{ name: "circuitpathways.access", value: access }] }] };
  writeFileSync("test-results/student.json", JSON.stringify(state));
}
