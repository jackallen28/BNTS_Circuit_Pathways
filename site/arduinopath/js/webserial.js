// Web Serial in Edge and Chrome: finding boards, reading and writing their
// serial port. Browsers never list every port: the student picks their
// board once in the browser's own "Select a port" box, and the browser
// remembers it for this site.
//
// When Web Serial can't see a board (no driver on this computer), or the
// browser has WebUSB but no Web Serial (Chrome on Android), the "USB way"
// talks to the board's USB chip itself: see usbserial.js.

import { UsbSerialPort, USB_FILTERS, driverFor } from "./usbserial.js";

/** Is Web Serial here? (Not in Safari or Firefox.) */
export const serialSupported = typeof navigator !== "undefined" && "serial" in navigator;
/** Is WebUSB here? (Chrome and Edge, including Chrome on Android.) */
export const usbSupported = typeof navigator !== "undefined" && "usb" in navigator;
/** Can this browser reach a board at all? */
export const supported = serialSupported || usbSupported;

export const NO_SERIAL_MESSAGE =
  "Uploading to a board needs Chrome or Edge. Open this page in one of those. (The simulator works in any browser.)";

const ids = new WeakMap();
let nextId = 1;

/** A stable name for a port during this visit, such as "usb-1a86-7523-2". */
export function portId(port) {
  if (!ids.has(port)) {
    const { usbVendorId: v, usbProductId: p } = port.getInfo?.() ?? {};
    ids.set(port, v ? `usb-${v.toString(16)}-${p.toString(16)}-${nextId++}` : `port-${nextId++}`);
  }
  return ids.get(port);
}

const byId = new Map();

function describe(port) {
  const { usbVendorId: vid, usbProductId: pid } = port.getInfo?.() ?? {};
  const id = portId(port);
  byId.set(id, port);
  return { port: id, vid: vid ? vid.toString(16).padStart(4, "0") : "", pid: pid ? pid.toString(16).padStart(4, "0") : "", chip: chipOf(vid), ...(port.via === "usb" ? { via: "usb" } : {}) };
}

/** What USB chip a vendor id belongs to (the common ones in school kits). */
export function chipOf(vid) {
  switch (vid) {
    case 0x1a86: return "CH340";
    case 0x10c4: return "CP2102";
    case 0x0403: return "FTDI";
    case 0x2341: case 0x2a03: return "Arduino";
    case 0x303a: return "ESP32 USB";
    case 0x2e8a: return "Raspberry Pi Pico";
    default: return "";
  }
}

/** Adds a port to the list (used when the browser hands us one, and by the tests). Returns its id. */
export function register(port) {
  return describe(port).port;
}

// One UsbSerialPort per USB device, so a board keeps its id while it's plugged in.
const usbPorts = new WeakMap();
function usbPort(device) {
  if (!usbPorts.has(device)) usbPorts.set(device, new UsbSerialPort(device));
  return usbPorts.get(device);
}

/** Boards this site has already been allowed to use (the normal way, then the USB way). */
export async function listPorts() {
  const out = [];
  if (serialSupported) {
    try { out.push(...(await navigator.serial.getPorts()).map(describe)); } catch { /* none */ }
  }
  if (usbSupported) {
    try {
      for (const d of await navigator.usb.getDevices()) if (driverFor(d)) out.push(describe(usbPort(d)));
    } catch { /* none */ }
  }
  return out;
}

/**
 * Opens the browser's "Select a port" box (or, in a browser without Web
 * Serial, its "connect a USB device" box). Returns the port's id, or null if
 * the student cancelled.
 */
export async function requestPort() {
  if (!serialSupported) {
    if (usbSupported) return requestUsbPort();
    throw new Error(NO_SERIAL_MESSAGE);
  }
  try {
    return describe(await navigator.serial.requestPort()).port;
  } catch (err) {
    if (err?.name === "NotFoundError") return null; // cancelled
    throw err;
  }
}

