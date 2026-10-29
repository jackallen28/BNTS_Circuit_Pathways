// PiPath in the browser: routing and start-up.
import { h, fill } from "./dom.js";
import { state } from "./state.js";
import { api, catalog, config, storageIsTemporary } from "./api.js";
import { showTestTag } from "../../shared/beta.js";
import { getAccess } from "/shared/access.js";
import { loginScreen } from "./screens/login.js";
import { setupScreen } from "./screens/setup.js";
import { pickerScreen } from "./screens/picker.js";
import { workspaceScreen } from "./screens/workspace.js";
import { openSettings } from "./dialogs/settings.js";
import { messageBox } from "./widgets/window.js";
import { warmUp } from "./runtime/shared.js";
import { lessonKey } from "./progress.js";

const root = document.getElementById("app");
let cleanup = null;

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

async function loadProgress() {
  state.progress = Object.fromEntries((await api.progress()).map((p) => [lessonKey(p.project_id), p.data]).filter(([id]) => state.catalog.projects.some((x) => x.id === id)));
}

async function logOut() {
  await api.logout().catch(() => {});
  state.me = null;
  go("#/");
}

async function route() {
  cleanup?.();
  cleanup = null;
  const hash = location.hash || "#/";
  if (!state.me && hash !== "#/") return go("#/");
  document.documentElement.style.setProperty("--code-size", `${state.me?.settings?.code_size ?? 15}px`);
  if (!state.me) {
    return loginScreen(root, {
      onLoggedIn: async (me) => { state.me = me; await loadProgress(); go(me.settings.help_level ? "#/activities" : "#/setup"); },
      onCreated: (me) => { state.me = me; state.progress = {}; go("#/setup"); },
    });
  }
  if (hash === "#/setup") return setupScreen(root, { onDone: () => go("#/activities") });
  const common = {
    openSettings: (opts) => openSettings({ ...opts, onChanged: () => {} }),
    logOut,
    onHome: () => { loadProgress().finally(() => go("#/activities")); },
  };
  if (hash === "#/free") {
    cleanup = await workspaceScreen(root, { lessonId: null, ...common });
    return;
  }
  const m = /^#\/activity\/([a-z0-9_]+)$/.exec(hash);
  if (m && state.catalog.projects.some((p) => p.id === m[1])) {
    const id = m[1];
    cleanup = await workspaceScreen(root, {
      lessonId: id, ...common,
      openSettings: () => openSettings({ startTab: "help", projectId: id }),
      nextActivity: (open) => {
        const i = state.catalog.projects.findIndex((p) => p.id === id);
        const next = state.catalog.projects.slice(i + 1).find((p) => p.status === "ready");
        if (open && next) loadProgress().finally(() => go(`#/activity/${next.id}`));
        return next;
      },
    });
    return;
  }
  warmUp();
  pickerScreen(root, {
    openActivity: (id) => go(`#/activity/${id}`),
    openFree: () => go("#/free"),
    openSettings: () => openSettings({ onChanged: route }),
    logOut,
  });
  document.title = "PiPath";
}

async function start() {
  showTestTag();
  if (!getAccess()) { location.replace("/?need=class"); return; }
  try {
    [state.catalog, state.config] = await Promise.all([catalog(), config()]);
  } catch (err) {
    fill(root, h("main", { class: "desktop" }, h("div", { class: "note error", text: `PiPath can't start: ${err.message}` })));
    return;
  }
  try {
    state.me = await api.me();
    await loadProgress();
  } catch { state.me = null; }
  window.addEventListener("hashchange", route);
  route();
  if (await storageIsTemporary()) {
    messageBox({ instruction: "Your browser isn't keeping your work", text: ["This browser window can't save your work between visits (a private window does this).", "Use Settings > My work > Save my work before you close it, or open Circuit Pathways in a normal window."] });
  }
}

start();
