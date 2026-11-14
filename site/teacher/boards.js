// The teacher portal's ESP boards: set up each of the school's ESP boards once. The server gives it a label, its
// own WiFi name and password, and a sticker code; this page flashes it (over USB, with ArduinoPath's own uploader)
// with a small set-up sketch that makes that WiFi, and records the board's chip (MAC address), so ArduinoPath can
// tell a student's board from everyone else's.

import { getAccess, clearAccess } from "/shared/access.js";

const $ = (s) => document.querySelector(s);
const access = getAccess();
const auth = { Authorization: `Bearer ${access.value}` };
let espBoards = []; // catalogue boards that are ESP boards
let boards = [];

const say = (text, kind = "") => { const n = $("#b-note"); n.textContent = text; n.className = `note ${kind}`; };

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

const kindName = (id) => espBoards.find((b) => b.id === id)?.name ?? id;

function button(text, onclick, cls = "btn btn-plain") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.textContent = text;
  b.addEventListener("click", onclick);
  return b;
}

function cell(tr, content) {
  const td = document.createElement("td");
  if (content instanceof Node) td.append(content);
  else td.textContent = content;
  tr.append(td);
}

const code = (text) => Object.assign(document.createElement("code"), { textContent: text });

/** The next free label: ESP-01, ESP-02... */
function nextLabel() {
  const used = new Set(boards.map((b) => b.label.toUpperCase()));
  for (let i = 1; i < 1000; i++) {
    const l = `ESP-${String(i).padStart(2, "0")}`;
    if (!used.has(l)) return l;
  }
  return "";
}

function draw() {
  const table = $("#b-table");
  table.hidden = boards.length === 0;
  $("#b-print").hidden = boards.length === 0;
  table.tBodies[0].replaceChildren(...boards.map((b) => {
    const tr = document.createElement("tr");
    cell(tr, b.label);
    cell(tr, kindName(b.kind));
    cell(tr, code(b.ssid));
    cell(tr, code(b.password));
    cell(tr, code(b.code));
    cell(tr, b.student || "Free");
    cell(tr, b.flashed_at ? "✓" : "Not yet");
    const td = document.createElement("td");
    td.append(button(b.flashed_at ? "Flash again" : "Flash it", () => flash(b).catch((e) => say(e.message, "bad"))));
    if (b.student) td.append(" ", button("Free it", async () => {
      if (!confirm(`Take ${b.label} off ${b.student}? Another student can then claim it.`)) return;
      await api("POST", `/api/teacher/boards/${b.id}/release`);
      await load();
    }));
    td.append(" ", button("Delete", async () => {
      if (!confirm(`Forget ${b.label}? Students won't be able to claim it. (Set it up again to use it.)`)) return;
      await api("DELETE", `/api/teacher/boards/${b.id}`);
      await load();
    }));
    tr.append(td);
    return tr;
  }));
  if (!$("#b-label").value || boards.some((b) => b.label.toUpperCase() === $("#b-label").value.toUpperCase())) $("#b-label").value = nextLabel();
  // the stickers, for printing
  $("#stickers").replaceChildren(...boards.map((b) => {
    const d = Object.assign(document.createElement("div"), { className: "sticker" });
    d.append(Object.assign(document.createElement("b"), { textContent: b.label }), "Code ", code(b.code), document.createElement("br"), `WiFi: ${b.ssid}`);
    return d;
  }));
}

async function load() {
  boards = (await api("GET", "/api/teacher/boards")).boards;
  draw();
}

/** Flashes a board with its set-up sketch and records its chip. */
async function flash(b) {
  const log = $("#b-log");
  let text = "";
  const write = (s) => { text = s; log.textContent = text; log.hidden = false; log.scrollTop = log.scrollHeight; };
  const realboard = await import("/arduinopath/js/realboard.js");
  if (!realboard.supported) throw new Error(realboard.NO_SERIAL_MESSAGE);
  const kind = espBoards.find((x) => x.id === b.kind);
  say(`Pick ${b.label} (${kind.name}) in the box your browser shows.`);
  const port = await realboard.requestPort();
  if (!port) { say("No board was picked."); return; }
  const { code: sketch } = await api("GET", `/api/teacher/boards/${b.id}/sketch`);
  say(`Setting up ${b.label}: compiling, then uploading. Hold the board's BOOT button if it says Connecting for a long time.`);
  let chip = null;
  const job = await realboard.upload(sketch, kind, "", port, (j) => {
    write(`${j.output ?? ""}${j.state === "uploading" ? `\nUploading ${j.progress || 0}%` : ""}`);
  }, { onChip: (c) => { chip = c; } });
  if (job.state === "failed" || job.result?.ok === false) {
    say(`${b.label} couldn't be set up: ${job.error || "the compiler found a problem"}. Check the board type, then press Flash it to try again.`, "bad");
    return;
  }
  if (!chip?.mac) {
    say(`${b.label} was flashed, but its chip couldn't be read. Press Flash again.`, "bad");
    return;
  }
  await api("POST", `/api/teacher/boards/${b.id}/flashed`, { mac: chip.mac });
  say(`${b.label} is set up ✓ Its WiFi ${b.ssid} is on now (join it with a phone to check). Write ${b.label} on the board and stick its code on it.`, "good");
  await load();
}

async function init() {
  if (access.kind !== "teacher") return;
  const cat = await fetch("/arduinopath/data/catalogue.json").then((r) => r.json());
  espBoards = cat.boards.filter((b) => /^esp(8266|32):/.test(b.fqbn ?? ""));
  $("#b-kind").replaceChildren(...espBoards.map((b) => new Option(b.name, b.id)));
  if (!window.isSecureContext) $("#b-insecure").hidden = false;
  $("#b-setup").addEventListener("click", async () => {
    const btn = $("#b-setup");
    btn.disabled = true;
    try {
      const b = await api("POST", "/api/teacher/boards", { label: $("#b-label").value.trim() || nextLabel(), kind: $("#b-kind").value });
      boards.push(b);
      draw();
      await flash(b);
    } catch (e) {
      say(e.message, "bad");
    } finally {
      btn.disabled = false;
    }
  });
  $("#b-print").addEventListener("click", () => window.print());
  await load();
}

init().catch((e) => say(e.message, "bad"));
