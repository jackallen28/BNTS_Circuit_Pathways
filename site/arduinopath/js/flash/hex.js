// Reads an Intel HEX file (what the Arduino compiler makes for an Uno or Nano)
// into bytes, with the gaps filled with 0xFF (an erased byte).

/** @returns {{ data: Uint8Array, start: number }} */
export function parseHex(text) {
  const chunks = [];
  let base = 0;
  let eof = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (line[0] !== ":") throw new Error("This isn't a .hex file.");
    const bytes = [];
    for (let i = 1; i + 1 < line.length; i += 2) bytes.push(parseInt(line.slice(i, i + 2), 16));
    if (bytes.some(Number.isNaN) || bytes.length < 5) throw new Error("The .hex file is damaged.");
    const len = bytes[0];
    if (bytes.length !== len + 5) throw new Error("The .hex file is damaged.");
    if (bytes.reduce((a, b) => (a + b) & 0xff, 0) !== 0) throw new Error("The .hex file is damaged (bad checksum).");
    const addr = (bytes[1] << 8) | bytes[2];
    const type = bytes[3];
    const payload = bytes.slice(4, 4 + len);
    if (type === 0) chunks.push({ at: base + addr, payload });
    else if (type === 1) { eof = true; break; }
    else if (type === 2) base = ((payload[0] << 8) | payload[1]) << 4;
    else if (type === 4) base = ((payload[0] << 8) | payload[1]) << 16;
  }
  if (!eof || !chunks.length) throw new Error("The .hex file is empty or cut short.");
  const start = Math.min(...chunks.map((c) => c.at));
  const end = Math.max(...chunks.map((c) => c.at + c.payload.length));
  if (end > 0x40000) throw new Error("This program is too big for the board.");
  const data = new Uint8Array(end - start).fill(0xff);
  for (const c of chunks) data.set(c.payload, c.at - start);
  return { data, start };
}
