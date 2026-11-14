// Gives the tests a student who has joined a class: a teacher makes a class on the school server, and a
// student joins it with a first name and school (what the home page does), and the browser keeps the token.
import { mkdirSync, writeFileSync } from "node:fs";

export default async function globalSetup(config) {
  const base = config.projects[0].use.baseURL ?? config.use.baseURL;
  const post = async (path, body, headers = {}) => {
    const r = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", ...headers }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
    return r.json();
  };
  const { token } = await post("/api/teacher/signin", { code: "teacher-code-dev" });
  const cls = await post("/api/teacher/class", { name: "Test class", days: 3 }, { Authorization: `Bearer ${token}` });
  const joined = await post("/api/class/join", { code: cls.code, names: ["Tester"], school: "Test School" });
  mkdirSync("test-results", { recursive: true });
  const access = JSON.stringify({ kind: "student", value: joined.token, expires_at: joined.expires_at, names: joined.student.names, school: joined.student.school, class: joined.class });
  const state = { cookies: [], origins: [{ origin: base, localStorage: [{ name: "circuitpathways.access", value: access }] }] };
  writeFileSync("test-results/student.json", JSON.stringify(state));
}
