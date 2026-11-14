// What kind of Circuit Pathways server this page came from, from /api/info:
//
// - the school server (the main Raspberry Pi), which every computer on the school network opens;
// - a student Pi, which serves the site itself (so it works with no network) and passes classes on to the
//   school server whenever it can reach it ("online").
//
// A class code is always optional: without one, work is saved in this browser; with one, it is saved with the
// student's class on the school server too.

async function ask() {
  if (typeof location === "undefined" || typeof fetch === "undefined") return {}; // (the Node tests)
  try {
    const res = await fetch("/api/info", { credentials: "omit", cache: "no-store" });
    return await res.json();
  } catch {
    return {};
  }
}

export const info = await ask();
/** This page is served by a student's own Raspberry Pi. */
export const studentPi = info.edition === "student-pi";
/** Pi Link is on: PiPath can run programs on a Raspberry Pi's pins (a student Pi; not a laptop). */
export const piLink = info.relay === "sse" || info.relay === "ws";

/** Is the school server there right now? (A student Pi asks again; the school server always is.) */
export async function online() {
  if (!studentPi) return true;
  return (await ask()).online === true;
}

const EDITIONS = { school: "School server", "student-pi": "Student Pi" };

/** Which build this is, for About boxes and bug reports. */
export const build = {
  edition: info.edition ?? "",
  name: info.name ?? "",
  commit: info.commit || (info.version && info.version !== "dev" ? info.version : ""),
};

/** "School server pathways.local, build 5e86a54" (or "" if the server didn't say). */
export function buildLabel(b = build) {
  if (!b.edition && !b.commit) return "";
  return [[EDITIONS[b.edition] ?? b.edition, b.name].filter(Boolean).join(" "), b.commit && `build ${b.commit}`].filter(Boolean).join(", ");
}
