// Settings: help level, what to show, text size, saving and opening your work, the curriculum, About.
import { beta, TEST_WORK_NOTE, buildLabel } from "../../../shared/beta.js";
import { h } from "../dom.js";
import { download, joinNames } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";
import { dialog, messageBox } from "../widgets/window.js";
import { LEVELS, LEVEL_INFO, normaliseLevel } from "../progress.js";
import { markdown } from "../markdown.js";

export function openSettings({ startTab = "help", projectId = null, onChanged = () => {} } = {}) {
  const s = () => state.me.settings;
  let tab = startTab;
  const panel = h("div", { class: "tabpanel", role: "tabpanel" });
  const tabsEl = h("div", { class: "tabs", role: "tablist" });
  const save = async (patch) => { state.me.settings = { ...s(), ...patch }; await api.saveSettings(state.me.settings); onChanged(); };

  const TABS = {
    help: ["Help", () => [
      h("p", { text: "How much help do you want?" }),
      ...LEVELS.map((l) => h("label", { class: ["choice", "bevel-out"] }, h("input", { type: "radio", name: "lvl", checked: normaliseLevel(s().help_level) === l, onchange: () => save({ help_level: l }) }), h("b", { text: LEVEL_INFO[l][0] }), h("span", { text: LEVEL_INFO[l][1] }))),
      h("label", { style: { display: "block", marginTop: "8px" } }, h("input", { type: "checkbox", checked: s().adaptive !== false, onchange: (e) => save({ adaptive: e.target.checked }) }), " Offer me nudges and tips when I seem stuck, or when things are going very well"),
    ]],
    show: ["Show", () => [
      h("p", { text: "What should the activity list show?" }),
      h("select", { class: "input", "aria-label": "What to show", onchange: (e) => save({ show: e.target.value }) },
        [["all", "Everything"], ["hardware", "Hardware projects"], ...state.catalog.tiers.map((t) => [t.id, t.title])].map(([v, t]) => h("option", { value: v, text: t, selected: s().show === v }))),
    ]],
    text: ["Text size", () => [
      h("p", { text: "Code text size" }),
      h("select", { class: "input", "aria-label": "Code text size", onchange: (e) => { document.documentElement.style.setProperty("--code-size", `${e.target.value}px`); save({ code_size: Number(e.target.value) }); } },
        [13, 15, 18, 22, 26].map((n) => h("option", { value: n, text: `${n} px${n === 15 ? " (normal)" : ""}`, selected: (s().code_size ?? 15) === n }))),
    ]],
    work: ["My work", () => beta ? [h("p", { text: TEST_WORK_NOTE })] : [
      h("p", { text: "Your work is saved in this browser, on this computer. To take it home or use another computer, save it as a file." }),
      h("p", {}, h("button", { class: "btn", type: "button", id: "save-work", text: "Save my work", onclick: async () => { const { bytes, name } = await api.exportMyWork(); download(bytes, name); } })),
      h("p", {}, h("label", { class: "btn", style: { display: "inline-block" } }, "Open my work ", h("input", { type: "file", id: "open-work", accept: ".pipath,.zip", hidden: true, onchange: (e) => openWork(e.target) }))),
      h("p", { class: "small muted", text: "Only your first name and school are in the file." }),
    ]],
    curriculum: ["Curriculum", () => {
      const cur = state.catalog.projects.filter((p) => p.curriculum?.length);
      const detail = h("div", {});
      const show = (p) => detail.replaceChildren(h("h3", { text: p.title }), h("ul", {}, p.curriculum.map((c) => h("li", { text: c }))));
      const sel = h("select", { class: "input", "aria-label": "Activity", onchange: () => show(cur.find((p) => p.id === sel.value)) }, cur.map((p) => h("option", { value: p.id, text: p.title, selected: p.id === (projectId ?? cur[0].id) })));
      show(cur.find((p) => p.id === (projectId ?? cur[0].id)));
      return [h("p", { text: "Victorian Curriculum: Digital Technologies, Levels 9 and 10." }), sel, detail];
    }],
    about: ["About", () => [markdown("**PiPath** was developed by the Banyule Nillumbik Tech School and reviewed by teachers. It is **not hosted on AI**: every hint was written by people. Your Python runs in your browser, and your work is saved in this browser. If you join a class, your first name(s), school and work are also kept with your class for your teacher, and deleted when the class ends. It aims to open up Python to every student by adapting to what each student needs.\n\nPart pictures and the school logo belong to their owners. Python runs with Pyodide (MPL-2.0)." + (buildLabel() ? `\n\nThis is: ${buildLabel()}.` : ""))]],
  };

  async function openWork(input) {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    try {
      const prev = await api.previewImport(file);
      const add = prev.changes.filter((c) => c.action === "add");
      const rep = prev.changes.filter((c) => c.action === "replace");
      if (!prev.same_name && prev.names?.length) {
        const go = await messageBox({ instruction: `This file belongs to ${joinNames(prev.names)}.`, text: "Open it anyway?", buttons: [{ label: "Open it", value: "yes" }, { label: "Cancel", value: "no", default: true }] });
        if (go !== "yes") return;
      }
      if (!add.length && !rep.length) return void messageBox({ instruction: "Nothing new in that file.", text: "Your work here is the same or newer." });
      let replace = false;
      if (rep.length) replace = (await messageBox({ instruction: "Replace your work with the copy from the file?", text: "The file has newer copies of some activities.", buttons: [{ label: "Replace", value: "yes" }, { label: "Keep mine", value: "no", default: true }] })) === "yes";
      const done = await api.applyImport(file, replace);
      state.progress = Object.fromEntries((await api.progress()).map((p) => [p.project_id.replace(/-/g, "_"), p.data]));
      await messageBox({ instruction: "Your work is open.", text: `${done.added} added, ${done.replaced} replaced.` });
      onChanged();
    } catch (e) {
      messageBox({ instruction: "That file can't be opened.", text: e.message });
    }
  }

  function draw() {
    tabsEl.replaceChildren(...Object.entries(TABS).map(([id, [label]]) => h("button", { class: "tab", type: "button", role: "tab", "aria-selected": String(id === tab), text: label, onclick: () => { tab = id; draw(); } })));
    panel.replaceChildren(...TABS[tab][1]());
  }
  draw();
  return dialog({ title: "Settings", wide: true, body: h("div", {}, tabsEl, panel), buttons: [{ label: "OK", value: "ok", default: true }] }).result;
}
