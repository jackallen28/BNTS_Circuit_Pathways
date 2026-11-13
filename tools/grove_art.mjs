// Draws ArduinoPath's Grove parts (site/arduinopath/parts/grove-*/): the Fritzing library doesn't
// have most Grove modules, so Circuit Pathways draws them all in one style. Each part gets
// part.json (legs, behaviour for the simulator, where the Grove socket is), breadboard.svg (the
// module) and schematic.svg (a box with its four Grove pins). Run it after changing a drawing:
//   node tools/grove_art.mjs
// The art uses only SVG attributes (no style), because the app's security policy blocks inline styles.
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const grove = JSON.parse(readFileSync(join(root, "site/shared/grove/grove.json"), "utf8"));
const OUT = join(root, "site/arduinopath/parts");
const PCB = "#1f5fa8", PCB_EDGE = "#123e72", SILK = "#ffffff";
const CABLE = Object.fromEntries(grove.cable.map((c) => [c.id, c.colour]));

const r = (n) => Math.round(n * 100) / 100;

/** A Grove socket (white, 4 pins) with its top-left at x,y. Returns the svg and each pin's centre. */
function socket(x, y) {
  const pins = [0, 1, 2, 3].map((i) => ({ x: r(x + 6 + i * 8), y: r(y + 9) }));
  const svg = `<rect x="${x}" y="${y}" width="36" height="15" rx="1.5" fill="#f3f3f0" stroke="#9c9c96" stroke-width="1"/>` +
    `<rect x="${x + 3}" y="${y + 3}" width="30" height="5" rx="1" fill="#d9d9d2"/>` +
    pins.map((p) => `<rect x="${r(p.x - 1.6)}" y="${r(p.y - 1.6)}" width="3.2" height="3.2" fill="#4a4a46"/>`).join("");
  return { svg, pins };
}

function pcb(w, h, label, labelY = 13) {
  const holes = [[7, 7], [w - 7, 7]].map(([cx, cy]) => `<circle cx="${cx}" cy="${cy}" r="3.4" fill="#e9e9e9" stroke="#b5b5b5" stroke-width="0.8"/>`).join("");
  return `<rect x="1" y="1" width="${w - 2}" height="${h - 2}" rx="5" fill="${PCB}" stroke="${PCB_EDGE}" stroke-width="1.5"/>${holes}` +
    `<text x="${w / 2}" y="${labelY}" font-family="Arial, Helvetica, sans-serif" font-size="6.5" font-weight="bold" fill="${SILK}" text-anchor="middle">${label}</text>`;
}

// Each module's drawing. w,h in 0.01 inch (80 = about 20 mm, one Grove unit).
const ART = {
  "grove-led": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "LED")}<circle cx="40" cy="36" r="14" fill="currentColor" opacity="0.92" stroke="#00000055" stroke-width="1"/><circle cx="35" cy="31" r="4" fill="#ffffff" opacity="0.55"/><text x="58" y="42" font-family="Arial" font-size="7" fill="${SILK}">+</text>`, socketAt: [22, 61] }),
  "grove-button": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "BUTTON")}<rect x="25" y="21" width="30" height="30" rx="2" fill="#2d2d2d"/><circle cx="40" cy="36" r="10" fill="#4a4a4a" stroke="#1a1a1a" stroke-width="1"/><circle cx="37" cy="33" r="3" fill="#6a6a6a"/>`, socketAt: [22, 61] }),
  "grove-micro-switch": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "MICRO SWITCH")}<rect x="18" y="30" width="44" height="20" rx="2" fill="#262626"/><line x1="22" y1="27" x2="66" y2="20" stroke="#c8c8c8" stroke-width="2.5" stroke-linecap="round"/><circle cx="66" cy="20" r="3" fill="#c8c8c8"/><rect x="30" y="26" width="5" height="5" fill="#b33"/>`, socketAt: [22, 61] }),
  "grove-servo": () => ({ w: 130, h: 80, body:
    `<rect x="4" y="16" width="86" height="46" rx="4" fill="#25307a" stroke="#141a4a" stroke-width="1.5"/>` +
    `<rect x="0" y="34" width="94" height="8" rx="2" fill="#1c255f"/>` +
    `<text x="58" y="56" font-family="Arial" font-size="7" font-weight="bold" fill="#dfe4ff" text-anchor="middle">SERVO</text>` +
    `<g id="horn"><circle cx="28" cy="39" r="8" fill="#f2f2f2" stroke="#999" stroke-width="1"/><rect x="24" y="8" width="8" height="34" rx="4" fill="#f7f7f7" stroke="#999" stroke-width="1"/></g>` +
    `<path d="M90 50 C102 50 98 66 108 66" fill="none" stroke="#333" stroke-width="3"/>` +
    `<rect x="88" y="58" width="40" height="20" rx="3" fill="#fafafa" stroke="#999" stroke-width="1"/>`, socketAt: [90, 61], plug: true }),
  "grove-ultrasonic": () => ({ w: 160, h: 80, body:
    `${pcb(160, 80, "ULTRASONIC RANGER")}` +
    [44, 116].map((cx) => `<circle cx="${cx}" cy="40" r="22" fill="#cfd3d6" stroke="#8b9196" stroke-width="2"/><circle cx="${cx}" cy="40" r="15" fill="#2f2f2f"/><circle cx="${cx}" cy="40" r="11" fill="#555" opacity="0.6"/>`).join(""),
    socketAt: [62, 61] }),
  "grove-rotary": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "ROTARY ANGLE")}<circle cx="40" cy="38" r="17" fill="#d9d9d9" stroke="#8a8a8a" stroke-width="1.5"/><g id="knob"><circle cx="40" cy="38" r="11" fill="#3a3a3a"/><line x1="40" y1="38" x2="40" y2="28" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/></g>`, socketAt: [22, 61] }),
  "grove-light": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "LIGHT SENSOR")}<circle cx="40" cy="37" r="11" fill="#e8a33a" stroke="#9c6416" stroke-width="1.2"/><path d="M33 33 h3 v4 h3 v-4 h3 v4 h3 v-4 h2" fill="none" stroke="#7a3a0a" stroke-width="1.2"/><circle cx="40" cy="37" r="11" fill="#ffffff" opacity="0.15"/>`, socketAt: [22, 61] }),
  "grove-moisture": () => ({ w: 80, h: 160, body:
    `<path d="M1 6 a5 5 0 0 1 5 -5 h68 a5 5 0 0 1 5 5 v74 h-12 v74 l-6 5 l-6 -5 v-74 h-30 v74 l-6 5 l-6 -5 v-74 h-12 z" fill="${PCB}" stroke="${PCB_EDGE}" stroke-width="1.5"/>` +
    `<rect x="16" y="82" width="7" height="68" fill="#d8c25a"/><rect x="57" y="82" width="7" height="68" fill="#d8c25a"/>` +
    `<text x="40" y="44" font-family="Arial" font-size="6.5" font-weight="bold" fill="${SILK}" text-anchor="middle">MOISTURE</text>`,
    socketAt: [22, 4] }),
  "grove-relay": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "RELAY")}<rect x="16" y="20" width="40" height="30" rx="2" fill="#2a5fd0" stroke="#173a85" stroke-width="1.2"/><text x="36" y="38" font-family="Arial" font-size="7" font-weight="bold" fill="#fff" text-anchor="middle">RELAY</text><rect x="60" y="22" width="14" height="26" rx="1" fill="#2f9c4a"/><circle id="relay-led" cx="67" cy="54" r="3" fill="#550000"/>`, socketAt: [22, 61] }),
  "grove-buzzer": () => ({ w: 80, h: 80, body: `${pcb(80, 80, "BUZZER")}<circle cx="40" cy="37" r="15" fill="#1e1e1e" stroke="#000" stroke-width="1"/><circle cx="40" cy="37" r="3" fill="#444"/><text x="57" y="27" font-family="Arial" font-size="7" fill="${SILK}">+</text>`, socketAt: [22, 61] }),
};

