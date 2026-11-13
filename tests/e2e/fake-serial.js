// A pretend USB Arduino Uno for Chromium: navigator.serial with one port
// behind it. It speaks the Optiboot (STK500v1) bootloader until the program
// is uploaded, then acts like the running program: it says what the test
// tells it to and records what the page writes. Also routes /api/compile to
// an answer with a tiny compiled program, since the real compiler isn't here.

/** base64 of an Intel HEX file for a small program */
export function tinyHex() {
  const bytes = Array.from({ length: 200 }, (_, i) => (i * 3 + 1) & 0xff);
  const lines = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const chunk = bytes.slice(i, i + 16);
    const rec = [chunk.length, i >> 8, i & 0xff, 0, ...chunk];
    const sum = rec.reduce((a, b) => (a + b) & 0xff, 0);
    lines.push(":" + [...rec, (256 - sum) & 0xff].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase());
  }
  lines.push(":00000001FF");
  return Buffer.from(lines.join("\n") + "\n").toString("base64");
}

/**
 * @param page
 * @param {{ silentFirst?: number, programSays?: string[], compile?: object, usb?: boolean }} opts
 *   silentFirst: how many upload attempts the bootloader ignores (like a wrong board setting)
 *   programSays: what the uploaded program prints, one entry per message
 *   usb: Web Serial can't see the board (no driver); it's only there the USB
 *     way, as a CH340 chip on navigator.usb
 */
