// The Raspberry Pi version: Circuit Pathways opened on a Raspberry Pi from the
// shortcuts its Pi Link installer makes (the Pi menu and the desktop). They open
// the site with ?pi=<this Pi's ID>, so this browser knows it is on that Pi:
// PiPath then runs programs on it with no ID to type.
//
// Everything stays in this browser on the Pi (work, names, the ID), like on a
// laptop; a student who has joined a class also has their work kept with the
// class, so it's the same on every device they use.

const PI_KEY = "pipath.pi_id"; // the Pi PiPath links to (runtime/pi.js)
const THIS_KEY = "circuitpathways.this_pi"; // this browser is on this Pi

/** "K7M2QX9P" or "k7m2-qx9p" → "K7M2-QX9P"; anything else → "". */
export function normalisePiId(s) {
  const raw = String(s ?? "").toUpperCase().replace(/[\s_-]/g, "");
  return /^[0-9A-Z]{8}$/.test(raw) ? `${raw.slice(0, 4)}-${raw.slice(4)}` : "";
}

/**
 * Reads ?pi= from the address (the Pi's shortcuts add it), remembers it, and
 * takes it out of the address bar. Returns the Pi's ID, or "".
 */
export function takePiFromUrl(loc = globalThis.location, store = globalThis.localStorage, hist = globalThis.history) {
  let id = "";
  try {
    const url = new URL(loc.href);
    if (!url.searchParams.has("pi")) return "";
    id = normalisePiId(url.searchParams.get("pi"));
    url.searchParams.delete("pi");
    hist?.replaceState?.(hist.state, "", url.pathname + url.search + url.hash);
  } catch {
    return "";
  }
  if (!id) return "";
  try {
    store.setItem(THIS_KEY, id);
    store.setItem(PI_KEY, id);
  } catch { /* private window: it just won't be remembered */ }
  return id;
}

/** This Pi's ID when the site was opened from a Pi's shortcut, else "". */
export function thisPi(store = globalThis.localStorage) {
  try { return normalisePiId(store.getItem(THIS_KEY)); } catch { return ""; }
}