const LEG_NAMES = ["yellow wire: signal (SIG)", "white wire: second signal (not used)", "red wire: power (VCC)", "black wire: GND"];
const GROVE_PIN = ["sig", "sig2", "vcc", "gnd"];

function schematic(name) {
  const w = 90, h = 54;
  const lines = ["SIG", "NC", "VCC", "GND"].map((t, i) => {
    const y = 10 + i * 11;
    return `<line x1="0" y1="${y}" x2="18" y2="${y}" stroke="#000" stroke-width="1.2"/><text x="21" y="${y + 2.5}" font-family="Arial" font-size="7" fill="#000">${t}</text>`;
  }).join("");
  return {
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w / 100}in" height="${h / 100}in"><rect x="18" y="2" width="70" height="50" fill="#fff" stroke="#000" stroke-width="1.4"/>${lines}<text x="${18 + 35 + 8}" y="50" font-family="Arial" font-size="6" fill="#000" text-anchor="middle">${name.replace(/^Grove /, "")}</text></svg>`,
    w, h, at: (i) => ({ x: 0, y: 10 + i * 11, dir: "left" }),
  };
}

const index = JSON.parse(readFileSync(join(OUT, "index.json"), "utf8"));
for (const [type, mod] of Object.entries(grove.modules)) {
  const art = ART[type]();
  const sock = socket(art.socketAt[0], art.socketAt[1]);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${art.w} ${art.h}" width="${art.w / 100}in" height="${art.h / 100}in"><g>${art.body}${sock.svg}</g></svg>\n`;
  const sim = mod.sim;
  const sch = schematic(mod.name);
  const part = {
    type, title: mod.name, art: "circuitpathways", licence: "Drawn for Circuit Pathways (tools/grove_art.mjs)",
    behaviour: sim.behaviour, unit: "0.01in",
    legs: sim.legs.map((id, i) => ({ id, name: LEG_NAMES[i], grove: GROVE_PIN[i] })),
    footprint: null,
    ...(type === "grove-led" ? { colors: { blue: "#2367e0", green: "#22b33a", red: "#e8221b", white: "#eef2f5", yellow: "#f5cf1d" } } : {}),
    ...(sim.switch ? { switch: sim.switch, idle: sim.idle } : {}),
    ...(sim.moisture_rises ? { moisture_rises: true } : {}),
    test_as: sim.test_as,
    grove: { ports: mod.ports, socket: sock.pins.map((p, i) => ({ leg: sim.legs[i], ...p, colour: CABLE[GROVE_PIN[i]] })) },
    breadboard: { file: "breadboard.svg", width: art.w, height: art.h, connectors: Object.fromEntries(sim.legs.map((id, i) => [id, sock.pins[i]])) },
    schematic: { file: "schematic.svg", width: sch.w, height: sch.h, connectors: Object.fromEntries(sim.legs.map((id, i) => [id, sch.at(i)])) },
  };
  const dir = join(OUT, type);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "breadboard.svg"), svg);
  writeFileSync(join(dir, "schematic.svg"), sch.svg + "\n");
  writeFileSync(join(dir, "part.json"), JSON.stringify(part, null, 2) + "\n");
  if (!index.parts.includes(type)) index.parts.push(type);
}
writeFileSync(join(OUT, "index.json"), JSON.stringify(index, null, 2) + "\n");
console.log(`Drew ${Object.keys(grove.modules).length} Grove parts in ${OUT}`);
