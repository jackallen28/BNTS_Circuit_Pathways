// Circuit Pathways home: drifting pixel squares, reveal-on-scroll, and the
// class forms (students join with a class code, teachers sign in).

import { getAccess, setAccess, clearAccess, postJSON, inClass } from "/shared/access.js";
import { info, studentPi, online, buildLabel } from "/shared/edition.js";
import { takePiFromUrl, thisPi } from "/shared/thispi.js";

// Opened from a Raspberry Pi's own shortcut (?pi=...): remember this Pi.
takePiFromUrl();

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

// ---- the school server
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "long", year: "numeric" });

// On a laptop, the site must be opened at its secure (https) address for uploading to boards and for Python
// programs that wait for input. Say so, with a link to the trust page for the first time on this computer.
if (!window.isSecureContext && info.tls) {
  const note = $("#secure-note");
  const secure = `https://${location.hostname}/`;
  note.replaceChildren("To upload to a board, and for Python programs that ask questions, use the secure address: ",
    Object.assign(document.createElement("a"), { href: secure, textContent: secure.replace(/\/$/, "") }),
    ". The first time on this computer? ", Object.assign(document.createElement("a"), { href: "/trust/", textContent: "Set it up here" }), ".");
  note.classList.add("warn");
  note.hidden = false;
}

// A student Pi: say when the school server can't be reached (work is still saved on the Pi).
async function checkOnline() {
  if (!studentPi) return;
  const up = await online();
  const note = $("#offline-note");
  note.textContent = "The school's Circuit Pathways server can't be reached right now. You can still use PiPath and ArduinoPath: your work is saved on this Pi, and goes to your class when the server is back. Joining a class, and uploading to a board, need the server.";
  note.classList.add("warn");
  note.hidden = up;
}
checkOnline();
setInterval(checkOnline, 30000);

// ---- classes
const titles = (async () => {
  const [ap, pp] = await Promise.all([
    fetch("/arduinopath/data/catalogue.json").then((r) => r.json()).catch(() => ({ projects: [] })),
    fetch("/pipath/data/catalog.json").then((r) => r.json()).catch(() => ({ projects: [] })),
  ]);
  const t = new Map();
  for (const p of ap.projects ?? []) t.set(`arduinopath/${p.id}`, p.title);
  for (const p of pp.projects ?? []) t.set(`pipath/${p.id}`, p.title);
  t.set("arduinopath/freeplay", "Free Play (ArduinoPath)");
  t.set("pipath/freeplay", "Free Play (PiPath)");
  return t;
})();

/** Where a piece of set work opens. */
export function taskLink(task) {
  if (task.app === "arduinopath") return task.item === "freeplay" ? "/arduinopath/#/freeplay" : `/arduinopath/#/project/${encodeURIComponent(task.item)}`;
  return task.item === "freeplay" ? "/pipath/#/free" : `/pipath/#/activity/${encodeURIComponent(task.item)}`;
}

async function showTasks(a) {
  const box = $("#tasks");
  if (a?.kind !== "student") { box.hidden = true; return; }
  let me;
  try {
    const res = await fetch("/api/student/me", { credentials: "omit", headers: { Authorization: `Bearer ${a.value}` } });
    if (res.status === 401) { clearAccess(); showState(); return; } // the class has ended, or they were taken off it
    if (!res.ok) return; // offline: try next time
    me = await res.json();
  } catch {
    return;
  }
  const t = await titles;
  const list = me.tasks ?? [];
  box.hidden = list.length === 0;
  $("#task-list").replaceChildren(...list.map((task) => {
    const li = document.createElement("li");
    const link = Object.assign(document.createElement("a"), { href: taskLink(task), textContent: t.get(`${task.app}/${task.item}`) ?? task.item });
    li.append(link, ` (${task.app === "pipath" ? "PiPath" : "ArduinoPath"})`);
    if (task.note) li.append(" ", Object.assign(document.createElement("span"), { className: "task-note", textContent: `: ${task.note}` }));
    return li;
  }));
}

function showState() {
  const a = getAccess();
  const member = inClass(a);
  $("#session-forms").hidden = member;
  $("#session-in").hidden = !member;
  $("#optional-note").hidden = member;
  $("#teacher-link").hidden = a.kind !== "teacher";
  $("#forget-me").hidden = a.kind !== "student";
  $("#leave").textContent = a.kind === "teacher" ? "Sign out" : "Leave this class";
  if (member) {
    $("#session-in-text").textContent = a.kind === "teacher"
      ? `You're signed in as a teacher until ${new Date(a.expires_at).toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}.`
      : `You're in ${a.class?.name ?? "your class"} (${a.class?.code ?? ""}) as ${(a.names ?? []).join(" and ")}, until the end of ${fmtDate(a.expires_at - 12 * 3600 * 1000)}. Your work is saved with your class.`;
  }
  showTasks(a);
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
    setNote(form, err.status === undefined ? "The Circuit Pathways server can't be reached. Check this computer is on the school network, and try again." : err.message, "bad");
  } finally {
    btn.disabled = false;
  }
}

/** "Mia, Sam" or "Mia and Sam" -> ["Mia", "Sam"] */
const splitNames = (s) => s.split(/\s*(?:,|&|\band\b)\s*/i).map((x) => x.trim()).filter(Boolean);

$("#join-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const askingNames = !$("#join-names").hidden;
  submit(form, async () => {
    const code = form.code.value;
    if (!askingNames) {
      // the code first (is it a class that's running?), then the student's first name(s) and school
      const res = await postJSON("/api/class/join", { code });
      $("#join-names").hidden = false;
      $("#join-class").textContent = `Class: ${res.class.name} (${res.class.school})`;
      form.school.value = res.class.school;
      form.code.readOnly = true;
      $("#join-btn").textContent = "Join ▸";
      form.names.required = true;
      form.names.focus();
      return;
    }
    const names = splitNames(form.names.value);
    const res = await postJSON("/api/class/join", { code, names, school: form.school.value });
    setAccess("student", res.token, res.expires_at, { names: res.student.names, school: res.student.school, class: res.class });
    form.reset();
    form.code.readOnly = false;
    form.names.required = false;
    $("#join-names").hidden = true;
    $("#join-btn").textContent = "Join class ▸";
    showState();
  });
});

$("#forget-me").addEventListener("click", async () => {
  const a = getAccess();
  if (a.kind !== "student") return;
  if (!confirm("Take your name and your saved work off this class? Your work stays in this browser.")) return;
  await fetch("/api/student/me", { method: "DELETE", headers: { "X-Circuit-Pathways": "1", Authorization: `Bearer ${a.value}` }, credentials: "omit" }).catch(() => {});
  clearAccess();
  showState();
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
$("#build").textContent = buildLabel(); // which build this is, for bug reports
if (thisPi()) {
  $("#on-pi").textContent = `This is the Raspberry Pi ${thisPi()}. In PiPath, your programs run on its pins. Your work is saved on this Pi, and with your class once you've joined one, so you can carry on on any computer at school.`;
  $("#on-pi").hidden = false;
}
