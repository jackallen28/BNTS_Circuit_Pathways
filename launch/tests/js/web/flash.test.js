import { test } from "node:test";
import assert from "node:assert/strict";
import { parseHex } from "../../../site/arduinopath/js/flash/hex.js";
import { flashAvr } from "../../../site/arduinopath/js/flash/stk500v1.js";
import { register } from "../../../site/arduinopath/js/webserial.js";
import { FakeUno } from "./fake-board.js";

// :LLAAAATT<data>CC lines for a 300-byte program at address 0.
function hexFor(bytes) {
  const lines = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const chunk = bytes.slice(i, i + 16);
    const rec = [chunk.length, i >> 8, i & 0xff, 0, ...chunk];
    const sum = rec.reduce((a, b) => (a + b) & 0xff, 0);
    lines.push(":" + [...rec, (256 - sum) & 0xff].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase());
  }
  lines.push(":00000001FF");
  return lines.join("\n") + "\n";
}

const program = Uint8Array.from({ length: 300 }, (_, i) => (i * 7 + 3) & 0xff);

test("an Intel HEX file is read into bytes", () => {
  const { data, start } = parseHex(hexFor(program));
  assert.equal(start, 0);
  assert.deepEqual([...data], [...program]);
});

test("a damaged .hex file is refused", () => {
  assert.throws(() => parseHex("hello"), /isn't a \.hex/);
  assert.throws(() => parseHex(":0400000001020304F1\n:00000001FF\n"), /bad checksum/);
  assert.throws(() => parseHex(":0400000001020304F2\n"), /cut short|empty/);
});

test("the program goes onto a pretend Uno, is read back, and the board is let go", async () => {
  const board = new FakeUno();
  const id = register(board);
  const progress = [];
  await flashAvr(id, hexFor(program), { baud: 115200, onProgress: (p) => progress.push(p) });
  assert.deepEqual([...board.flash.slice(0, program.length)], [...program]);
  assert.equal(board.flash[program.length], 0xff, "the rest of the last page stays erased");
  assert.equal(board.baud, 115200);
  assert.ok(board.left, "the bootloader was told to leave programming mode");
  assert.ok(board.closed, "the port was closed");
  assert.equal(progress.at(-1), 100);
  assert.ok(progress.every((p, i) => i === 0 || p >= progress[i - 1]), "progress never goes backwards");
});

test("a board that reads back something different is reported", async () => {
  const id = register(new FakeUno({ corruptRead: true }));
  await assert.rejects(flashAvr(id, hexFor(program)), /doesn't match/);
});

test("a board that never answers gives a helpful message and still closes the port", async () => {
  const board = new FakeUno({ silent: true });
  const id = register(board);
  await assert.rejects(flashAvr(id, hexFor(program)), /isn't answering/);
  assert.ok(board.closed);
});
