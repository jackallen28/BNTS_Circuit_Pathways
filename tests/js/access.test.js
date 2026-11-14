import { test } from "node:test";
import assert from "node:assert/strict";

// localStorage isn't in Node: a tiny stand-in
const mem = new Map();
globalThis.localStorage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const { getAccess, setAccess, clearAccess, inClass } = await import("../../site/shared/access.js");

test("with no class a student is 'local': their work is saved in this browser", () => {
  clearAccess();
  const a = getAccess();
  assert.equal(a.kind, "local");
  assert.equal(a.value, "local");
  assert.equal(inClass(a), false);
  assert.equal(inClass(null), false);
});

test("a joined class wins over local, and an ended one falls back to local", () => {
  clearAccess();
  setAccess("student", "s2.token", Date.now() + 60_000, { names: ["Mia"] });
  assert.equal(getAccess().kind, "student");
  assert.equal(inClass(getAccess()), true);
  assert.equal(getAccess(Date.now() + 120_000).kind, "local"); // the class ended
});

test("a teacher's sign-in lasts until it expires; an old kind of access is forgotten", () => {
  clearAccess();
  setAccess("teacher", "t2.token", Date.now() + 60_000);
  assert.equal(getAccess().kind, "teacher");
  assert.equal(inClass(getAccess()), true);
  assert.equal(getAccess(Date.now() + 120_000).kind, "local");
  setAccess("class", "ABCDE-FGHJK", Date.now() + 60_000); // the old stateless class codes
  assert.equal(getAccess().kind, "local");
  assert.equal(mem.has("circuitpathways.access"), false);
});
