// Uploads a program to an Arduino Uno or Nano (the Optiboot / STK500v1
// bootloader) from the browser. This is the same conversation avrdude has
// with the board: reset the board, say hello, send the program page by page,
// read it back to check, and start it.

import { Pump, getPort, sleep } from "../webserial.js";
import { parseHex } from "./hex.js";

const STK = {
  GET_SYNC: 0x30, ENTER_PROGMODE: 0x50, LEAVE_PROGMODE: 0x51, LOAD_ADDRESS: 0x55,
  PROG_PAGE: 0x64, READ_PAGE: 0x74, READ_SIGN: 0x75,
  CRC_EOP: 0x20, INSYNC: 0x14, OK: 0x10, FAILED: 0x11, NOSYNC: 0x15,
};

const PAGE = 128; // an ATmega328P's flash page, in bytes

async function command(pump, bytes, replyLen = 0, ms = 600) {
  await pump.write([...bytes, STK.CRC_EOP]);
  const head = await pump.read(1, ms);
  if (head[0] !== STK.INSYNC) throw new Error("The board answered, but not in the way the bootloader should. Is the right board chosen?");
  const body = replyLen ? await pump.read(replyLen, ms) : new Uint8Array();
  const end = await pump.read(1, ms);
  if (end[0] !== STK.OK) throw new Error("The board refused a command (is it the right board? Nano clones often need the old bootloader setting).");
  return body;
}

async function reset(pump) {
  await pump.setSignals(true, true);
  await sleep(250);
  await pump.setSignals(false, false);
  await sleep(60);
}

async function sync(pump) {
  for (let i = 0; i < 12; i++) {
    pump.flush();
    try {
      await command(pump, [STK.GET_SYNC], 0, 150);
      // The bootloader sometimes answers twice; make sure the line is clear.
      await sleep(20);
      pump.flush();
      return;
    } catch {
      if (i === 5) await reset(pump); // one more reset part-way through
    }
  }
  throw new Error("The board isn't answering. Check the board in Settings (Uno, or Nano with the old bootloader), unplug and replug it, then try again.");
}

/**
 * @param {string} portId        from listPorts / requestPort
 * @param {string} hexText       the compiled sketch (.hex)
 * @param {{baud: number, onProgress?: (pct: number, what: string) => void, onLog?: (s: string) => void}} opts
 */
export async function flashAvr(portId, hexText, { baud = 115200, onProgress = () => {}, onLog = () => {} } = {}) {
  const { data } = parseHex(hexText);
  const pump = new Pump(getPort(portId));
  await pump.open(baud);
  try {
    onLog("Resetting the board...\n");
    await reset(pump);
    await sync(pump);
    onLog("Talking to the bootloader.\n");
    await command(pump, [STK.ENTER_PROGMODE]);
    const pages = Math.ceil(data.length / PAGE);
    // write
    for (let p = 0; p < pages; p++) {
      const chunk = new Uint8Array(PAGE).fill(0xff);
      chunk.set(data.subarray(p * PAGE, (p + 1) * PAGE));
      const word = (p * PAGE) >> 1;
      await command(pump, [STK.LOAD_ADDRESS, word & 0xff, word >> 8]);
      await command(pump, [STK.PROG_PAGE, PAGE >> 8, PAGE & 0xff, 0x46, ...chunk], 0, 1500);
      onProgress(Math.round(((p + 1) / pages) * 50), "Uploading");
    }
    // read it back and compare
    for (let p = 0; p < pages; p++) {
      const word = (p * PAGE) >> 1;
      await command(pump, [STK.LOAD_ADDRESS, word & 0xff, word >> 8]);
      const back = await command(pump, [STK.READ_PAGE, PAGE >> 8, PAGE & 0xff, 0x46], PAGE, 1500);
      const want = data.subarray(p * PAGE, (p + 1) * PAGE);
      for (let i = 0; i < want.length; i++) {
        if (back[i] !== want[i]) throw new Error("The board's copy of the program doesn't match. Try uploading again.");
      }
      onProgress(50 + Math.round(((p + 1) / pages) * 50), "Checking");
    }
    await command(pump, [STK.LEAVE_PROGMODE]);
    onLog(`Done: ${data.length} bytes written and checked.\n`);
  } catch (err) {
    if (err?.timeout) throw new Error("The board stopped answering. Unplug it, plug it back in, and try again.");
    throw err;
  } finally {
    await pump.close();
  }
}
