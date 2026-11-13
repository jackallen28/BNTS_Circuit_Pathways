// Who may use the apps: a student with a class code, or a signed-in teacher.
// The class code (or teacher token) is kept in this browser only, until it
// expires. The server checks it again whenever it is asked to compile.

import { beta, piBeta } from "./beta.js";

const KEY = "circuitpathways.access";

/**
 * kind "class": a class code (the Go site); "student": a student who joined a saved class (the Cloudflare
 * site), with their first names and school as they joined; "teacher": a teacher's sign-in; "local": no class
 * (the Pi beta, where a class code is optional and work is saved on this device).
 * @returns {{kind: "class"|"student"|"teacher"|"local", value: string, expires_at: number, names?: string[], school?: string, class?: object}|null}
 */
export function getAccess(now = Date.now(), optional = piBeta) {
  if (beta) return { kind: "beta", value: "beta", expires_at: now + 12 * 3600 * 1000 }; // the TEST version needs no class code
  try {
    const a = JSON.parse(localStorage.getItem(KEY) || "null");
    if (a && typeof a.value === "string" && a.expires_at > now && ["class", "student", "teacher"].includes(a.kind)) return a;
    if (a) localStorage.removeItem(KEY);
  } catch { /* storage blocked */ }
  return optional ? { kind: "local", value: "local", expires_at: now + 12 * 3600 * 1000 } : null;
}

/** Is the student in a class (or a teacher), rather than just using this device? */
export function inClass(access = getAccess()) {
  return Boolean(access) && access.kind !== "local" && access.kind !== "beta";
}

export function setAccess(kind, value, expires_at, extra = {}) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ kind, value, expires_at, ...extra }));
  } catch { /* storage blocked: they'll be asked again */ }
}

export function clearAccess() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

/** A POST to our server, with the header it requires. */
export async function postJSON(path, body, extraHeaders = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Circuit-Pathways": "1", ...extraHeaders },
    body: JSON.stringify(body),
    credentials: "omit",
  });
  let data = null;
  try { data = await res.json(); } catch { /* no body */ }
  if (!res.ok) {
    const err = new Error(data?.message || "Something went wrong. Try again.");
    err.status = res.status;
    err.code = data?.error || "unknown";
    throw err;
  }
  return data;
}
