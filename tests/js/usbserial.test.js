import { test } from "node:test";
import assert from "node:assert/strict";
import { UsbSerialPort, ch340Baud, ftdiBaud, cdcLineCoding, driverFor, stripStatus, USB_FILTERS } from "../../site/arduinopath/js/usbserial.js";
import { Pump } from "../../site/arduinopath/js/webserial.js";

/** A pretend USB board: records control requests, echoes what's written. */
function fakeDevice({ vendorId, productId, interfaces, status = 0, packet = 64 }) {
  const queue = [];
  let waiting = null;
  const dev = {
    vendorId, productId, opened: false, configuration: null, controls: [], claimed: new Set(), written: [],
    async open() { this.opened = true; },
    async close() { this.opened = false; if (waiting) { const w = waiting; waiting = null; w.reject(Object.assign(new Error("The device was disconnected."), { name: "NotFoundError" })); } },
    async selectConfiguration() { this.configuration = { interfaces }; },
    async claimInterface(n) { this.claimed.add(n); },
    async releaseInterface(n) { this.claimed.delete(n); },
    async controlTransferOut(setup, data) { this.controls.push({ ...setup, data: data ? [...data] : undefined }); return { status: "ok" }; },
    async controlTransferIn(setup, len) { this.controls.push({ ...setup, in: len }); return { status: "ok", data: new DataView(new ArrayBuffer(len)) }; },
    async clearHalt() {},
    async transferOut(ep, data) {
      const bytes = [...new Uint8Array(data.buffer ?? data, data.byteOffset ?? 0, data.byteLength ?? data.length)];
      this.written.push(...bytes);
      // echo it back, with the chip's status bytes in front of each packet
      const body = bytes.map((b) => b ^ 0xff);
      const out = [];
      for (let i = 0; i < body.length; i += packet - status) out.push(...new Array(status).fill(0x01), ...body.slice(i, i + packet - status));
      queue.push(Uint8Array.from(out));
      if (waiting) { const w = waiting; waiting = null; w.resolve(); }
      return { status: "ok", bytesWritten: bytes.length };
    },
    async transferIn() {
      while (!queue.length) await new Promise((resolve, reject) => { waiting = { resolve, reject }; });
      const b = queue.shift();
      return { status: "ok", data: new DataView(b.buffer) };
    },
  };
  return dev;
}

const vendorIface = [{ interfaceNumber: 0, alternate: { interfaceClass: 0xff, endpoints: [
  { endpointNumber: 2, direction: "in", type: "bulk", packetSize: 32 },
  { endpointNumber: 2, direction: "out", type: "bulk", packetSize: 32 },
] } }];
const cdcIfaces = [
  { interfaceNumber: 0, alternate: { interfaceClass: 0x02, endpoints: [{ endpointNumber: 3, direction: "in", type: "interrupt", packetSize: 8 }] } },
  { interfaceNumber: 1, alternate: { interfaceClass: 0x0a, endpoints: [
    { endpointNumber: 4, direction: "in", type: "bulk", packetSize: 64 },
    { endpointNumber: 4, direction: "out", type: "bulk", packetSize: 64 },
  ] } },
];

test("CH340 baud rates match the chip's known register values", () => {
  assert.deepEqual(ch340Baud(115200), { reg1312: 0xcc83, reg0f2c: 0x08 });
  assert.deepEqual(ch340Baud(9600), { reg1312: 0xb282, reg0f2c: 0x0c });
  assert.deepEqual(ch340Baud(57600), { reg1312: 0x9883, reg0f2c: 0x10 });
  assert.deepEqual(ch340Baud(921600), { reg1312: 0xf387, reg0f2c: 0x00 });
});

test("FTDI baud divisors match the chip's known values", () => {
  assert.deepEqual(ftdiBaud(9600), { value: 0x4138, index: 0 });
  assert.deepEqual(ftdiBaud(115200), { value: 0x001a, index: 0 });
  assert.deepEqual(ftdiBaud(3000000), { value: 0, index: 0 });
});

test("CDC line coding is the baud rate (little-endian) then 8N1", () => {
  assert.deepEqual([...cdcLineCoding(115200)], [0x00, 0xc2, 0x01, 0x00, 0, 0, 8]);
});

test("each school board's chip gets the right driver, and the browser box offers them", () => {
  assert.equal(driverFor({ vendorId: 0x1a86, productId: 0x7523 }), "ch340");
  assert.equal(driverFor({ vendorId: 0x10c4, productId: 0xea60 }), "cp210x");
  assert.equal(driverFor({ vendorId: 0x0403, productId: 0x6001 }), "ftdi");
  assert.equal(driverFor({ vendorId: 0x2341, productId: 0x0043 }), "cdc");
  assert.equal(driverFor({ vendorId: 0x303a, productId: 0x1001 }), "cdc");
  assert.equal(driverFor({ vendorId: 0x1234, productId: 0x5678 }), "");
  assert.ok(USB_FILTERS.some((f) => f.vendorId === 0x1a86 && f.productId === 0x7523));
  assert.ok(USB_FILTERS.some((f) => f.vendorId === 0x303a && f.productId === undefined));
});

test("FTDI status bytes come off every packet", () => {
  const raw = Uint8Array.from([1, 0x60, 10, 11, 1, 0x60, 12]);
  assert.deepEqual([...stripStatus(raw, 4, 2)], [10, 11, 12]);
  assert.deepEqual([...stripStatus(Uint8Array.from([1, 0x60]), 64, 2)], []);
});

