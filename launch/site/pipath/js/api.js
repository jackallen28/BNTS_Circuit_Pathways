// PiPath's storage and data. A student's profile, code and progress are kept in this browser
// (the same code ArduinoPath uses); the lessons come from the website as JSON.

import { createLocalApi, tabSession, LocalError } from "/shared/local/localapi.js";
import { openStore } from "/shared/local/store.js";
import { ValidationError } from "/shared/local/validate.js";
import { LEVELS, projectKey } from "./progress.js";

export { LocalError };

const BASE = "/pipath/";

async function getJSON(path) {
  const res = await fetch(BASE + path, { credentials: "omit" });
  if (!res.ok) throw new Error(`Couldn't load ${path} (${res.status})`);
  return res.json();
}

let catalogPromise;
export const catalog = () => (catalogPromise ??= getJSON("data/catalog.json"));
export const config = () => getJSON("data/config.json");
export const errorsJson = () => fetch(BASE + "data/errors.json").then((r) => r.text());
export const freeplay = () => getJSON("data/freeplay.json");
const lessons = new Map();
export async function lesson(id) {
  if (!lessons.has(id)) lessons.set(id, getJSON(`data/lessons/${id}.json`));
  return lessons.get(id);
}

/** Demo files a lesson copies next to the student's program (see a lesson's `files`). */
export async function demoFileBytes(rel) {
  const res = await fetch(`${BASE}data/demo_files/${rel}`);
  return res.ok ? new Uint8Array(await res.arrayBuffer()) : null;
}

// ---- settings
const DEFAULTS = () => ({ help_level: "", show: "all", adaptive: true, free_play_mode: "guide", tour_done: false, code_size: 15, camera_object: "face", adapt: { history: [], cooldown: 0 } });

const policy = {
  defaults: () => DEFAULTS(),
  check(st, cat) {
    const bad = (m) => { throw new ValidationError("bad_settings", m); };
    if (!st || typeof st !== "object") bad("Those settings couldn't be saved.");
    if (st.help_level && !LEVELS.includes(st.help_level)) bad("Pick Beginner, Moderate or Advanced.");
    const shows = ["all", "hardware", ...cat.tiers.map((t) => t.id)];
    if (st.show && !shows.includes(st.show)) bad("Pick something from the list to show.");
    if (!Number.isInteger(st.code_size) || st.code_size < 11 || st.code_size > 30) bad("Pick a text size from the list.");
    if (JSON.stringify(st.adapt ?? {}).length > 4000) bad("Those settings are too big.");
  },
  stored(saved, cat) {
    const st = { ...DEFAULTS(), ...(saved && typeof saved === "object" ? saved : {}) };
    try { policy.check(st, cat); } catch {
      const d = DEFAULTS();
      if (!LEVELS.includes(st.help_level)) st.help_level = "";
      if (![...cat.tiers.map((t) => t.id), "all", "hardware"].includes(st.show)) st.show = "all";
      if (!Number.isInteger(st.code_size) || st.code_size < 11 || st.code_size > 30) st.code_size = d.code_size;
      st.adapt = d.adapt;
    }
    return st;
  },
};

const storePromise = openStore("circuitpathways-pipath");
const localPromise = storePromise.then((store) => createLocalApi({
  store, catalogue: catalog, session: tabSession("circuitpathways.pi.student"), version: "web",
  app: { name: "PiPath", format: "pipath-save", ext: "pipath", school: "Banyule Nillumbik Tech School", oldFormats: [] },
  settings: policy,
}));

export async function storageIsTemporary() {
  return !(await storePromise).persistent;
}

/** Calls the in-browser "server". Errors have .code and .message a student can read. */
export async function call(name, ...args) {
  return (await localPromise)[name](...args);
}

export const api = {
  students: () => call("students"),
  createStudent: (p) => call("createStudent", p),
  login: (id) => call("login", id),
  logout: () => call("logout"),
  me: () => call("me"),
  saveSettings: (s) => call("saveSettings", s),
  progress: () => call("progress"),
  saveProgress: (lessonId, data) => call("saveProgress", projectKey(lessonId), data),
  code: async (key) => { try { return (await call("sketch", key)).code; } catch (e) { if (e.status === 404) return null; throw e; } },
  saveCode: (key, code) => call("saveSketch", key, code),
  exportMyWork: () => call("exportMyWork"),
  exportEveryone: () => call("exportEveryone"),
  previewImport: (f) => call("previewImport", f),
  applyImport: (f, replace) => call("applyImport", f, replace),
  wipe: () => call("wipe"),
};

let demoManifest;
/** The files for a lesson's `files` list ("p3/party" copies the whole folder), as { "party/1.wav": bytes }. */
export async function demoFilesFor(rels) {
  demoManifest ??= getJSON("data/demo_files/manifest.json");
  const all = (await demoManifest).files;
  const out = {};
  for (const rel of rels ?? []) {
    const base = rel.split("/").pop();
    const prefix = rel.endsWith("/") ? rel : rel + "/";
    for (const f of all.filter((x) => x === rel || x.startsWith(prefix))) {
      const bytes = await demoFileBytes(f);
      if (bytes) out[f === rel ? base : `${base}/${f.slice(prefix.length)}`] = bytes;
    }
  }
  return out;
}
