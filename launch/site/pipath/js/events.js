// Turns a step's demo_events ("1.5 press 23", "2 tap 23", "1 tap 23 every 0.8 until 30",
// "1.5 distance 26 15", "2 stat load 90", "0.5 show ball") into timed commands for the
// simulated board. The same rules as PiPath's gpio.expand_events.

/** @returns {{at: number, cmd: string}[]} sorted by time (seconds) */
export function expandEvents(events) {
  const out = [];
  for (const ev of events ?? []) {
    const w = String(ev).trim().split(/\s+/);
    const t = parseFloat(w[0]);
    const action = w[1];
    const everyAt = w.indexOf("every");
    const args = everyAt >= 0 ? w.slice(2, everyAt) : w.slice(2);
    const pin = args[0];
    const every = everyAt >= 0 ? parseFloat(w[everyAt + 1]) : null;
    const untilAt = w.indexOf("until");
    const until = untilAt >= 0 ? parseFloat(w[untilAt + 1]) : t;
    const times = [];
    if (!every) times.push(t);
    else for (let i = 0; i <= Math.floor((until - t) / every); i++) times.push(t + i * every);
    for (const x of times) {
      if (action === "tap") {
        out.push({ at: x, cmd: `press ${pin}` }, { at: x + 0.2, cmd: `release ${pin}` });
      } else {
        out.push({ at: x, cmd: [action, ...args].join(" ") });
      }
    }
  }
  return out.sort((a, b) => a.at - b.at || (a.cmd < b.cmd ? -1 : a.cmd > b.cmd ? 1 : 0)); // ties by text, like Python sorts the pairs
}

/** "press 23" -> {t: "press", pin: 23}; "distance 26 15" -> {t: "distance", pin: 26, cm: 15}; and so on. Null if not understood. */
export function commandToEvent(cmd) {
  const w = String(cmd).trim().split(/\s+/);
  if ((w[0] === "press" || w[0] === "release") && /^\d+$/.test(w[1] ?? "")) return { t: w[0], pin: Number(w[1]) };
  if (w[0] === "distance" && /^\d+$/.test(w[1] ?? "") && Number.isFinite(Number(w[2]))) return { t: "distance", pin: Number(w[1]), cm: Number(w[2]) };
  if (w[0] === "stat" && ["temp", "load", "ram"].includes(w[1]) && Number.isFinite(Number(w[2]))) return { t: "stat", name: w[1], value: Number(w[2]) };
  if (w[0] === "show" && w[1]) return { t: "show", object: w[1] };
  return null;
}
