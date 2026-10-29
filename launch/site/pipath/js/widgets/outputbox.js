// The Output box (MS-DOS Prompt style) with the "type your answer" row for input().
import { h } from "../dom.js";

const MAX_LINES = 4000;

export function createConsole({ onInput = () => {} } = {}) {
  const out = h("div", { class: "console-out", role: "log", "aria-label": "Output", "aria-live": "polite", tabindex: "0" });
  const input = h("input", { type: "text", "aria-label": "Type your answer here", placeholder: "Type your answer, then press Enter", autocomplete: "off", spellcheck: "false" });
  const send = h("button", { class: "btn small", type: "button", text: "Enter" });
  const row = h("div", { class: "console-in" }, input, send);
  const el = h("div", { class: "win console panel" }, out, row);
  const history = [];
  let hi = 0;
  let pending = [];
  let scheduled = false;
  let lines = 1;

  function flush() {
    scheduled = false;
    const stick = out.scrollTop + out.clientHeight >= out.scrollHeight - 30;
    for (const [text, kind] of pending) {
      lines += (text.match(/\n/g) ?? []).length;
      out.append(kind ? h("span", { class: kind, text }) : document.createTextNode(text));
    }
    pending = [];
    while (lines > MAX_LINES && out.firstChild) {
      lines -= ((out.firstChild.textContent ?? "").match(/\n/g) ?? []).length;
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

  function submit() {
    const text = input.value;
    input.value = "";
    history.push(text);
    hi = history.length;
    write(text + "\n", "typed");
    onInput(text);
  }
  send.addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "ArrowUp" && hi > 0) { input.value = history[--hi]; e.preventDefault(); }
    else if (e.key === "ArrowDown") { input.value = hi < history.length - 1 ? history[++hi] : ((hi = history.length), ""); e.preventDefault(); }
  });

  return {
    el, write,
    clear() { pending = []; out.replaceChildren(); lines = 1; },
    setWaiting(on) { row.classList.toggle("waiting", on); if (on) input.focus(); },
    focusInput: () => input.focus(),
    get text() { return out.textContent; },
  };
}
