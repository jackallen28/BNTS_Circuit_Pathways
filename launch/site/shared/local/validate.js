// What a name, a school, settings and saved work may look like. The same
// rules the desktop app's server used, so save files move between them.

export const MAX_NAMES = 4;
export const MAX_NAME = 30;
export const MAX_SCHOOL = 60;
export const MAX_SKETCH_BYTES = 100 << 10;
export const MAX_PROGRESS_BYTES = 64 << 10;

const HELP_LEVELS = ["beginner", "moderate", "advanced"];
const CODING = ["text", "blocks"];

export class ValidationError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const letter = /\p{L}/u;
const mark = /\p{Mn}/u;

/** One first name, tidied; "" if it isn't valid. */
export function cleanName(s) {
  s = String(s ?? "").trim().split(/\s+/).filter(Boolean).join(" ");
  const chars = [...s];
  if (chars.length === 0 || chars.length > MAX_NAME) return "";
  let letters = 0;
  for (const ch of chars) {
    if (letter.test(ch)) letters++;
    else if (mark.test(ch) || " -'’.".includes(ch)) continue;
    else return "";
  }
  if (!letters) return "";
  if (s === s.toLowerCase()) s = s.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
  return s;
}

export function cleanNames(names) {
  if (!Array.isArray(names) || names.length === 0 || names.length > MAX_NAMES) throw new ValidationError("bad_names", "Type 1 to 4 first names.");
  const out = [];
  for (const n of names) {
    const c = cleanName(n);
    if (!c) throw new ValidationError("bad_names", "First names can only have letters, spaces, dashes and apostrophes (up to 30 letters).");
    if (out.some((p) => p.toLowerCase() === c.toLowerCase())) throw new ValidationError("bad_names", "Each name only needs to be typed once.");
    out.push(c);
  }
  return out;
}

export function cleanSchool(s) {
  s = String(s ?? "").trim().split(/\s+/).filter(Boolean).join(" ");
  const chars = [...s];
  if (chars.length === 0 || chars.length > MAX_SCHOOL) throw new ValidationError("bad_school", "Type your school's name (up to 60 letters).");
  for (const ch of chars) {
    if (!(letter.test(ch) || /\p{Nd}/u.test(ch) || mark.test(ch) || " -'’.,&()/".includes(ch))) {
      throw new ValidationError("bad_school", "A school name can only have letters, numbers, spaces and simple punctuation.");
    }
  }
  return s;
}

/** Spots two profiles with the same names at the same school. Name order doesn't matter. */
export function nameKey(names, school) {
  const low = names.map((n) => n.trim().split(/\s+/).join(" ").toLowerCase()).sort();
  return `${low.join("|")}@${String(school).trim().split(/\s+/).join(" ").toLowerCase()}`;
}

export function joinNames(names) {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

const projectRe = /^[a-z0-9][a-z0-9-]{0,63}$/;
export const validProjectId = (id) => typeof id === "string" && projectRe.test(id);
export const validSketch = (code) => typeof code === "string" && new TextEncoder().encode(code).length <= MAX_SKETCH_BYTES;
export function validProgress(data) {
  if (data === null || typeof data !== "object" || Array.isArray(data)) return false;
  return new TextEncoder().encode(JSON.stringify(data)).length <= MAX_PROGRESS_BYTES;
}

export function defaultBoard(catalogue) {
  const boards = catalogue.boards;
  return (boards.find((b) => b.default) ?? [...boards].sort((a, b) => (a.order ?? 99) - (b.order ?? 99))[0]).id;
}

export function defaultSettings(catalogue) {
  return { help_level: "", board: defaultBoard(catalogue), nudges: true };
}

export function checkSettings(st, catalogue) {
  if (st === null || typeof st !== "object") throw new ValidationError("bad_settings", "Those settings couldn't be saved.");
  if (st.help_level && !HELP_LEVELS.includes(st.help_level)) throw new ValidationError("bad_settings", "Pick Beginner, Moderate or Advanced.");
  if (st.coding && !CODING.includes(st.coding)) throw new ValidationError("bad_settings", "Pick Text or Blocks.");
  const b = catalogue.boards.find((x) => x.id === st.board);
  if (!b) throw new ValidationError("bad_settings", "Pick one of the boards on the list.");
  if (st.board_variant && !(b.variants ?? []).some((v) => v.id === st.board_variant)) {
    throw new ValidationError("bad_settings", "That board setting doesn't match the board.");
  }
}

/** Reads saved settings leniently: anything that no longer fits falls back to its default. */
export function storedSettings(saved, catalogue) {
  const st = { ...defaultSettings(catalogue), ...(saved && typeof saved === "object" ? saved : {}) };
  if (st.help_level && !HELP_LEVELS.includes(st.help_level)) st.help_level = "";
  if (st.coding && !CODING.includes(st.coding)) st.coding = "";
  if (!catalogue.boards.some((b) => b.id === st.board)) {
    st.board = defaultBoard(catalogue);
    st.board_variant = "";
  }
  try {
    checkSettings(st, catalogue);
  } catch {
    st.board_variant = "";
  }
  return st;
}
