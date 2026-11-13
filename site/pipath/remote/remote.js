// The Pi Link page: pair with a Pi, see its 40-pin header, and control the pins.

import { getAccess } from "/shared/access.js";
import { PiRemote, HEADER, USABLE } from "./pi-remote.js";

if (!getAccess()) location.replace("/?need=class");

const $ = (s) => document.querySelector(s);
const remote = new PiRemote();
window.piRemote = remote; // handy for trying things in the browser's console, and for the tests

// ---- the drifting squares, as on the other pages
{
  const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#815a99"];
  for (let i = 0; i < 8; i++) {
    const s = 14 + Math.random() * 30;
    const sq = document.createElement("i");
    sq.style.cssText = `left:${Math.random() * 100}%;top:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};animation-delay:${-Math.random() * 20}s;animation-duration:${16 + Math.random() * 18}s`;
    $(".sky").append(sq);
  }
}

$("#cmd").textContent = `curl -fsSL ${location.origin}/pipath/remote/install.sh | sudo bash -s -- CPK1-XXXXXXXX-XXXXXXXXXX`;

function say(text, kind = "") {
  const s = $("#status");
  s.textContent = text;
  s.className = `status ${kind}`;
}

function log(text, bad = false) {
  const li = document.createElement("li");
  li.textContent = `${new Date().toLocaleTimeString("en-AU")}  ${text}`;
  if (bad) li.className = "bad";
  const list = $("#log");
  list.append(li);
  while (list.children.length > 80) list.firstChild.remove();
  list.scrollTop = list.scrollHeight;
}

// ---- pairing
$("#pair").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.currentTarget.querySelector("button");
  btn.disabled = true;
  say("Connecting...");
  try {
    await remote.connect($("#code").value);
  } catch (err) {
    say(err.message, "bad");
    if (err.code === "no_class") location.replace("/?need=class");
  } finally {
    btn.disabled = false;
  }
});

remote.addEventListener("status", (e) => {
  const { state, name, reason, reconnecting } = e.detail;
  const connected = state === "connected" || state === "pi-offline";
  $("#panel").hidden = !connected;
  $("#connect").hidden = connected;
  if (connected) $("#pi-name").textContent = name;
  if (state === "connected") { say(""); log(`Connected to ${name}.`); remote.command({ op: "read" }).catch(() => {}); }
  if (state === "pi-offline") { $("#pi-info").textContent = "The Pi app isn't running right now. Start it again on the Pi; this page will carry on."; $("#pi-info").className = "status bad"; log("The Pi went offline.", true); stopBlink(); }
  if (state === "connected") { $("#pi-info").className = "status"; }
  if (state === "closed") { say(reason || "Disconnected.", "bad"); log(reason || "Disconnected.", true); stopBlink(); }
  if (state === "idle") stopBlink();
  if (reconnecting) say("Lost the connection. Trying again...", "bad");
});

remote.addEventListener("hello", (e) => {
  const h = e.detail;
  $("#pi-info").textContent = `${h.model}. Pins ${h.pins[0]} to ${h.pins[1]}. ${h.backend === "mock" ? "(A pretend Pi: no real pins.)" : ""}`;
});

remote.addEventListener("problem", (e) => { log(e.detail.message, true); say(e.detail.message, "bad"); });
remote.addEventListener("pong", () => {});

$("#leave").addEventListener("click", () => { remote.disconnect(); $("#connect").hidden = false; $("#panel").hidden = true; say(""); });

// ---- the header
let selected = null; // the GPIO (BCM) number
const pinButtons = new Map();

function buildHeader() {
  const box = $("#header");
  for (let row = 0; row < 20; row++) {
    for (const side of [0, 1]) {
      const phys = row * 2 + 1 + side;
      const what = HEADER[phys];
      const usable = USABLE(what);
      const el = document.createElement(usable ? "button" : "div");
      el.className = `hp ${side ? "right" : ""}`;
      const dot = document.createElement("i");
      dot.className = "dot";
      const label = document.createElement("span");
      label.textContent = usable ? `${what}` : String(what);
      const num = document.createElement("small");
      num.textContent = `#${phys}`;
      el.append(dot, label, num);
      if (usable) {
        el.type = "button";
        el.classList.add("hp-btn");
        el.setAttribute("aria-label", `GPIO ${what}, physical pin ${phys}`);
        el.addEventListener("click", () => select(what));
        pinButtons.set(what, { el, dot });
      } else {
        el.classList.add(what === "5V" ? "pwr5" : what === "3V3" ? "pwr3" : what === "GND" ? "gnd" : "id");
      }
      box.append(el);
    }
  }
}

