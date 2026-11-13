// Dialogs and message boxes in the same Windows 95 style.
import { h } from "../dom.js";

/**
 * A modal window. Returns { el, close(value), result } where result resolves when it closes.
 * @param {{title: string, body: Node|Node[], buttons?: {label: string, value?: any, default?: boolean, onclick?: Function, keepOpen?: boolean}[], wide?: boolean}} o
 */
export function dialog({ title, body, buttons = [], wide = false, onClose }) {
  let done;
  const result = new Promise((r) => { done = r; });
  const prevFocus = document.activeElement;
  const close = (value) => {
    overlay.remove();
    document.removeEventListener("keydown", onKey, true);
    prevFocus?.focus?.();
    onClose?.(value);
    done(value);
  };
  const btnEls = buttons.map((b) => h("button", {
    class: ["btn", b.default && "default"], type: "button", text: b.label,
    onclick: async () => {
      if (b.onclick) await b.onclick();
      if (!b.keepOpen) close(b.value);
    },
  }));
  const win = h("section", { class: "win dialog", role: "dialog", "aria-modal": "true", "aria-label": title, style: wide ? { width: "min(820px, 100%)" } : {} },
    h("div", { class: "titlebar" }, h("span", { class: "logo" }), h("span", { class: "title", text: title }),
      h("button", { class: "btn x", type: "button", "aria-label": "Close", text: "✕", onclick: () => close(undefined) })),
    h("div", { class: "win-body" }, body, buttons.length ? h("div", { class: "dlg-buttons" }, btnEls) : null));
  const overlay = h("div", { class: "overlay" }, win);
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(undefined); } };
  document.addEventListener("keydown", onKey, true);
  document.body.append(overlay);
  (win.querySelector("[autofocus]") ?? btnEls.find((_, i) => buttons[i].default) ?? btnEls[0])?.focus();
  return { el: win, close, result };
}

/** A simple message with an OK button, or choices. Resolves with the chosen value. */
export function messageBox({ title = "PiPath", instruction, text, buttons = [{ label: "OK", value: "ok", default: true }] }) {
  const lines = Array.isArray(text) ? text : text ? [text] : [];
  return dialog({ title, body: [instruction ? h("p", { class: "msg-title" }, h("b", { text: instruction })) : null, ...lines.map((t) => h("p", { text: t }))], buttons }).result;
}
