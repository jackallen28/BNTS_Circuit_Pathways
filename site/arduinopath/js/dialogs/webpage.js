// The Web Page Designer (ESP boards). Students drag elements (headings, text, buttons, switches, sliders, colour
// pickers, readings, status lights) onto a phone, wire each one to their project's parts, and press "Try it" to use the
// page on a pretend board (LEDs light, the buzzer beeps, knobs move readings) before putting the code on the real one.
// webpage.js makes the code and holds the model; this file is the screen.
//
// Drag and drop uses pointer events, so it works with a mouse, a touchscreen or a pen. Everything can also be done
// with the keyboard: a palette tile adds its element (Enter), an element on the phone is picked with Enter, moved with
// Alt+Up / Alt+Down and removed with Delete. Undo / Redo cover every change.
import { h, icon } from "../dom.js";
import { openDialog, messageBox } from "../widgets/window.js";
import {
  THEMES, ELEMENTS, BUTTON_ACTIONS, READING_SOURCES, STATUS_SOURCES, TEMPLATES,
  generateSketch, namedItems, starterDesign, connections, connectionText, pinClashes,
  defaultItem, moveItem, insertItem, dropIndex, tryIt, partName, ledColour,
} from "../webpage.js";

const GROUPS = [["words", "Words"], ["control", "Controls: they work your project"], ["show", "Show: they tell you what's happening"]];

/**
 * @param {{ board: object, design?: object, currentCode: string, onSave: (design) => void, onUse: (code: string, design) => void }} o
 */
