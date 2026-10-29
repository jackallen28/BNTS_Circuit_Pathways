// Real boards, from the browser: the server compiles the code, then this
// page uploads it over USB with Web Serial (Edge or Chrome), and the Serial
// Monitor reads the board's port.

import { api } from "./api.js";
import * as ws from "./webserial.js";
import { flashAvr } from "./flash/stk500v1.js";
import { flashEsp } from "./flash/esp.js";

export const supported = ws.supported;
export const NO_SERIAL_MESSAGE = ws.NO_SERIAL_MESSAGE;

/** Which family a board belongs to. */
export function familyOf(board) {
  return board?.family ?? "avr";
}

/** The boards this site has already been allowed to use (see requestPort). */
export const listPorts = ws.listPorts;

/** Asks the student to pick their board in the browser's own box. Returns its id, or null if they cancelled. */
export const requestPort = ws.requestPort;

const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

/** How this board is uploaded: its own settings, or its chosen variant's. */
export function uploadSettings(board, variant) {
  const v = variant && (board.variants ?? []).find((x) => x.id === variant);
  return v?.upload ?? board.upload ?? {};
}

/** The server's answer in the shape the workspace shows: { state, kind, result, output, error }. */
function compileJob(res, kind) {
  const result = { ok: res.ok, output: res.output, errors: res.errors ?? [], size: res.size };
  return { state: res.ok ? "done" : "failed", kind, result, output: res.output, error: "" };
}

/** Compiles code for the student's board with the real compiler: the judge. */
export async function compile(code, board, variant, onUpdate = () => {}) {
  onUpdate({ state: "compiling", output: "" });
  const res = await api.compile(code, board.id, variant);
  const job = compileJob(res, "compile");
  onUpdate(job);
  return job;
}

/** Compiles the code, then uploads it to the board on port (an id from listPorts / requestPort). */
export async function upload(code, board, variant, port, onUpdate = () => {}) {
  onUpdate({ state: "compiling", output: "" });
  const res = await api.compile(code, board.id, variant);
  if (!res.ok) {
    const job = compileJob(res, "upload");
    onUpdate(job);
    return job;
  }
  const settings = uploadSettings(board, variant);
  let log = "";
  const update = (extra = {}) => onUpdate({ state: "uploading", kind: "upload", output: log, progress: 0, ...extra });
  const onLog = (s) => { log += s; update({ progress: lastPct }); };
  let lastPct = 0;
  const onProgress = (pct) => { lastPct = pct; update({ progress: pct }); };
  try {
    if (!ws.supported) throw new Error(ws.NO_SERIAL_MESSAGE);
    update();
    if (settings.protocol === "stk500v1") {
      const hex = res.artifacts?.find((a) => a.name.endsWith(".hex"));
      if (!hex) throw new Error("The compiler didn't make a program for the board.");
      await flashAvr(port, new TextDecoder().decode(b64(hex.data)), { baud: settings.baud || 115200, onProgress, onLog });
    } else if (settings.protocol === "esptool") {
      if (!res.artifacts?.length) throw new Error("The compiler didn't make a program for the board.");
      await flashEsp(port, res.artifacts.map((a) => ({ data: b64(a.data), offset: a.offset })), { baud: settings.baud, onProgress, onLog });
    } else {
      throw new Error("Uploading to this board from the website isn't ready yet. You can still check your code and use the simulator.");
    }
  } catch (err) {
    const message = ws.friendlyError(err);
    const job = { ...compileJob(res, "upload"), state: "failed", output: log, error: message };
    onUpdate(job);
    return job;
  }
  const job = { ...compileJob(res, "upload"), progress: 100 };
  onUpdate(job);
  return job;
}

/**
 * Is this a USB port (a board)? Browsers only ever list ports the student
 * chose, so these are all boards.
 */
export function isUsb(p) {
  return Boolean(p?.vid);
}

/** USB ports first. */
export function sortPorts(ports) {
  return [...ports].sort((a, b) => Number(isUsb(b)) - Number(isUsb(a)));
}

/**
 * The best guess at the student's board: the remembered port if it's still
 * there, else a port whose board matches, else the only USB port, else null.
 */
export function guessPort(ports, board, remembered) {
  if (remembered && ports.some((p) => p.port === remembered)) return remembered;
  const match = ports.find((p) => p.fqbn && board && p.fqbn.startsWith(board.fqbn.split(":").slice(0, 3).join(":")));
  if (match) return match.port;
  const usb = ports.filter(isUsb);
  return usb.length === 1 ? usb[0].port : null;
}

const PORT_KEY = "arduinopath.port";

/** The port the student used last (shared by the workspace and the Wiring Wizard). */
export function rememberedPort() {
  try {
    return sessionStorage.getItem(PORT_KEY);
  } catch {
    return null;
  }
}

export function rememberPort(port) {
  try {
    sessionStorage.setItem(PORT_KEY, port);
  } catch { /* storage blocked */ }
}

/** A friendly name for a port: "CH340: most clone boards". */
export function portLabel(p) {
  const chips = {
    CH340: "CH340: most clone boards",
    CP2102: "CP2102: NodeMCU, ESP32",
    FTDI: "FTDI",
    Arduino: "Arduino",
    "ESP32 USB": "ESP32 USB",
  };
  const what = p.board || chips[p.chip];
  const name = p.vid ? `USB board ${p.vid}:${p.pid}` : "Serial port";
  return what ? `${name} (${what})` : name;
}

/**
 * The Serial Monitor for a real board. onData(text), onClose(reason).
 * Returns { write(text), close() }.
 *
 * Right after an upload the port can be missing or busy for a moment while
 * the board restarts (boards with USB built in, like the ESP32-C3, even
 * disappear and come back), so it tries again for a few seconds
 * (retryMs) before giving up.
 */
export function openSerial(portId, baud, { onData, onOpen = () => {}, onClose = () => {}, retryMs = 0 } = {}) {
  const giveUpAt = Date.now() + retryMs;
  let pump = null;
  let closed = false;
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const finish = (reason) => {
    if (closed) return;
    closed = true;
    pump?.close();
    onClose(reason);
  };
  (async () => {
    for (;;) {
      if (closed) return;
      try {
        pump = new ws.Pump(ws.getPort(portId));
        await pump.open(baud);
        break;
      } catch (err) {
        pump = null;
        if (Date.now() < giveUpAt) { await ws.sleep(700); continue; }
        finish(ws.friendlyError(err));
        return;
      }
    }
    if (closed) { pump.close(); return; }
    pump.onBytes = (bytes) => onData(decoder.decode(bytes, { stream: true }));
    pump.onEnd = (reason) => finish(reason || "Your board was unplugged, or the connection stopped. Plug it back in, then press Upload again.");
    onOpen();
  })();
  return {
    write: async (text) => {
      if (!pump) throw new Error("The Serial Monitor isn't connected yet.");
      await pump.write(encoder.encode(text));
    },
    close: () => finish(""),
  };
}