for (const [name, opts, check] of [
  ["CH340", { vendorId: 0x1a86, productId: 0x7523, interfaces: vendorIface }, (dev) => {
    assert.ok(dev.controls.some((c) => c.request === 0x9a && c.value === 0x1312 && c.index === 0xcc83), "sets 115200 baud");
    assert.ok(dev.controls.some((c) => c.request === 0x9a && c.value === 0x2518 && c.index === 0xc3), "8N1, send and receive on");
    assert.deepEqual(dev.controls.filter((c) => c.request === 0xa4).map((c) => c.value), [0xffff, 0xff9f, 0xffff], "DTR and RTS off, on, off");
  }],
  ["CP2102", { vendorId: 0x10c4, productId: 0xea60, interfaces: vendorIface }, (dev) => {
    assert.ok(dev.controls.some((c) => c.request === 0x1e && c.recipient === "interface" && c.data.join() === "0,194,1,0"));
    assert.ok(dev.controls.some((c) => c.request === 0x00 && c.value === 0), "the UART is turned off on close");
    assert.deepEqual(dev.controls.filter((c) => c.request === 0x07).map((c) => c.value), [0x0300, 0x0303, 0x0300]);
  }],
  ["FTDI", { vendorId: 0x0403, productId: 0x6001, interfaces: vendorIface, status: 2, packet: 32 }, (dev) => {
    assert.ok(dev.controls.some((c) => c.request === 3 && c.value === 0x001a));
    assert.ok(dev.controls.some((c) => c.request === 9 && c.value === 1), "a 1 ms latency timer");
  }],
  ["CDC (genuine Uno, ESP32-C3)", { vendorId: 0x2341, productId: 0x0043, interfaces: cdcIfaces }, (dev) => {
    assert.ok(dev.controls.some((c) => c.request === 0x20 && c.recipient === "interface" && c.index === 0));
    assert.deepEqual(dev.controls.filter((c) => c.request === 0x22).map((c) => c.value), [0, 3, 0]);
  }],
]) {
  test(`a ${name} board talks through the same Pump that uploads and the Serial Monitor use`, async () => {
    const dev = fakeDevice(opts);
    const port = new UsbSerialPort(dev);
    assert.deepEqual(port.getInfo(), { usbVendorId: opts.vendorId, usbProductId: opts.productId });
    const pump = new Pump(port);
    await pump.open(115200);
    await pump.setSignals(true, true);
    await pump.setSignals(false, false);
    const msg = Array.from({ length: 70 }, (_, i) => i); // longer than one packet
    await pump.write(msg);
    const back = await pump.read(70, 1000);
    assert.deepEqual([...back], msg.map((b) => b ^ 0xff));
    await pump.close();
    assert.equal(dev.opened, false);
    assert.equal(dev.claimed.size, 0);
    check(dev);
    // it opens again (esptool-js closes and reopens to change speed)
    const again = new Pump(port);
    await again.open(9600);
    await again.write([1, 2, 3]);
    assert.deepEqual([...(await again.read(3, 1000))], [0xfe, 0xfd, 0xfc]);
    await again.close();
  });
}

test("a fresh readable stream after the last one was cancelled, like Web Serial", async () => {
  const port = new UsbSerialPort(fakeDevice({ vendorId: 0x1a86, productId: 0x7523, interfaces: vendorIface }));
  await port.open({ baudRate: 115200 });
  const first = port.readable;
  assert.equal(port.readable, first);
  const r = first.getReader();
  await r.cancel();
  r.releaseLock();
  assert.notEqual(port.readable, first);
  const w = port.writable.getWriter();
  await w.close();
  w.releaseLock();
  assert.ok(port.writable && !port.writable.locked, "a new writable after closing the old one");
  await port.close();
  assert.equal(port.readable, null);
});

test("a board the computer's driver already owns gets a clue, not a crash", async () => {
  const dev = fakeDevice({ vendorId: 0x1a86, productId: 0x7523, interfaces: vendorIface });
  dev.claimInterface = async () => { throw Object.assign(new Error("Unable to claim interface."), { name: "NetworkError" }); };
  const port = new UsbSerialPort(dev);
  await assert.rejects(port.open({ baudRate: 115200 }), /already using the board through its own driver/);
  assert.equal(dev.opened, false);
});

test("the Can't see your board? help fits the student's computer", async () => {
  const { platformOf, boardHelpText } = await import("../../site/arduinopath/js/dialogs/boardhelp.js");
  assert.equal(platformOf({ userAgentData: { platform: "Windows" } }), "windows");
  assert.equal(platformOf({ platform: "MacIntel" }), "mac");
  assert.equal(platformOf({ userAgent: "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0)" }), "chromeos");
  assert.equal(platformOf({ userAgent: "Mozilla/5.0 (Linux; Android 14; SM-X200)", platform: "Linux armv8l" }), "android");
  const win = boardHelpText("windows").join(" ");
  assert.match(win, /data/);
  assert.match(win, /Windows usually adds it by itself/);
  assert.match(win, /Try the USB way/);
  assert.doesNotMatch(boardHelpText("windows", false).join(" "), /USB way/);
  assert.match(boardHelpText("android").join(" "), /OTG adapter/);
});
