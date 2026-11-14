// Talks to a Raspberry Pi through the Circuit Pathways site. The Pi runs
// circuitpathways_pi.py (started at boot by its installer); connect(id) links this
// page to the Pi with that ID. Nothing here is stored. Events: "status", "hello", "state", "problem".
//
// PiPath's "Run on my Pi" uses run() / stdin() / stop(): the student's program is sent to the Pi,
// which runs it for real and sends back what it prints. Nothing is stored on the way.

import { getAccess } from "/shared/access.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// The Circuit Pathways server relays over a stream of events (a server could offer WebSockets: /api/info says which).
let relayKind;
async function relay() {
  relayKind ??= fetch("/api/info", { credentials: "omit" }).then((r) => r.json()).then((i) => (i.relay === "ws" ? "ws" : "sse")).catch(() => "sse");
  return relayKind;
}

export class PiRemote extends EventTarget {
  constructor() {
    super();
    this.code = "";
    this.state = "idle"; // idle | connecting | connected | pi-offline | closed
    this.pins = {};
    this.hello = null;
    this.name = "";
    this.abort = null;
    this._pending = new Map(); // pwm commands waiting for their turn
    this._last = new Map();
    this.job = null; // the program running on the Pi: { rid, out, err, resolve }
    this._rid = 0;
  }

