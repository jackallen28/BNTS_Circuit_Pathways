// Class sync: work saved in the browser also goes to the student's class (the Cloudflare site), newer
// work comes back down on another device, and a save file carries the class link to a new device.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createLocalApi } from "../../../site/shared/local/localapi.js";
import { memoryStore } from "../../../site/shared/local/store.js";
import { createCloud, validLink } from "../../../site/shared/local/cloud.js";

const TOKEN = `s2.${"a".repeat(32)}.${"b".repeat(32)}`;
const catalogue = { boards: [{ id: "uno", default: true, order: 1 }] };

/** A pretend class on the server: just the work rows, as the Worker keeps them. */
function fakeServer() {
  const rows = new Map();
  let ended = false;
  const fetchImpl = async (url, init = {}) => {
    const auth = (init.headers?.Authorization ?? "").replace("Bearer ", "");
    if (ended || auth !== TOKEN) return new Response("{}", { status: 401 });
    if ((init.method ?? "GET") === "POST") {
      assert.equal(init.headers["X-Circuit-Pathways"], "1");
      for (const it of JSON.parse(init.body).items) {
        const k = `${it.app}/${it.item}/${it.kind}`;
        if (!rows.has(k) || rows.get(k).updated_at <= it.updated_at) rows.set(k, it);
      }
      return Response.json({ saved: 1 });
    }
    return Response.json({ work: [...rows.values()] });
  };
  return { rows, fetchImpl, end: () => { ended = true; } };
}

function newApi(server, link) {
  let id = null;
  let t = 1_000_000;
  const cloud = createCloud({ link: () => link, fetchImpl: server.fetchImpl, delay: 0 });
  const api = createLocalApi({
    store: memoryStore(), catalogue: async () => catalogue, cloud,
    session: { get: () => id, set: (v) => { id = v; } }, now: () => (t += 1000),
  });
  return { api, cloud };
}

test("a class member's work goes up to the class, and comes down on a second device", async () => {
  const server = fakeServer();
  const link = { token: TOKEN, names: ["Mia"], school: "Test College" };
  const a = newApi(server, link);
  await a.api.createStudent({ names: ["mia"], school: "Test College" });
  await a.api.saveSketch("blink", "void setup(){}");
  await a.api.saveProgress("blink", { step: 2 });
  await a.cloud.flush();
  assert.equal(server.rows.get("arduinopath/blink/sketch").body, "void setup(){}");
  assert.equal(JSON.parse(server.rows.get("arduinopath/blink/progress").body).step, 2);

  // a second device (the Raspberry Pi), same class link: the work is there when the profile is made
  const b = newApi(server, link);
  await b.api.createStudent({ names: ["Mia"], school: "Test College" });
  assert.equal((await b.api.sketch("blink")).code, "void setup(){}");
  assert.deepEqual((await b.api.progress()).map((p) => p.data.step), [2]);
});

test("another student on the same device isn't linked to someone else's class place", async () => {
  const server = fakeServer();
  const a = newApi(server, { token: TOKEN, names: ["Mia"], school: "Test College" });
  await a.api.createStudent({ names: ["Noor"], school: "Test College" });
  await a.api.saveSketch("blink", "Noor's code");
  await a.cloud.flush();
  assert.equal(server.rows.size, 0, "Noor's work stays in this browser");
});

test("a save file carries the class link to a new device, and a class that has ended stops syncing", async () => {
  const server = fakeServer();
  const a = newApi(server, { token: TOKEN, names: ["Mia"], school: "Test College" });
  await a.api.createStudent({ names: ["Mia"], school: "Test College" });
  await a.api.saveSketch("blink", "first");
  const { bytes } = await a.api.exportMyWork();

  // a device with no class link (a Pi at home): opening the file links it
  const b = newApi(server, null);
  await b.api.createStudent({ names: ["Mia"], school: "Test College" });
  const file = { arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
  const res = await b.api.applyImport(file, true);
  assert.equal(res.linked, true);
  await b.api.saveSketch("blink", "second, on the Pi");
  await b.cloud.flush();
  assert.equal(server.rows.get("arduinopath/blink/sketch").body, "second, on the Pi");

  server.end();
  await b.api.saveSketch("blink", "after the class ended");
  assert.equal(await b.cloud.flush(), "ended");
  assert.equal(server.rows.get("arduinopath/blink/sketch").body, "second, on the Pi");
  assert.ok(validLink(TOKEN) && !validLink("s2.x.y"));
});
