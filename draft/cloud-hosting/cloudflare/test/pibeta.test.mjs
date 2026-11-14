// The Pi beta (PI_BETA=1): students on Raspberry Pis start with no class code (work stays on the device),
// or join a class and sync to the database. This checks the Worker's side: what "local" may do.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { startWorker, api } from "./harness.mjs";

let pi;
let testSite;
let normal;
let onPi;
let onTest;
let onNormal;

before(async () => {
  [pi, testSite, normal] = await Promise.all([startWorker({ env: "pi" }), startWorker({ env: "test" }), startWorker()]);
  onPi = api(pi.url);
  onTest = api(testSite.url);
  onNormal = api(normal.url);
});
after(() => { pi?.stop(); testSite?.stop(); normal?.stop(); });

test("/api/info says it's the Pi beta and that a class code is optional", async () => {
  const { data } = await onPi("GET", "/api/info");
  assert.equal(data.edition, "pi-beta");
  assert.equal(data.host, "cloudflare");
  assert.equal(data.class_optional, true);
  assert.equal(data.classes, true, "classes still work");
  assert.equal(data.beta, false, "it saves, unlike the TEST version");
  const plain = (await onNormal("GET", "/api/info")).data;
  assert.equal(plain.edition, "");
  assert.equal(plain.class_optional, false);
});

test("a student with no class ('local') may compile and link a Pi; a made-up word may not", async () => {
  const body = { code: "void setup(){}\nvoid loop(){}", board: "uno" };
  const local = await onPi("POST", "/api/compile", { body, headers: { "X-Access": "local" } });
  assert.notEqual(local.status, 401, "local is let in (503 just means no compiler is set up here)");
  assert.equal((await onPi("POST", "/api/compile", { body, headers: { "X-Access": "made-up" } })).status, 401);
  const cmd = await onPi("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "local" } });
  assert.notEqual(cmd.status, 401);
  assert.equal((await onPi("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "made-up" } })).status, 401);
});

test("the normal site still needs a class: 'local' means nothing there", async () => {
  const body = { code: "void setup(){}\nvoid loop(){}", board: "uno" };
  assert.equal((await onNormal("POST", "/api/compile", { body, headers: { "X-Access": "local" } })).status, 401);
  assert.equal((await onNormal("POST", "/api/pi/command", { body: { code: "K7M2-QX9P", cmd: { op: "ping" } }, headers: { "X-Access": "local" } })).status, 401);
});

test("classes, teachers and the Pi installer are all there (unlike the TEST version)", async () => {
  assert.equal((await onPi("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).status, 200);
  const res = await fetch(`${pi.url}/pipath/remote/install.sh`);
  assert.equal(res.status, 200);
  assert.match(await res.text(), /Circuit Pathways Pi Link/);
});

// Beta teacher mode: on both beta editions a teacher makes up a teacher code of their own (8+ characters),
// so anyone testing can make a class and have students join it. The real site only takes the school's codes.
test("/api/info says teacher mode is on in both beta editions, and only there", async () => {
  assert.equal((await onPi("GET", "/api/info")).data.teacher_mode, true);
  const t = (await onTest("GET", "/api/info")).data;
  assert.equal(t.teacher_mode, true);
  assert.equal(t.beta, true);
  assert.equal(t.edition, "test");
  assert.equal(t.classes, true, "the TEST version keeps classes now");
  assert.equal((await onNormal("GET", "/api/info")).data.teacher_mode, false);
});

for (const [name, site] of [["the Pi beta", () => onPi], ["the TEST version", () => onTest]]) {
  test(`${name}: a teacher makes up a code, makes a class, a student joins and their work reaches the teacher`, async () => {
    const call = site();
    assert.equal((await call("POST", "/api/teacher/signin", { body: { code: "short" } })).status, 401, "needs 8 characters");
    const t = await call("POST", "/api/teacher/signin", { body: { code: "my own teacher code" } });
    assert.equal(t.status, 200, JSON.stringify(t.data));
    const mine = t.data.token;
    // the same made-up code is the same teacher (their classes follow it); another code is a different one
    const again = (await call("POST", "/api/teacher/signin", { body: { code: "my own teacher code" } })).data.token;
    const other = (await call("POST", "/api/teacher/signin", { body: { code: "somebody else's code" } })).data.token;

    const made = await call("POST", "/api/teacher/class", { token: mine, body: { name: "Beta class", school: "Eltham High", days: 7 } });
    assert.equal(made.status, 200, JSON.stringify(made.data));
    const code = made.data.code;
    assert.equal((await call("GET", "/api/teacher/classes", { token: again })).data.classes.length, 1);
    assert.equal((await call("GET", "/api/teacher/classes", { token: other })).data.classes.length, 0, "other testers can't see it");

    const joined = await call("POST", "/api/class/join", { body: { code, names: ["Ari"] } });
    assert.equal(joined.status, 200, JSON.stringify(joined.data));
    const push = await call("POST", "/api/student/work", { token: joined.data.token, body: { items: [{ app: "pipath", item: "free", kind: "sketch", body: 'print("hi")', updated_at: 5000 }] } });
    assert.equal(push.status, 200);
    const roster = await call("GET", `/api/teacher/class/${code}`, { token: again });
    assert.deepEqual(roster.data.students.map((x) => x.names), [["Ari"]]);
    // a student in a class may use the compiler and Pi relay (a class member, as on the real site)
    assert.notEqual((await call("POST", "/api/compile", { body: { code: "x", board: "uno" }, headers: { "X-Access": joined.data.token } })).status, 401);
  });
}

test("the real site still takes only the school's teacher codes", async () => {
  assert.equal((await onNormal("POST", "/api/teacher/signin", { body: { code: "my own teacher code" } })).status, 401);
  assert.equal((await onNormal("POST", "/api/teacher/signin", { body: { code: "teacher-code-one" } })).status, 200);
});

test("the TEST version's open access word still works, and the Pi installer is no longer hidden there", async () => {
  const body = { code: "void setup(){}\nvoid loop(){}", board: "uno" };
  assert.notEqual((await onTest("POST", "/api/compile", { body, headers: { "X-Access": "beta" } })).status, 401);
  assert.equal((await onTest("POST", "/api/compile", { body, headers: { "X-Access": "local" } })).status, 401, "'local' is the Pi beta's word, not the TEST version's");
  assert.equal((await fetch(`${testSite.url}/teacher/`)).status, 200);
});
