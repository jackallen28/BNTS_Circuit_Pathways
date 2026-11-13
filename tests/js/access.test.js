import { test } from "node:test";
import assert from "node:assert/strict";

// localStorage isn't in Node: a tiny stand-in
const mem = new Map();
globalThis.localStorage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const { getAccess, setAccess, clearAccess, inClass } = await import("../../site/shared/access.js");

test("a normal site needs a class code", () => {
  clearAccess();
  assert.equal(getAccess(Date.now(), false), null);
  setAccess("student", "s2.token", Date.now() + 60_000, { names: ["Mia"] });
  assert.equal(getAccess(Date.now(), false).kind, "student");
  assert.equal(inClass(getAccess(Date.now(), false)), true);
});

test("the TEST version gives the open 'beta' access, but a class joined (beta teacher mode) or a teacher wins", () => {
  clearAccess();
  assert.equal(getAccess(Date.now(), false, true).kind, "beta");
  assert.equal(inClass(getAccess(Date.now(), false, true)), false);
  setAccess("student", "s2.token", Date.now() + 60_000, { names: ["Ari"] });
  assert.equal(getAccess(Date.now(), false, true).kind, "student");
  assert.equal(inClass(getAccess(Date.now(), false, true)), true);
  clearAccess();
  setAccess("teacher", "t2.token", Date.now() + 60_000);
  assert.equal(getAccess(Date.now(), false, true).kind, "teacher");
  assert.equal(getAccess(Date.now() + 120_000, false, true).kind, "beta", "an expired sign-in falls back to open access");
});

test("the Pi beta lets a student start with no class: they're 'local'", () => {
  clearAccess();
  const a = getAccess(Date.now(), true);
  assert.equal(a.kind, "local");
  assert.equal(a.value, "local");
  assert.equal(inClass(a), false);
  assert.equal(inClass(null), false);
});

test("in the Pi beta a joined class wins over local, and an expired one falls back to local", () => {
  clearAccess();
  setAccess("student", "s2.token", Date.now() + 60_000, { names: ["Mia"] });
  assert.equal(getAccess(Date.now(), true).kind, "student");
  assert.equal(inClass(getAccess(Date.now(), true)), true);
  assert.equal(getAccess(Date.now() + 120_000, true).kind, "local"); // the class ended
  assert.equal(inClass({ kind: "teacher", value: "t" }), true);
});
