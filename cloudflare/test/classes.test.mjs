// The Worker's saved classes, against a real local Worker and D1.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { startWorker, api } from "./harness.mjs";

let w;
let call;
before(async () => { w = await startWorker(); call = api(w.url); });
after(() => w?.stop());

test("static pages come with the site's security headers", async () => {
  const home = await fetch(w.url + "/");
  assert.equal(home.status, 200);
  assert.match(home.headers.get("content-security-policy"), /style-src 'self' 'unsafe-inline'/);
  const pi = await fetch(w.url + "/pipath/");
  assert.equal(pi.headers.get("cross-origin-embedder-policy"), "require-corp");
  assert.match(pi.headers.get("content-security-policy"), /style-src 'self'$/);
  assert.equal(pi.headers.get("content-security-policy").includes("unsafe-inline"), false);
  const teacher = await fetch(w.url + "/teacher/");
  assert.equal(teacher.status, 200);
  assert.ok(teacher.headers.get("content-security-policy"), "pages the Worker passes on keep their headers");
  const cat = await fetch(w.url + "/arduinopath/data/catalogue.json");
  assert.equal(cat.status, 200);
  assert.ok((await cat.json()).projects.length > 10);
  const info = await call("GET", "/api/info");
  assert.equal(info.data.classes, true);
  assert.equal(info.data.relay, "ws");
});

test("a teacher makes a class, students join with first names and school, work syncs, and deleting removes it all", async () => {
  assert.equal((await call("POST", "/api/teacher/signin", { body: { code: "wrong-code-xx" } })).status, 401);
  const t1 = (await call("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).data.token;
  const t2 = (await call("POST", "/api/teacher/signin", { body: { code: "teacher-code-two" } })).data.token;
  assert.ok(t1 && t2 && t1 !== t2);

  const made = await call("POST", "/api/teacher/class", { token: t1, body: { name: "7B Thursday", school: "Eltham High", days: 30 } });
  assert.equal(made.status, 200, JSON.stringify(made.data));
  const code = made.data.code;
  assert.match(code, /^[0-9A-Z]{5}-[0-9A-Z]{5}$/);
  assert.equal((await call("POST", "/api/teacher/class", { token: t1, body: { name: "Mia's class <b>", days: 3 } })).status, 400);
  assert.equal((await call("POST", "/api/teacher/class", { token: t1, body: { name: "x", days: 999 } })).status, 400);

  // only the teacher who made it sees it
  assert.equal((await call("GET", "/api/teacher/classes", { token: t1 })).data.classes.length, 1);
  assert.equal((await call("GET", "/api/teacher/classes", { token: t2 })).data.classes.length, 0);
  assert.equal((await call("GET", `/api/teacher/class/${code}`, { token: t2 })).status, 404);

  // joining: the code alone says the class is real; then first names + school
  assert.equal((await call("POST", "/api/class/join", { body: { code: "ZZZZZ-ZZZZZ" } })).status, 404);
  const peek = await call("POST", "/api/class/join", { body: { code: code.toLowerCase() } });
  assert.equal(peek.data.needs_names, true);
  assert.equal(peek.data.class.school, "Eltham High");
  assert.equal((await call("POST", "/api/class/join", { body: { code, names: ["Mia Smith-Jones!"] } })).status, 400);
  const mia = await call("POST", "/api/class/join", { body: { code, names: ["mia"] } });
  assert.equal(mia.status, 200);
  assert.deepEqual(mia.data.student, { names: ["Mia"], school: "Eltham High" });
  const noor = await call("POST", "/api/class/join", { body: { code, names: ["Noor", "Sam"], school: "Diamond Valley College" } });

  // work syncs, and newer work is never replaced by older
  const push = (token, items) => call("POST", "/api/student/work", { token, body: { items } });
  assert.equal((await push(mia.data.token, [{ app: "arduinopath", item: "blink", kind: "sketch", body: "void setup(){}", updated_at: 2000 }])).status, 200);
  await push(mia.data.token, [{ app: "arduinopath", item: "blink", kind: "sketch", body: "OLD", updated_at: 1000 }]);
  await push(mia.data.token, [{ app: "pipath", item: "s1_hello", kind: "progress", body: '{"step":2}', updated_at: 3000 }]);
  const mine = await call("GET", "/api/student/work", { token: mia.data.token });
  assert.equal(mine.data.work.find((x) => x.item === "blink").body, "void setup(){}");
  assert.equal(mine.data.work.length, 2);
  for (const bad of [{ app: "evil", item: "x", kind: "sketch", body: "" }, { app: "pipath", item: "../x", kind: "sketch", body: "" }, { app: "pipath", item: "x", kind: "photo", body: "" }, { app: "pipath", item: "x", kind: "sketch", body: "x".repeat(101 * 1024) }]) {
    assert.ok([400, 413].includes((await push(mia.data.token, [bad])).status), JSON.stringify(bad).slice(0, 60));
  }
  assert.equal((await push("s2.nonsense", [{ app: "pipath", item: "x", kind: "sketch", body: "" }])).status, 401);

  // the teacher sees first names, school and work; nothing else is stored about a student
  const roster = await call("GET", `/api/teacher/class/${code}`, { token: t1 });
  assert.deepEqual(roster.data.students.map((s) => s.names), [["Mia"], ["Noor", "Sam"]]);
  assert.deepEqual(Object.keys(roster.data.students[0]).sort(), ["id", "items", "joined_at", "last_work", "names", "school", "seen_at"]);
  const work = await call("GET", `/api/teacher/class/${code}/work`, { token: t1 });
  assert.equal(work.data.students[0].work.length, 2);

  // a student can take themselves off; the teacher can remove a student
  assert.equal((await call("DELETE", "/api/student/me", { token: noor.data.token })).status, 204);
  assert.equal((await call("GET", "/api/student/me", { token: noor.data.token })).status, 401);
  assert.equal((await call("GET", `/api/teacher/class/${code}`, { token: t1 })).data.students.length, 1);

  // deleting the class removes everything, and the student's token stops working
  assert.equal((await call("DELETE", `/api/teacher/class/${code}`, { token: t1 })).status, 204);
  assert.equal((await call("GET", "/api/student/work", { token: mia.data.token })).status, 401);
  assert.equal((await call("POST", "/api/class/join", { body: { code } })).status, 404);
});

test("writes need the site's header, and a class that has ended is cleaned up by the daily job", async () => {
  const r = await fetch(w.url + "/api/teacher/signin", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: "teacher-code-one" }) });
  assert.equal(r.status, 403);
  const t = (await call("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).data.token;
  const c = (await call("POST", "/api/teacher/class", { token: t, body: { name: "Short", ends_at: Date.now() + 1500 } })).data.code;
  const s = (await call("POST", "/api/class/join", { body: { code: c, names: ["Ava"] } })).data.token;
  await call("POST", "/api/student/work", { token: s, body: { items: [{ app: "pipath", item: "x", kind: "sketch", body: "print(1)" }] } });
  await new Promise((res) => setTimeout(res, 1800));
  assert.equal((await call("GET", "/api/student/work", { token: s })).status, 401, "an ended class doesn't work any more");
  const cron = await fetch(w.url + "/cdn-cgi/handler/scheduled");
  assert.equal(cron.status, 200);
  const left = await call("GET", "/api/teacher/classes", { token: t });
  assert.equal(left.data.classes.find((x) => x.code === c), undefined);
});
