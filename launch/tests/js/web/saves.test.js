import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deflateRawSync } from "node:zlib";
import { writeZip, readZip, crc32 } from "../../../site/shared/local/zip.js";
import { writeSaveFile, readSaveFile, planImport, saveFileName } from "../../../site/shared/local/savefile.js";
import { createLocalApi, LocalError } from "../../../site/shared/local/localapi.js";
import { memoryStore } from "../../../site/shared/local/store.js";
import { cleanName, cleanNames, cleanSchool, nameKey } from "../../../site/shared/local/validate.js";

const dec = new TextDecoder();

/** A one-file zip whose entry is deflate-compressed, claiming `size` bytes unzipped. */
function deflatedZip(name, raw, size) {
  const n = Buffer.from(name);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(8, 8);
  local.writeUInt32LE(raw.length, 18); local.writeUInt32LE(size, 22); local.writeUInt16LE(n.length, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6); central.writeUInt16LE(8, 10);
  central.writeUInt32LE(raw.length, 20); central.writeUInt32LE(size, 24); central.writeUInt16LE(n.length, 28);
  const end = Buffer.alloc(22);
  const cdOffset = 30 + n.length + raw.length;
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(1, 8); end.writeUInt16LE(1, 10);
  end.writeUInt32LE(46 + n.length, 12); end.writeUInt32LE(cdOffset, 16);
  return new Uint8Array(Buffer.concat([local, n, raw, central, n, end]));
}

test("a zip written here is read back, and zlib's own zip reader agrees on the checksum", async () => {
  const bytes = writeZip([{ name: "a.txt", data: "hello" }, { name: "dir/b.bin", data: Uint8Array.of(1, 2, 3) }]);
  const m = await readZip(bytes);
  assert.equal(dec.decode(m.get("a.txt")), "hello");
  assert.deepEqual([...m.get("dir/b.bin")], [1, 2, 3]);
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
});

test("zips with unsafe names, too many files or a lying size are refused", async () => {
  await assert.rejects(readZip(writeZip([{ name: "../evil", data: "x" }])), /bad name/);
  await assert.rejects(readZip(writeZip([{ name: "a", data: "x" }, { name: "b", data: "y" }]), { maxEntries: 1 }), /too many/);
  await assert.rejects(readZip(writeZip([{ name: "big", data: "x".repeat(100) }]), { maxEntryBytes: 10 }), /too big/);
  await assert.rejects(readZip(Uint8Array.of(1, 2, 3)), /not a zip/);
  // a compressed entry that says it is 5 bytes but really holds 500 is a zip bomb
  await assert.rejects(readZip(deflatedZip("x", deflateRawSync(Buffer.alloc(500, 97)), 5)), /damaged/);
  assert.equal(dec.decode((await readZip(deflatedZip("x", deflateRawSync(Buffer.from("hello")), 5))).get("x")), "hello");
});

test("a save file from the desktop app (compressed) opens", async () => {
  const f = await readSaveFile(new Uint8Array(readFileSync(new URL("../fixtures/desktop.circuit", import.meta.url))));
  assert.deepEqual(f.profile.names, ["Mia", "Sam"]);
  assert.equal(f.profile.school, "Test Secondary College");
  assert.equal(f.sketches[0].project_id, "blink-traffic-lights");
  assert.match(f.sketches[0].code, /pinMode\(13, OUTPUT\)/);
  assert.equal(f.progress[0].data.stars, 3);
});

