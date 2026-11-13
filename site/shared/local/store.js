import { beta } from "../beta.js";
// Where a student's work is kept: in this browser (IndexedDB), on this
// computer only. Nothing here ever goes to a server. If the browser won't
// keep data (a private window, say), a temporary store is used and the
// student is told.

const DB_NAME = "circuitpathways-arduinopath";

/** In memory only: lost when the tab closes. Also used by the tests. */
export function memoryStore() {
  const students = new Map();
  const sketches = new Map();
  const progress = new Map();
  let next = 1;
  const key = (sid, pid) => `${sid}/${pid}`;
  const mine = (m, sid) => [...m.values()].filter((r) => r.student_id === sid).map((r) => structuredClone(r));
  return {
    persistent: false,
    async listStudents() { return [...students.values()].map((s) => structuredClone(s)); },
    async getStudent(id) { const s = students.get(id); return s ? structuredClone(s) : null; },
    async addStudent(rec) { const id = next++; students.set(id, { ...structuredClone(rec), id }); return id; },
    async putStudent(rec) { students.set(rec.id, structuredClone(rec)); },
    async getSketch(sid, pid) { const s = sketches.get(key(sid, pid)); return s ? structuredClone(s) : null; },
    async listSketches(sid) { return mine(sketches, sid); },
    async putSketch(rec) { sketches.set(key(rec.student_id, rec.project_id), structuredClone(rec)); },
    async listProgress(sid) { return mine(progress, sid); },
    async putProgress(rec) { progress.set(key(rec.student_id, rec.project_id), structuredClone(rec)); },
    async wipe() { students.clear(); sketches.clear(); progress.clear(); },
  };
}

const wrap = (req) => new Promise((resolve, reject) => {
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});

function idbStore(db) {
  const tx = (names, mode = "readonly") => db.transaction(names, mode);
  const done = (t) => new Promise((resolve, reject) => {
    t.oncomplete = () => resolve();
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  });
  const range = (sid) => IDBKeyRange.bound([sid, ""], [sid, "￿"]);
  return {
    persistent: true,
    listStudents: () => wrap(tx("students").objectStore("students").getAll()),
    async getStudent(id) { return (await wrap(tx("students").objectStore("students").get(id))) ?? null; },
    async addStudent(rec) {
      const { id: _drop, ...rest } = rec;
      return wrap(tx("students", "readwrite").objectStore("students").add(rest));
    },
    async putStudent(rec) { const t = tx("students", "readwrite"); t.objectStore("students").put(rec); await done(t); },
    async getSketch(sid, pid) { return (await wrap(tx("sketches").objectStore("sketches").get([sid, pid]))) ?? null; },
    listSketches: (sid) => wrap(tx("sketches").objectStore("sketches").getAll(range(sid))),
    async putSketch(rec) { const t = tx("sketches", "readwrite"); t.objectStore("sketches").put(rec); await done(t); },
    listProgress: (sid) => wrap(tx("progress").objectStore("progress").getAll(range(sid))),
    async putProgress(rec) { const t = tx("progress", "readwrite"); t.objectStore("progress").put(rec); await done(t); },
    async wipe() {
      const t = tx(["students", "sketches", "progress"], "readwrite");
      for (const n of ["students", "sketches", "progress"]) t.objectStore(n).clear();
      await done(t);
    },
  };
}

/** Opens the browser's store, or a temporary one if the browser won't keep data. */
export async function openStore(dbName = DB_NAME) {
  if (beta) return memoryStore(); // the TEST version saves nothing
  try {
    if (typeof indexedDB === "undefined") return memoryStore();
    const db = await new Promise((resolve, reject) => {
      const req = indexedDB.open(dbName, 1);
      req.onupgradeneeded = () => {
        const d = req.result;
        d.createObjectStore("students", { keyPath: "id", autoIncrement: true });
        d.createObjectStore("sketches", { keyPath: ["student_id", "project_id"] });
        d.createObjectStore("progress", { keyPath: ["student_id", "project_id"] });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
      req.onblocked = () => reject(new Error("blocked"));
    });
    // Ask the browser not to clear this when it is short of space.
    try { await navigator.storage?.persist?.(); } catch { /* not allowed: fine */ }
    // A private window can open the database but fail on the first write.
    const store = idbStore(db);
    await store.getStudent(-1);
    return store;
  } catch {
    return memoryStore();
  }
}
