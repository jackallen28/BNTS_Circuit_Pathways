// Who may use the apps: a student with a class code, or a signed-in teacher.
// The class code (or teacher token) is kept in this browser only, until it
// expires. The server checks it again whenever it is asked to compile.

const KEY = "circuitpathways.access";

/** @returns {{kind: "class"|"teacher", value: string, expires_at: number}|null} */
export function getAccess(now = Date.now()) {
  try {
    const a = JSON.parse(localStorage.getItem(KEY) || "null");
    if (a && typeof a.value === "string" && a.expires_at > now && (a.kind === "class" || a.kind === "teacher")) return a;
    if (a) localStorage.removeItem(KEY);
  } catch { /* storage blocked */ }
  return null;
}

export function setAccess(kind, value, expires_at) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ kind, value, expires_at }));
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
