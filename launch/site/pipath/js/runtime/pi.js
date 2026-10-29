// "Run on my Pi": the page's link to the student's Raspberry Pi, shared by every screen.
// The Pi ID is only the label on the Pi (like K7M2-QX9P). It is remembered in this browser only.
import { PiRemote } from "/pipath/remote/pi-remote.js";
import { getAccess } from "/shared/access.js";

const KEY = "pipath.pi_id";
let pi;

export const getPi = () => (pi ??= new PiRemote());

export function savedPiId() {
  try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; }
}

export function rememberPiId(id) {
  try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY); } catch { /* private window: it just won't be remembered */ }
}

/** True once the Pi is linked and its app allows running programs. */
export const piReady = () => getPi().state === "connected" && getPi().canRun;

/** Is the student in a class (so the site lets them reach a Pi)? */
export const hasClass = () => Boolean(getAccess());

/** The helper modules a program imports, which the Pi gets from the website. */
export function supportFor(code) {
  return ["pipath_camera", "pipath_computer"].filter((m) => new RegExp(`^\\s*(import|from)\\s+${m}\\b`, "m").test(code));
}

/** A short line about the link, for the toolbar and the Pi panel. */
export function piSummary(p = getPi()) {
  switch (p.state) {
    case "connected": return p.canRun ? { tone: "ok", text: `${p.name || "Raspberry Pi"} (${p.code.toUpperCase()}) is ready` } : { tone: "warn", text: `${p.name || "Raspberry Pi"} is linked but won't run programs` };
    case "pi-offline": return { tone: "warn", text: `${p.code.toUpperCase()} is offline` };
    case "connecting": return { tone: "wait", text: "Linking to your Pi..." };
    case "closed": return { tone: "warn", text: "The link ended" };
    default: return { tone: "none", text: "Not linked to a Pi yet" };
  }
}
