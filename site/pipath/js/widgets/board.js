// The on-screen board (the Simulator): LEDs glow, buzzers sound, buttons can be pressed, the
// distance sensor has a slider, servos turn. It draws parts from the lesson's wiring rows and
// from what the program makes, and reports clicks back as press / release / distance commands.
import { h } from "../dom.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  for (const c of kids) if (c) e.append(c);
  return e;
};

const COLOURS = { red: "#ff3b30", amber: "#ffb000", yellow: "#ffe600", orange: "#ff8a00", green: "#22d34a", blue: "#3b82ff", white: "#ffffff" };

const KIND = {
  LED: "led", PWMLED: "led", OutputDevice: "led", DigitalOutputDevice: "led", PWMOutputDevice: "led",
  Buzzer: "buzzer", TonalBuzzer: "buzzer", Button: "button", DigitalInputDevice: "switch", InputDevice: "switch",
  MotionSensor: "pir", RGBLED: "rgbled", DistanceSensor: "distance", Servo: "servo",
  // Grove (grove.py) on the Base Hat
  GroveUltrasonicRanger: "distance", RotaryAngle: "analog", Light: "analog", Moisture: "analog",
};
const ANALOG_LABEL = { RotaryAngle: "Grove knob", Light: "Grove light sensor", Moisture: "Grove moisture sensor" };

const key = (kind, pins) => `${kind}:${pins.join(",")}`;

/**
 * @param {{ onCommand: (ev: object) => void }} o   ev is {t: "press"|"release", pin} | {t: "distance", pin, cm} | {t: "stat", name, value} | {t: "show", object}
 */
