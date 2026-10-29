// The activity picker: Free Play first, then every activity. Nothing is locked.
import { h, fill } from "../dom.js";
import { state } from "../state.js";
import { api } from "../api.js";
import { LEVELS, LEVEL_INFO, shown, starsFor, NOT_IN_BROWSER, normaliseLevel } from "../progress.js";

export function pickerScreen(root, { openActivity, openFree, openSettings, logOut }) {
  const settings = () => state.me.settings;
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Show" });
  const grid = h("div", { class: "grid" });
  const levelSel = h("select", { class: "input", "aria-label": "Help level", style: { width: "auto" }, onchange: async () => {
    state.me.settings = { ...settings(), help_level: levelSel.value };
    await api.saveSettings(state.me.settings);
    draw();
  } }, LEVELS.map((l) => h("option", { value: l, text: LEVEL_INFO[l][0], selected: l === normaliseLevel(settings().help_level) })));

  const filters = [["all", "All activities"], ["hardware", "Hardware"], ...state.catalog.tiers.map((t) => [t.id, t.title])];
  function draw() {
    const show = settings().show ?? "all";
    chips.replaceChildren(...filters.map(([id, label]) => h("button", { class: ["btn chip", id === show && "on"], type: "button", "aria-pressed": String(id === show), text: label, onclick: async () => {
      state.me.settings = { ...settings(), show: id };
      api.saveSettings(state.me.settings).catch(() => {});
      draw();
    } })));
    const done = new Set(Object.entries(state.progress).filter(([, p]) => p.status === "complete").map(([id]) => id));
    const cards = [h("button", { class: "card win free", type: "button", id: "free-play", onclick: openFree },
      h("div", { class: "stripe" }), h("div", { class: "inner" }, h("h3", { text: state.config.free_play_name ?? "Free Play" }), h("div", { text: "Build anything you like! Or pick one of these activities for step-by-step help." }), h("div", { class: "small muted", text: "Always open." })))];
    for (const p of state.catalog.projects) {
      if (!shown(p, show)) continue;
      const lp = state.progress[p.id];
      const tier = state.catalog.tiers.find((t) => t.id === p.tier);
      const blocked = NOT_IN_BROWSER[p.id];
      const tips = (p.try_first ?? []).filter((id) => !done.has(id)).map((id) => state.catalog.projects.find((x) => x.id === id)?.title).filter(Boolean);
      cards.push(h("button", { class: "card win", type: "button", disabled: Boolean(blocked), "data-id": p.id, onclick: () => openActivity(p.id) },
        h("div", { class: ["stripe", `tier-${p.tier}`] }),
        h("div", { class: "inner" },
          h("div", {}, h("span", { class: ["badge", `tier-${p.tier}`], text: tier?.title ?? p.tier }), p.gpio ? h("span", { class: "small muted", text: "needs a GPIO kit (or the Simulator)" }) : null),
          h("h3", { text: p.title }), h("div", { text: p.subtitle }),
          h("div", { class: "small muted", text: `${p.minutes} minutes · ${(p.concepts ?? []).slice(0, 3).join(", ")}` }),
          blocked ? h("div", { class: "small note", text: blocked }) : null,
          !blocked && tips.length && !lp ? h("div", { class: "small", text: `Good to try first: ${tips.join(", ")}` }) : null,
          lp?.status === "complete" ? h("div", { class: "stars", "aria-label": "Stars", text: "★".repeat(starsFor(lp.hints_used ?? 0, state.config)) + "☆".repeat(3 - starsFor(lp.hints_used ?? 0, state.config)) })
            : lp ? h("div", { class: "small", text: `In progress: step ${(lp.step ?? 0) + 1}` }) : null)));
    }
    fill(grid, ...cards);
  }
  draw();
  fill(root, h("div", { class: "win", style: { flex: "1", margin: "0" } },
    h("div", { class: "bar" }, h("img", { src: "../img/bnts-mark.svg", alt: "", width: 24, height: 24 }), h("b", { text: `PiPath: hi ${state.me.student.names.join(" and ")}!` }), h("span", { class: "spacer" }),
      h("label", { class: "small" }, "Help: ", levelSel),
      h("button", { class: "btn", type: "button", text: "Settings", onclick: openSettings }), h("button", { class: "btn", type: "button", id: "logout", text: "Log out", onclick: logOut })),
    chips,
    h("main", { class: "picker", id: "main" }, h("div", { class: "picker-win" }, grid)),
    h("div", { class: "statusbar" }, h("span", { text: `Help: ${LEVEL_INFO[normaliseLevel(settings().help_level)][0]}` }), h("span", { style: { flex: "1" } }), h("a", { href: "remote/", text: "Link to a Raspberry Pi (beta)" }))));
}
