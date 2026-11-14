// The teacher portal, on the school's own Circuit Pathways server. Signing in gives a teacher token (kept in
// this browser for 12 hours). Classes, the work a teacher sets, and students' first names, school and work are
// kept on the school server until the class ends. Class files (.circuitclass) are an optional copy on the
// teacher's own computer.

import { getAccess, clearAccess, postJSON } from "/shared/access.js";
import { writeZip, readZip } from "/shared/local/zip.js";
import { readSaveFile, writeSaveFile, saveFileName } from "/shared/local/savefile.js";
import { joinNames } from "/shared/local/validate.js";

const $ = (s) => document.querySelector(s);

const access = getAccess();
if (access.kind !== "teacher") location.replace("/");

// ---- the sky, as on the home page
{
  const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#815a99"];
  for (let i = 0; i < 10; i++) {
    const s = 14 + Math.random() * 30;
    const sq = document.createElement("i");
    sq.style.cssText = `left:${Math.random() * 100}%;top:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};animation-delay:${-Math.random() * 20}s;animation-duration:${16 + Math.random() * 18}s`;
    $(".sky").append(sq);
  }
}

$("#signout").addEventListener("click", () => {
  clearAccess();
  location.href = "/";
});

const fmt = (ms) => new Date(ms).toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const say = (id, text, kind = "") => { const n = $(id); n.textContent = text; n.className = `note ${kind}`; };

const cls = null; // (class files from older versions kept a class code; classes now live on the school server)

// ---- 2. class files and student work from files
/** @type {{ file: string, bytes: Uint8Array, names: string[], school: string, projects: number, updated: number }[]} */
let students = [];

const CLASS_FORMAT = "circuitpathways-class";
const enc = new TextEncoder();
const dec = new TextDecoder();

function drawStudents() {
  const table = $("#students");
  table.hidden = students.length === 0;
  $("#save-all").disabled = students.length === 0;
  const body = table.querySelector("tbody");
  body.replaceChildren(...students.map((s, i) => {
    const tr = document.createElement("tr");
    for (const text of [joinNames(s.names), s.school, s.app, String(s.projects), s.updated ? new Date(s.updated).toLocaleString("en-AU") : ""]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    const td = document.createElement("td");
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "btn btn-plain";
    rm.textContent = "Remove";
    rm.addEventListener("click", () => { students.splice(i, 1); drawStudents(); });
    td.append(rm);
    tr.append(td);
    return tr;
  }));
}

const FORMATS = ["arduinopath-save", "circuitpath-save", "pipath-save"];
const isStudentFile = (n) => /\.(circuit|pipath)$/i.test(n);

async function addStudentFile(name, bytes) {
  const f = await readSaveFile(bytes, Date.now(), { formats: FORMATS, what: "Circuit Pathways" });
  if (!f.profile.names.length) throw new Error("has no name in it");
  const updated = Math.max(0, ...f.sketches.map((s) => s.updated_at), ...f.progress.map((p) => p.updated_at));
  const projects = new Set([...f.sketches, ...f.progress].map((x) => x.project_id)).size;
  const same = students.findIndex((s) => s.app === (f.manifest.format === "pipath-save" ? "PiPath" : "ArduinoPath") && s.names.join("|").toLowerCase() === f.profile.names.join("|").toLowerCase() && s.school.toLowerCase() === f.profile.school.toLowerCase());
  const app = f.manifest.format === "pipath-save" ? "PiPath" : "ArduinoPath";
  const rec = { file: name, bytes, app, names: f.profile.names, school: f.profile.school, projects, updated };
  if (same >= 0) {
    if (students[same].updated >= updated) return "kept";
    students[same] = rec;
    return "updated";
  }
  students.push(rec);
  return "added";
}

async function addFiles(files) {
  const problems = [];
  let added = 0;
  for (const file of files) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    try {
      // A zip of .circuit files (such as "Save everyone's work") is opened too.
      if (!isStudentFile(file.name)) {
        const inner = await readZip(bytes, { maxEntries: 600, maxEntryBytes: 9 << 20, maxTotalBytes: 256 << 20 }).catch(() => null);
        if (inner) {
          for (const [n, b] of inner) {
            if (!isStudentFile(n)) continue;
            try { await addStudentFile(n.split("/").pop(), b); added++; } catch (e) { problems.push(`${n}: ${e.message}`); }
          }
          continue;
        }
      }
      await addStudentFile(file.name, bytes);
      added++;
    } catch (err) {
      problems.push(`${file.name}: ${err.message}`);
    }
  }
  students.sort((a, b) => joinNames(a.names).localeCompare(joinNames(b.names)));
  drawStudents();
  say("#file-note", problems.length ? `${added} added. Couldn't open: ${problems.join("; ")}` : `${added} student file${added === 1 ? "" : "s"} added.`, problems.length ? "bad" : "good");
}

