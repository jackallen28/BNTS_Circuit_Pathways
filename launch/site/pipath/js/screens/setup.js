// Step 2 of the welcome: how much help do you want?
import { h, fill } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";
import { LEVELS, LEVEL_INFO } from "../progress.js";

export function setupScreen(root, { onDone }) {
  const names = state.me.student.names;
  let level = state.me.settings.help_level || "beginner";
  let show = state.me.settings.show || "all";
  const levelBox = h("div", {});
  const draw = () => levelBox.replaceChildren(...LEVELS.map((l) => h("label", { class: ["choice", "bevel-out", l === level && "picked"] },
    h("input", { type: "radio", name: "level", value: l, checked: l === level, onchange: () => { level = l; draw(); } }),
    h("b", { text: LEVEL_INFO[l][0] }), h("span", { text: LEVEL_INFO[l][1] }))));
  draw();
  const showSel = h("select", { class: "input", id: "show", "aria-label": "What to show", onchange: () => { show = showSel.value; } },
    [["all", "Everything"], ["hardware", "Hardware projects (GPIO and camera)"], ...state.catalog.tiers.map((t) => [t.id, `${t.title}: ${t.tagline}`])].map(([v, t]) => h("option", { value: v, text: t, selected: v === show })));
  fill(root, h("main", { class: "desktop", id: "main" },
    h("div", { class: "brand" }, h("img", { src: "../img/bnts-mark.svg", alt: "" }), h("div", {}, h("h1", { text: "PiPath" }))),
    h("div", { class: "win dialog", style: { width: "min(640px, 100%)" } },
      h("div", { class: "titlebar" }, h("span", { class: "logo" }), h("span", { class: "title", text: "Let's get you set up" })),
      h("div", { class: "win-body" },
        h("p", {}, h("b", { text: `Nice to meet you, ${names.join(" and ")}!` })),
        h("p", { text: "How much help do you want? You can change this any time in Settings." }),
        levelBox,
        h("div", { class: "field" }, h("label", { for: "show", text: "What should the activity list show?" }), showSel),
        h("div", { class: "dlg-buttons" }, h("button", { class: "btn default", type: "button", id: "go", text: "Let's go!", onclick: async () => {
          state.me.settings = { ...state.me.settings, help_level: level, show };
          await api.saveSettings(state.me.settings);
          onDone();
        } }))))));
}
