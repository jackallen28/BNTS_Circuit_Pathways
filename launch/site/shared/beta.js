// The TEST version (a copy of the site run with BETA=1, for colleagues to try): everyone gets in
// with no class code, nothing is saved, and a small "TEST" tag is shown. The server says whether
// it is the test version in /api/info. In a normal site this does nothing.
//
// The Pi beta (PI_BETA=1, for students using Raspberry Pis) is different: it saves. A class code is
// optional. Without one, work is saved on this device only; with one, it also syncs to the class.

async function ask() {
  if (typeof location === "undefined" || typeof fetch === "undefined") return {}; // (the Node tests)
  try {
    const res = await fetch("/api/info", { credentials: "omit" });
    return await res.json();
  } catch {
    return {};
  }
}

const info = await ask();
export const beta = info.beta === true;
/** The Pi beta: a class code is optional, and work is saved on this device unless a class is joined. */
export const piBeta = info.edition === "pi-beta" && info.class_optional === true;
/** Beta teacher mode: in a beta edition a teacher makes up their own teacher code, so students can join a class. */
export const teacherMode = info.teacher_mode === true;
/** Classes are kept by the server (the Cloudflare site), so a student who joins one has their work saved to it. */
export const savedClasses = info.classes === true;

/** What Settings > My work says on the TEST version. */
export const TEST_WORK_NOTE = savedClasses
  ? "This is the TEST version, so nothing is saved on this computer and there are no save files. Your work is cleared when you close or reload this tab, unless you've joined a class on the home page: then it is saved to your class."
  : "This is the TEST version, so nothing is saved and there are no save files. When you close or reload this tab, your work is cleared.";

/** The yellow BETA box beside the title (the Pi beta shows it; it saves, so it has no TEST ticker). */
export function showBetaBadge() {
  if (typeof document === "undefined" || document.getElementById("beta-css")) return;
  const css = document.createElement("link");
  css.id = "beta-css";
  css.rel = "stylesheet";
  css.href = "/css/beta.css";
  document.head.append(css);
  const badge = document.getElementById("beta-badge");
  if (badge) badge.hidden = false;
}

/** The "TEST" tag and page title. Call once when a page starts. */
export function showTestTag() {
  if (!beta) return;
  document.title = `TEST: ${document.title.replace(/^TEST: /, "")}`;
  if (document.getElementById("test-tag")) return;
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "/css/beta.css";
  document.head.append(css);
  // A red LED news ticker along the bottom of the page.
  const message = savedClasses
    ? "TEST VERSION \u2022 Nothing is saved on this computer \u2022 Join a class to save your work to it \u2022 "
    : "TEST VERSION \u2022 Nothing is saved \u2022 Closing or reloading this tab clears everything \u2022 ";
  const tag = document.createElement("div");
  tag.id = "test-tag";
  tag.setAttribute("role", "note");
  tag.setAttribute("aria-label", savedClasses
    ? "TEST version. Nothing is saved on this computer. Join a class to save your work to it."
    : "TEST version. Nothing is saved. Closing or reloading this tab clears everything.");
  const track = document.createElement("div");
  track.className = "track";
  track.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 2; i++) {
    const part = document.createElement("span");
    part.textContent = message.repeat(3);
    track.append(part);
  }
  tag.append(track);
  document.body.append(tag);
  document.body.classList.add("has-test-tag");
}
