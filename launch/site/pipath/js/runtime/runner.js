// The page's side of the Python worker: start it, run a program, send it button presses and typed
// answers, stop it, and ask PiPath's Coach (which also lives in Python) about code and errors.

import { Ring, CTL } from "./ipc.js";
import { commandToEvent, expandEvents } from "../events.js";

const OUTPUT_WINDOW_MS = 20_000;

export class PyRunner extends EventTarget {
  /** @param {{base?: string, busySeconds?: number, maxLines?: number, maxChars?: number}} [opts] */
  constructor({ base = "/pipath/", busySeconds = 8, maxLines = 3000, maxChars = 300_000 } = {}) {
    super();
    this.base = base;
    this.busyMs = busySeconds * 1000;
    this.maxLines = maxLines;
    this.maxChars = maxChars;
    this.pending = new Map();
    this.nextId = 1;
    this.running = false;
    this.ready = null;
  }

  static get supported() {
    return typeof Worker !== "undefined" && typeof SharedArrayBuffer !== "undefined" && globalThis.crossOriginIsolated !== false;
  }

  /** Starts the worker and loads Python. Resolves with the Python version when ready. */
  start(errorsJson) {
    this.ready ??= new Promise((resolve, reject) => {
      if (!PyRunner.supported) {
        reject(new Error("Your browser can't run Python here. Use a recent Chrome or Edge, and open Circuit Pathways from its own address."));
        return;
      }
      this.sabs = { ctl: new SharedArrayBuffer(16), events: Ring.create(64 * 1024), stdin: Ring.create(16 * 1024) };
      this.ctl = new Int32Array(this.sabs.ctl);
      this.events = new Ring(this.sabs.events);
      this.stdin = new Ring(this.sabs.stdin);
      this.interrupt = new SharedArrayBuffer(1);
      this.worker = new Worker(`${this.base}js/runtime/worker.js`, { type: "module" });
      this.worker.onerror = (e) => reject(new Error(e.message || "Python couldn't start."));
      this.worker.onmessage = (e) => this._message(e.data, resolve, reject);
      this.worker.postMessage({ type: "init", sabs: this.sabs, interrupt: this.interrupt, base: this.base, errorsJson });
    });
    return this.ready;
  }

  _message(m, resolveReady, rejectReady) {
    switch (m.type) {
      case "ready": resolveReady(m.version); break;
      case "out": this._output(m.stream, m.text); break;
      case "board":
        if (m.msg.t === "devices") this.devicesMade = m.msg.devices.length > 0;
        this.dispatchEvent(new CustomEvent("board", { detail: { ...m.msg, bytes: m.bytes } })); break;
      case "done":
      case "result":
      case "file": this.pending.get(m.id)?.resolve(m); this.pending.delete(m.id); break;
      case "error":
        if (m.id && this.pending.has(m.id)) { this.pending.get(m.id).reject(new Error(m.message)); this.pending.delete(m.id); }
        else rejectReady(new Error(m.message));
        break;
    }
  }

  _output(stream, text) {
    if (stream === "out") {
      this.out += text;
      this.lines += (text.match(/\n/g) ?? []).length;
      this.chars += text.length;
      if (this.running && !this.flood && (this.lines > this.maxLines || this.chars > this.maxChars)) {
        this.flood = true;
        this.stopWith("runaway_output");
      }
    } else {
      this.err += text;
    }
    this.dispatchEvent(new CustomEvent("output", { detail: { stream, text } }));
  }

  _ask(msg, transfer) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ ...msg, id }, transfer ?? []);
    });
  }

  wake() {
    Atomics.add(this.ctl, CTL.WAKE, 1);
    Atomics.notify(this.ctl, CTL.WAKE);
  }

  /**
   * Runs a program. Resolves when it has ended.
   * @param {{code: string, filename: string, env?: object, files?: object, events?: string[], seconds?: number, seed?: number}} job
   * @returns {Promise<{rc: number, stopped: boolean, reason: string|null, stdout: string, stderr: string, cwd: string, started: number}>}
   */
  async run(job) {
    await this.ready;
    this.out = this.err = "";
    this.lines = this.chars = 0;
    this.flood = false;
    this.devicesMade = false;
    this.reason = null;
    this.runId = (this.runId ?? 0) + 1;
    this.running = true;
    Atomics.store(this.ctl, CTL.STOP, 0);
    Atomics.store(this.ctl, CTL.EOF, 0);
    this.stdin.clear();
    new Uint8Array(this.interrupt)[0] = 0;
    const timed = expandEvents(job.events).map((e) => ({ at: e.at, ev: commandToEvent(e.cmd) })).filter((e) => e.ev);
    let lastActivity = Atomics.load(this.ctl, CTL.ACTIVITY);
    let lastChange = performance.now();
    const watchdog = setInterval(() => {
      const a = Atomics.load(this.ctl, CTL.ACTIVITY);
      const now = performance.now();
      if (a !== lastActivity) { lastActivity = a; lastChange = now; }
      else if (now - lastChange > this.busyMs && !this.reason) this.stopWith(this.devicesMade ? "runaway_busy_gpio" : "runaway_busy", true);
    }, 500);
    try {
      const done = await this._ask({ type: "run", code: job.code, filename: job.filename, env: job.env, files: job.files, events: timed, seconds: job.seconds, seed: job.seed });
      return { rc: done.rc, stopped: done.stopped || this.reason === "stop", reason: this.reason, stdout: this.out, stderr: this.err, cwd: done.cwd, started: done.started };
    } finally {
      clearInterval(watchdog);
      this.running = false;
    }
  }

  /**
   * Ends the running program. A program that waits or sleeps notices the flag straight away; one
   * that never waits (a loop with nothing in it) needs Python's interrupt, so that follows
   * if the program is still going a moment later (or at once if it isn't doing anything at all).
   */
  stopWith(reason, now = false) {
    this.reason = reason;
    Atomics.store(this.ctl, CTL.STOP, 1);
    this.wake();
    const runId = this.runId; // a late interrupt must never land in the next program
    const interrupt = () => { if (this.running && this.runId === runId) new Uint8Array(this.interrupt)[0] = 2; };
    if (now) interrupt();
    else setTimeout(interrupt, 400);
  }

  /** The student pressed Stop. */
  stop() {
    if (this.running) this.stopWith("stop");
  }

  /** A press, release, distance, stat or show command for the running program. */
  sendEvent(ev) {
    if (!this.running) return;
    this.events.push(JSON.stringify(ev));
    this.wake();
  }

  /** The student typed an answer to input(). */
  sendLine(text) {
    this.stdin.push(String(text));
    this.wake();
  }

  /** Calls one of the Coach's Python functions (JSON in, JSON out). Only works between runs. */
  async call(fn, ...args) {
    await this.ready;
    const r = await this._ask({ type: "call", fn, args });
    return r.value === undefined || r.value === null ? null : JSON.parse(r.value);
  }

  /** Like call(), for functions that return nothing. */
  async do(fn, ...args) {
    await this.ready;
    await this._ask({ type: "call", fn, args });
  }

  /** Puts files (the ones a program running on the Pi made) into Python's file system, so the lesson's file checks can look at them. */
  async putFiles(dir, files) {
    await this.ready;
    await this._ask({ type: "putfiles", dir, files });
    return dir;
  }

  async readFile(path) {
    const r = await this._ask({ type: "readfile", path });
    return r.bytes;
  }
}