test("a file that isn't a save file, or is from the future, says so", async () => {
  await assert.rejects(readSaveFile(writeZip([{ name: "x.txt", data: "hi" }])), /can't be opened/);
  const newer = writeZip([{ name: "manifest.json", data: JSON.stringify({ format: "arduinopath-save", version: 99 }) }]);
  await assert.rejects(readSaveFile(newer), /newer/);
  const dup = writeZip([
    { name: "manifest.json", data: JSON.stringify({ format: "arduinopath-save", version: 1 }) },
    { name: "progress.json", data: JSON.stringify([{ project_id: "../../x", data: {}, updated_at: 1 }]) },
  ]);
  await assert.rejects(readSaveFile(dup), /can't be opened/);
});

test("times from the future are pulled back so they can't beat later saves", async () => {
  const bytes = writeSaveFile({ profile: { names: ["Mia"], school: "S", settings: {} }, sketches: [{ project_id: "p", code: "x", updated_at: 9e15 }], progress: [] }, 1000);
  const f = await readSaveFile(bytes, 2000);
  assert.equal(f.sketches[0].updated_at, 2000);
});

test("names and schools: the same rules as the desktop app", () => {
  assert.equal(cleanName("  mia  jo "), "Mia Jo");
  assert.equal(cleanName("McDonald"), "McDonald");
  assert.equal(cleanName("Zoë-Ann"), "Zoë-Ann");
  assert.equal(cleanName("Mia1"), "");
  assert.equal(cleanName("<script>"), "");
  assert.equal(cleanName("x".repeat(31)), "");
  assert.throws(() => cleanNames([]), /1 to 4/);
  assert.throws(() => cleanNames(["Mia", "mia"]), /once/);
  assert.equal(cleanSchool("St Helena Secondary College"), "St Helena Secondary College");
  assert.throws(() => cleanSchool("<b>"), /letters, numbers/);
  assert.equal(nameKey(["Sam", "Mia"], "Test  School"), nameKey(["mia", "SAM"], "test school"));
});

const catalogue = { boards: [{ id: "uno", default: true, order: 1 }, { id: "nano", order: 2, variants: [{ id: "old-bootloader" }] }] };
function newApi(extra = {}) {
  let id = null;
  let t = 1_000_000;
  return createLocalApi({
    store: extra.store ?? memoryStore(), catalogue: async () => catalogue,
    session: { get: () => id, set: (v) => { id = v; } }, now: () => (t += 1000),
  });
}

test("a student makes a profile, saves work, and gets it all back after logging in again", async () => {
  const api = newApi();
  await assert.rejects(api.me(), (e) => e.code === "logged_out");
  const me = await api.createStudent({ names: ["mia"], school: "Test College" });
  assert.deepEqual(me.student.names, ["Mia"]);
  assert.equal(me.settings.board, "uno");
  await assert.rejects(api.createStudent({ names: ["Mia"], school: "test college" }), (e) => e.status === 409);
  await api.saveSettings({ help_level: "moderate", board: "nano", board_variant: "old-bootloader", nudges: false });
  await api.saveSketch("blink-traffic-lights", "void setup(){}");
  await api.saveProgress("blink-traffic-lights", { step: 1 });
  await api.logout();
  const again = await api.login(me.student.id);
  assert.equal(again.settings.help_level, "moderate");
  assert.equal(again.settings.board_variant, "old-bootloader");
  assert.equal((await api.sketch("blink-traffic-lights")).code, "void setup(){}");
  assert.deepEqual((await api.progress()).map((p) => p.data), [{ step: 1 }]);
  assert.deepEqual((await api.students()).map((s) => s.names), [["Mia"]]);
  await assert.rejects(api.sketch("nothing-here"), (e) => e.status === 404);
  await assert.rejects(api.saveSketch("Bad Name", "x"), (e) => e.code === "bad_project");
  await assert.rejects(api.saveSketch("ok", "x".repeat(101 << 10)), (e) => e.status === 413);
  await assert.rejects(api.saveSettings({ board: "nope" }), (e) => e.code === "bad_settings");
});

test("Save my work then Open my work on another browser; older copies never replace newer work", async () => {
  const a = newApi();
  await a.createStudent({ names: ["Mia"], school: "Test College" });
  await a.saveSketch("servo-dial", "// first");
  const { bytes, name } = await a.exportMyWork();
  assert.match(name, /^Mia_ArduinoPath_\d{4}-\d{2}-\d{2}\.circuit$/);

  const b = newApi();
  await b.createStudent({ names: ["Mia"], school: "Test College" });
  const file = new Blob([bytes]);
  const preview = await b.previewImport(file);
  assert.equal(preview.same_name, true);
  assert.deepEqual(preview.changes.map((c) => c.action), ["add"]);
  assert.deepEqual(await b.applyImport(file, false), { added: 1, replaced: 0 });
  assert.equal((await b.sketch("servo-dial")).code, "// first");

  await b.saveSketch("servo-dial", "// newer on b"); // b is newer than the file now
  assert.deepEqual((await b.previewImport(file)).changes.map((c) => c.action), ["keep"]);
  assert.deepEqual(await b.applyImport(file, true), { added: 0, replaced: 0 });
  assert.equal((await b.sketch("servo-dial")).code, "// newer on b");

  await assert.rejects(b.previewImport(new Blob([Uint8Array.of(1, 2, 3)])), (e) => e.code === "not_save_file");
});

test("wipe deletes every profile and everything they saved", async () => {
  const api = newApi();
  await api.createStudent({ names: ["Mia"], school: "S" });
  await api.saveSketch("p", "x");
  const all = await api.exportEveryone();
  assert.match(all.name, /^Everyone_ArduinoPath_/);
  assert.equal((await readZip(all.bytes)).size, 1);
  await api.wipe();
  assert.deepEqual(await api.students(), []);
  await assert.rejects(api.me(), (e) => e instanceof LocalError && e.code === "logged_out");
});

test("two students can share a name at different schools", async () => {
  const api = newApi();
  await api.createStudent({ names: ["Sam"], school: "North High" });
  await api.createStudent({ names: ["Sam"], school: "South High" });
  assert.equal((await api.students()).length, 2);
});

test("file names are safe", () => {
  assert.equal(saveFileName(["Zoë", "Sam"], new Date("2026-10-29T00:00:00Z")), "Zo-Sam_ArduinoPath_2026-10-29.circuit");
  assert.equal(saveFileName(["Ñ"], new Date("2026-10-29T00:00:00Z")), "My_ArduinoPath_2026-10-29.circuit");
});

test("planImport", () => {
  const file = { sketches: [{ project_id: "a", updated_at: 5 }], progress: [{ project_id: "b", updated_at: 9 }] };
  const plan = planImport(file, [{ project_id: "a", updated_at: 5 }], [{ project_id: "b", updated_at: 3 }]);
  assert.deepEqual(plan.map((c) => [c.project_id, c.action]), [["a", "keep"], ["b", "replace"]]);
});