$("#add-files").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  if (files.length) await addFiles(files);
});

function download(bytes, name, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

const safe = (s) => s.replace(/[^A-Za-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");

$("#save-class").addEventListener("click", () => {
  const label = $("#label").value.trim();
  const now = Date.now();
  const files = [
    { name: "manifest.json", data: JSON.stringify({ format: CLASS_FORMAT, version: 1, created_at: now }, null, 2) + "\n" },
    { name: "class.json", data: JSON.stringify({ label, code: cls?.code ?? "", expires_at: cls?.expires_at ?? 0 }, null, 2) + "\n" },
  ];
  const used = new Set();
  for (const s of students) {
    let n = s.file.replace(/[^A-Za-z0-9._-]+/g, "_");
    while (used.has(n.toLowerCase())) n = n.replace(/(\.(circuit|pipath))?$/, "_2$1");
    used.add(n.toLowerCase());
    files.push({ name: `students/${n}`, data: s.bytes });
  }
  download(writeZip(files, now), `${safe(label) || "Class"}_${new Date(now).toISOString().slice(0, 10)}.circuitclass`, "application/zip");
  say("#file-note", `Class file saved${students.length ? ` with ${students.length} student${students.length === 1 ? "" : "s"}` : ""}.`, "good");
});

$("#open-class").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const entries = await readZip(new Uint8Array(await file.arrayBuffer()), { maxEntries: 600, maxEntryBytes: 9 << 20, maxTotalBytes: 256 << 20 });
    const manifest = JSON.parse(dec.decode(entries.get("manifest.json") ?? enc.encode("{}")));
    if (manifest.format !== CLASS_FORMAT) throw new Error("not a class file");
    if (manifest.version > 1) throw new Error("This class file is from a newer Circuit Pathways.");
    const info = JSON.parse(dec.decode(entries.get("class.json") ?? enc.encode("{}")));
    $("#label").value = String(info.label ?? "").slice(0, 60);
    students = [];
    for (const [n, b] of entries) {
      if (n.startsWith("students/") && isStudentFile(n)) await addStudentFile(n.slice(9), b).catch(() => {});
    }
    students.sort((a, b) => joinNames(a.names).localeCompare(joinNames(b.names)));
    drawStudents();
    say("#file-note", "Class file opened.", "good");
  } catch (err) {
    say("#file-note", /newer/.test(err.message) ? err.message : "That file can't be opened. Pick a .circuitclass file saved from this page.", "bad");
  }
});

$("#save-all").addEventListener("click", () => {
  const files = students.map((s) => ({ name: s.file, data: s.bytes }));
  download(writeZip(files), `Everyone_${new Date().toISOString().slice(0, 10)}.zip`, "application/zip");
});



