// USB serial without a driver: WebUSB "drivers" for the USB chips on school
// boards, for when Web Serial can't see the board (no driver on this
// computer, or a browser with WebUSB but no Web Serial, such as Chrome on an
// Android tablet).
//
// A browser can't install a driver on the computer. Instead, this file talks
// to the USB chip itself, the way the Linux and Android drivers do, and looks
// to the rest of ArduinoPath exactly like Web Serial's SerialPort: open(),
// readable, writable, setSignals(), getInfo(), close(). Uploading (STK500,
// esptool-js), the Serial Monitor and the Wiring Wizard's test all work
// through it unchanged.
//
// When the computer already has a driver for the board, the operating system
// owns the USB chip and WebUSB can't claim it: use Web Serial (the normal
// way) then. On Windows, WebUSB only reaches chips without a driver of their
// own in some set-ups, so the normal way is the one to use there.

/** The USB chips this file can drive, by vendor id (and product ids where it matters). */
export const CHIPS = [
  { vid: 0x1a86, pids: [0x7523, 0x7522, 0x5523, 0x55d4], driver: "ch340", name: "CH340" },
  { vid: 0x10c4, pids: [0xea60, 0xea70, 0xea71], driver: "cp210x", name: "CP2102" },
  { vid: 0x0403, pids: [0x6001, 0x6015, 0x6010, 0x6014], driver: "ftdi", name: "FTDI" },
  { vid: 0x2341, driver: "cdc", name: "Arduino" },
  { vid: 0x2a03, driver: "cdc", name: "Arduino" },
  { vid: 0x303a, driver: "cdc", name: "ESP32 USB" },
  { vid: 0x2e8a, driver: "cdc", name: "Raspberry Pi Pico" },
];

/** The filters for the browser's "connect a USB device" box. */
export const USB_FILTERS = CHIPS.flatMap((c) => (c.pids ? c.pids.map((p) => ({ vendorId: c.vid, productId: p })) : [{ vendorId: c.vid }]));

/** Which driver suits a device: "ch340", "cp210x", "ftdi", "cdc", or "" (none). */
export function driverFor(device) {
  const c = CHIPS.find((x) => x.vid === device.vendorId && (!x.pids || x.pids.includes(device.productId)));
  if (c) return c.driver;
  return findCdc(device) ? "cdc" : "";
}

// ----- the numbers each chip wants for a baud rate -----

/**
 * CH340 / CH341: the values for its divisor and prescaler register (0x1312)
 * and the clock factor register (0x0f2c), as the Android driver works them out.
 */
export function ch340Baud(baud) {
  let factor;
  let divisor;
  if (baud === 921600) {
    divisor = 7;
    factor = 0xf300;
  } else {
    factor = Math.floor(1532620800 / baud);
    divisor = 3;
    while (factor > 0xfff0 && divisor > 0) {
      factor >>= 3;
      divisor--;
    }
    if (factor > 0xfff0) throw new Error(`The board's USB chip can't talk at ${baud} baud.`);
    factor = 0x10000 - factor;
  }
  divisor |= 0x80; // send each byte straight away, don't wait for a full packet
  return { reg1312: (factor & 0xff00) | divisor, reg0f2c: factor & 0xff };
}

/** FTDI (FT232R and friends): the value and index for its SET_BAUD request (a 48 MHz clock). */
export function ftdiBaud(baud) {
  const frac = [0, 3, 2, 4, 1, 5, 6, 7];
  const div3 = Math.round(48000000 / (2 * baud)); // the divisor, in eighths
  let d = (div3 >> 3) | (frac[div3 & 7] << 14);
  if (d === 1) d = 0; // 3 Mbaud
  else if (d === 0x4001) d = 1; // 2 Mbaud
  return { value: d & 0xffff, index: d >>> 16 };
}

/** The 7 bytes of a CDC-ACM SET_LINE_CODING request: 8 data bits, no parity, 1 stop bit. */
export function cdcLineCoding(baud) {
  const b = new Uint8Array(7);
  new DataView(b.buffer).setUint32(0, baud, true);
  b[6] = 8;
  return b;
}

function findCdc(device) {
  const ifaces = device.configuration?.interfaces ?? device.configurations?.[0]?.interfaces ?? [];
  const data = ifaces.find((i) => i.alternates?.some((a) => a.interfaceClass === 0x0a) || i.alternate?.interfaceClass === 0x0a);
  if (!data) return null;
  const comm = ifaces.find((i) => (i.alternate?.interfaceClass ?? i.alternates?.[0]?.interfaceClass) === 0x02);
  return { data: data.interfaceNumber, comm: comm ? comm.interfaceNumber : data.interfaceNumber };
}

