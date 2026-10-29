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
 * @param {{ silentFirst?: number, programSays?: string[], compile?: object }} opts
 *   silentFirst: how many upload attempts the bootloader ignores (like a wrong board setting)
 *   programSays: what the uploaded program prints, one entry per message
 */
export async function installFakeBoard(page, { silentFirst = 0, programSays = [], compile } = {}) {
  await page.addInitScript(({ silentFirst, programSays }) => {
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
    Object.defineProperty(navigator, "serial", {
      configurable: true,
      value: {
        getPorts: async () => (granted ? [port] : []),
        requestPort: async () => { log.requested++; granted = true; return port; },
      },
    });
  }, { silentFirst, programSays });

  await page.route("**/api/compile", (r) => r.fulfill({
    json: compile ?? { ok: true, output: "", errors: [], size: { flash: 924, flash_max: 32256, ram: 9, ram_max: 2048 },
      artifacts: [{ name: "sketch.ino.hex", offset: 0, data: tinyHex() }] },
  }));
}
