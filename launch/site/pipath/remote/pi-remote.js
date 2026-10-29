// Talks to a Raspberry Pi through the Circuit Pathways site. The Pi runs
// circuitpathways_pi.py, which shows a pairing code; connect(code) pairs this
// page with it. Nothing here is stored. Events: "status", "hello", "state", "problem".
//
// A later PiPath "Real Pi" mode can use this same class to run a student's
// gpiozero program's pin changes on the real pins.

import { getAccess } from "/shared/access.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  _setState(state, extra = {}) {
    this.state = state;
    this._emit("status", { state, ...extra });
  }

  /** Pairs with the Pi showing this code. Resolves when connected; rejects with a friendly message. */
  async connect(code) {
    this.disconnect();
    const access = getAccess();
    if (!access) throw Object.assign(new Error("Join a class with your class code first."), { code: "no_class" });
    this.code = code.trim();
    this.abort = new AbortController();
    this._setState("connecting");
    const res = await fetch(`/api/pi/events?code=${encodeURIComponent(this.code)}`, {
      headers: { "X-Access": access.value }, signal: this.abort.signal, credentials: "omit",
    }).catch(() => { throw new Error("Circuit Pathways can't be reached. Check your internet connection."); });
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
        this.connect(this.code).catch((e) => this._setState("closed", { reason: e.message }));
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
      case "pi-offline": this._setState("pi-offline", { name: this.name }); break;
      case "hello": this.hello = ev.data; this._emit("hello", ev.data); break;
      case "state": this.pins = ev.data.pins ?? {}; this._emit("state", this.pins); break;
      case "pong": this._emit("pong", ev.data); break;
      case "error": this._emit("problem", ev.data); break;
      case "closed":
        this.abort?.abort();
        this._setState("closed", { reason: ev.data.reason });
        break;
    }
  }

  disconnect() {
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
export const HEADER = {
  1: "3V3", 2: "5V", 3: 2, 4: "5V", 5: 3, 6: "GND", 7: 4, 8: 14, 9: "GND", 10: 15,
  11: 17, 12: 18, 13: 27, 14: "GND", 15: 22, 16: 23, 17: "3V3", 18: 24, 19: 10, 20: "GND",
  21: 9, 22: 25, 23: 11, 24: 8, 25: "GND", 26: 7, 27: "ID", 28: "ID", 29: 5, 30: "GND",
  31: 6, 32: 12, 33: 13, 34: "GND", 35: 19, 36: 16, 37: 26, 38: 20, 39: "GND", 40: 21,
};

/** Pins a student may control (the Pi app refuses the rest). */
export const USABLE = (n) => typeof n === "number" && n >= 2 && n <= 27;
