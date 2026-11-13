// A pretend Arduino Uno with an Optiboot (STK500v1) bootloader, behind a
// pretend Web Serial port, so the uploader can be tested without hardware.

const ARGS = { 0x30: 0, 0x50: 0, 0x51: 0, 0x55: 2, 0x74: 3, 0x75: 0 };

export class FakeUno {
  constructor({ corruptRead = false, silent = false } = {}) {
    this.flash = new Uint8Array(32768).fill(0xff);
    this.corruptRead = corruptRead;
    this.silent = silent;
    this.rx = [];
    this.addr = 0;
    this.progMode = false;
    this.ready = false; // the bootloader only listens after a reset
    this.sawAssert = false;
    this.left = false;
    this.opened = false;
    this.closed = false;
    this.readable = new ReadableStream({ start: (c) => { this.ctl = c; } });
    this.writable = new WritableStream({ write: (chunk) => this.receive(chunk) });
  }

  getInfo() { return { usbVendorId: 0x2341, usbProductId: 0x0043 }; }
  async open(opts) { this.opened = true; this.baud = opts.baudRate; }
  async close() { this.closed = true; }

  async setSignals({ dataTerminalReady }) {
    if (dataTerminalReady) this.sawAssert = true;
    else if (this.sawAssert) this.ready = true; // released after being asserted: reset done
  }

  reply(...bytes) { if (!this.silent) this.ctl.enqueue(Uint8Array.from(bytes)); }

  receive(chunk) {
    if (!this.ready || this.silent) return;
    this.rx.push(...chunk);
    for (;;) {
      const cmd = this.rx[0];
      if (cmd === undefined) return;
      if (cmd === 0x64) {
        if (this.rx.length < 4) return;
        const len = (this.rx[1] << 8) | this.rx[2];
        if (this.rx.length < 4 + len + 1) return;
        const data = this.rx.slice(4, 4 + len);
        this.flash.set(data, this.addr * 2);
        this.rx.splice(0, 4 + len + 1);
        this.reply(0x14, 0x10);
        continue;
      }
      const n = ARGS[cmd];
      if (n === undefined) { this.rx.shift(); this.reply(0x15); continue; }
      if (this.rx.length < 1 + n + 1) return;
      const args = this.rx.slice(1, 1 + n);
      this.rx.splice(0, 1 + n + 1);
      if (cmd === 0x50) this.progMode = true;
      if (cmd === 0x51) { this.progMode = false; this.left = true; }
      if (cmd === 0x55) this.addr = args[0] | (args[1] << 8);
      if (cmd === 0x74) {
        const len = (args[0] << 8) | args[1];
        const page = Array.from(this.flash.slice(this.addr * 2, this.addr * 2 + len));
        if (this.corruptRead) page[3] ^= 0xff;
        this.reply(0x14, ...page, 0x10);
      } else {
        this.reply(0x14, 0x10);
      }
    }
  }
}