export function openWebPageDesigner({ board, design: saved, currentCode = "", onSave = () => {}, onUse = () => {} }) {
  let design = tidy(structuredClone(saved ?? starterDesign()));
  let selected = -1; // the element being changed, or -1 for the page's own settings
  let mode = "design"; // "design" | "try"
  let bench = tryIt(design, board);
  const past = [];
  const future = [];
  let lastEdit = { key: "", at: 0 };

  const roles = Object.keys(board.pin_plan ?? {});
  const outputRoles = roles.filter((r) => /^(LED_|RELAY)/.test(r));
  const pinText = (r) => `${r} (pin ${board.pin_plan?.[r] ?? "?"})`;

  // ---------------------------------------------------------------- changing the design (with Undo)
  /** Every change goes through here: a snapshot for Undo, the change, then a redraw. Typing in one box is one Undo step. */
  function change(fn, { key = "", structure = false, bench: rebench = structure } = {}) {
    const now = Date.now();
    if (!key || key !== lastEdit.key || now - lastEdit.at > 1500) {
      past.push(JSON.stringify(design));
      if (past.length > 100) past.shift();
      future.length = 0;
    }
    lastEdit = { key, at: now };
    fn();
    if (rebench) rebuildBench();
    redraw({ inspector: structure });
    onSave(design);
  }
  function restore(from, to) {
    if (!from.length) return;
    to.push(JSON.stringify(design));
    design = tidy(JSON.parse(from.pop()));
    selected = Math.min(selected, design.items.length - 1);
    lastEdit = { key: "", at: 0 };
    rebuildBench();
    redraw({ inspector: true });
    onSave(design);
  }
  const undo = () => restore(past, future);
  const redo = () => restore(future, past);

  /** A new pretend board for a changed design, keeping what the student had set on the old one. */
  function rebuildBench() {
    const old = bench.state;
    bench = tryIt(design, board);
    for (const k of Object.keys(bench.state.inputs)) if (k in old.inputs) bench.state.inputs[k] = old.inputs[k];
    for (const k of Object.keys(bench.state.outputs)) if (k in old.outputs) bench.state.outputs[k] = old.outputs[k];
    bench.state.seconds = old.seconds;
  }

  function addAt(kind, index) {
    const item = defaultItem(kind, board);
    const at = index ?? (selected >= 0 ? selected + 1 : design.items.length);
    change(() => { design.items = insertItem(design.items, at, item); selected = at; }, { structure: true });
    announce(`Added a ${ELEMENTS[kind].name.toLowerCase()}.`);
  }
  function move(from, to) {
    if (from === to || from < 0) return;
    change(() => { design.items = moveItem(design.items, from, to); selected = Math.min(to, design.items.length - 1); }, { structure: true });
  }
  function remove(i) {
    const name = ELEMENTS[design.items[i]?.kind]?.name ?? "element";
    change(() => { design.items.splice(i, 1); selected = -1; }, { structure: true });
    announce(`Removed the ${name.toLowerCase()}. Undo brings it back.`);
  }
  function duplicate(i) {
    change(() => { design.items = insertItem(design.items, i + 1, structuredClone(design.items[i])); selected = i + 1; }, { structure: true });
  }

  // ---------------------------------------------------------------- the screen
  const live = h("p", { class: "wp-live visually-hidden", role: "status", "aria-live": "polite" });
  const announce = (t) => { live.textContent = t; };
  const palette = h("div", { class: "wp-palette", role: "group", "aria-label": "Elements to add" });
  const list = h("div", { class: "wp-list", role: "list", "aria-label": "The page's elements" });
  const titleEl = h("h1");
  const card = h("div", { class: "wp-card" }, titleEl, list);
  const screen = h("div", { class: "wp-screen" }, card);
  const phone = h("div", { class: "wp-phone", "aria-label": "Your page on a phone" }, screen);
  const bin = h("div", { class: "wp-bin", "aria-hidden": "true" }, "✕ Drop here to remove");
  const benchEl = h("div", { class: "wp-bench", role: "group", "aria-label": "Your project (pretend parts)" });
  const inspector = h("div", { class: "wp-inspector" });
  const codeView = h("pre", { class: "wp-code", tabindex: 0, "aria-label": "The code your page makes" });
  const codeBox = h("details", { class: "wp-code-box", ontoggle: () => drawCode() }, h("summary", { text: "See the code it makes" }), codeView);
  const modeBtns = {
    design: h("button", { class: "tab", type: "button", role: "tab", onclick: () => setMode("design") }, "✎ Design"),
    try: h("button", { class: "tab", type: "button", role: "tab", onclick: () => setMode("try") }, "▶ Try it"),
  };
  const modeHelp = h("p", { class: "small muted wp-mode-help" });
  const undoBtn = h("button", { class: "btn small", type: "button", onclick: undo, "aria-label": "Undo" }, "↶ Undo");
  const redoBtn = h("button", { class: "btn small", type: "button", onclick: redo, "aria-label": "Redo" }, "↷ Redo");
  const ideas = h("select", { class: "input", "aria-label": "Start from an idea", onchange: (e) => startFrom(e.target) },
    h("option", { value: "", text: "Start from an idea..." }),
    Object.entries(TEMPLATES).map(([id, t]) => h("option", { value: id, text: t.name })));
  const root = h("div", { class: ["wp-designer", "mode-design"] },
    h("div", { class: "wp-left" },
      h("div", { class: "wp-history" }, undoBtn, redoBtn), ideas,
      h("p", { class: "small muted", text: "Drag an element onto the phone, or click it to add it." }),
      palette),
    h("div", { class: "wp-centre" },
      h("div", { class: "tabs wp-modes", role: "tablist", "aria-label": "Design or try" }, modeBtns.design, modeBtns.try),
      modeHelp, h("div", { class: "wp-stage" }, phone, bin), benchEl, codeBox),
    inspector, live);

  // the palette: one tile per element, in groups
  for (const [group, name] of GROUPS) {
    palette.append(h("p", { class: "wp-group", text: name }),
      h("div", { class: "wp-tiles" }, Object.entries(ELEMENTS).filter(([, e]) => e.group === group).map(([kind, e]) =>
        h("button", {
          class: "wp-tile", type: "button", title: e.tip, "aria-label": `Add ${e.name}`, dataset: { kind },
          onpointerdown: (ev) => startDrag(ev, { source: "palette", kind, label: e.name }),
          onclick: () => { if (!justDragged) addAt(kind); },
        }, h("span", { class: "wp-tile-symbol", text: e.symbol, "aria-hidden": "true" }), h("span", { text: e.name })))));
  }

  // ---------------------------------------------------------------- drawing
  function redraw({ inspector: insp = true } = {}) {
    root.classList.toggle("mode-design", mode === "design");
    root.classList.toggle("mode-try", mode === "try");
    for (const [m, b] of Object.entries(modeBtns)) b.setAttribute("aria-selected", String(m === mode));
    modeHelp.textContent = mode === "design"
      ? "Drag elements to move them. Click one to change it. Drag it to the bin to remove it."
      : "Use the page like a phone would: press buttons, flick switches, move sliders. The pretend parts below react. Change the knobs and sensors to see the readings move.";
    undoBtn.disabled = !past.length;
    redoBtn.disabled = !future.length;
    drawPhone();
    drawBench();
    if (insp) drawInspector();
    drawCode();
  }

  let updaters = []; // functions that refresh just the numbers on the phone and the bench (so a slider being dragged keeps going)
  function refreshValues() { for (const u of updaters) u(); }

  function drawPhone() {
    const t = THEMES[design.theme] ?? THEMES.teal;
    for (const [k, v] of Object.entries({ "--wp-bg": t.bg, "--wp-card": t.card, "--wp-ink": t.ink, "--wp-accent": t.accent, "--wp-accent-ink": t.accentInk })) phone.style.setProperty(k, v);
    titleEl.textContent = design.title || "My page";
    updaters = updaters.filter((u) => u.bench);
    const items = namedItems(design);
    const clashes = pinClashes(design, board);
    list.replaceChildren(...items.map((it, i) => {
      const el = h("div", {
        class: ["wp-el", `wp-el-${it.kind}`, i === selected && mode === "design" && "selected"], role: "listitem",
        tabindex: mode === "design" ? 0 : -1, dataset: { index: String(i) },
        "aria-label": `${ELEMENTS[it.kind]?.name}: ${summary(it)}. Enter to change it, Alt and the arrow keys to move it, Delete to remove it.`,
        onpointerdown: (ev) => { if (mode === "design") startDrag(ev, { source: "phone", from: i, kind: it.kind, label: ELEMENTS[it.kind]?.name }); },
        onclick: () => { if (mode === "design" && !justDragged) pick(i); },
        onkeydown: (ev) => keyOnElement(ev, i),
      }, view(it, i));
      if (mode === "design") {
        const badges = connections(it, board).map((c) => h("span", { class: "wp-badge", text: connectionText(c) }));
        const clash = clashes.find((c) => c.items.includes(i));
        if (clash) badges.push(h("span", { class: "wp-badge warn", text: `⚠ pin ${clash.pin} is shared` }));
        if (badges.length) el.append(h("div", { class: "wp-badges" }, badges));
      }
      return el;
    }));
    if (!items.length) list.append(h("p", { class: "wp-empty", text: "Drag something here from the left, or click it." }));
    refreshValues();
  }

  /** One element as the phone shows it. In Try it, the controls work. */
  function view(it, i) {
    const trying = mode === "try";
    const use = (v) => { bench.use(i, v); refreshValues(); };
    switch (it.kind) {
      case "heading": return h("h2", { text: it.text });
      case "text": return h("p", { text: it.text });
      case "button": {
        const b = h(trying ? "button" : "span", { class: "wp-btn", type: trying ? "button" : null, text: it.label || "Press me", onclick: trying ? () => use() : null });
        return h("p", {}, b);
      }
      case "switch": {
        const sw = h(trying ? "button" : "span", { class: "wp-switch", type: trying ? "button" : null, role: trying ? "switch" : null, onclick: trying ? () => use() : null },
          h("span", { class: "wp-track" }, h("span", { class: "wp-knob" })), h("span", { text: ` ${it.label || "Switch"} ` }), h("b"));
        updaters.push(() => { const on = bench.show(i) === "on"; sw.classList.toggle("on", on); sw.querySelector("b").textContent = on ? "ON" : "OFF"; if (trying) sw.setAttribute("aria-checked", String(on)); });
        return h("p", {}, sw);
      }
      case "slider": {
        const shown = h("b");
        const range = h("input", { type: "range", min: it.min ?? 0, max: it.max ?? 100, value: bench.show(i), disabled: !trying, "aria-label": it.label || "Slider",
          oninput: (e) => use(Number(e.target.value)) });
        updaters.push(() => { shown.textContent = String(bench.show(i)); if (document.activeElement !== range) range.value = bench.show(i); });
        return h("div", { class: "wp-slider" }, h("span", { text: `${it.label || "Slider"} ` }), shown, h("br"), range);
      }
      case "colour": {
        const pick = h("input", { type: "color", value: bench.show(i), disabled: !trying, "aria-label": it.label || "Colour", oninput: (e) => use(e.target.value) });
        return h("div", { class: "wp-colour" }, h("span", { text: `${it.label || "Colour"} ` }), pick);
      }
      case "reading": {
        const num = h("b");
        const bar = it.style === "bar" ? h("meter", { min: 0, max: it.max ?? 100 }) : null;
        updaters.push(() => { const v = bench.show(i); num.textContent = String(v); if (bar) bar.value = v; });
        return h("p", { class: "wp-reading" }, `${it.label || "Reading"}: `, num, it.unit ? ` ${it.unit}` : "", bar ? h("br") : null, bar);
      }
      case "status": {
        const p = h("p", { class: "wp-status" }, h("span", { class: "wp-dot" }), ` ${it.label || "Status"}: `, h("b"));
        updaters.push(() => { const on = bench.show(i) === "on"; p.classList.toggle("on", on); p.querySelector("b").textContent = on ? (it.onText || "Yes") : (it.offText || "No"); });
        return p;
      }
      default: return h("p", { text: "?" });
    }
  }

  /** The pretend parts: what the page drives, and what it reads. */
  function drawBench() {
    updaters = updaters.filter((u) => !u.bench);
    const add = (fn) => { fn.bench = true; updaters.push(fn); };
    const s = bench.state;
    const parts = [];
    for (const role of Object.keys(s.outputs)) {
      const led = h("span", { class: "wp-led", "aria-hidden": "true" });
      led.style.setProperty("--led", ledColour(role));
      const state = h("span", { class: "small muted" });
      add(() => { led.style.setProperty("--level", String(s.outputs[role] ?? 0)); state.textContent = s.outputs[role] ? (s.outputs[role] < 1 ? `${Math.round(s.outputs[role] * 100)}%` : "on") : "off"; });
      parts.push(h("div", { class: "wp-part" }, led, h("span", { text: pinText(role) }), state));
    }
    if (s.rgb) {
      const rgb = h("span", { class: "wp-led rgb", "aria-hidden": "true" });
      const label = h("span", { class: "small muted" });
      add(() => { rgb.style.setProperty("--led", `rgb(${s.rgb.r}, ${s.rgb.g}, ${s.rgb.b})`); rgb.style.setProperty("--level", String(Math.max(s.rgb.r, s.rgb.g, s.rgb.b) / 255)); label.textContent = `rgb ${s.rgb.r}, ${s.rgb.g}, ${s.rgb.b}`; });
      parts.push(h("div", { class: "wp-part" }, rgb, h("span", { text: "RGB LED" }), label));
    }
    const usesBuzzer = design.items.some((it) => connections(it, board).some((c) => c.role === "BUZZER_PIN"));
    if (usesBuzzer) {
      const note = h("span", { class: "wp-buzz", "aria-hidden": "true", text: "♪" });
      const label = h("span", { class: "small muted" });
      let beeps = s.beep;
      add(() => {
        if (s.beep !== beeps) { beeps = s.beep; note.classList.remove("beep"); void note.offsetWidth; note.classList.add("beep"); sound(880, 0.3); }
        label.textContent = s.pitch ? `playing ${s.pitch} Hz` : "quiet";
        note.classList.toggle("playing", s.pitch > 0);
      });
      parts.push(h("div", { class: "wp-part" }, note, h("span", { text: pinText("BUZZER_PIN") }), label));
    }
    for (const [role, v] of Object.entries(s.inputs)) {
      if (typeof v === "boolean") {
        const hold = role === "BUTTON_PIN";
        const ctl = h("button", { class: "btn small", type: "button", "aria-pressed": String(v),
          onpointerdown: hold ? () => setIn(role, true) : null, onpointerup: hold ? () => setIn(role, false) : null, onpointerleave: hold ? () => setIn(role, false) : null,
          onkeydown: hold ? (e) => { if (e.key === " " || e.key === "Enter") setIn(role, true); } : null,
          onkeyup: hold ? (e) => { if (e.key === " " || e.key === "Enter") setIn(role, false); } : null,
          onclick: hold ? null : () => setIn(role, !bench.state.inputs[role]) }, hold ? "Hold to press" : "Wave at it");
        add(() => { ctl.setAttribute("aria-pressed", String(Boolean(bench.state.inputs[role]))); ctl.classList.toggle("down", Boolean(bench.state.inputs[role])); });
        parts.push(h("div", { class: "wp-part input" }, h("span", { text: `${partName(role)} (pin ${board.pin_plan?.[role] ?? "?"})` }), ctl));
      } else {
        const range = h("input", { type: "range", min: 0, max: bench.analogMax, value: v, "aria-label": `Pretend ${partName(role).toLowerCase()}`, oninput: (e) => setIn(role, Number(e.target.value)) });
        parts.push(h("div", { class: "wp-part input" }, h("span", { text: `${partName(role)} (pin ${board.pin_plan?.[role] ?? "?"})` }), range));
      }
    }
    benchEl.replaceChildren(h("p", { class: "wp-bench-title" }, h("b", { text: "Your project " }), h("span", { class: "small muted", text: "(pretend parts: the real ones do the same)" })),
      parts.length ? h("div", { class: "wp-parts" }, parts) : h("p", { class: "small muted", text: "Add a button, switch, slider, colour, reading or status light to see the parts it uses." }));
    refreshValues();
  }
  function setIn(role, v) { bench.setInput(role, v); refreshValues(); }

  // ---------------------------------------------------------------- the inspector
  const field = (label, input) => h("label", { class: "wp-field" }, h("span", { text: label }), input);
  const text = (obj, key, opts = {}) => h("input", { class: "input", value: obj[key] ?? "", maxlength: opts.max ?? 60, placeholder: opts.placeholder ?? "",
    oninput: (e) => change(() => { obj[key] = e.target.value; }, { key: `${selected}.${key}`, bench: true }) });
  const num = (obj, key, dflt) => h("input", { class: "input wp-num", type: "number", value: obj[key] ?? dflt,
    oninput: (e) => change(() => { obj[key] = Number(e.target.value); }, { key: `${selected}.${key}`, bench: true }) });
  const select = (obj, key, options, structure = true) => h("select", { class: "input",
    onchange: (e) => change(() => { obj[key] = e.target.value; }, { structure }) },
  options.map(([v, t]) => h("option", { value: v, text: t, selected: (obj[key] ?? "") === v })));
  const pinChoice = (it, label = "Which pin") => field(label, select(it, "pin", outputRoles.map((r) => [r, pinText(r)])));

  function drawInspector() {
    if (selected < 0 || !design.items[selected]) return drawPageSettings();
    const it = design.items[selected];
    const i = selected;
    const e = ELEMENTS[it.kind];
    const fields = [];
    if (it.kind === "heading" || it.kind === "text") fields.push(field(e.name, text(it, "text", { max: it.kind === "text" ? 160 : 60 })));
    if (it.kind === "button") {
      fields.push(field("Words on the button", text(it, "label")), field("What it does", select(it, "action", Object.entries(BUTTON_ACTIONS))));
      if (["on", "off", "toggle"].includes(it.action)) fields.push(pinChoice(it));
    }
    if (it.kind === "switch") fields.push(field("Name", text(it, "label")), pinChoice(it, "It switches"));
    if (it.kind === "slider") {
      fields.push(field("Name", text(it, "label")), h("div", { class: "wp-row" }, field("From", num(it, "min", 0)), field("To", num(it, "max", 100))),
        field("It changes", select(it, "pin", [["", "A number I'll use in my code"], ...outputRoles.map((r) => [r, `How bright ${r} is`]), ["BUZZER_PIN", "How high the buzzer beeps"]])));
    }
    if (it.kind === "colour") fields.push(field("Name", text(it, "label")), h("p", { class: "small muted", text: `It sets the RGB LED: red on ${pinText("RGB_RED")}, green on ${pinText("RGB_GREEN")}, blue on ${pinText("RGB_BLUE")}.` }));
    if (it.kind === "reading") {
      fields.push(field("Name", text(it, "label")), field("It shows", select(it, "source", READING_SOURCES.map((s) => [s.source, s.label]))),
        h("div", { class: "wp-row" }, field("Unit", text(it, "unit", { max: 12, placeholder: "e.g. °C" })), field("Show it as", select(it, "style", [["number", "A number"], ["bar", "A bar"]]))));
      if (it.style === "bar") fields.push(field("The bar is full at", num(it, "max", board.analog_max ?? 1023)));
    }
    if (it.kind === "status") {
      fields.push(field("Name", text(it, "label")), field("It shows", select(it, "source", Object.entries(STATUS_SOURCES).map(([k, s]) => [k, s.label]))));
      if ((it.source ?? "light") === "light") fields.push(pinChoice(it, "Which light"));
      fields.push(h("div", { class: "wp-row" }, field("Words when it's on", text(it, "onText", { max: 24 })), field("Words when it's off", text(it, "offText", { max: 24 }))));
    }
    const clash = pinClashes(design, board).find((c) => c.items.includes(i));
    inspector.replaceChildren(...[
      h("div", { class: "wp-insp-head" }, h("span", { class: "wp-tile-symbol", text: e.symbol, "aria-hidden": "true" }), h("b", { text: e.name }),
        h("button", { class: "btn small", type: "button", onclick: () => pick(-1) }, "Page settings")),
      h("p", { class: "wp-does", text: describe(it) }),
      h("div", { class: "wp-fields" }, fields),
      clash ? h("p", { class: "wp-warn", role: "alert", text: `⚠ ${clash.roles.join(" and ")} are both on pin ${clash.pin} of your ${board.short || board.name}. They can't work at the same time: pick another part, or remove one.` }) : null,
      h("div", { class: "wp-insp-actions" },
        h("button", { class: "btn small", type: "button", disabled: i === 0, onclick: () => move(i, i - 1) }, "▲ Move up"),
        h("button", { class: "btn small", type: "button", disabled: i === design.items.length - 1, onclick: () => move(i, i + 1) }, "▼ Move down"),
        h("button", { class: "btn small", type: "button", onclick: () => duplicate(i) }, "Copy"),
        h("button", { class: "btn small danger", type: "button", onclick: () => remove(i) }, "✕ Remove"))].filter(Boolean));
  }

  function drawPageSettings() {
    const swatches = Object.entries(THEMES).map(([k, t]) => {
      const b = h("button", { class: ["wp-swatch", design.theme === k && "on"], type: "button", "aria-label": `${t.name} colours`, "aria-pressed": String(design.theme === k),
        onclick: () => change(() => { design.theme = k; }, { structure: true }) }, h("span", { text: t.name }));
      b.style.setProperty("--sw-bg", t.bg);
      b.style.setProperty("--sw-accent", t.accent);
      b.style.setProperty("--sw-ink", t.ink);
      return b;
    });
    inspector.replaceChildren(
      h("div", { class: "wp-insp-head" }, h("b", { text: "The page" })),
      h("p", { class: "wp-does", text: "Click an element on the phone to change it." }),
      field("Title", text(design, "title")),
      h("div", { class: "wp-field" }, h("span", { text: "Colours" }), h("div", { class: "wp-swatches" }, swatches)),
      h("fieldset", { class: "groupbox" }, h("legend", { text: "WiFi" }),
        field("How phones reach it", select(design.wifi, "mode", [["hotspot", "The board makes its own WiFi"], ["join", "The board joins a WiFi"]])),
        field(design.wifi.mode === "join" ? "WiFi name to join" : "Its WiFi's name", text(design.wifi, "name", { max: 32 })),
        field("Password (8+ characters)", text(design.wifi, "password", { max: 63 })),
        (design.wifi.password ?? "").length < 8 ? h("p", { class: "wp-warn", text: "⚠ A WiFi password needs at least 8 characters." }) : null,
        design.wifi.mode === "join" ? h("p", { class: "small muted", text: "At school, ask your teacher which WiFi to use (for example Tech Guest)." }) : null),
      field("Readings update every (seconds)", num(design, "refresh", 5)));
  }

  // ---------------------------------------------------------------- the code view
  function drawCode() {
    if (codeBox.open) codeView.textContent = generateSketch(design, board);
  }

  // ---------------------------------------------------------------- drag and drop (pointer events: mouse, touch or pen)
  let drag = null;
  let justDragged = false;
  const marker = h("div", { class: "wp-marker", "aria-hidden": "true" });

  function startDrag(ev, info) {
    if (ev.button !== 0 || mode !== "design") return;
    drag = { ...info, x0: ev.clientX, y0: ev.clientY, started: false, pointerId: ev.pointerId };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", cancelDrag);
  }
  function onMove(ev) {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    if (!drag.started) {
      if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 5) return;
      drag.started = true;
      drag.ghost = h("div", { class: "wp-ghost", "aria-hidden": "true" }, h("span", { class: "wp-tile-symbol", text: ELEMENTS[drag.kind]?.symbol ?? "" }), ` ${drag.label}`);
      document.body.append(drag.ghost);
      root.classList.add("dragging");
      if (drag.source === "phone") list.querySelector(`[data-index="${drag.from}"]`)?.classList.add("lifted");
    }
    ev.preventDefault();
    drag.ghost.style.transform = `translate(${ev.clientX + 12}px, ${ev.clientY + 8}px)`;
    drag.target = targetAt(ev.clientX, ev.clientY);
    bin.classList.toggle("hot", drag.target?.bin === true);
    phone.classList.toggle("hot", drag.target?.index != null);
    if (drag.target?.index != null) {
      const els = [...list.querySelectorAll(".wp-el:not(.lifted)")];
      const before = els[drag.target.index];
      if (before) list.insertBefore(marker, before); else list.append(marker);
    } else marker.remove();
  }
  /** Where a drop would go: a gap in the list, the bin, or nowhere. */
  function targetAt(x, y) {
    const inside = (r) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    if (drag.source === "phone" && inside(bin.getBoundingClientRect())) return { bin: true };
    if (!inside(phone.getBoundingClientRect())) return null;
    const middles = [...list.querySelectorAll(".wp-el:not(.lifted)")].map((el) => { const r = el.getBoundingClientRect(); return r.top + r.height / 2; });
    return { index: dropIndex(middles, y) };
  }
  function onUp(ev) {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    const d = drag;
    cancelDrag();
    if (!d.started) return;
    justDragged = true;
    setTimeout(() => { justDragged = false; }, 0);
    if (d.target?.bin && d.source === "phone") remove(d.from);
    else if (d.target?.index != null) {
      if (d.source === "palette") addAt(d.kind, d.target.index);
      else move(d.from, d.target.index);
    }
  }
  function cancelDrag() {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    document.removeEventListener("pointercancel", cancelDrag);
    drag?.ghost?.remove();
    marker.remove();
    root.classList.remove("dragging");
    bin.classList.remove("hot");
    phone.classList.remove("hot");
    list.querySelector(".lifted")?.classList.remove("lifted");
    drag = null;
  }

  // ---------------------------------------------------------------- the keyboard
  function keyOnElement(ev, i) {
    if (mode !== "design") return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(i); }
    else if (ev.altKey && ev.key === "ArrowUp" && i > 0) { ev.preventDefault(); move(i, i - 1); focusEl(i - 1); }
    else if (ev.altKey && ev.key === "ArrowDown" && i < design.items.length - 1) { ev.preventDefault(); move(i, i + 1); focusEl(i + 1); }
    else if (ev.key === "Delete" || ev.key === "Backspace") { ev.preventDefault(); remove(i); }
  }
  const focusEl = (i) => list.querySelector(`[data-index="${i}"]`)?.focus();
  root.addEventListener("keydown", (ev) => {
    if (!(ev.ctrlKey || ev.metaKey) || /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;
    const k = ev.key.toLowerCase();
    if (k === "z" && !ev.shiftKey) { ev.preventDefault(); undo(); }
    else if (k === "y" || (k === "z" && ev.shiftKey)) { ev.preventDefault(); redo(); }
  });

  // ---------------------------------------------------------------- the rest
  function pick(i) { selected = i; drawPhone(); drawInspector(); }
  function setMode(m) {
    mode = m;
    if (m === "try") selected = -1;
    redraw();
    announce(m === "try" ? "Try it: the page works. The pretend parts show what your project would do." : "Design: drag elements to change the page.");
  }
  async function startFrom(sel) {
    const id = sel.value;
    sel.value = "";
    if (!id) return;
    if (design.items.length) {
      const ok = await messageBox({ kind: "question", instruction: `Start again from "${TEMPLATES[id].name}"?`, text: "Your page is replaced. (Undo brings it back.)",
        buttons: [{ id: "yes", label: "Start from it" }, { id: "no", label: "Cancel", default: true, cancel: true }] });
      if (ok !== "yes") return;
    }
    change(() => {
      design = tidy(structuredClone(TEMPLATES[id].design));
      for (const it of design.items) if (it.kind === "reading" && /analogRead/.test(it.source ?? "")) it.max = board.analog_max ?? it.max;
      selected = -1;
    }, { structure: true });
  }

  /** A design with everything it needs (older saved designs may be missing a part). */
  function tidy(d) {
    d.items = Array.isArray(d.items) ? d.items.filter((it) => it && ELEMENTS[it.kind]) : [];
    d.wifi = { mode: "hotspot", name: "", password: "", ...(d.wifi ?? {}) };
    d.theme = THEMES[d.theme] ? d.theme : "teal";
    return d;
  }

  /** One sentence: what pressing or seeing this element does, with its pins. */
  function describe(it) {
    const pin = (r) => pinText(r);
    switch (it.kind) {
      case "heading": case "text": return "Words on the page. They don't need any parts.";
      case "button": {
        const name = `“${it.label || "Press me"}”`;
        if (it.action === "on") return `Pressing ${name} turns ${pin(it.pin || "LED_PIN")} on.`;
        if (it.action === "off") return `Pressing ${name} turns ${pin(it.pin || "LED_PIN")} off.`;
        if (it.action === "toggle") return `Pressing ${name} switches ${pin(it.pin || "LED_PIN")} on, then off, then on...`;
        if (it.action === "beep") return `Pressing ${name} beeps the buzzer on ${pin("BUZZER_PIN")}.`;
        return `Pressing ${name} runs code you write yourself (look for its function in your code).`;
      }
      case "switch": return `Flicking “${it.label || "Switch"}” turns ${pin(it.pin || "LED_PIN")} on or off, and the page shows which.`;
      case "slider": return it.pin === "BUZZER_PIN" ? `Moving “${it.label}” changes how high the buzzer beeps (0 is quiet).`
        : it.pin ? `Moving “${it.label}” changes how bright ${pin(it.pin)} is.` : `Moving “${it.label}” sets a number your code can use.`;
      case "colour": return "Picking a colour lights the RGB LED in that colour.";
      case "reading": {
        const src = READING_SOURCES.find((s) => s.source === (it.source ?? ""));
        const what = src?.source ? src.label.replace(/^\w/, (c) => c.toLowerCase()) : "a number your code sets in loop()";
        return `Shows ${what}${it.style === "bar" ? " as a bar" : ""}. The page updates every ${design.refresh ?? 5} seconds.`;
      }
      case "status": {
        const s = STATUS_SOURCES[it.source] ?? STATUS_SOURCES.light;
        return s.role ? `Lights up when ${s.label.replace(/^Is /, "").replace(/\?.*$/, "")} (${pin(s.role)}).` : `Lights up when ${pin(it.pin || "LED_PIN")} is on.`;
      }
      default: return "";
    }
  }
  function summary(it) { return it.text || it.label || ELEMENTS[it.kind]?.name || ""; }

  // a short beep from the computer when the pretend buzzer beeps (if sound is allowed)
  let audio;
  function sound(freq, secs) {
    try {
      audio ??= new AudioContext();
      const o = audio.createOscillator();
      const g = audio.createGain();
      g.gain.value = 0.05;
      o.frequency.value = freq;
      o.connect(g).connect(audio.destination);
      o.start();
      o.stop(audio.currentTime + secs);
    } catch { /* no sound: the note still shows */ }
  }

  // readings that count seconds keep counting while the designer is open
  const clock = setInterval(() => { bench.tick(1); refreshValues(); }, 1000);

  redraw();
  const useBtn = h("button", { class: "pill", type: "button", onclick: async () => {
    const code = generateSketch(design, board);
    if (currentCode.trim() && !/Web Page Designer/.test(currentCode)) {
      const ok = await messageBox({ kind: "question", instruction: "Replace your code with the web page's code?", text: "Download your code first (.ino) if you want to keep it.", buttons: [{ id: "yes", label: "Replace it" }, { id: "no", label: "Cancel", default: true, cancel: true }] });
      if (ok !== "yes") return;
    }
    onUse(code, design);
    dlg.close(true);
  } }, icon("check"), "Put it in my code");
  const dlg = openDialog({
    title: "Web Page Designer", wide: true, iconName: "wifi", className: "wp-dialog",
    content: [h("p", { class: "wp-intro", text: `Build your project's web page, try it, then press "Put it in my code". Your ${board.short || board.name} serves the page, and its controls work your project.` }), root],
    buttons: [useBtn, h("button", { class: "pill", type: "button", onclick: () => dlg.close(undefined) }, "Close")],
  });
  dlg.result.then(() => { clearInterval(clock); cancelDrag(); try { audio?.close(); } catch { /* fine */ } });
  return dlg;
}
