// ArduinoPath's web app: starts up, then shows the right screen for the
// address (#/projects, #/project/<id>, #/freeplay, #/wipe...).

import { api, onLoggedOut, storageIsTemporary } from "./api.js";
import { takePiFromUrl } from "/shared/thispi.js";

takePiFromUrl(); // opened from a Raspberry Pi's own shortcut
import { h, clear, loadSprites } from "./dom.js";
import { state } from "./state.js";
import { messageBox } from "./widgets/window.js";
import { loginScreen } from "./screens/login.js";
import { wipeScreen } from "./screens/wipe.js";
import { setupScreen } from "./screens/setup.js";
import { pickerScreen } from "./screens/picker.js";
import { workspaceScreen } from "./screens/workspace.js";
import { openSettings } from "./dialogs/settings.js";

const root = document.getElementById("app");
let cleanup = null;
let routing = Promise.resolve();

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

async function leaveScreen() {
  const fn = cleanup;
  cleanup = null;
  if (fn) {
    try {
      await fn();
    } catch {
      // Leaving must never get stuck.
    }
  }
}

function route() {
  routing = routing.then(async () => {
    await leaveScreen();
    const hash = location.hash || "#/";
    if (hash === "#/wipe") {
      wipeScreen(root, {
        onDone: () => { state.me = null; go("#/"); },
        onCancel: () => history.back(),
      });
      return;
    }
    if (!state.me) {
      // (a link to a project, such as work the teacher set: open it once the student has picked their name)
      if (hash !== "#/") { try { sessionStorage.setItem("circuitpathways.after", hash); } catch { /* fine */ } }
      if (hash !== "#/") history.replaceState(null, "", "#/");
      loginScreen(root, { onLoggedIn, openWipe: () => go("#/wipe") });
      return;
    }
    if (!state.me.settings.help_level && hash !== "#/setup") {
      go("#/setup");
      return;
    }
    const [, page, id] = hash.split("/");
    switch (page) {
      case "setup":
        setupScreen(root, { onDone: () => go(afterLogin()) });
        break;
      case "project":
      case "freeplay":
        cleanup = workspaceScreen(root, {
          projectId: page === "freeplay" ? "freeplay" : decodeURIComponent(id || ""),
          openSettings,
          back: () => go("#/projects"),
        });
        break;
      default:
        if (hash !== "#/projects") history.replaceState(null, "", "#/projects");
        cleanup = pickerScreen(root, {
          openSettings,
          logOut,
          openProject: (pid) => go(pid === "freeplay" ? "#/freeplay" : `#/project/${encodeURIComponent(pid)}`),
        });
    }
    document.title = "ArduinoPath";
  });
  return routing;
}

function afterLogin() {
  let hash = null;
  try { hash = sessionStorage.getItem("circuitpathways.after"); sessionStorage.removeItem("circuitpathways.after"); } catch { /* fine */ }
  return /^#\/(project\/[a-z0-9-]+|freeplay)$/.test(hash ?? "") ? hash : "#/projects";
}

function onLoggedIn(me) {
  state.me = me;
  go(me.settings.help_level ? afterLogin() : "#/setup");
}

async function logOut() {
  await leaveScreen();
  try {
    await api.logout();
  } catch {
    // Logged out on this laptop either way.
  }
  state.me = null;
  go("#/");
}

onLoggedOut(() => {
  if (!state.me) return;
  state.me = null;
  messageBox({ kind: "info", instruction: "Please log in again.", text: "You've been logged out. Your code is kept in this browser and will save after you log in." })
    .then(() => go("#/"));
});

async function start() {
  await loadSprites(["img/icons.svg"]);
  try {
    [state.info, state.catalogue] = await Promise.all([api.info(), api.catalogue()]);
  } catch (err) {
    clear(root).append(h("div", { class: "logon" },
      h("main", { class: "logon-stage" },
        h("h1", { text: "ArduinoPath can't start" }),
        h("p", { class: "logon-lead", text: err.message }),
        h("button", { class: "pill", type: "button", onclick: () => location.reload() }, "Try again"))));
    return;
  }
  try {
    state.me = await api.me();
  } catch {
    state.me = null;
  }
  window.addEventListener("hashchange", route);
  route();
  if (await storageIsTemporary()) {
    messageBox({
      kind: "info",
      instruction: "Your browser isn't keeping your work",
      text: ["This browser window can't save your work between visits (a private window does this).",
        "Use Settings > Save my work before you close it, or open Circuit Pathways in a normal window."],
    });
  }
}

start();
