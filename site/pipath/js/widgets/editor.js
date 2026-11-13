// The code editor: a text box with line numbers, Tab / Shift+Tab, auto-indent, Ctrl+/ for
// comments, and a red band on the line the Coach is talking about.
import { h } from "../dom.js";

export function createEditor({ onChange = () => {}, onRun = () => {} } = {}) {
  const gutter = h("div", { class: "gutter", "aria-hidden": "true" });
  const band = h("div", { class: "errline", hidden: true });
  const ta = h("textarea", { class: "code", spellcheck: "false", autocapitalize: "off", autocomplete: "off", autocorrect: "off", wrap: "off", "aria-label": "Your code", id: "code" });
  const el = h("div", { class: "editor" }, gutter, ta, band);
  let errorLine = 0;

  const lineHeight = () => parseFloat(getComputedStyle(ta).lineHeight) || 21;

  function paintGutter() {
    const n = ta.value.split("\n").length;
    gutter.textContent = Array.from({ length: n }, (_, i) => i + 1).join("\n");
    gutter.style.width = `${Math.max(2, String(n).length) * 9 + 14}px`;
    syncScroll();
  }

  function syncScroll() {
    gutter.scrollTop = ta.scrollTop;
    if (errorLine) {
      band.hidden = false;
      band.style.top = `${6 + (errorLine - 1) * lineHeight() - ta.scrollTop}px`;
    }
  }

  const changed = () => { paintGutter(); onChange(ta.value); };
  ta.addEventListener("input", () => { clearError(); changed(); });
  ta.addEventListener("scroll", syncScroll);

  function lineRange() {
    const v = ta.value;
    const start = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
    let end = v.indexOf("\n", ta.selectionEnd);
    if (end < 0) end = v.length;
    return [start, end];
  }

  function replace(start, end, text, selStart, selEnd) {
    ta.focus();
    ta.setSelectionRange(start, end);
    if (!document.execCommand?.("insertText", false, text)) ta.setRangeText(text, start, end, "end"); // execCommand keeps Ctrl+Z working
    ta.setSelectionRange(selStart ?? start + text.length, selEnd ?? selStart ?? start + text.length);
    changed();
  }

  ta.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" && (e.ctrlKey || e.metaKey)) || e.key === "F5") { e.preventDefault(); onRun(); return; }
    if (e.key === "Tab") {
      e.preventDefault();
      const [s, en] = lineRange();
      if (ta.selectionStart === ta.selectionEnd && !e.shiftKey) { replace(ta.selectionStart, ta.selectionEnd, "    "); return; }
      const block = ta.value.slice(s, en).split("\n");
      const out = block.map((l) => (e.shiftKey ? l.replace(/^( {1,4}|\t)/, "") : "    " + l));
      replace(s, en, out.join("\n"), s, s + out.join("\n").length);
    } else if (e.key === "Enter" && !e.shiftKey) {
      const v = ta.value;
      const ls = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
      const line = v.slice(ls, ta.selectionStart);
      const indent = /^[ \t]*/.exec(line)[0];
      const extra = /:\s*(#.*)?$/.test(line) ? "    " : "";
      if (indent || extra) { e.preventDefault(); replace(ta.selectionStart, ta.selectionEnd, "\n" + indent + extra); }
    } else if (e.key === "/" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      const [s, en] = lineRange();
      const lines = ta.value.slice(s, en).split("\n");
      const all = lines.filter((l) => l.trim()).every((l) => /^\s*#/.test(l));
      const out = lines.map((l) => (!l.trim() ? l : all ? l.replace(/^(\s*)# ?/, "$1") : l.replace(/^(\s*)/, "$1# ")));
      replace(s, en, out.join("\n"), s, s + out.join("\n").length);
    }
  });

  function clearError() {
    errorLine = 0;
    band.hidden = true;
    gutter.querySelector(".err")?.classList.remove("err");
  }

  return {
    el, textarea: ta,
    get value() { return ta.value; },
    set value(v) { ta.value = v; clearError(); paintGutter(); },
    focus: () => ta.focus(),
    /** Marks a line (1-based) red and scrolls to it. */
    setErrorLine(n) {
      clearError();
      if (!n) return;
      errorLine = n;
      paintGutter();
      ta.scrollTop = Math.max(0, (n - 4) * lineHeight());
      syncScroll();
    },
    clearError,
    /** Puts text at the cursor (or the end if the editor isn't focused). */
    insert(text) {
      const at = document.activeElement === ta ? ta.selectionStart : ta.value.length;
      const end = document.activeElement === ta ? ta.selectionEnd : ta.value.length;
      replace(at, end, text);
    },
    setReadOnly(on) { ta.readOnly = on; },
  };
}