function paint() {
  for (const [pin, { el, dot }] of pinButtons) {
    const p = remote.pins[String(pin)];
    let cls = "dot";
    if (p?.mode === "out") cls += p.value ? " out-on" : " out-off";
    else if (p?.mode === "pwm") cls += " pwm";
    else if (p) cls += p.value ? " in-hi" : " in-lo";
    dot.className = cls;
    el.setAttribute("aria-pressed", String(pin === selected));
  }
  showControls();
}

function select(pin) {
  selected = pin;
  paint();
}

function showControls() {
  const box = $("#pin-box");
  box.hidden = selected == null;
  $("#pin-title").textContent = selected == null ? "Pick a pin" : `GPIO ${selected} (physical pin ${Object.keys(HEADER).find((k) => HEADER[k] === selected)})`;
  if (selected == null) return;
  const p = remote.pins[String(selected)];
  const mode = p?.mode ?? "none";
  for (const r of document.querySelectorAll('input[name="mode"]')) r.checked = r.value === mode;
  $("#ctl-out").hidden = mode !== "out";
  $("#ctl-pwm").hidden = mode !== "pwm";
  $("#ctl-in").hidden = !["in", "in_up", "in_down"].includes(mode);
  if (mode === "out") {
    $("#toggle").textContent = p.value ? "Turn OFF" : "Turn ON";
    $("#toggle").setAttribute("aria-pressed", String(Boolean(p.value)));
  }
  if (mode === "pwm" && document.activeElement !== $("#duty")) {
    $("#duty").value = Math.round(p.duty * 100);
    $("#duty-out").textContent = `${Math.round(p.duty * 100)}%`;
  }
  const rd = $("#reading");
  if (p) { rd.textContent = p.value ? "HIGH" : "LOW"; rd.className = `hp-reading ${p.value ? "hi" : ""}`; }
}

async function act(promise, what) {
  try {
    await promise;
    if (what) log(what);
  } catch (err) {
    log(err.message, true);
    say(err.message, "bad");
  }
}

for (const r of document.querySelectorAll('input[name="mode"]')) {
  r.addEventListener("change", () => {
    if (selected == null) return;
    stopBlink();
    if (r.value === "none") act(remote.release(selected), `GPIO ${selected}: let go.`);
    else act(remote.setMode(selected, r.value), `GPIO ${selected}: ${r.parentElement.textContent.trim()}.`);
  });
}

$("#toggle").addEventListener("click", () => {
  const on = !remote.pins[String(selected)]?.value;
  act(remote.write(selected, on ? 1 : 0), `GPIO ${selected} ${on ? "ON" : "OFF"}.`);
});

$("#duty").addEventListener("input", () => {
  const v = Number($("#duty").value);
  $("#duty-out").textContent = `${v}%`;
  remote.pwm(selected, v / 100).catch((e) => log(e.message, true));
});

remote.addEventListener("state", () => paint());

// ---- quick tries
let blinkTimer = 0;
function stopBlink() {
  if (!blinkTimer) return;
  clearInterval(blinkTimer);
  blinkTimer = 0;
  $("#blink").textContent = "Blink an LED on GPIO 17";
}

$("#blink").addEventListener("click", async () => {
  if (blinkTimer) {
    stopBlink();
    act(remote.write(17, 0), "Stopped blinking.");
    return;
  }
  select(17);
  try {
    await remote.setMode(17, "out");
  } catch (err) {
    log(err.message, true);
    return;
  }
  let on = 0;
  $("#blink").textContent = "Stop blinking";
  log("Blinking GPIO 17.");
  blinkTimer = setInterval(() => {
    on ^= 1;
    remote.write(17, on).catch((err) => { log(err.message, true); stopBlink(); });
  }, 500);
});

$("#alloff").addEventListener("click", () => {
  stopBlink();
  act(remote.allOff(), "Everything is off.");
});

buildHeader();
