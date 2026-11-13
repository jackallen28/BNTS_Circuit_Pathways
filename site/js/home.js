// Circuit Pathways home: drifting pixel squares, reveal-on-scroll, and the
// class forms (students join with a class code, teachers sign in).

import { getAccess, setAccess, clearAccess, postJSON, inClass } from "/shared/access.js";
import { beta, piBeta, teacherMode, savedClasses as classesKept, showTestTag, showBetaBadge } from "/shared/beta.js";
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

// ---- classes
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "long", year: "numeric" });

// The Cloudflare site keeps classes (first names and school, and students' work), so joining asks for
// names; the Go site's class codes need none. /api/info says which.
let savedClasses = false;
fetch("/api/info", { credentials: "omit" }).then((r) => r.json()).then((info) => {
  savedClasses = info.classes === true;
  if (savedClasses) {
    $("#privacy").textContent = "When you join a class, only your first name(s) and school are kept, with your work, so your teacher can see it and you can carry on on another computer. It's all deleted when the class ends. Nothing else about you is kept.";
  }
  if (piBeta) {
    $("#privacy").textContent = "Without a class code, your work is saved on this device only. When you join a class, only your first name(s) and school are kept with your work, so your teacher can see it and you can carry on on another computer. It's all deleted when the class ends. Nothing else about you is kept.";
  }
}).catch(() => {});

function showState() {
  const a = getAccess();
  const member = inClass(a); // in the Pi beta, a student with no class is just using this device
  $("#session-forms").hidden = member;
  $("#session-in").hidden = !member;
  $("#teacher-link").hidden = a?.kind !== "teacher";
  $("#forget-me").hidden = a?.kind !== "student";
  if (member) {
    const until = `until the end of ${fmtDate(a.expires_at - 12 * 3600 * 1000)}`;
    $("#session-in-text").textContent = a.kind === "teacher"
      ? `You're signed in as a teacher until ${new Date(a.expires_at).toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}.`
      : a.kind === "student"
        ? `You're in ${a.class?.name ?? "your class"} (${a.class?.code ?? ""}) as ${(a.names ?? []).join(" and ")}, ${until}. Your work is saved with your class.`
        : `You're in class ${a.value}, ${until}.`;
  }
  $("#need-class").hidden = new URLSearchParams(location.search).get("need") !== "class" || member || piBeta;
  $("#optional-note").hidden = !(piBeta || (beta && teacherMode)) || member;
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

/** "Mia, Sam" or "Mia and Sam" -> ["Mia", "Sam"] */
const splitNames = (s) => s.split(/\s*(?:,|&|\band\b)\s*/i).map((x) => x.trim()).filter(Boolean);

$("#join-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const askingNames = !$("#join-names").hidden;
  submit(form, async () => {
    const code = form.code.value;
    if (!askingNames) {
      const res = await postJSON("/api/class/join", { code });
      if (res.needs_names) {
        // a saved class: now the student's first name(s) and school
        $("#join-names").hidden = false;
        $("#join-class").textContent = `Class: ${res.class.name} (${res.class.school})`;
        form.school.value = res.class.school;
        form.code.readOnly = true;
        $("#join-btn").textContent = "Join ▸";
        form.names.required = true;
        form.names.focus();
        return;
      }
      const tidy = code.toUpperCase().replace(/[^0-9A-Z]/g, "").replace(/[IL]/g, "1").replace(/O/g, "0");
      setAccess("class", `${tidy.slice(0, 5)}-${tidy.slice(5)}`, res.expires_at);
    } else {
      const names = splitNames(form.names.value);
      const res = await postJSON("/api/class/join", { code, names, school: form.school.value });
      setAccess("student", res.token, res.expires_at, { names: res.student.names, school: res.student.school, class: res.class });
    }
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
  if (a?.kind !== "student") return;
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
if (thisPi() && !beta) {
  $("#on-pi").textContent = `This is the Raspberry Pi ${thisPi()}. When you choose "My Raspberry Pi" in PiPath, your programs run on it. Your work is saved on this Pi, and with your class once you've joined one, so you can carry on on any computer.`;
  $("#on-pi").hidden = false;
}
if (teacherMode) $("#teacher-hint").hidden = false; // beta teacher mode: teachers make up their own code
if (piBeta) {
  // The Pi beta: students start straight away (saved on this device); a class code is optional.
  showBetaBadge();
  $(".scroll-hint").textContent = "Got a class code, or a teacher? Scroll down ▾";
}
if (beta) {
  // The TEST version: anyone can use the apps with no code, and nothing is saved on this computer. With beta
  // teacher mode, teachers make up a code and make a class, and students can join it to try that.
  showTestTag();
  document.getElementById("beta-badge").hidden = false;
  if (teacherMode) {
    $("#optional-note").textContent = classesKept
      ? "This is the TEST version: pick PiPath or ArduinoPath above and try it with no code. Nothing is saved on this computer. To try a class, a teacher makes up a teacher code below and makes a class, and students join it with the class code. A student who joins has their work saved to the class."
      : "This is the TEST version: pick PiPath or ArduinoPath above and try it with no code. Nothing is saved. To try a class, a teacher makes up a teacher code below and makes a class code, and students join with it.";
    if (classesKept) $("#privacy").textContent = "This is the TEST version, so nothing is saved on this computer. If you join a class, only your first name(s) and school are kept with your work, so your teacher can see it. It's all deleted when the class ends. Nothing else about you is kept.";
    $(".scroll-hint").textContent = "Got a class code, or a teacher? Scroll down ▾";
  } else {
    $("#session").hidden = true;
    $(".scroll-hint").hidden = true;
  }
} else if (!$("#need-class").hidden) {
  $("#session").scrollIntoView();
}
