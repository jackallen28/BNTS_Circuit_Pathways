import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLabel } from "../../site/shared/edition.js";

test("the build line says which server a tester is on, and the build", () => {
  assert.equal(buildLabel({ edition: "school", name: "pathways.local", commit: "5e86a54" }), "School server pathways.local, build 5e86a54");
  assert.equal(buildLabel({ edition: "student-pi", name: "pi-07.local", commit: "abc1234" }), "Student Pi pi-07.local, build abc1234");
  assert.equal(buildLabel({ edition: "school", name: "", commit: "" }), "School server");
});

test("a server that doesn't say anything gives no line at all", () => {
  assert.equal(buildLabel({ edition: "", name: "", commit: "" }), "");
});
