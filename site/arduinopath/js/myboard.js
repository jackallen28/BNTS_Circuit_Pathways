// "My ESP board": the student's own ESP board and its own WiFi.
//
// The teacher sets up each of the school's ESP boards once (the teacher portal flashes it): a label such as
// ESP-07, its own WiFi name and password, and a code on its sticker. A student in a class claims their board with
// that code. From then on:
//  - their WiFi projects use that board's WiFi name and password (the #define MY_WIFI_NAME / MY_WIFI_PASSWORD lines
//    at the top of their code are filled in, and a hotspot with any other name is changed to the board's), so every
//    board's WiFi is different and only its student knows the password;
//  - Upload only flashes that board: the uploader reads the chip's own MAC address and stops if it isn't theirs.
// A student without a class (or without a school board) gets a WiFi name and password of their own, made in this
// browser, so two students' boards still never share a WiFi.

import { getAccess } from "../../shared/access.js"; // (relative, so the Node tests can load it too)
import { DEFAULT_WIFI } from "./sim/pins.js";

const LOCAL_KEY = "circuitpathways.mywifi";
const CACHE_KEY = "circuitpathways.myboard";
const ALPHA = "abcdefghjkmnpqrstuvwxyz23456789";

const rand = (n, alpha = ALPHA) => [...crypto.getRandomValues(new Uint8Array(n))].map((b) => alpha[b % alpha.length]).join("");

function store() {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}

/** The WiFi this browser uses when there's no school board: made once, kept. */
export function localIdentity(ls = store()) {
  try {
    const saved = JSON.parse(ls?.getItem(LOCAL_KEY) || "null");
    if (saved && /^ArduinoPath-[a-z0-9]{4}$/.test(saved.ssid) && /^[a-z0-9]{10}$/.test(saved.password)) return { ...saved, source: "local" };
  } catch { /* made again below */ }
  const made = { ssid: `ArduinoPath-${rand(4)}`, password: rand(10) };
  try { ls?.setItem(LOCAL_KEY, JSON.stringify(made)); } catch { /* fine: a new one next time */ }
  return { ...made, source: "local" };
}

const auth = (a) => ({ Authorization: `Bearer ${a.value}` });

function fromServer(b) {
  return b ? { source: "school", label: b.label, kind: b.kind, mac: b.mac, ssid: b.ssid, password: b.password, code: b.code } : null;
}

/**
 * The student's board: their school board (asked of the server, remembered for when it can't be reached), or this
 * browser's own WiFi. Never throws.
 */
export async function myBoard({ access = getAccess(), fetchImpl = (...a) => fetch(...a), ls = store() } = {}) {
  if (access?.kind === "student") {
    try {
      const res = await fetchImpl("/api/student/board", { credentials: "omit", headers: auth(access) });
      if (res.ok) {
        const b = fromServer((await res.json()).board);
        try { b ? ls?.setItem(CACHE_KEY, JSON.stringify(b)) : ls?.removeItem(CACHE_KEY); } catch { /* fine */ }
        if (b) return b;
      } else if (res.status === 401) {
        try { ls?.removeItem(CACHE_KEY); } catch { /* fine */ }
      } else throw new Error(String(res.status));
    } catch {
      // the school server can't be reached (a student Pi offline): the board it last said
      try {
        const b = JSON.parse(ls?.getItem(CACHE_KEY) || "null");
        if (b?.source === "school") return b;
      } catch { /* none */ }
    }
  }
  return localIdentity(ls);
}

async function call(method, body, access = getAccess()) {
  const res = await fetch("/api/student/board", {
    method, credentials: "omit",
    headers: { ...auth(access), "X-Circuit-Pathways": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message ?? "That didn't work. Try again.");
  return data;
}

/** Claims the board with this code (from its sticker). */
export async function claimBoard(code) {
  const b = fromServer((await call("POST", { code })).board);
  try { store()?.setItem(CACHE_KEY, JSON.stringify(b)); } catch { /* fine */ }
  return b;
}

/** Gives the student's board back (for another student to claim). */
export async function giveBackBoard() {
  await call("DELETE");
  try { store()?.removeItem(CACHE_KEY); } catch { /* fine */ }
}

const cstr = (s) => String(s).replace(/[\\"]/g, "");

/**
 * Puts the board's own WiFi into a sketch. Returns the sketch (the same text if nothing needed changing).
 *  - #define MY_WIFI_NAME / MY_WIFI_PASSWORD lines get the board's name and password (added at the top if the code
 *    uses them without them);
 *  - with a school board, a hotspot started with any other name (WiFi.softAP("...", "...") or the Web Page Designer's
 *    WIFI_NAME / WIFI_PASSWORD) uses the board's, so it can't pretend to be someone else's.
 */
export function applyWifi(code, id) {
  if (!id || typeof code !== "string") return code;
  const name = cstr(id.ssid);
  const pass = cstr(id.password);
  let out = code;
  if (id.source === "school") {
    out = out.replace(/WiFi\.softAP\(\s*"[^"\n]*"\s*,\s*"[^"\n]*"\s*\)/g, "WiFi.softAP(MY_WIFI_NAME, MY_WIFI_PASSWORD)");
    if (/WiFi\.softAP\(\s*WIFI_NAME\s*,\s*WIFI_PASSWORD\s*\)/.test(out)) {
      out = out.replace(/^(\s*const\s+char\s*\*\s*WIFI_NAME\s*=\s*)"[^"\n]*"/m, `$1"${name}"`)
        .replace(/^(\s*const\s+char\s*\*\s*WIFI_PASSWORD\s*=\s*)"[^"\n]*"/m, `$1"${pass}"`);
    }
  }
  out = out.replace(/^(\s*#define\s+MY_WIFI_NAME\s+)"[^"\n]*"/m, `$1"${name}"`)
    .replace(/^(\s*#define\s+MY_WIFI_PASSWORD\s+)"[^"\n]*"/m, `$1"${pass}"`);
  const uses = /\bMY_WIFI_(NAME|PASSWORD)\b/.test(out.replace(/^\s*#define\s+MY_WIFI_\w+.*$/gm, ""));
  if (uses && !/^\s*#define\s+MY_WIFI_NAME\b/m.test(out)) {
    out = `#define MY_WIFI_NAME "${name}"  // your board's own WiFi\n#define MY_WIFI_PASSWORD "${pass}"\n${out}`;
  } else if (uses && !/^\s*#define\s+MY_WIFI_PASSWORD\b/m.test(out)) {
    out = out.replace(/^(\s*#define\s+MY_WIFI_NAME\b.*)$/m, `$1\n#define MY_WIFI_PASSWORD "${pass}"`);
  }
  return out;
}

/** Is this an ESP board (it has WiFi, and a MAC address the uploader can read)? */
export const isEspBoard = (board) => /^esp(8266|32):/.test(board?.fqbn ?? "");

/** The message when a student plugs in a board that isn't theirs. */
export function notYourBoard(id) {
  return `This isn't your board. Your board is ${id.label} (its WiFi is ${id.ssid}). Plug in your own board and press Upload again, or ask your teacher.`;
}

export { DEFAULT_WIFI };