/** The USB way: the browser's "connect a USB device" box, for boards Web Serial can't see. */
export async function requestUsbPort() {
  if (!usbSupported) throw new Error(NO_SERIAL_MESSAGE);
  try {
    return describe(usbPort(await navigator.usb.requestDevice({ filters: USB_FILTERS }))).port;
  } catch (err) {
    if (err?.name === "NotFoundError") return null; // cancelled, or no board plugged in
    throw err;
  }
}

/** The SerialPort for an id from listPorts / requestPort. */
export function getPort(id) {
  const p = byId.get(id);
  if (!p) throw new Error("That port isn't there any more. Pick your board again.");
  return p;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export { sleep };

/** Turns the browser's serial errors into something a student can act on. */
export function friendlyError(err) {
  const name = err?.name;
  if (name === "InvalidStateError" || /already open/i.test(err?.message || "")) {
    return "Your board's port is busy. Close other tabs or programs using it (like the Arduino IDE), then try again.";
  }
  if (name === "NetworkError" || /failed to open/i.test(err?.message || "")) {
    return "The board's port couldn't be opened. Is another program using it? Unplug the board, plug it back in, and try again.";
  }
  if (name === "NotFoundError" || /device has been lost/i.test(err?.message || "")) {
    return "The board was unplugged, or the connection stopped. Plug it back in and try again.";
  }
  return err?.message || "Something went wrong with the serial connection.";
}

/**
 * An open serial port with a background reader. bytes arrive in a buffer so
 * callers can wait for exactly the number they need, with a timeout.
 */
export class Pump {
  constructor(port) {
    this.port = port;
    this.buf = [];
    this.waiters = [];
    this.closed = false;
    this.onBytes = null; // (Uint8Array) => void, for the Serial Monitor
    this.onEnd = null; // (reason) => void
  }

  async open(baudRate) {
    await this.port.open({ baudRate, dataBits: 8, stopBits: 1, parity: "none", flowControl: "none", bufferSize: 8192 });
    this.reader = this.port.readable.getReader();
    this.writer = this.port.writable.getWriter();
    this.loop = this.pump();
  }

  async pump() {
    let reason = "";
    try {
      for (;;) {
        const { value, done } = await this.reader.read();
        if (done) break;
        if (value?.length) {
          if (this.onBytes) this.onBytes(value);
          else for (const b of value) this.buf.push(b);
          this.wake();
        }
      }
    } catch (err) {
      reason = this.closed ? "" : friendlyError(err);
    }
    this.wake();
    if (!this.closed && this.onEnd) this.onEnd(reason);
  }

  wake() {
    const ws = this.waiters;
    this.waiters = [];
    ws.forEach((w) => w());
  }

  async write(bytes) {
    await this.writer.write(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
  }

  /** Waits for n bytes. Rejects with {timeout: true} if they don't come in ms. */
  async read(n, ms = 500) {
    const until = Date.now() + ms;
    while (this.buf.length < n) {
      const left = until - Date.now();
      if (left <= 0) throw Object.assign(new Error("The board didn't answer."), { timeout: true });
      await new Promise((resolve) => {
        const t = setTimeout(resolve, left);
        this.waiters.push(() => { clearTimeout(t); resolve(); });
      });
    }
    return Uint8Array.from(this.buf.splice(0, n));
  }

  flush() {
    this.buf.length = 0;
  }

  setSignals(dtr, rts) {
    return this.port.setSignals({ dataTerminalReady: dtr, requestToSend: rts });
  }

  async close() {
    this.closed = true;
    try { await this.reader.cancel(); } catch { /* already gone */ }
    try { this.reader.releaseLock(); } catch { /* ignore */ }
    try { this.writer.releaseLock(); } catch { /* ignore */ }
    try { await this.loop; } catch { /* ignore */ }
    try { await this.port.close(); } catch { /* ignore */ }
  }
}
