// Uploads a program to an ESP8266 or ESP32 board from the browser, with
// Espressif's esptool-js (vendored in /arduinopath/vendor/esptool-js).

import { getPort } from "../webserial.js";

let lib;
async function load() {
  lib ??= await import("../../vendor/esptool-js/bundle.js");
  return lib;
}

/**
 * @param {string} portId
 * @param {{ data: Uint8Array, offset: number }[]} files
 * @param {{baud?: number, onProgress?: (pct: number, what: string) => void, onLog?: (s: string) => void,
 *   mustBe?: string, notYours?: string, onChip?: (c: {chip: string, mac: string}) => void}} opts
 *   mustBe: the MAC address of the only board this may flash (a student's own school board); notYours: what to say if
 *   it's another one. onChip hears which chip and MAC address it found (the teacher portal records it).
 * @returns {Promise<{chip: string, mac: string}>}
 */
export async function flashEsp(portId, files, { baud = 460800, onProgress = () => {}, onLog = () => {}, mustBe = "", notYours = "", onChip = () => {} } = {}) {
  const { ESPLoader, Transport } = await load();
  const port = getPort(portId);
  const transport = new Transport(port, false);
  const terminal = {
    clean() {},
    write: (s) => onLog(s),
    writeLine: (s) => onLog(s + "\n"),
  };
  // Cheap USB chips are unreliable above this speed.
  const loader = new ESPLoader({ transport, baudrate: Math.min(baud, 460800), romBaudrate: 115200, terminal });
  try {
    onLog("Connecting to the board...\n(If this stalls, hold the BOOT or FLASH button while it connects.)\n");
    const chip = await loader.main();
    onLog(`Found ${chip}.\n`);
    const mac = normaliseMac(await loader.chip.readMac(loader));
    onChip({ chip, mac });
    if (mustBe && mac !== normaliseMac(mustBe)) {
      // a student's school board: only theirs may be flashed (nothing has been written to this one)
      throw Object.assign(new Error(notYours || "This isn't your board."), { code: "not_your_board" });
    }
    const total = files.reduce((n, f) => n + f.data.length, 0);
    let done = 0;
    const sizes = files.map((f) => f.data.length);
    await loader.writeFlash({
      fileArray: files.map((f) => ({ data: f.data, address: f.offset })),
      flashSize: "keep", flashMode: "keep", flashFreq: "keep", eraseAll: false, compress: true,
      reportProgress: (i, written, size) => {
        done = sizes.slice(0, i).reduce((a, b) => a + b, 0) + (written / size) * sizes[i];
        onProgress(Math.min(99, Math.round((done / total) * 100)), "Uploading");
      },
    });
    await loader.after();
    onProgress(100, "Done");
    return { chip, mac };
  } catch (err) {
    if (err?.code === "not_your_board") throw err;
    const m = String(err?.message || err);
    if (/timeout|failed to connect|no serial data|wrong boot mode/i.test(m)) {
      throw new Error("Failed to connect to the board: timed out. Hold the BOOT (or FLASH) button on the board, press Upload again, and let go once it says Connecting. Check you chose the right board too.");
    }
    throw err;
  } finally {
    try { await transport.disconnect(); } catch { /* already closed */ }
  }
}

/** "A4:CF:12:0B:9E:01" or "a4cf120b9e01" → "a4:cf:12:0b:9e:01" ("" if it isn't a MAC address). */
export function normaliseMac(s) {
  const hex = String(s ?? "").toLowerCase().replace(/[^0-9a-f]/g, "");
  return hex.length === 12 ? hex.match(/../g).join(":") : "";
}
