import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLabel } from "../../site/shared/beta.js";

test("the build line says which edition, host and commit a tester is on", () => {
  assert.equal(buildLabel({ edition: "pi-beta", host: "cloudflare", commit: "5e86a54" }), "Pi beta, Cloudflare, build 5e86a54");
  assert.equal(buildLabel({ edition: "test", host: "render", commit: "abc1234" }), "TEST version, Render, build abc1234");
  assert.equal(buildLabel({ edition: "", host: "cloudflare", commit: "bc2377e" }), "Real site, Cloudflare, build bc2377e");
  assert.equal(buildLabel({ edition: "", host: "go", commit: "" }), "Real site, Go server");
});

test("a server that doesn't say anything gives no line at all", () => {
  assert.equal(buildLabel({ edition: "", host: "", commit: "" }), "");
});
