// The TEST version (a copy of the site run with BETA=1, for colleagues to try): everyone gets in
// with no class code, nothing is saved, and a small "TEST" tag is shown. The server says whether
// it is the test version in /api/info. In a normal site this does nothing.

async function ask() {
  if (typeof location === "undefined" || typeof fetch === "undefined") return false; // (the Node tests)
  try {
    const res = await fetch("/api/info", { credentials: "omit" });
    return (await res.json()).beta === true;
  } catch {
    return false;
  }
}

export const beta = await ask();

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
  const message = "TEST VERSION \u2022 Nothing is saved \u2022 Closing or reloading this tab clears everything \u2022 ";
  const tag = document.createElement("div");
  tag.id = "test-tag";
  tag.setAttribute("role", "note");
  tag.setAttribute("aria-label", "TEST version. Nothing is saved. Closing or reloading this tab clears everything.");
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
