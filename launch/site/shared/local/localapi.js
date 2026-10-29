// The ArduinoPath "server" that lives in the browser. It answers the same
// calls the desktop app's server did (profiles, settings, progress, sketches,
// save files), keeping everything in this browser's own storage. Nothing
// about a student is ever sent anywhere.

import {
  ValidationError, cleanNames, cleanSchool, nameKey, joinNames, validProjectId, validSketch, validProgress,
  defaultSettings, checkSettings, storedSettings,
} from "./validate.js";
import { writeSaveFile, readSaveFile, planImport, saveFileName, SaveFileError, FORMAT, OLD_FORMAT } from "./savefile.js";
import { writeZip } from "./zip.js";

export class LocalError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const SCHOOL = "Banyule Nillumbik Tech School";
const SESSION_KEY = "circuitpathways.ap.student";

/**
 * @param {object} deps
 * @param {object} deps.store      from openStore() / memoryStore()
 * @param {() => Promise<object>} deps.catalogue
 * @param {{get(): number|null, set(id: number|null): void}} deps.session  which profile is open in this tab
 * @param {() => number} [deps.now]
 */
export function createLocalApi({
  store, catalogue, session, now = Date.now, version = "web",
  app = { name: "ArduinoPath", format: FORMAT, ext: "circuit", school: SCHOOL, oldFormats: [OLD_FORMAT] },
  settings: policy = { defaults: defaultSettings, check: checkSettings, stored: storedSettings },
}) {
  const need = async () => {
    const id = session.get();
    const st = id != null ? await store.getStudent(id) : null;
    if (!st) {
      session.set(null);
      throw new LocalError(401, "logged_out", "Please log in again.");
    }
    return st;
  };

  const meOf = async (st) => ({ student: st, settings: policy.stored(st.settings, await catalogue()) });

  const wrapValidation = (fn) => {
    try {
      return fn();
    } catch (err) {
      if (err instanceof ValidationError) throw new LocalError(400, err.code, err.message);
      throw err;
    }
  };

  async function saveFile(st) {
    const bytes = writeSaveFile({
      profile: { names: st.names, school: st.school, settings: st.settings },
      sketches: await store.listSketches(st.id),
      progress: await store.listProgress(st.id),
      appVersion: version,
      format: app.format,
    }, now());
    return { bytes, name: saveFileName(st.names, new Date(now()), app.name, app.ext) };
  }

  const api = {
    info: async () => ({ app: app.name, version, school: app.school, data_dir: "this browser" }),
    ping: async () => null,

    students: async () => (await store.listStudents())
      .sort((a, b) => a.name_key.localeCompare(b.name_key))
      .map(({ id, names, school, last_seen }) => ({ id, names, school, last_seen })),

    async createStudent({ names, school }) {
      const clean = wrapValidation(() => cleanNames(names));
      const sch = wrapValidation(() => cleanSchool(school));
      const key = nameKey(clean, sch);
      if ((await store.listStudents()).some((s) => s.name_key === key)) {
        throw new LocalError(409, "exists", `There's already a profile for ${joinNames(clean)} from ${sch} in this browser. Is it you? Go back and pick your name.`);
      }
      const t = now();
      const rec = { names: clean, name_key: key, school: sch, settings: policy.defaults(await catalogue()), created_at: t, last_seen: t };
      rec.id = await store.addStudent(rec);
      session.set(rec.id);
      return meOf(rec);
    },

    async login(studentId) {
      const st = await store.getStudent(studentId);
      if (!st) throw new LocalError(404, "not_found", "That profile isn't here any more. Go back and pick your name.");
      st.last_seen = now();
      await store.putStudent(st);
      session.set(st.id);
      return meOf(st);
    },

    async logout() { session.set(null); return null; },

    async me() {
      const st = await need();
      st.last_seen = now();
      await store.putStudent(st);
      return meOf(st);
    },

    async saveSettings(settings) {
      const st = await need();
      const cat = await catalogue();
      wrapValidation(() => policy.check(settings, cat));
      st.settings = settings;
      await store.putStudent(st);
      return settings;
    },

    async progress() {
      const st = await need();
      return (await store.listProgress(st.id)).sort((a, b) => a.project_id.localeCompare(b.project_id))
        .map(({ project_id, data, updated_at }) => ({ project_id, data, updated_at }));
    },

    async saveProgress(project, data) {
      const st = await need();
      if (!validProjectId(project)) throw new LocalError(400, "bad_project", "That isn't a project name.");
      if (!validProgress(data)) throw new LocalError(400, "bad_progress", "That progress couldn't be saved.");
      const updated_at = now();
      await store.putProgress({ student_id: st.id, project_id: project, data, updated_at });
      return { updated_at };
    },

    async sketch(project) {
      const st = await need();
      if (!validProjectId(project)) throw new LocalError(400, "bad_project", "That isn't a project name.");
      const sk = await store.getSketch(st.id, project);
      if (!sk) throw new LocalError(404, "not_found", "No code saved yet.");
      return { project_id: project, code: sk.code, updated_at: sk.updated_at };
    },

    async saveSketch(project, code) {
      const st = await need();
      if (!validProjectId(project)) throw new LocalError(400, "bad_project", "That isn't a project name.");
      if (!validSketch(code)) throw new LocalError(413, "too_big", "This sketch is too long to save (the limit is 100 KB).");
      const updated_at = now();
      await store.putSketch({ student_id: st.id, project_id: project, code, updated_at });
      return { updated_at };
    },

    /** Save my work: { blob, name } for a .circuit file. */
    async exportMyWork() {
      const { bytes, name } = await saveFile(await need());
      return { bytes, name };
    },

    /** The WIPE page: one zip of everyone's .circuit files. */
    async exportEveryone() {
      const used = new Map();
      const files = [];
      for (const st of await store.listStudents()) {
        const { bytes, name } = await saveFile(st);
        const n = (used.get(name.toLowerCase()) ?? 0) + 1;
        used.set(name.toLowerCase(), n);
        files.push({ name: n > 1 ? name.replace(new RegExp(`\\.${app.ext}$`), `_${n}.${app.ext}`) : name, data: bytes });
      }
      return { bytes: writeZip(files, now()), name: `Everyone_${app.name}_${new Date(now()).toISOString().slice(0, 10)}.zip` };
    },

    async previewImport(file) {
      const st = await need();
      const f = await readFile(file);
      const changes = planImport(f, await store.listSketches(st.id), await store.listProgress(st.id));
      return {
        names: f.profile.names, school: f.profile.school,
        same_name: nameKey(f.profile.names, "") === nameKey(st.names, ""),
        changes,
      };
    },

    async applyImport(file, replace) {
      const st = await need();
      const f = await readFile(file);
      const changes = planImport(f, await store.listSketches(st.id), await store.listProgress(st.id));
      const pick = new Set();
      let added = 0;
      let replaced = 0;
      for (const c of changes) {
        if (c.action === "add") { pick.add(c.project_id); added++; }
        else if (c.action === "replace" && replace) { pick.add(c.project_id); replaced++; }
      }
      for (const s of f.sketches.filter((x) => pick.has(x.project_id))) await store.putSketch({ student_id: st.id, ...s });
      for (const p of f.progress.filter((x) => pick.has(x.project_id))) await store.putProgress({ student_id: st.id, ...p });
      return { added, replaced };
    },

    async wipe() {
      await store.wipe();
      session.set(null);
      return null;
    },
  };

  async function readFile(file) {
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      return await readSaveFile(bytes, now(), { formats: [app.format, ...(app.oldFormats ?? [])], what: app.name });
    } catch (err) {
      if (err instanceof SaveFileError) throw new LocalError(400, err.code, err.message);
      throw err;
    }
  }

  return api;
}

/** The profile open in this tab: it survives a reload but not closing the tab. */
export function tabSession(key = SESSION_KEY) {
  return {
    get() {
      try {
        const v = sessionStorage.getItem(key);
        return v ? Number(v) : null;
      } catch { return null; }
    },
    set(id) {
      try {
        if (id == null) sessionStorage.removeItem(key);
        else sessionStorage.setItem(key, String(id));
      } catch { /* storage blocked: stays logged in until reload */ }
    },
  };
}
