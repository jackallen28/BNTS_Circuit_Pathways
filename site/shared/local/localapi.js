// The ArduinoPath (and PiPath) "server" that lives in the browser. It answers the same
// calls the desktop app's server did (profiles, settings, progress, sketches,
// save files), keeping everything in this browser's own storage. With a class
// link (a student who joined a class on the Cloudflare site, see cloud.js), work
// is also copied to their class; otherwise nothing about a student is sent anywhere.

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
 * @param {object} [deps.cloud]  from createCloud(): syncs work to the student's class (optional)
 */
export function createLocalApi({
  store, catalogue, session, now = Date.now, version = "web",
  app = { name: "ArduinoPath", format: FORMAT, ext: "circuit", school: SCHOOL, oldFormats: [OLD_FORMAT] },
  settings: policy = { defaults: defaultSettings, check: checkSettings, stored: storedSettings },
  cloud = null,
}) {
  const cloudApp = app.name.toLowerCase();

  // ---- class sync (only with a class link) --------------------------------------------
  const sameNames = (a, b) => nameKey(a ?? [], "") === nameKey(b ?? [], "");
  const upload = (st, kind, item, body, updated_at) => {
    if (cloud && st.cloud) cloud.queue(st.cloud, { app: cloudApp, item, kind, body, updated_at });
  };
  async function uploadAll(st) {
    for (const sk of await store.listSketches(st.id)) upload(st, "sketch", sk.project_id, sk.code, sk.updated_at);
    for (const pr of await store.listProgress(st.id)) upload(st, "progress", pr.project_id, JSON.stringify(pr.data), pr.updated_at);
    upload(st, "settings", "profile", JSON.stringify(st.settings ?? {}), now());
  }
  /** Links this profile to the class joined in this browser (if the names match), and brings down newer work. */
  async function syncClass(st) {
    if (!cloud) return;
    const link = cloud.link?.();
    if (!st.cloud && link && sameNames(link.names, st.names)) {
      st.cloud = link.token;
      await store.putStudent(st);
      await uploadAll(st);
    }
    if (!st.cloud) return;
    let work;
    try {
      work = await cloud.pull(st.cloud);
    } catch {
      return; // offline: try next time
    }
    if (work === null) { // the class has ended, or they were taken off it
      st.cloud = null;
      await store.putStudent(st);
      return;
    }
    const cat = await catalogue();
    for (const w of work.filter((x) => x.app === cloudApp)) {
      try {
        if (w.kind === "sketch" && validProjectId(w.item) && validSketch(w.body)) {
          const have = await store.getSketch(st.id, w.item);
          if (!have || have.updated_at < w.updated_at) await store.putSketch({ student_id: st.id, project_id: w.item, code: w.body, updated_at: w.updated_at });
        } else if (w.kind === "progress" && validProjectId(w.item)) {
          const data = JSON.parse(w.body);
          const have = (await store.listProgress(st.id)).find((p) => p.project_id === w.item);
          if (validProgress(data) && (!have || have.updated_at < w.updated_at)) await store.putProgress({ student_id: st.id, project_id: w.item, data, updated_at: w.updated_at });
        } else if (w.kind === "settings" && w.item === "profile" && st.fresh) {
          const settings = JSON.parse(w.body);
          policy.check(settings, cat);
          st.settings = settings;
          delete st.fresh;
          await store.putStudent(st);
        }
      } catch { /* a piece that doesn't fit here is skipped */ }
    }
  }

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
      profile: { names: st.names, school: st.school, settings: st.settings, class_link: st.cloud ?? undefined },
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
      rec.fresh = true;
      await syncClass(rec);
      delete rec.fresh;
      return meOf(rec);
    },

    async login(studentId) {
      const st = await store.getStudent(studentId);
      if (!st) throw new LocalError(404, "not_found", "That profile isn't here any more. Go back and pick your name.");
      st.last_seen = now();
      await store.putStudent(st);
      session.set(st.id);
      await syncClass(st);
      return meOf(st);
    },

    async logout() { session.set(null); return null; },

    async me() {
      const st = await need();
      st.last_seen = now();
      await store.putStudent(st);
      // a student who joined a class after starting here (the Pi beta): link this profile and send up what they've done
      if (!st.cloud && cloud?.link?.()) await syncClass(st);
      return meOf(st);
    },

    async saveSettings(settings) {
      const st = await need();
      const cat = await catalogue();
      wrapValidation(() => policy.check(settings, cat));
      st.settings = settings;
      await store.putStudent(st);
      upload(st, "settings", "profile", JSON.stringify(settings), now());
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
      upload(st, "progress", project, JSON.stringify(data), updated_at);
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
      upload(st, "sketch", project, code, updated_at);
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
      // a save file from a class member carries the class link: opening it here joins this profile to the class too
      if (f.profile.class_link && !st.cloud && cloud) {
        st.cloud = f.profile.class_link;
        await store.putStudent(st);
        await syncClass(st);
        await uploadAll(st);
      } else if (st.cloud) {
        for (const s of f.sketches.filter((x) => pick.has(x.project_id))) upload(st, "sketch", s.project_id, s.code, s.updated_at);
        for (const p of f.progress.filter((x) => pick.has(x.project_id))) upload(st, "progress", p.project_id, JSON.stringify(p.data), p.updated_at);
      }
      return st.cloud ? { added, replaced, linked: true } : { added, replaced };
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
