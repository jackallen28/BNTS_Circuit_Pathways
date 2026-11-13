// The Web Page Designer (ESP boards): students build their project's web page from headings, text,
// buttons, sliders and readings, see it on a phone straight away, and get a complete, commented
// sketch with the web server already written (webpage.js makes the code).
import { h, icon } from "../dom.js";
import { openDialog, messageBox } from "../widgets/window.js";
import { THEMES, ITEM_KINDS, BUTTON_ACTIONS, READING_SOURCES, generateSketch, namedItems, starterDesign } from "../webpage.js";

/**
 * @param {{ board: object, design?: object, currentCode: string, onSave: (design) => void, onUse: (code: string, design) => void }} o
 */
export function openWebPageDesigner({ board, design: saved, currentCode = "", onSave = () => {}, onUse = () => {} }) {
  const design = structuredClone(saved ?? starterDesign());
  const roles = Object.keys(board.pin_plan ?? {}).filter((r) => /^(LED_|BUZZER|SERVO|RELAY|RGB_)/.test(r));
  const editor = h("div", { class: "wp-editor" });
  const preview = h("div", { class: "wp-phone", "aria-label": "How the page looks on a phone" });
  const changed = () => { draw(); onSave(design); };

  const field = (label, input) => h("label", { class: "wp-field" }, h("span", { text: label }), input);
  const text = (obj, key, opts = {}) => h("input", { class: "input", value: obj[key] ?? "", maxlength: opts.max ?? 60, placeholder: opts.placeholder ?? "",
    oninput: (e) => { obj[key] = e.target.value; changed(); } });
  const num = (obj, key, dflt) => h("input", { class: "input wp-num", type: "number", value: obj[key] ?? dflt, oninput: (e) => { obj[key] = Number(e.target.value); changed(); } });
  const select = (obj, key, options, onchange) => h("select", { class: "input", onchange: (e) => { obj[key] = e.target.value; onchange?.(); changed(); } },
    options.map(([v, t]) => h("option", { value: v, text: t, selected: (obj[key] ?? "") === v })));

  function itemRow(it, i) {
    const move = (d) => { const j = i + d; if (j < 0 || j >= design.items.length) return; [design.items[i], design.items[j]] = [design.items[j], design.items[i]]; render(); changed(); };
    const fields = [];
    if (it.kind === "heading" || it.kind === "text") fields.push(field(ITEM_KINDS[it.kind], text(it, "text", { max: it.kind === "text" ? 160 : 60 })));
    if (it.kind === "button") {
      fields.push(field("Words on the button", text(it, "label")));
      fields.push(field("What it does", select(it, "action", Object.entries(BUTTON_ACTIONS), render)));
      if (it.action !== "custom") fields.push(field("Which pin", select(it, "pin", roles.map((r) => [r, `${r} (pin ${board.pin_plan[r]})`]))));
    }
    if (it.kind === "slider") {
      fields.push(field("Name", text(it, "label")), field("From", num(it, "min", 0)), field("To", num(it, "max", 100)));
      fields.push(field("It changes", select(it, "pin", [["", "A number I'll use"], ...roles.map((r) => [r, `How bright ${r} is`])])));
    }
    if (it.kind === "reading") {
      fields.push(field("Name", text(it, "label")), field("Unit", text(it, "unit", { max: 12, placeholder: "e.g. °C" })));
      fields.push(field("It shows", select(it, "source", READING_SOURCES.map((s) => [s.source, s.label]))));
    }
    return h("li", { class: "wp-item" },
      h("div", { class: "wp-item-head" }, h("b", { text: ITEM_KINDS[it.kind] }),
        h("span", { class: "spacer" }),
        h("button", { class: "btn small", type: "button", "aria-label": "Move up", onclick: () => move(-1) }, "▲"),
        h("button", { class: "btn small", type: "button", "aria-label": "Move down", onclick: () => move(1) }, "▼"),
        h("button", { class: "btn small", type: "button", "aria-label": `Remove this ${ITEM_KINDS[it.kind].toLowerCase()}`, onclick: () => { design.items.splice(i, 1); render(); changed(); } }, "✕")),
      h("div", { class: "wp-item-fields" }, fields));
  }

  function add(kind) {
    const fresh = { heading: { kind, text: "A heading" }, text: { kind, text: "Some words about my project." },
      button: { kind, label: "Press me", action: roles.length ? "toggle" : "custom", pin: roles[0] ?? "" },
      slider: { kind, label: "Speed", min: 0, max: 10 }, reading: { kind, label: "Reading", source: "millis() / 1000" } }[kind];
    design.items.push(fresh);
    render();
    changed();
  }

  function render() {
    editor.replaceChildren(
      h("fieldset", { class: "groupbox" }, h("legend", { text: "The page" }),
        field("Title", text(design, "title")),
        field("Colours", select(design, "theme", Object.entries(THEMES).map(([k, t]) => [k, t.name])))),
      h("fieldset", { class: "groupbox" }, h("legend", { text: "WiFi" }),
        field("How phones reach it", select(design.wifi, "mode", [["hotspot", "The board makes its own WiFi"], ["join", "The board joins a WiFi"]], render)),
        field(design.wifi.mode === "join" ? "WiFi name to join" : "Its WiFi's name", text(design.wifi, "name", { max: 32 })),
        field("Password (8+ characters)", text(design.wifi, "password", { max: 63 })),
        design.wifi.mode === "join" ? h("p", { class: "small muted", text: "At school, ask your teacher which WiFi to use (for example Tech Guest)." }) : null),
      h("fieldset", { class: "groupbox" }, h("legend", { text: "What's on it" }),
        h("ol", { class: "wp-items" }, design.items.map(itemRow)),
        h("div", { class: "wp-add" }, h("span", { text: "Add: " }), Object.entries(ITEM_KINDS).map(([k, t]) => h("button", { class: "btn small", type: "button", onclick: () => add(k) }, `+ ${t}`)))));
    draw();
  }

  /** The phone preview, drawn with the page's own colours (CSSOM, so the security policy allows it). */
  function draw() {
    const t = THEMES[design.theme] ?? THEMES.teal;
    for (const [k, v] of Object.entries({ "--wp-bg": t.bg, "--wp-card": t.card, "--wp-ink": t.ink, "--wp-accent": t.accent, "--wp-accent-ink": t.accentInk })) preview.style.setProperty(k, v);
    const items = namedItems(design);
    preview.replaceChildren(h("div", { class: "wp-screen" }, h("div", { class: "wp-card" },
      h("h1", { text: design.title || "My page" }),
      items.map((it) => {
        switch (it.kind) {
          case "heading": return h("h2", { text: it.text });
          case "text": return h("p", { text: it.text });
          case "button": return h("p", {}, h("span", { class: "wp-btn", text: it.label || "Press me" }));
          case "slider": return h("p", {}, h("span", { text: `${it.label || "Slider"} ` }), h("b", { text: String(it.min ?? 0) }), h("br"), h("input", { type: "range", min: it.min ?? 0, max: it.max ?? 100, value: it.min ?? 0, "aria-label": `${it.label} (preview)` }), h("br"), h("span", { class: "wp-btn small", text: "Set" }));
          case "reading": return h("p", { class: "wp-reading" }, `${it.label || "Reading"}: `, h("b", { text: "42" }), it.unit ? ` ${it.unit}` : "");
          default: return null;
        }
      }))));
  }

  render();
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
    title: "Web Page Designer", wide: true, iconName: "wifi",
    content: [h("p", { class: "wp-intro", text: `Build your project's web page, then press "Put it in my code". Your ${board.short || board.name} serves the page, and its buttons and sliders work your project.` }),
      h("div", { class: "wp-layout" }, editor, h("div", { class: "wp-side" }, h("p", { class: "small muted", text: "On a phone:" }), preview))],
    buttons: [useBtn, h("button", { class: "pill", type: "button", onclick: () => dlg.close(undefined) }, "Close")],
  });
  return dlg;
}