export async function installFakeBoard(page, { silentFirst = 0, programSays = [], compile, usb = false } = {}) {
  await page.addInitScript(({ silentFirst, programSays, usb }) => {
    const log = (window.__serial = { opens: [], writes: [], uploads: 0, requested: 0, flash: [] });
    const enc = new TextEncoder();
    let attempt = 0;

    const port = {
      state: "closed",
      getInfo: () => ({ usbVendorId: 0x1a86, usbProductId: 0x7523 }),
      async setSignals({ dataTerminalReady }) {
        if (dataTerminalReady) this.sawAssert = true;
        else if (this.sawAssert) { this.ready = true; }
      },
      async open(opts) {
        if (this.state === "open") throw Object.assign(new Error("The port is already open."), { name: "InvalidStateError" });
        this.state = "open";
        this.mode = "bootloader";
        this.ready = false;
        this.sawAssert = false;
        this.rx = [];
        this.addr = 0;
        log.opens.push(opts.baudRate);
        if (opts.baudRate === 115200 || opts.baudRate === 57600) {
          // the first open after a reset is the bootloader
          if (!this.uploaded) { attempt++; this.silent = attempt <= silentFirst; }
        }
        this.readable = new ReadableStream({ start: (c) => { this.ctl = c; } });
        this.writable = new WritableStream({ write: (chunk) => this.receive(chunk) });
        if (this.uploaded) this.startProgram();
      },
      async close() { this.state = "closed"; try { this.ctl.close(); } catch { /* ignore */ } this.readable = null; this.writable = null; },
      reply(...b) { if (!this.silent) this.ctl.enqueue(Uint8Array.from(b)); },
      startProgram() {
        this.mode = "program";
        let i = 0;
        const say = () => {
          if (this.state !== "open" || i >= programSays.length) return;
          try { this.ctl.enqueue(enc.encode(programSays[i++])); } catch { return; }
          setTimeout(say, 60);
        };
        setTimeout(say, 120);
      },
      receive(chunk) {
        if (this.mode === "program") { log.writes.push(new TextDecoder().decode(chunk)); return; }
        if (!this.ready || this.silent) return;
        this.rx.push(...chunk);
        const ARGS = { 0x30: 0, 0x50: 0, 0x51: 0, 0x55: 2, 0x74: 3, 0x75: 0 };
        for (;;) {
          const cmd = this.rx[0];
          if (cmd === undefined) return;
          if (cmd === 0x64) {
            if (this.rx.length < 4) return;
            const len = (this.rx[1] << 8) | this.rx[2];
            if (this.rx.length < 4 + len + 1) return;
            const data = this.rx.slice(4, 4 + len);
            log.flash[this.addr] = data;
            this.rx.splice(0, 4 + len + 1);
            this.reply(0x14, 0x10);
            continue;
          }
          const n = ARGS[cmd];
          if (n === undefined) { this.rx.shift(); this.reply(0x15); continue; }
          if (this.rx.length < 1 + n + 1) return;
          const args = this.rx.slice(1, 1 + n);
          this.rx.splice(0, 1 + n + 1);
          if (cmd === 0x55) this.addr = args[0] | (args[1] << 8);
          if (cmd === 0x51) { this.uploaded = true; log.uploads++; }
          if (cmd === 0x74) {
            const len = (args[0] << 8) | args[1];
            this.reply(0x14, ...(log.flash[this.addr] ?? new Array(len).fill(0xff)).slice(0, len), 0x10);
          } else this.reply(0x14, 0x10);
        }
      },
    };
    let granted = false;
    if (usb) {
      // No driver: Web Serial's box is empty (the student closes it).
      Object.defineProperty(navigator, "serial", {
        configurable: true,
        value: {
          getPorts: async () => [],
          requestPort: async () => { log.requested++; throw new DOMException("No port selected by the user.", "NotFoundError"); },
        },
      });
      // The same board as a CH340 chip, for WebUSB: control requests set the
      // speed and DTR, bulk transfers carry the bytes.
      const BAUD = { 0xcc83: 115200, 0x9883: 57600, 0xb282: 9600 };
      let reader = null;
      const shut = async () => { if (port.state === "open") await port.close(); reader = null; };
      const dev = {
        vendorId: 0x1a86, productId: 0x7523, opened: false, configuration: null,
        async open() { this.opened = true; },
        async close() { this.opened = false; await shut(); },
        async selectConfiguration() {
          this.configuration = { interfaces: [{ interfaceNumber: 0, alternate: { interfaceClass: 0xff, endpoints: [
            { endpointNumber: 2, direction: "in", type: "bulk", packetSize: 32 },
            { endpointNumber: 2, direction: "out", type: "bulk", packetSize: 32 }] } }] };
        },
        async claimInterface() { log.usbClaims = (log.usbClaims || 0) + 1; },
        async releaseInterface() { await shut(); },
        async clearHalt() {},
        async controlTransferIn(setup, len) { return { status: "ok", data: new DataView(new ArrayBuffer(len)) }; },
        async controlTransferOut(setup) {
          if (setup.request === 0x9a && setup.value === 0x1312) {
            await shut();
            await port.open({ baudRate: BAUD[setup.index] ?? 9600 });
            reader = port.readable.getReader();
          }
          if (setup.request === 0xa4) await port.setSignals({ dataTerminalReady: Boolean(~setup.value & 0x20) });
          return { status: "ok" };
        },
        async transferOut(ep, data) {
          port.receive(new Uint8Array(data.buffer ?? data, data.byteOffset ?? 0, data.byteLength));
          return { status: "ok", bytesWritten: data.byteLength };
        },
        async transferIn() {
          const r = reader;
          const { value, done } = r ? await r.read() : { done: true };
          if (done) throw new DOMException("The device was disconnected.", "NetworkError");
          return { status: "ok", data: new DataView(value.buffer, value.byteOffset, value.byteLength) };
        },
      };
      let usbGranted = false;
      Object.defineProperty(navigator, "usb", {
        configurable: true,
        value: {
          getDevices: async () => (usbGranted ? [dev] : []),
          requestDevice: async ({ filters }) => {
            log.usbRequested = (log.usbRequested || 0) + 1;
            if (!filters.some((f) => f.vendorId === 0x1a86 && (!f.productId || f.productId === 0x7523))) throw new DOMException("No device selected.", "NotFoundError");
            usbGranted = true;
            return dev;
          },
        },
      });
      return;
    }
    Object.defineProperty(navigator, "serial", {
      configurable: true,
      value: {
        getPorts: async () => (granted ? [port] : []),
        requestPort: async () => { log.requested++; granted = true; return port; },
      },
    });
  }, { silentFirst, programSays, usb });

  await page.route("**/api/compile", (r) => r.fulfill({
    json: compile ?? { ok: true, output: "", errors: [], size: { flash: 924, flash_max: 32256, ram: 9, ram_max: 2048 },
      artifacts: [{ name: "sketch.ino.hex", offset: 0, data: tinyHex() }] },
  }));
}
