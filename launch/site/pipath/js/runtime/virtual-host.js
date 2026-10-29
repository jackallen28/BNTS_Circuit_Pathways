// A pretend page for the Python simulator, with a clock that only moves when the program
// sleeps, so a 30-second demo runs in a moment. Used by the tests (and anything that wants
// to run a program faster than real time).

import { expandEvents, commandToEvent } from "../events.js";

export class VirtualHost {
  constructor() {
    this.reset();
  }

  /** @param {{events?: string[], seconds?: number, stdin?: string}} opts */
  reset({ events = [], seconds = 0, stdin = "" } = {}) {
    this.t = 0; // ms
    this.queue = expandEvents(events).map((e) => ({ at: e.at * 1000, ev: commandToEvent(e.cmd) })).filter((e) => e.ev);
    this.limit = seconds ? seconds * 1000 : Infinity;
    this.lines = stdin === "" ? [] : stdin.replace(/\n$/, "").split("\n");
    this.stopped = false;
    this.messages = [];
    this.sleeps = 0;
  }

  // ---- what the Python side calls (the _cp_host module)
  now_ms() { return this.t; }

  sleep(ms) {
    this.sleeps++;
    this.t += Math.max(0, ms);
    if (this.t >= this.limit) this.stopped = true; // the demo's time is up: Stop
  }

  should_stop() { return this.stopped; }

  poll() {
    const due = [];
    while (this.queue.length && this.queue[0].at <= this.t) due.push(this.queue.shift().ev);
    return JSON.stringify(due);
  }

  emit(json) { this.messages.push(JSON.parse(json)); }
  input_state() { return this.lines.length ? 1 : 2; }
  read_line() { return this.lines.shift(); }
}
