// Circuit Pathways home: drifting pixel squares, reveal-on-scroll, and the
// class forms (students join with a class code, teachers sign in).

import { getAccess, setAccess, clearAccess, postJSON } from "/shared/access.js";
import { beta, showTestTag } from "/shared/beta.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---- the sky
const sky = $(".sky");
const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#815a99"];
for (let i = 0; i < 14; i++) {
  const s = 14 + Math.random() * 34;
  const sq = document.createElement("i");
  sq.style.cssText = `left:${Math.random() * 100}%;top:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};` +
    `animation-delay:${-Math.random() * 20}s;animation-duration:${16 + Math.random() * 18}s`;
  sky.append(sq);
}

const revealer = new IntersectionObserver((es) => es.forEach((e) => {
  if (e.isIntersecting) { e.target.classList.add("in"); revealer.unobserve(e.target); }
}), { threshold: 0.12 });
$$(".reveal").forEach((el) => revealer.observe(el));

// ---- classes
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "long", year: "numeric" });

function showState() {
  const a = getAccess();
  $("#session-forms").hidden = Boolean(a);
  $("#session-in").hidden = !a;
  $("#teacher-link").hidden = a?.kind !== "teacher";
  if (a) {
    $("#session-in-text").textContent = a.kind === "teacher"
      ? `You're signed in as a teacher until ${new Date(a.expires_at).toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}.`
      : `You're in class ${a.value}, until the end of ${fmtDate(a.expires_at - 12 * 3600 * 1000)}.`;
  }
  $("#need-class").hidden = new URLSearchParams(location.search).get("need") !== "class" || Boolean(a);
}

function setNote(form, text, kind = "") {
  const n = $(".note", form);
  n.textContent = text;
  n.className = `note ${kind}`;
}

async function submit(form, fn) {
  const btn = $("button[type=submit]", form);
  btn.disabled = true;
  setNote(form, "Checking...");
  try {
    await fn();
    setNote(form, "");
  } catch (err) {
    setNote(form, err.status === undefined ? "Circuit Pathways can't be reached. Check your internet connection and try again." : err.message, "bad");
  } finally {
    btn.disabled = false;
  }
}

$("#join-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  submit(form, async () => {
    const code = form.code.value;
    const res = await postJSON("/api/class/join", { code });
    const tidy = code.toUpperCase().replace(/[^0-9A-Z]/g, "").replace(/[IL]/g, "1").replace(/O/g, "0");
    setAccess("class", `${tidy.slice(0, 5)}-${tidy.slice(5)}`, res.expires_at);
    form.reset();
    showState();
  });
});

$("#teacher-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  submit(form, async () => {
    const res = await postJSON("/api/teacher/signin", { code: form.teacher.value });
    setAccess("teacher", res.token, res.expires_at);
    form.reset();
    location.href = "teacher/";
  });
});

$("#leave").addEventListener("click", () => {
  clearAccess();
  showState();
});

showState();
if (beta) {
  // The TEST version: the same home page, but no class codes or teacher sign-in.
  showTestTag();
  $("#session").hidden = true;
  $(".scroll-hint").hidden = true;
} else if (!$("#need-class").hidden) {
  $("#session").scrollIntoView();
}
