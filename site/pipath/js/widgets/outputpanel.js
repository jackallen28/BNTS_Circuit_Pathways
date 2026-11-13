// The Output box, with the "type your answer" row for input().
import { h } from "../dom.js";

const MAX_LINES = 4000;

export function createConsole({ onInput = () => {} } = {}) {
  const out = h("div", { class: "console-out", role: "log", "aria-label": "Output", "aria-live": "polite", tabindex: "0" });
  const input = h("input", { type: "text", "aria-label": "Type your answer here", placeholder: "Type your answer, then press Enter", autocomplete: "off", spellcheck: "false" });
  const send = h("button", { class: "btn small", type: "submit", text: "Enter" });
  const row = h("form", { class: "console-in", autocomplete: "off" }, input, send);
  const el = h("div", { class: "win console panel" }, out, row);
  let pending = [];
  let scheduled = false;
  let lines = 1;

  function flush() {
    scheduled = false;
    const stick = out.scrollTop + out.clientHeight >= out.scrollHeight - 30;
    for (const [text, kind] of pending) {
      lines += text.split("\n").length - 1;
      out.append(kind ? h("span", { class: kind, text }) : document.createTextNode(text));
    }
    pending = [];
    while (lines > MAX_LINES && out.firstChild) {
      lines -= (out.firstChild.textContent ?? "").split("\n").length - 1;
      out.firstChild.remove();
    }
    if (stick) out.scrollTop = out.scrollHeight;
  }

  function write(text, kind = "") {
    pending.push([text, kind]);
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(flush);
    }
  }

  // Pressing Enter in the box (or the Enter button) sends the answer to the program.
  row.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value;
    input.value = "";
    write(text + "\n", "typed");
    onInput(text);
  });

  return {
    el, write,
    clear() { pending = []; out.replaceChildren(); lines = 1; },
    setWaiting(on) { row.classList.toggle("waiting", on); if (on) input.focus(); },
    focusInput: () => input.focus(),
    get text() { return out.textContent; },
  };
}
