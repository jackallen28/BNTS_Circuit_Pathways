// Who is using the apps: a student who joined a class (their token, first names, school and class), a
// teacher who signed in, or (with no class) "local": a student whose work is saved in this browser only.
// The token is kept in this browser until the class ends (a teacher's after 12 hours).

const KEY = "circuitpathways.access";

/**
 * kind "student": a student who joined a class on the school server, with their first names and school as they
 * joined; "teacher": a teacher's sign-in; "local": no class (work is saved in this browser).
 * @returns {{kind: "student"|"teacher"|"local", value: string, expires_at: number, names?: string[], school?: string, class?: object}}
 */
export function getAccess(now = Date.now()) {
  try {
    const a = JSON.parse(localStorage.getItem(KEY) || "null");
    if (a && typeof a.value === "string" && a.expires_at > now && ["student", "teacher"].includes(a.kind)) return a;
    if (a) localStorage.removeItem(KEY); // ended, or from an older version
  } catch { /* storage blocked */ }
  return { kind: "local", value: "local", expires_at: now + 12 * 3600 * 1000 };
}

/** Is the student in a class (or a teacher), rather than just using this browser? */
export function inClass(access = getAccess()) {
  return Boolean(access) && access.kind !== "local";
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
