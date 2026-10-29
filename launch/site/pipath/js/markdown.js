// The mini-markdown PiPath's lessons are written in: ## headings, **bold**, *italic*, `code`,
// - bullets, 1. numbers and ``` code blocks ```. Builds DOM (never innerHTML), so lesson text can't inject anything.

import { h } from "./dom.js";

function inline(text) {
  const out = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (let m; (m = re.exec(text)); ) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(h("code", { text: m[1].slice(1, -1) }));
    else if (m[2]) out.push(h("b", { text: m[2].slice(2, -2) }));
    else out.push(h("i", { text: m[3].slice(1, -1) }));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** @returns {HTMLElement} a div.md */
export function markdown(src) {
  const root = h("div", { class: "md" });
  const lines = String(src ?? "").replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const code = [];
      for (i++; i < lines.length && !/^```/.test(lines[i]); i++) code.push(lines[i]);
      i++;
      root.append(h("pre", { text: code.join("\n") }));
    } else if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      root.append(h(`h${level}`, {}, inline(line.replace(/^#+\s+/, ""))));
      i++;
    } else if (/^\s*[-*]\s+/.test(line)) {
      const ul = h("ul");
      for (; i < lines.length && /^\s*[-*]\s+/.test(lines[i]); i++) ul.append(h("li", {}, inline(lines[i].replace(/^\s*[-*]\s+/, ""))));
      root.append(ul);
    } else if (/^\s*\d+[.)]\s+/.test(line)) {
      const ol = h("ol");
      for (; i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i]); i++) ol.append(h("li", {}, inline(lines[i].replace(/^\s*\d+[.)]\s+/, ""))));
      root.append(ol);
    } else if (!line.trim()) {
      i++;
    } else {
      const para = [];
      for (; i < lines.length && lines[i].trim() && !/^(```|#{1,3}\s|\s*[-*]\s+|\s*\d+[.)]\s+)/.test(lines[i]); i++) para.push(lines[i]);
      root.append(h("p", {}, inline(para.join(" "))));
    }
  }
  return root;
}