// ---- 1. classes on the school server: first names, school and work, until the class ends
const auth = { Authorization: `Bearer ${access?.value ?? ""}` };
const day = 24 * 3600 * 1000;
const isoDay = (ms) => new Date(ms - new Date(ms).getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const endOfDay = (iso) => new Date(`${iso}T23:59:00`).getTime();
let openCode = null;
let openWork = null;

async function api(method, path, body) {
  const res = await fetch(path, {
    method, credentials: "omit",
    headers: { ...auth, ...(method === "GET" ? {} : { "X-Circuit-Pathways": "1" }), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { clearAccess(); location.replace("/"); throw new Error("signed out"); }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message ?? "That didn't work. Try again.");
  return data;
}

function cell(tr, text) {
  const td = document.createElement("td");
  if (text instanceof Node) td.append(text);
  else td.textContent = text;
  tr.append(td);
  return td;
}

function button(text, onclick, cls = "btn btn-plain") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.textContent = text;
  b.addEventListener("click", onclick);
  return b;
}

async function loadClasses() {
  const { classes } = await api("GET", "/api/teacher/classes");
  const table = $("#c-table");
  table.hidden = classes.length === 0;
  table.querySelector("tbody").replaceChildren(...classes.map((c) => {
    const tr = document.createElement("tr");
    cell(tr, c.name);
    cell(tr, c.code);
    cell(tr, fmt(c.ends_at));
    cell(tr, String(c.students));
    const td = cell(tr, "");
    td.append(button("Open", () => openClass(c.code)));
    return tr;
  }));
  return classes;
}

async function openClass(code) {
  openCode = code;
  openWork = null;
  $("#r-work").hidden = true;
  const { class: c, students: list, tasks: set } = await api("GET", `/api/teacher/class/${code}`);
  tasks = (set ?? []).map((t) => ({ app: t.app, item: t.item, note: t.note ?? "" }));
  drawTasks();
  say("#w-note-msg", "");
  drawProgress().catch(() => {});
  $("#roster").hidden = false;
  $("#r-title").textContent = `${c.name} (${c.school}): ${list.length} student${list.length === 1 ? "" : "s"}`;
  $("#r-code").textContent = c.code;
  $("#r-ends").value = isoDay(c.ends_at);
  say("#r-note", `Ends ${fmt(c.ends_at)}. After that the class, the names and all the work are deleted.`);
  $("#r-table").querySelector("tbody").replaceChildren(...list.map((st) => {
    const tr = document.createElement("tr");
    cell(tr, joinNames(st.names));
    cell(tr, st.school);
    cell(tr, new Date(st.joined_at).toLocaleDateString("en-AU"));
    cell(tr, st.last_work ? new Date(st.last_work).toLocaleString("en-AU") : "Nothing yet");
    cell(tr, String(st.items));
    const td = cell(tr, "");
    td.append(button("See work", () => showWork(st.id)), " ", button("Remove", async () => {
      if (!confirm(`Take ${joinNames(st.names)} and their work off this class?`)) return;
      await api("DELETE", `/api/teacher/class/${code}/students/${st.id}`);
      await openClass(code);
      await loadClasses();
    }));
    return tr;
  }));
}

async function classWork() {
  openWork ??= await api("GET", `/api/teacher/class/${openCode}/work`);
  return openWork;
}

const ext = (app) => (app === "pipath" ? "py" : "ino");

async function showWork(id) {
  const { students: list } = await classWork();
  const st = list.find((x) => x.id === id);
  const box = $("#r-work");
  box.hidden = false;
  const h = document.createElement("h3");
  h.textContent = `${joinNames(st.names)}'s work`;
  const parts = [h];
  const sketches = st.work.filter((w) => w.kind === "sketch").sort((a, b) => b.updated_at - a.updated_at);
  if (!sketches.length) {
    const p = document.createElement("p");
    p.textContent = "No code saved yet.";
    parts.push(p);
  }
  for (const w of sketches) {
    const h4 = document.createElement("h4");
    h4.textContent = `${w.app === "pipath" ? "PiPath" : "ArduinoPath"}: ${w.item} (saved ${new Date(w.updated_at).toLocaleString("en-AU")})`;
    const pre = document.createElement("pre");
    pre.textContent = w.body;
    parts.push(h4, pre);
  }
  box.replaceChildren(...parts);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** Each student's synced work as save files (.circuit / .pipath), the same as students save themselves. */
async function saveFilesFor() {
  const { students: list } = await classWork();
  const out = [];
  for (const st of list) {
    for (const app of ["arduinopath", "pipath"]) {
      const mine = st.work.filter((w) => w.app === app);
      if (!mine.length) continue;
      const settings = mine.find((w) => w.kind === "settings");
      const bytes = writeSaveFile({
        profile: { names: st.names, school: st.school, settings: settings ? JSON.parse(settings.body) : {} },
        sketches: mine.filter((w) => w.kind === "sketch").map((w) => ({ project_id: w.item, code: w.body, updated_at: w.updated_at })),
        progress: mine.filter((w) => w.kind === "progress").map((w) => ({ project_id: w.item, data: JSON.parse(w.body), updated_at: w.updated_at })),
        format: app === "pipath" ? "pipath-save" : "arduinopath-save",
      });
      out.push({ name: saveFileName(st.names, new Date(), app === "pipath" ? "PiPath" : "ArduinoPath", app === "pipath" ? "pipath" : "circuit"), data: bytes, st, app, mine });
    }
  }
  return out;
}

async function initSavedClasses() {
  await setWorkUI();
  $("#c-ends").value = isoDay(Date.now() + 70 * day);
  $("#c-ends").min = isoDay(Date.now() + day);
  $("#c-ends").max = isoDay(Date.now() + 399 * day);
  $("#r-ends").min = $("#c-ends").min;
  $("#r-ends").max = $("#c-ends").max;
  $("#c-make").addEventListener("click", async () => {
    try {
      const c = await api("POST", "/api/teacher/class", { name: $("#c-name").value, school: $("#c-school").value, ends_at: endOfDay($("#c-ends").value) });
      say("#c-note", `Made ${c.name}. Its code is ${c.code}.`, "good");
      $("#c-name").value = "";
      await loadClasses();
      await openClass(c.code);
    } catch (e) { say("#c-note", e.message, "bad"); }
  });
  $("#r-refresh").addEventListener("click", () => openClass(openCode));
  $("#w-save").addEventListener("click", saveTasks);
  $("#r-copy").addEventListener("click", () => navigator.clipboard.writeText($("#r-code").textContent).catch(() => {}));
  $("#r-end").addEventListener("click", async () => {
    try {
      await api("POST", `/api/teacher/class/${openCode}/end`, { ends_at: endOfDay($("#r-ends").value) });
      await openClass(openCode);
      await loadClasses();
    } catch (e) { say("#r-note", e.message, "bad"); }
  });
  $("#r-delete").addEventListener("click", async () => {
    if (!confirm("Delete this class now, with every student's name and work in it? This can't be undone. (Download their work first if you want to keep it.)")) return;
    await api("DELETE", `/api/teacher/class/${openCode}`);
    $("#roster").hidden = true;
    say("#c-note", "The class, its names and its work have been deleted.", "good");
    await loadClasses();
  });
  $("#r-zip").addEventListener("click", async () => {
    const files = [];
    for (const f of await saveFilesFor()) {
      const folder = f.name.replace(/\.(circuit|pipath)$/, "");
      files.push({ name: f.name, data: f.data });
      for (const w of f.mine.filter((x) => x.kind === "sketch")) files.push({ name: `${folder}/${w.item}.${ext(f.app)}`, data: w.body });
    }
    if (!files.length) return say("#r-note", "Nobody has saved any work yet.");
    download(writeZip(files), `${safe($("#r-title").textContent.split(" (")[0]) || "Class"}_work_${new Date().toISOString().slice(0, 10)}.zip`, "application/zip");
  });
  $("#r-files").addEventListener("click", async () => {
    let n = 0;
    for (const f of await saveFilesFor()) { await addStudentFile(f.name, f.data); n++; }
    students.sort((a, b) => joinNames(a.names).localeCompare(joinNames(b.names)));
    drawStudents();
    $("#label").value = $("#r-title").textContent.split(" (")[0];
    say("#r-note", n ? `Added ${n} save file${n === 1 ? "" : "s"} to the class file below. Press Save class file to keep a copy.` : "Nobody has saved any work yet.", n ? "good" : "");
  });
  await loadClasses();
}



// ---- set work, and progress on it
/** @type {{ app: string, item: string, note: string }[]} */
let tasks = [];
const names = new Map(); // "app/item" -> title
const stepCounts = new Map(); // "app/item" -> number of steps
const appName = (app) => (app === "pipath" ? "PiPath" : "ArduinoPath");
const titleOf = (t) => names.get(`${t.app}/${t.item}`) ?? t.item;

async function setWorkUI() {
  const [ap, pp] = await Promise.all([
    fetch("/arduinopath/data/catalogue.json").then((r) => r.json()).catch(() => ({ projects: [] })),
    fetch("/pipath/data/catalog.json").then((r) => r.json()).catch(() => ({ projects: [] })),
  ]);
  const fill = (sel, app, list, free) => {
    sel.replaceChildren(new Option("Choose...", ""), new Option(free, "freeplay"));
    names.set(`${app}/freeplay`, free);
    for (const p of list) {
      sel.append(new Option(p.title, p.id));
      names.set(`${app}/${p.id}`, p.title);
      if (p.step_count) stepCounts.set(`${app}/${p.id}`, p.step_count);
    }
  };
  fill($("#w-ard"), "arduinopath", [...(ap.projects ?? [])].sort((a, b) => (a.order ?? 99) - (b.order ?? 99)), "Free Play (their own project)");
  fill($("#w-pi"), "pipath", (pp.projects ?? []).filter((p) => p.status !== "planned"), "Free Play (their own program)");
  $("#w-add").addEventListener("click", () => {
    const note = $("#w-note").value.trim();
    for (const [sel, app] of [[$("#w-ard"), "arduinopath"], [$("#w-pi"), "pipath"]]) {
      if (!sel.value) continue;
      if (!tasks.some((t) => t.app === app && t.item === sel.value)) tasks.push({ app, item: sel.value, note });
      sel.value = "";
    }
    $("#w-note").value = "";
    drawTasks();
    say("#w-note-msg", "Not saved yet: press Save the work for this class.");
  });
}

function drawTasks() {
  $("#w-list").replaceChildren(...tasks.map((t, i) => {
    const li = document.createElement("li");
    const title = Object.assign(document.createElement("span"), { className: "w-title", textContent: titleOf(t) });
    const app = Object.assign(document.createElement("span"), { className: "w-app", textContent: appName(t.app) });
    const note = Object.assign(document.createElement("span"), { className: "w-n", textContent: t.note ? `"${t.note}"` : "" });
    const move = (d) => () => {
      const j = i + d;
      if (j < 0 || j >= tasks.length) return;
      [tasks[i], tasks[j]] = [tasks[j], tasks[i]];
      drawTasks();
      say("#w-note-msg", "Not saved yet: press Save the work for this class.");
    };
    li.append(title, app, note,
      button("▲", move(-1)), button("▼", move(1)),
      button("Remove", () => { tasks.splice(i, 1); drawTasks(); say("#w-note-msg", "Not saved yet: press Save the work for this class."); }));
    return li;
  }));
  if (!tasks.length) {
    const li = document.createElement("li");
    li.textContent = "No work set yet. Students can still pick any project.";
    $("#w-list").replaceChildren(li);
  }
}

async function saveTasks() {
  try {
    const res = await api("PUT", `/api/teacher/class/${openCode}/tasks`, { tasks });
    tasks = res.tasks.map((t) => ({ app: t.app, item: t.item, note: t.note ?? "" }));
    drawTasks();
    say("#w-note-msg", tasks.length ? "Saved. Students see this work on their home page." : "Saved: no work is set for this class.", "good");
    await drawProgress();
  } catch (e) { say("#w-note-msg", e.message, "bad"); }
}

/** How far a student is through one piece of work, from the progress their app saved. */
export function progressOf(work, task, steps) {
  if (task.item === "freeplay") {
    const n = work.filter((w) => w.app === task.app && w.kind === "sketch" && (w.item === "freeplay" || w.item.startsWith("freeplay"))).length;
    return n ? { text: "·", cls: "p-some", title: "Started" } : { text: "", cls: "", title: "Not started" };
  }
  const p = work.find((w) => w.app === task.app && w.item === task.item && w.kind === "progress");
  const code = work.find((w) => w.app === task.app && w.item === task.item && w.kind === "sketch");
  if (!p) return code ? { text: "·", cls: "p-some", title: "Opened" } : { text: "", cls: "", title: "Not started" };
  let data = {};
  try { data = JSON.parse(p.body); } catch { /* old */ }
  let done = 0;
  let finished = false;
  if (task.app === "pipath") {
    done = Array.isArray(data.steps_done) ? data.steps_done.length : 0;
    finished = data.status === "complete" || Boolean(data.completed);
  } else {
    const list = Array.isArray(data.steps) ? data.steps : [];
    done = list.filter((s) => s?.done).length;
    finished = Boolean(data.finished) || (steps > 0 && done >= steps);
  }
  if (finished) return { text: "✓", cls: "p-done", title: "Finished" };
  if (done) return { text: steps ? `${done}/${steps}` : String(done), cls: "p-some", title: `${done} step${done === 1 ? "" : "s"} done` };
  return { text: "·", cls: "p-some", title: "Opened" };
}

async function drawProgress() {
  const table = $("#p-table");
  if (!tasks.length) { table.hidden = true; return; }
  table.hidden = false;
  // PiPath lessons say how many steps they have in their own files
  await Promise.all(tasks.filter((t) => t.app === "pipath" && t.item !== "freeplay" && !stepCounts.has(`pipath/${t.item}`)).map(async (t) => {
    try {
      const l = await (await fetch(`/pipath/data/lessons/${encodeURIComponent(t.item)}.json`)).json();
      if (Array.isArray(l.steps)) stepCounts.set(`pipath/${t.item}`, l.steps.length);
    } catch { /* fine */ }
  }));
  openWork = null;
  const { students: list } = await classWork();
  const head = document.createElement("tr");
  head.append(Object.assign(document.createElement("th"), { textContent: "First name(s)" }));
  for (const t of tasks) head.append(Object.assign(document.createElement("th"), { className: "p-cell", textContent: titleOf(t), title: appName(t.app) }));
  table.tHead.replaceChildren(head);
  table.tBodies[0].replaceChildren(...list.map((st) => {
    const tr = document.createElement("tr");
    tr.append(Object.assign(document.createElement("td"), { textContent: joinNames(st.names) }));
    for (const t of tasks) {
      const p = progressOf(st.work, t, stepCounts.get(`${t.app}/${t.item}`) ?? 0);
      tr.append(Object.assign(document.createElement("td"), { className: `p-cell ${p.cls}`, textContent: p.text, title: p.title }));
    }
    return tr;
  }));
  if (!list.length) {
    const tr = document.createElement("tr");
    tr.append(Object.assign(document.createElement("td"), { textContent: "Nobody has joined yet.", colSpan: tasks.length + 1 }));
    table.tBodies[0].replaceChildren(tr);
  }
}

initSavedClasses().catch((e) => say("#c-note", e.message, "bad"));