function bulkEndpoints(device, ifaceNumber) {
  const iface = device.configuration.interfaces.find((i) => i.interfaceNumber === ifaceNumber);
  const alt = iface?.alternate ?? iface?.alternates?.[0];
  const eps = alt?.endpoints ?? [];
  const inEp = eps.find((e) => e.direction === "in" && e.type === "bulk");
  const outEp = eps.find((e) => e.direction === "out" && e.type === "bulk");
  if (!inEp || !outEp) throw new Error("This USB device doesn't look like a board's serial port.");
  return { in: inEp.endpointNumber, out: outEp.endpointNumber, packet: inEp.packetSize || 64 };
}

// ----- the drivers: set up, set the speed, set DTR / RTS -----

const vendorOut = (dev, request, value, index = 0, data) =>
  dev.controlTransferOut({ requestType: "vendor", recipient: "device", request, value, index }, data);

const DRIVERS = {
  ch340: {
    iface: () => 0,
    async init(dev) {
      await dev.controlTransferIn({ requestType: "vendor", recipient: "device", request: 0x5f, value: 0, index: 0 }, 2);
      await vendorOut(dev, 0xa1, 0, 0);
    },
    async setBaud(dev, baud) {
      const { reg1312, reg0f2c } = ch340Baud(baud);
      await vendorOut(dev, 0x9a, 0x1312, reg1312);
      await vendorOut(dev, 0x9a, 0x0f2c, reg0f2c);
      await vendorOut(dev, 0x9a, 0x2518, 0xc3); // receive on, send on, 8 data bits, no parity, 1 stop bit
    },
    setLines: (dev, _iface, dtr, rts) => vendorOut(dev, 0xa4, ~((dtr ? 0x20 : 0) | (rts ? 0x40 : 0)) & 0xffff, 0),
  },
  cp210x: {
    iface: () => 0,
    out: (dev, iface, request, value, data) =>
      dev.controlTransferOut({ requestType: "vendor", recipient: "interface", request, value, index: iface }, data),
    async init(dev, iface) {
      await this.out(dev, iface, 0x00, 0x0001); // the UART on
    },
    async setBaud(dev, baud, iface) {
      const b = new Uint8Array(4);
      new DataView(b.buffer).setUint32(0, baud, true);
      await this.out(dev, iface, 0x1e, 0, b);
      await this.out(dev, iface, 0x03, 0x0800); // 8 data bits, no parity, 1 stop bit
    },
    setLines(dev, iface, dtr, rts) {
      return this.out(dev, iface, 0x07, 0x0300 | (dtr ? 1 : 0) | (rts ? 2 : 0));
    },
    async close(dev, iface) {
      await this.out(dev, iface, 0x00, 0x0000);
    },
  },
  ftdi: {
    iface: () => 0,
    status: 2, // each packet from the chip starts with 2 status bytes
    async init(dev) {
      await vendorOut(dev, 0, 0, 0); // reset
      await vendorOut(dev, 2, 0, 0); // no flow control
      await vendorOut(dev, 9, 1, 0); // answer within 1 ms (uploading needs quick replies)
    },
    async setBaud(dev, baud) {
      const { value, index } = ftdiBaud(baud);
      await vendorOut(dev, 3, value, index);
      await vendorOut(dev, 4, 0x0008, 0); // 8 data bits, no parity, 1 stop bit
    },
    setLines: (dev, _iface, dtr, rts) => vendorOut(dev, 1, (dtr ? 0x0101 : 0x0100) | (rts ? 0x0202 : 0x0200), 0),
  },
  cdc: {
    iface: (dev) => findCdc(dev)?.data ?? 0,
    comm: (dev) => findCdc(dev)?.comm ?? 0,
    out(dev, request, value, data) {
      return dev.controlTransferOut({ requestType: "class", recipient: "interface", request, value, index: this.comm(dev) }, data);
    },
    async init() {},
    async setBaud(dev, baud) {
      await this.out(dev, 0x20, 0, cdcLineCoding(baud));
    },
    setLines(dev, _iface, dtr, rts) {
      return this.out(dev, 0x22, (dtr ? 1 : 0) | (rts ? 2 : 0));
    },
  },
};

/** Explains WebUSB's errors in words a student can act on. */
export function friendlyUsbError(err) {
  const m = String(err?.message || err);
  if (err?.name === "SecurityError" || /access denied|unable to claim|claim interface/i.test(m)) {
    return "This computer is already using the board through its own driver. Choose it the normal way instead (Choose a board...).";
  }
  if (err?.name === "NotFoundError" || /disconnected|device unavailable|no device selected/i.test(m)) {
    return "The board was unplugged, or the connection stopped. Plug it back in and try again.";
  }
  return m;
}