  /** Does this Pi's app allow students' programs? (It says in its hello.) */
  get canRun() {
    return this.hello?.can_run === true;
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  _setState(state, extra = {}) {
    this.state = state;
    this._emit("status", { state, ...extra });
  }

  /** Links to the Pi with this ID (the one on its label). Resolves when connected; rejects with a friendly message. */
  async connect(code, { resume = false } = {}) {
    if (resume) this.abort?.abort(); // the same link coming back after a blip: a running program carries on
    else this.disconnect();
    const access = getAccess();
    if (!access) throw Object.assign(new Error("Join a class with your class code first."), { code: "no_class" });
    this.code = code.trim();
    this.abort = new AbortController();
    this._setState("connecting");
    if ((await relay()) === "ws") return this._connectWS(access.value);
    const res = await fetch(`/api/pi/events?code=${encodeURIComponent(this.code)}`, {
      headers: { "X-Access": access.value }, signal: this.abort.signal, credentials: "omit",
    }).catch(() => { throw new Error("The Circuit Pathways server can't be reached. Check this computer is on the school network."); });
    if (!res.ok) {
      this._setState("idle");
      const body = await res.json().catch(() => ({}));
      throw Object.assign(new Error(body.message || "That didn't work. Try again."), { code: body.error });
    }
    this._read(res.body);
    return new Promise((resolve) => {
      const done = () => { this.removeEventListener("status", on); resolve(); };
      const on = (e) => { if (e.detail.state === "connected" || e.detail.state === "pi-offline") done(); };
      this.addEventListener("status", on);
    });
  }

  _connectWS(token) {
    const signal = this.abort.signal;
    const url = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/pi/ws?code=${encodeURIComponent(this.code)}`;
    const ws = new WebSocket(url, ["cp-access", token]);
    this.ws = ws;
    signal.addEventListener("abort", () => ws.close());
    let opened = false;
    const ready = new Promise((resolve, reject) => {
      const on = (e) => {
        if (e.detail.state === "connected" || e.detail.state === "pi-offline") { this.removeEventListener("status", on); resolve(); }
      };
      this.addEventListener("status", on);
      ws.onopen = () => { opened = true; };
      ws.onerror = () => {
        if (!opened) {
          this.removeEventListener("status", on);
          this._setState("idle");
          reject(Object.assign(new Error("Couldn't link to that Pi. Check you've joined your class on the home page, then try again."), { code: "no_link" }));
        }
      };
    });
    ws.onmessage = (e) => {
      try { this._onEvent(JSON.parse(e.data)); } catch { /* not for us */ }
    };
    ws.onclose = async () => {
      if (this.ws !== ws || signal.aborted || this.state === "closed" || !opened) return;
      this._setState("connecting", { reconnecting: true });
      if (this.job) this._emit("output", { stream: "err", text: "[The connection blinked. Some output may be missing.]\n" });
      await sleep(1500);
      if (!signal.aborted && this.state === "connecting") this.connect(this.code, { resume: true }).catch((err) => this._setState("closed", { reason: err.message }));
    };
    return ready;
  }

  async _read(body) {
    const reader = body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + 2);
          const line = block.split("\n").find((l) => l.startsWith("data: "));
          if (line) this._onEvent(JSON.parse(line.slice(6)));
        }
      }
    } catch {
      /* the stream ended: handled below */
    }
    if (this.abort && !this.abort.signal.aborted && this.state !== "closed") {
      this._setState("connecting", { reconnecting: true });
      await sleep(1500);
      if (this.abort && !this.abort.signal.aborted && this.state === "connecting") {
        if (this.job) this._emit("output", { stream: "err", text: "[The connection blinked. Some output may be missing.]\n" });
        this.connect(this.code, { resume: true }).catch((e) => this._setState("closed", { reason: e.message }));
      }
    }
  }

  _onEvent(ev) {
    switch (ev.type) {
      case "connected":
        this.name = ev.data.name;
        this._setState(ev.data.pi_online ? "connected" : "pi-offline", { name: this.name });
        break;
      case "pi-online": this._setState("connected", { name: this.name }); break;
      case "pi-offline":
        this._setState("pi-offline", { name: this.name });
        this._end({ rc: 1, stopped: true, reason: "offline", files: {} }, "[The Pi went offline, so your program stopped]");
        break;
      case "hello": this.hello = ev.data; this._emit("hello", ev.data); break;
      case "state": this.pins = ev.data.pins ?? {}; this._emit("state", this.pins); break;
      case "pong": this._emit("pong", ev.data); break;
      case "error":
        if (this.job && ev.data.rid === this.job.rid) this._end({ rc: 1, stopped: false, reason: "refused", files: {} }, ev.data.message);
        else this._emit("problem", ev.data);
        break;
      case "run": if (this.job?.rid === ev.data.rid) this._emit("run", ev.data); break;
      case "out":
        if (this.job && ev.data.rid === this.job.rid) {
          this.job[ev.data.stream === "err" ? "err" : "out"] += ev.data.text;
          this._emit("output", { stream: ev.data.stream, text: ev.data.text });
        }
        break;
      case "exit": if (this.job && ev.data.rid === this.job.rid) this._end(ev.data); break;
      case "closed":
        this.abort?.abort();
        this._setState("closed", { reason: ev.data.reason });
        this._end({ rc: 1, stopped: true, reason: "closed", files: {} }, `[${ev.data.reason || "The link to the Pi ended"}]`);
        break;
    }
  }

  /** The program on the Pi has ended (or can't be known any more): finish the run() promise. */
  _end(exit, note) {
    const job = this.job;
    if (!job) return;
    this.job = null;
    clearInterval(job.beat);
    if (note) {
      job.err += `${note}\n`;
      this._emit("output", { stream: "err", text: `${note}\n` });
    }
    job.resolve({ ...exit, stdout: job.out, stderr: job.err });
  }

  /**
   * Runs a program on the Pi. Resolves when it has ended (however it ended) with
   * { rc, stopped, reason, stdout, stderr, files }. Output arrives as "output" events as it is printed.
   * @param {{code: string, name: string, files?: Record<string, Uint8Array>, support?: string[], cameraObject?: string}} job
   */
  async run({ code, name, files = {}, support = [], cameraObject = "" }) {
    if (this.job) throw new Error("A program is already running on your Pi.");
    const rid = ++this._rid;
    const b64 = {};
    for (const [fname, bytes] of Object.entries(files)) b64[fname] = bytesToBase64(bytes);
    const cmd = { op: "run", rid, name, code };
    if (Object.keys(b64).length) cmd.files = b64;
    if (support.length) cmd.support = support;
    if (cameraObject) cmd.camera_object = cameraObject;
    const done = new Promise((resolve) => {
      this.job = { rid, out: "", err: "", resolve, beat: 0 };
    });
    // the Pi stops a program whose page goes quiet, so a heartbeat while it runs
    this.job.beat = setInterval(() => this.ping().catch(() => {}), 5000);
    try {
      await this.command(cmd);
    } catch (e) {
      this._end({ rc: 1, stopped: false, reason: "refused", files: {} }, e.message);
    }
    return done;
  }

  /** A line for the program's input(). */
  stdin(text) {
    if (!this.job) return Promise.resolve();
    return this.command({ op: "stdin", rid: this.job.rid, text: String(text).slice(0, 1000) }).catch((e) => this._emit("problem", { message: e.message }));
  }

  /** The student pressed Stop. */
  stop() {
    if (!this.job) return Promise.resolve();
    return this.command({ op: "stop", rid: this.job.rid }).catch((e) => this._emit("problem", { message: e.message }));
  }

  get running() {
    return this.job !== null;
  }

  disconnect() {
    this._end({ rc: 1, stopped: true, reason: "closed", files: {} });
    this.abort?.abort();
    this.abort = null;
    if (this.state !== "idle") this._setState("idle");
  }

  async command(cmd) {
    const access = getAccess();
    const res = await fetch("/api/pi/command", {
      method: "POST", credentials: "omit",
      headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", "X-Access": access?.value ?? "" },
      body: JSON.stringify({ code: this.code, cmd }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.message || "The Pi didn't get that.");
    }
  }

  setMode(pin, mode) { return this.command({ op: "mode", pin, mode }); }
  write(pin, value) { return this.command({ op: "write", pin, value }); }
  release(pin) { return this.command({ op: "release", pin }); }
  allOff() { return this.command({ op: "all_off" }); }
  ping(id = Date.now() % 1e6) { return this.command({ op: "ping", id }); }

  /** Brightness for a PWM pin. A slider sends lots of values: at most ~10 a second go out, and the last one always does. */
  pwm(pin, duty) {
    const send = () => { this._last.set(pin, performance.now()); this._pending.delete(pin); return this.command({ op: "pwm", pin, duty }); };
    const wait = 100 - (performance.now() - (this._last.get(pin) ?? 0));
    if (wait <= 0) return send();
    clearTimeout(this._pending.get(pin));
    this._pending.set(pin, setTimeout(() => send().catch((e) => this._emit("problem", { message: e.message })), wait));
    return Promise.resolve();
  }
}

/** The 40-pin header: physical pin number -> what it is (a GPIO (BCM) number, or a power / ground pin). */
function bytesToBase64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export const HEADER = {
  1: "3V3", 2: "5V", 3: 2, 4: "5V", 5: 3, 6: "GND", 7: 4, 8: 14, 9: "GND", 10: 15,
  11: 17, 12: 18, 13: 27, 14: "GND", 15: 22, 16: 23, 17: "3V3", 18: 24, 19: 10, 20: "GND",
  21: 9, 22: 25, 23: 11, 24: 8, 25: "GND", 26: 7, 27: "ID", 28: "ID", 29: 5, 30: "GND",
  31: 6, 32: 12, 33: 13, 34: "GND", 35: 19, 36: 16, 37: 26, 38: 20, 39: "GND", 40: 21,
};

/** Pins a student may control (the Pi app refuses the rest). */
export const USABLE = (n) => typeof n === "number" && n >= 2 && n <= 27;