export function createBoard({ onCommand = () => {}, camera = false, stats = false } = {}) {
  const body = h("div", { class: "board-body" });
  const live = h("span", { class: "title", text: "Simulator" });
  const sound = h("button", { class: "btn small", type: "button", text: "Sound: on" });
  const head = h("div", { class: "board-head" }, live, sound);
  const el = h("div", { class: "win board panel", "aria-label": "The board" }, head, body);

  /** @type {Map<string, {kind: string, pins: number[], label: string, colour: string, node: HTMLElement, set: (v: Record<string, number>) => void}>} */
  const parts = new Map();
  let values = {};
  let audio = null;
  let soundOn = true;
  const tones = new Map();

  function ensureAudio() {
    if (!audio && typeof AudioContext !== "undefined") {
      try { audio = new AudioContext(); } catch { audio = null; }
    }
    audio?.resume?.();
    return audio;
  }
  sound.addEventListener("click", () => {
    soundOn = !soundOn;
    sound.textContent = `Sound: ${soundOn ? "on" : "off"}`;
    if (!soundOn) stopTones();
    else ensureAudio();
  });
  function setTone(id, on) {
    if (!audio || !soundOn) return;
    if (on && !tones.has(id)) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.type = "square";
      o.frequency.value = 880;
      g.gain.value = 0.04;
      o.connect(g).connect(audio.destination);
      o.start();
      tones.set(id, o);
    } else if (!on && tones.has(id)) {
      tones.get(id).stop();
      tones.delete(id);
    }
  }
  function stopTones() { for (const id of [...tones.keys()]) setTone(id, false); }

  // ---------------------------------------------------------------- the parts
  function make(kind, pins, label, colour) {
    const k = key(kind, pins);
    if (parts.has(k)) return parts.get(k);
    const part = { kind, pins, label, colour, node: null, set: () => {} };
    const lbl = h("div", { class: "lbl", text: label });
    const val = h("div", { class: "val", text: pins.length === 1 ? `GPIO${pins[0]}` : `GPIO${pins.join(", ")}` });
    let art;
    if (kind === "led") {
      const c = COLOURS[colour] ?? COLOURS.red;
      const lamp = svg("circle", { cx: 28, cy: 24, r: 14, fill: c, stroke: "#222", "stroke-width": 2 });
      lamp.style.opacity = "0.25";
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-label": `${label}` },
        lamp, svg("rect", { x: 20, y: 36, width: 16, height: 5, fill: "#bbb" }), svg("line", { x1: 24, y1: 41, x2: 24, y2: 54, stroke: "#ccc", "stroke-width": 2 }), svg("line", { x1: 32, y1: 41, x2: 32, y2: 50, stroke: "#ccc", "stroke-width": 2 }));
      part.set = (v) => {
        const b = Math.max(0, Math.min(1, v[pins[0]] ?? 0));
        lamp.style.opacity = String(0.22 + 0.78 * b);
        lamp.style.filter = b > 0 ? `drop-shadow(0 0 ${3 + 9 * b}px ${c})` : "none";
        val.textContent = `GPIO${pins[0]} ${b > 0 ? (b < 1 ? Math.round(b * 100) + "%" : "ON") : "off"}`;
      };
    } else if (kind === "rgbled") {
      const lamp = svg("circle", { cx: 28, cy: 24, r: 14, fill: "#222", stroke: "#111", "stroke-width": 2 });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-label": label }, lamp, svg("rect", { x: 20, y: 36, width: 16, height: 5, fill: "#bbb" }));
      part.set = (v) => {
        const [r, g, b] = pins.map((p) => Math.max(0, Math.min(1, v[p] ?? 0)));
        lamp.setAttribute("fill", `rgb(${Math.round(30 + 225 * r)},${Math.round(30 + 225 * g)},${Math.round(30 + 225 * b)})`);
        val.textContent = `R${Math.round(r * 100)} G${Math.round(g * 100)} B${Math.round(b * 100)}`;
      };
    } else if (kind === "buzzer") {
      const w1 = svg("path", { d: "M38 16 q8 8 0 16", fill: "none", stroke: "#ffe27a", "stroke-width": 3 });
      const w2 = svg("path", { d: "M44 10 q14 14 0 28", fill: "none", stroke: "#ffe27a", "stroke-width": 3 });
      w1.style.opacity = w2.style.opacity = "0";
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-label": label }, svg("circle", { cx: 22, cy: 24, r: 14, fill: "#222", stroke: "#000", "stroke-width": 2 }), svg("circle", { cx: 22, cy: 24, r: 3, fill: "#666" }), w1, w2);
      part.set = (v) => {
        const on = (v[pins[0]] ?? 0) > 0;
        w1.style.opacity = w2.style.opacity = on ? "1" : "0";
        setTone(k, on);
        val.textContent = `GPIO${pins[0]} ${on ? "BUZZ" : "quiet"}`;
      };
    } else if (kind === "button" || kind === "switch") {
      const cap = svg("circle", { cx: 28, cy: 26, r: 14, fill: "#c33", stroke: "#600", "stroke-width": 3 });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-hidden": "true" }, svg("rect", { x: 8, y: 8, width: 40, height: 40, fill: "#ddd", stroke: "#555", "stroke-width": 2 }), cap);
      part.set = (v) => {
        const on = (v[pins[0]] ?? 0) > 0;
        cap.setAttribute("fill", on ? "#7a0000" : "#e33");
        cap.setAttribute("r", on ? "11" : "14");
        val.textContent = `GPIO${pins[0]} ${on ? "PRESSED" : "up"}`;
      };
    } else if (kind === "pir") {
      const dome = svg("circle", { cx: 28, cy: 26, r: 16, fill: "#eee", stroke: "#999", "stroke-width": 2 });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-hidden": "true" }, dome, svg("circle", { cx: 28, cy: 26, r: 7, fill: "#ccc" }));
      part.set = (v) => {
        const on = (v[pins[0]] ?? 0) > 0;
        dome.setAttribute("fill", on ? "#ffd54a" : "#eee");
        val.textContent = `GPIO${pins[0]} ${on ? "MOTION" : "still"}`;
      };
    } else if (kind === "servo") {
      const horn = svg("line", { x1: 28, y1: 30, x2: 28, y2: 6, stroke: "#fff", "stroke-width": 5, "stroke-linecap": "round" });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-label": label }, svg("rect", { x: 10, y: 28, width: 36, height: 22, fill: "#2b6fd1", stroke: "#123", "stroke-width": 2 }), horn, svg("circle", { cx: 28, cy: 30, r: 4, fill: "#ccc" }));
      part.set = (v) => {
        const x = Math.max(-1, Math.min(1, v[pins[0]] ?? 0));
        horn.setAttribute("transform", `rotate(${x * 90} 28 30)`);
        val.textContent = `GPIO${pins[0]} ${Math.round(90 + x * 90)}°`;
      };
    } else if (kind === "distance") {
      const echo = pins[0];
      const slider = h("input", { type: "range", min: 2, max: 150, value: 100, "aria-label": `${label}: how far away something is, in centimetres`,
        oninput: () => { reading.textContent = `${slider.value} cm`; onCommand({ t: "distance", pin: echo, cm: Number(slider.value) }); } });
      const reading = h("div", { class: "val", text: "100 cm" });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-hidden": "true" }, svg("rect", { x: 6, y: 16, width: 44, height: 24, fill: "#2a6fd1", stroke: "#123", "stroke-width": 2 }), svg("circle", { cx: 19, cy: 28, r: 7, fill: "#ddd", stroke: "#555", "stroke-width": 2 }), svg("circle", { cx: 37, cy: 28, r: 7, fill: "#ddd", stroke: "#555", "stroke-width": 2 }));
      part.set = () => {};
      part.node = h("div", { class: "part" }, art, lbl, slider, reading, val);
      part.slider = slider;
      part.reading = reading;
    } else if (kind === "analog") {
      // a Grove sensor on one of the Base Hat's analog ports: drag to change what it reads (0 to 999)
      const ch = pins[0];
      const slider = h("input", { type: "range", min: 0, max: 999, value: 500, "aria-label": `${label}: its reading`,
        oninput: () => { reading.textContent = slider.value; onCommand({ t: "analog", ch, value: Number(slider.value) }); } });
      const reading = h("div", { class: "val", text: "500" });
      art = svg("svg", { viewBox: "0 0 56 56", role: "img", "aria-hidden": "true" }, svg("rect", { x: 8, y: 8, width: 40, height: 40, rx: 4, fill: "#1f5fa8", stroke: "#123", "stroke-width": 2 }), svg("circle", { cx: 28, cy: 26, r: 10, fill: "#ddd", stroke: "#555", "stroke-width": 2 }), svg("rect", { x: 20, y: 40, width: 16, height: 6, fill: "#f3f3f0" }));
      part.set = () => {};
      part.node = h("div", { class: "part" }, art, lbl, slider, reading, h("div", { class: "val", text: `port A${ch}` }));
      part.slider = slider;
      part.reading = reading;
      part.analog = true;
    }
    if (!part.node) {
      const interactive = kind === "button" || kind === "switch" || kind === "pir";
      const node = h("div", { class: ["part", interactive && "click"] }, art, lbl, val);
      part.node = node;
      if (interactive) {
        const pin = pins[0];
        let held = false;
        const down = () => { if (kind === "pir") { if (!held) { held = true; onCommand({ t: "press", pin }); setTimeout(() => { held = false; onCommand({ t: "release", pin }); }, 3000); } } else { held = true; onCommand({ t: "press", pin }); ensureAudio(); } };
        const up = () => { if (kind !== "pir" && held) { held = false; onCommand({ t: "release", pin }); } };
        const btn = h("button", { type: "button", class: "btn small", text: kind === "pir" ? "Wave" : "Press & hold", "aria-label": `${kind === "pir" ? "Wave at" : "Press and hold"} ${label}`,
          onpointerdown: (e) => { e.preventDefault(); btn.setPointerCapture?.(e.pointerId); down(); }, onpointerup: up, onpointercancel: up, onlostpointercapture: up,
          onkeydown: (e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); down(); } }, onkeyup: (e) => { if (e.key === " " || e.key === "Enter") up(); } });
        art.addEventListener("pointerdown", (e) => { e.preventDefault(); down(); });
        art.addEventListener("pointerup", up);
        art.addEventListener("pointerleave", up);
        node.append(btn);
      }
    }
    part.set(values);
    parts.set(k, part);
    body.append(part.node);
    return part;
  }

  // the camera and the Pi's numbers, when a lesson uses them
  let photo = null;
  if (camera) {
    const img = h("img", { alt: "The last photo", width: 120, height: 90 });
    const sel = h("select", { class: "input", "aria-label": "What the simulated camera sees", onchange: () => onCommand({ t: "show", object: sel.value }) },
      ["face", "ball", "box", "nothing"].map((o) => h("option", { value: o, text: o === "nothing" ? "Empty" : o[0].toUpperCase() + o.slice(1) })));
    photo = { img };
    body.append(h("div", { class: "part", style: { width: "150px" } }, h("div", { class: "lbl", text: "Camera (Simulator)" }), img, sel));
  }
  if (stats) {
    const row = (name, label, min, max, val) => {
      const out = h("span", { class: "val", text: String(val) });
      return h("label", { class: "lbl" }, `${label} `, h("input", { type: "range", min, max, value: val, "aria-label": label, oninput: (e) => { out.textContent = e.target.value; onCommand({ t: "stat", name, value: Number(e.target.value) }); } }), out);
    };
    body.append(h("div", { class: "part", style: { width: "170px" } }, h("div", { class: "lbl", text: "Pretend Pi numbers" }), row("temp", "Temp °C", 30, 85, 48), row("load", "CPU %", 0, 100, 12), row("ram", "RAM %", 0, 100, 31)));
  }

  return {
    el,
    ensureAudio,
    /** Parts from the lesson's [[wiring]] rows (before anything runs). */
    setParts(rows = []) {
      for (const p of parts.values()) p.node.remove();
      parts.clear();
      stopTones();
      for (const r of rows) {
        const pins = r.pins ?? (r.pin !== undefined ? [r.pin] : []);
        if (r.kind && pins.length) make(KIND[r.kind] ?? r.kind, pins.map(Number), r.part ?? r.kind, r.colour ?? "red");
      }
      this.static = new Set(parts.keys());
    },
    /** A message from the running program: devices, pins, photo. */
    apply(msg) {
      if (msg.t === "devices") {
        for (const d of msg.devices) {
          const kind = KIND[d.kind];
          if (!kind) continue;
          const pins = kind === "distance" || kind === "rgbled" || kind === "servo" ? d.pins : [d.pins[0]];
          if (kind === "analog") { if (!parts.has(key("analog", pins))) make("analog", pins, ANALOG_LABEL[d.kind] ?? "Grove sensor", ""); continue; }
          if (kind === "distance" && ![...parts.values()].some((p) => p.kind === "distance" && p.pins[0] === pins[0])) make("distance", pins, `Distance sensor`, "");
          else if (kind !== "distance" && !parts.has(key(kind, pins))) {
            // a part the program made on a pin that isn't in the wiring list: add it, and remove the plain LED it duplicates
            make(kind, pins, `${d.kind} GPIO${pins.join(", ")}`, "red");
          }
        }
      } else if (msg.t === "pins") {
        values = Object.fromEntries(Object.entries(msg.pins).map(([k, v]) => [Number(k), v]));
        for (const p of parts.values()) p.set(values);
      } else if (msg.t === "photo" && msg.bytes && photo) {
        photo.img.src = URL.createObjectURL(new Blob([msg.bytes], { type: /\.png$/i.test(msg.name ?? "") ? "image/png" : "image/jpeg" }));
      }
    },
    /** The program ended: everything switches off, like real hardware. */
    switchOff() {
      values = {};
      for (const p of parts.values()) p.set({});
      stopTones();
    },
    /** A fresh run: parts the last program added go away; the wiring list stays. */
    resetForRun() {
      for (const [k, p] of [...parts]) if (!this.static?.has(k)) { p.node.remove(); parts.delete(k); }
      for (const p of parts.values()) {
        if (p.slider && p.analog) { p.slider.value = 500; p.reading.textContent = "500"; } else if (p.slider) { p.slider.value = 100; p.reading.textContent = "100 cm"; }
      }
      values = {};
      for (const p of parts.values()) p.set({});
    },
    get partCount() { return parts.size; },
  };
}