/** A USB board's serial port, driven over WebUSB, shaped like Web Serial's SerialPort. */
export class UsbSerialPort {
  constructor(device) {
    this.device = device;
    this.kind = driverFor(device);
    this.driver = DRIVERS[this.kind];
    if (!this.driver) throw new Error("ArduinoPath doesn't know this USB device's chip.");
    this.via = "usb";
    this.isOpen = false;
    this.signals = { dataTerminalReady: false, requestToSend: false };
    this._readable = null;
    this._writable = null;
  }

  getInfo() {
    return { usbVendorId: this.device.vendorId, usbProductId: this.device.productId };
  }

  async open({ baudRate = 9600 } = {}) {
    if (this.isOpen) throw Object.assign(new Error("The port is already open."), { name: "InvalidStateError" });
    const dev = this.device;
    try {
      if (!dev.opened) await dev.open();
      if (!dev.configuration) await dev.selectConfiguration(1);
      this.iface = this.driver.iface(dev);
      const claim = [this.iface];
      if (this.kind === "cdc" && this.driver.comm(dev) !== this.iface) claim.push(this.driver.comm(dev));
      for (const n of claim) await dev.claimInterface(n);
      this.claimed = claim;
      this.ep = bulkEndpoints(dev, this.iface);
      await this.driver.init(dev, this.iface);
      await this.driver.setBaud(dev, baudRate, this.iface);
      await this.driver.setLines(dev, this.iface, this.signals.dataTerminalReady, this.signals.requestToSend);
    } catch (err) {
      try { await dev.close(); } catch { /* not open */ }
      throw Object.assign(new Error(friendlyUsbError(err)), { name: err?.name === "SecurityError" ? "NetworkError" : err?.name });
    }
    this.isOpen = true;
    this._readable = null;
    this._writable = null;
  }

  /** Like Web Serial: a fresh stream after the last one was cancelled. */
  get readable() {
    if (!this.isOpen) return null;
    if (!this._readable) this._readable = this.makeReadable();
    return this._readable;
  }

  get writable() {
    if (!this.isOpen) return null;
    if (!this._writable) this._writable = this.makeWritable();
    return this._writable;
  }

  makeReadable() {
    const dev = this.device;
    const { in: ep, packet } = this.ep;
    const status = this.driver.status || 0;
    let stopped = false;
    const stream = new ReadableStream({
      pull: async (controller) => {
        for (;;) {
          if (stopped || !this.isOpen) { try { controller.close(); } catch { /* closed */ } return; }
          let r;
          try {
            r = await dev.transferIn(ep, status ? packet * 8 : 4096);
          } catch (err) {
            if (stopped || !this.isOpen) { try { controller.close(); } catch { /* closed */ } return; }
            controller.error(Object.assign(new Error(friendlyUsbError(err)), { name: "NetworkError" }));
            return;
          }
          if (r.status === "stall") { await dev.clearHalt("in", ep).catch(() => {}); continue; }
          const bytes = new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength);
          const out = status ? stripStatus(bytes, packet, status) : bytes;
          if (out.length) { controller.enqueue(out); return; }
        }
      },
      cancel: () => {
        stopped = true;
        if (this._readable === stream) this._readable = null;
      },
    });
    return stream;
  }

  makeWritable() {
    const dev = this.device;
    const ep = this.ep.out;
    const done = () => { if (this._writable === stream) this._writable = null; };
    const stream = new WritableStream({
      write: async (chunk) => {
        const r = await dev.transferOut(ep, chunk);
        if (r.status === "stall") {
          await dev.clearHalt("out", ep);
          await dev.transferOut(ep, chunk);
        }
      },
      close: done,
      abort: done,
    });
    return stream;
  }

  async setSignals({ dataTerminalReady, requestToSend } = {}) {
    if (dataTerminalReady !== undefined) this.signals.dataTerminalReady = dataTerminalReady;
    if (requestToSend !== undefined) this.signals.requestToSend = requestToSend;
    await this.driver.setLines(this.device, this.iface, this.signals.dataTerminalReady, this.signals.requestToSend);
  }

  async close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    const dev = this.device;
    try { await this.driver.close?.(dev, this.iface); } catch { /* unplugged */ }
    for (const n of this.claimed || []) {
      try { await dev.releaseInterface(n); } catch { /* unplugged */ }
    }
    try { await dev.close(); } catch { /* unplugged */ }
    this._readable = null;
    this._writable = null;
  }
}

/** Takes the status bytes off the front of each packet (FTDI chips). */
export function stripStatus(bytes, packet, status) {
  const parts = [];
  let n = 0;
  for (let i = 0; i < bytes.length; i += packet) {
    const p = bytes.subarray(i + status, Math.min(i + packet, bytes.length));
    if (p.length) { parts.push(p); n += p.length; }
  }
  const out = new Uint8Array(n);
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}
