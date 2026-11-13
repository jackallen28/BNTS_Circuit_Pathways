import { test } from "node:test";
import assert from "node:assert/strict";
import { normalisePiId, takePiFromUrl, thisPi } from "../../site/shared/thispi.js";

function memory() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), map: m };
}

test("Pi IDs are tidied, and anything else is ignored", () => {
  assert.equal(normalisePiId("k7m2qx9p"), "K7M2-QX9P");
  assert.equal(normalisePiId(" K7M2-QX9P "), "K7M2-QX9P");
  assert.equal(normalisePiId("K7M2-QX9"), "");
  assert.equal(normalisePiId("<script>"), "");
  assert.equal(normalisePiId(null), "");
});

test("a Pi's shortcut (?pi=) is remembered for PiPath and taken out of the address", () => {
  const store = memory();
  let replaced = null;
  const hist = { state: null, replaceState: (_s, _t, url) => { replaced = url; } };
  const id = takePiFromUrl({ href: "https://cp.example/pipath/?pi=k7m2-qx9p#/lesson/l1" }, store, hist);
  assert.equal(id, "K7M2-QX9P");
  assert.equal(replaced, "/pipath/#/lesson/l1");
  assert.equal(store.getItem("pipath.pi_id"), "K7M2-QX9P");
  assert.equal(thisPi(store), "K7M2-QX9P");
});

test("no ?pi=, or a bad one, changes nothing it shouldn't", () => {
  const store = memory();
  const hist = { replaceState: () => assert.fail("nothing to tidy") };
  assert.equal(takePiFromUrl({ href: "https://cp.example/pipath/?x=1" }, store, hist), "");
  assert.equal(store.map.size, 0);
  let replaced = null;
  assert.equal(takePiFromUrl({ href: "https://cp.example/?pi=nope&need=class" }, store, { replaceState: (_s, _t, url) => { replaced = url; } }), "");
  assert.equal(replaced, "/?need=class"); // the bad value still leaves the address
  assert.equal(store.map.size, 0);
  assert.equal(thisPi(store), "");
});
