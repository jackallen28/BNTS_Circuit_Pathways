// What the app asks for. Profiles, settings, progress and sketches are kept
// in this browser (./local); only the catalogue (the projects and boards)
// is loaded from the website, and only /api/compile talks to the server,
// to turn a sketch into a program for the board. The server keeps nothing.

import { createLocalApi, tabSession, LocalError } from "./local/localapi.js";
import { openStore } from "./local/store.js";
import { getAccess, postJSON } from "/shared/access.js";

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || "Something went wrong. Try again.");
    this.status = status;
    this.code = body?.error || "unknown";
    this.retryAfter = body?.retry_after || 0;
  }

  /** True when the website couldn't be reached. */
  get offline() {
    return this.status === 0;
  }
}

const listeners = new Set();

/** Called with no arguments when the student is logged out. */
export function onLoggedOut(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

async function getJSON(path) {
  let res;
  try {
    res = await fetch(path, { credentials: "omit" });
  } catch {
    throw new ApiError(0, { error: "offline", message: "Circuit Pathways can't be reached. Check your internet connection and try again." });
  }
  if (!res.ok) throw new ApiError(res.status, { error: "not_found", message: "That isn't here." });
  return res.json();
}

let cataloguePromise;
const catalogue = () => (cataloguePromise ??= getJSON("data/catalogue.json").catch((e) => { cataloguePromise = null; throw e; }));

const storePromise = openStore();
let localPromise;
const local = () => (localPromise ??= storePromise.then((store) => createLocalApi({ store, catalogue, session: tabSession(), version: "web" })));

/** True if this browser won't keep the student's work between visits (a private window, say). */
export async function storageIsTemporary() {
  return !(await storePromise).persistent;
}

async function call(name, ...args) {
  try {
    return await (await local())[name](...args);
  } catch (err) {
    if (err instanceof LocalError) {
      const e = new ApiError(err.status, { error: err.code, message: err.message });
      if (err.code === "logged_out") listeners.forEach((fn) => fn());
      throw e;
    }
    throw err;
  }
}

/** Compiles a sketch on the server for the chosen board. Needs a class code. */
async function compile(code, board, variant) {
  const access = getAccess();
  if (!access) throw new ApiError(401, { error: "no_class", message: "Join a class with your class code to upload to a board." });
  try {
    return await postJSON("/api/compile", { code, board, variant: variant || "" }, { "X-Access": access.value });
  } catch (err) {
    if (err.status === undefined) throw new ApiError(0, { error: "offline", message: "Circuit Pathways can't be reached. Check your internet connection and try again." });
    throw new ApiError(err.status, { error: err.code, message: err.message });
  }
}

export const api = {
  info: () => call("info"),
  catalogue,
  project: (id) => getJSON(`data/projects/${encodeURIComponent(id)}.json`),
  ping: () => call("ping"),
  students: () => call("students"),
  createStudent: (profile) => call("createStudent", profile),
  login: (studentId) => call("login", studentId),
  wipe: () => call("wipe"),
  exportEveryone: () => call("exportEveryone"),
  compile,
  logout: () => call("logout"),
  me: () => call("me"),
  saveSettings: (settings) => call("saveSettings", settings),
  progress: () => call("progress"),
  saveProgress: (project, data) => call("saveProgress", project, data),
  sketch: (project) => call("sketch", project),
  saveSketch: (project, code) => call("saveSketch", project, code),
  previewImport: (file) => call("previewImport", file),
  applyImport: (file, replace) => call("applyImport", file, replace),
  exportMyWork: () => call("exportMyWork"),
};
