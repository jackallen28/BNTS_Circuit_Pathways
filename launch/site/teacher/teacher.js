// The teacher page. Signing in gives a teacher token (kept in this browser
// for 12 hours). A class code is made by the server from a signature; the
// class name, the class file and every student's work stay on the teacher's
// computer, read and written only in this browser.

import { getAccess, clearAccess, postJSON } from "/shared/access.js";
import { writeZip, readZip } from "/shared/local/zip.js";
import { readSaveFile } from "/shared/local/savefile.js";
import { joinNames } from "/shared/local/validate.js";

const $ = (s) => document.querySelector(s);

const access = getAccess();
if (!access || access.kind !== "teacher") location.replace("/");

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

// ---- 1. a class code
let cls = null; // { code, expires_at }

function showCode() {
  $("#code-box").hidden = !cls;
  if (!cls) return;
  $("#code").textContent = cls.code;
  $("#code-note").textContent = `Works until the end of ${fmt(cls.expires_at - 12 * 3600 * 1000)}.`;
}

$("#make").addEventListener("click", async () => {
  const btn = $("#make");
  btn.disabled = true;
  say("#make-note", "Making a code...");
  try {
    const res = await postJSON("/api/teacher/class", { days: Number($("#days").value) }, { Authorization: `Bearer ${access.value}` });
    cls = { code: res.code, expires_at: res.expires_at };
    showCode();
    say("#make-note", "");
  } catch (err) {
    if (err.status === 401) {
      clearAccess();
      location.replace("/");
      return;
    }
    say("#make-note", err.status === undefined ? "Circuit Pathways can't be reached. Check your internet connection." : err.message, "bad");
  } finally {
    btn.disabled = false;
  }
});

$("#copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(cls.code);
    $("#copy").textContent = "Copied ✓";
  } catch {
    $("#copy").textContent = "Select the code and copy it";
  }
  setTimeout(() => { $("#copy").textContent = "Copy the code"; }, 2500);
});

// ---- 2. the class file and student work
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
    for (const text of [joinNames(s.names), s.school, String(s.projects), s.updated ? new Date(s.updated).toLocaleString("en-AU") : ""]) {
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

async function addStudentFile(name, bytes) {
  const f = await readSaveFile(bytes);
  if (!f.profile.names.length) throw new Error("has no name in it");
  const updated = Math.max(0, ...f.sketches.map((s) => s.updated_at), ...f.progress.map((p) => p.updated_at));
  const projects = new Set([...f.sketches, ...f.progress].map((x) => x.project_id)).size;
  const same = students.findIndex((s) => s.names.join("|").toLowerCase() === f.profile.names.join("|").toLowerCase() && s.school.toLowerCase() === f.profile.school.toLowerCase());
  const rec = { file: name, bytes, names: f.profile.names, school: f.profile.school, projects, updated };
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
      if (!/\.circuit$/i.test(file.name)) {
        const inner = await readZip(bytes, { maxEntries: 600, maxEntryBytes: 9 << 20, maxTotalBytes: 256 << 20 }).catch(() => null);
        if (inner) {
          for (const [n, b] of inner) {
            if (!/\.circuit$/i.test(n)) continue;
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
    while (used.has(n.toLowerCase())) n = n.replace(/(\.circuit)?$/, "_2$1");
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
    cls = info.code && info.expires_at > Date.now() ? { code: info.code, expires_at: info.expires_at } : null;
    showCode();
    students = [];
    for (const [n, b] of entries) {
      if (n.startsWith("students/") && /\.circuit$/i.test(n)) await addStudentFile(n.slice(9), b).catch(() => {});
    }
    students.sort((a, b) => joinNames(a.names).localeCompare(joinNames(b.names)));
    drawStudents();
    say("#file-note", `Class opened${info.code && !cls ? ". Its class code has finished, so make a new one above" : ""}.`, "good");
  } catch (err) {
    say("#file-note", /newer/.test(err.message) ? err.message : "That file can't be opened. Pick a .circuitclass file saved from this page.", "bad");
  }
});

$("#save-all").addEventListener("click", () => {
  const files = students.map((s) => ({ name: s.file, data: s.bytes }));
  download(writeZip(files), `Everyone_${new Date().toISOString().slice(0, 10)}.zip`, "application/zip");
});

showCode();
