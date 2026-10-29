// .circuit save files: a zip of one profile's settings, progress and
// sketches. The same format the desktop app uses (version 1), so files move
// between them. Never break it: bump the version and keep reading old ones.
//
//   manifest.json   {"format": "arduinopath-save", "version": 1, ...}
//   profile.json    names, school, settings
//   progress.json   [{project_id, data, updated_at}]
//   sketches.json   [{project_id, updated_at}]
//   sketches/<id>.ino

import { writeZip, readZip, ZipError } from "./zip.js";
import { validProjectId, validProgress, validSketch } from "./validate.js";

export const FORMAT = "arduinopath-save"; // ArduinoPath's; PiPath passes its own ("pipath-save")
export const OLD_FORMAT = "circuit" + "path-save";
export const VERSION = 1;
export const MAX_FILE_BYTES = 8 << 20;

export class SaveFileError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const dec = new TextDecoder();

/** @returns {Uint8Array} */
export function writeSaveFile({ profile, sketches, progress, appVersion = "web", format = FORMAT }, now = Date.now()) {
  const files = [
    { name: "manifest.json", data: JSON.stringify({ format, version: VERSION, exported_at: now, app_version: appVersion }, null, 2) + "\n" },
    { name: "profile.json", data: JSON.stringify({ names: profile.names, school: profile.school, settings: profile.settings }, null, 2) + "\n" },
    { name: "progress.json", data: JSON.stringify(progress ?? [], null, 2) + "\n" },
    { name: "sketches.json", data: JSON.stringify((sketches ?? []).map((s) => ({ project_id: s.project_id, updated_at: s.updated_at })), null, 2) + "\n" },
    ...(sketches ?? []).map((s) => ({ name: `sketches/${s.project_id}.ino`, data: s.code })),
  ];
  return writeZip(files, now);
}

const notSaveFile = (what = "ArduinoPath") => new SaveFileError("not_save_file", `This file can't be opened. Pick a save file made by ${what}.`);

/** Reads and checks a save file. */
export async function readSaveFile(bytes, now = Date.now(), { formats = [FORMAT, OLD_FORMAT], what = "ArduinoPath" } = {}) {
  const notSave = () => notSaveFile(what);
  if (bytes.length > MAX_FILE_BYTES) throw new SaveFileError("too_big", `That file is too big to be a ${what} save file.`);
  let entries;
  try {
    entries = await readZip(bytes);
  } catch (err) {
    if (err instanceof ZipError) throw notSave();
    throw err;
  }
  const json = (name) => {
    const b = entries.get(name);
    if (!b) return undefined;
    try {
      return JSON.parse(dec.decode(b));
    } catch {
      throw notSave();
    }
  };
  const manifest = json("manifest.json");
  if (!manifest || !formats.includes(manifest.format)) throw notSave();
  if (manifest.version > VERSION) throw new SaveFileError("newer_version", `This file was saved by a newer ${what}. Ask your teacher to update this one.`);
  if (!(manifest.version >= 1)) throw notSave();
  const profile = json("profile.json") ?? {};
  const progress = json("progress.json") ?? [];
  const meta = json("sketches.json") ?? [];
  if (!Array.isArray(progress) || !Array.isArray(meta)) throw notSave();
  const seen = new Set();
  const outProgress = [];
  for (const p of progress) {
    if (!p || !validProjectId(p.project_id) || !validProgress(p.data) || seen.has(p.project_id)) throw notSave();
    seen.add(p.project_id);
    outProgress.push({ project_id: p.project_id, data: p.data, updated_at: clampTime(p.updated_at, now) });
  }
  seen.clear();
  const sketches = [];
  for (const m of meta) {
    const code = entries.get(`sketches/${m?.project_id}.ino`);
    if (!m || !validProjectId(m.project_id) || !code || seen.has(m.project_id)) throw notSave();
    const text = dec.decode(code);
    if (!validSketch(text)) throw notSave();
    seen.add(m.project_id);
    sketches.push({ project_id: m.project_id, code: text, updated_at: clampTime(m.updated_at, now) });
  }
  return {
    manifest,
    profile: { names: Array.isArray(profile.names) ? profile.names.map(String) : [], school: String(profile.school ?? ""), settings: profile.settings },
    sketches,
    progress: outProgress,
  };
}

// A time can't be in the future, or this copy would beat every later save.
const clampTime = (t, now) => Math.min(Math.max(Number(t) || 0, 0), now);

/** Says what opening a file would do to each project: add, replace (file is newer) or keep. */
export function planImport(file, sketches, progress) {
  const have = new Map();
  for (const s of sketches) have.set(s.project_id, Math.max(have.get(s.project_id) ?? 0, s.updated_at));
  for (const p of progress) have.set(p.project_id, Math.max(have.get(p.project_id) ?? 0, p.updated_at));
  const inFile = new Map();
  for (const s of file.sketches) inFile.set(s.project_id, Math.max(inFile.get(s.project_id) ?? 0, s.updated_at));
  for (const p of file.progress) inFile.set(p.project_id, Math.max(inFile.get(p.project_id) ?? 0, p.updated_at));
  return [...inFile].map(([project_id, file_updated]) => {
    if (!have.has(project_id)) return { project_id, action: "add", file_updated };
    const server_updated = have.get(project_id);
    return { project_id, action: file_updated > server_updated ? "replace" : "keep", file_updated, server_updated };
  });
}

export function saveFileName(names, now = new Date(), app = "ArduinoPath", ext = "circuit") {
  const date = now.toISOString().slice(0, 10);
  const ascii = names.join("-").replace(/[^A-Za-z0-9-]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "") || "My";
  return `${ascii}_${app}_${date}.${ext}`;
}
