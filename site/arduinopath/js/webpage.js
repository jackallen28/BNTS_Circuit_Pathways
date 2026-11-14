// The Web Page Designer's model and code maker. A page design (a title, colours, WiFi, and a list of elements:
// headings, text, buttons, switches, sliders, colour pickers, readings and status lights) becomes a complete,
// commented ESP sketch with a web server. Everything here is pure (tested in Node and in the simulator);
// dialogs/webpage.js is the drag-and-drop designer.
//
//   generateSketch(design, board) → C++ code
//   connections(item, board)      → what an element is wired to, for the badges and the "Try it" bench
//   tryIt(design, board)          → a pretend board to try the page on before uploading

export const THEMES = {
  teal: { name: "Teal", bg: "#e8fbfc", card: "#ffffff", ink: "#08363a", accent: "#19c1ca", accentInk: "#ffffff" },
  purple: { name: "Purple", bg: "#f3eef8", card: "#ffffff", ink: "#2e1d3b", accent: "#704988", accentInk: "#ffffff" },
  dark: { name: "Night", bg: "#111827", card: "#1f2937", ink: "#f3f4f6", accent: "#22d3ee", accentInk: "#0b1220" },
  sunset: { name: "Sunset", bg: "#fff4e6", card: "#ffffff", ink: "#3b1f0b", accent: "#f97316", accentInk: "#ffffff" },
};

/** The elements, in palette order: what each is called, its symbol, and what it does, in a few words. */
export const ELEMENTS = {
  heading: { name: "Heading", symbol: "H", group: "words", tip: "Big words to start a part of the page" },
  text: { name: "Text", symbol: "¶", group: "words", tip: "A sentence or two about your project" },
  button: { name: "Button", symbol: "●", group: "control", tip: "Press it to switch something on or off, or beep" },
  switch: { name: "Switch", symbol: "⇄", group: "control", tip: "An on/off switch that shows if it's on" },
  slider: { name: "Slider", symbol: "↔", group: "control", tip: "Pick a number: how bright, how fast, how high" },
  colour: { name: "Colour", symbol: "◐", group: "control", tip: "Pick a colour for an RGB LED" },
  reading: { name: "Reading", symbol: "#", group: "show", tip: "Show a number from a sensor, or as a bar" },
  status: { name: "Status light", symbol: "◉", group: "show", tip: "A light on the page: is it on? is something there?" },
};

/** Older name, still used by the tests and the workspace. */
export const ITEM_KINDS = Object.fromEntries(Object.entries(ELEMENTS).map(([k, e]) => [k, e.name]));

export const BUTTON_ACTIONS = { on: "Turn a pin ON", off: "Turn a pin OFF", toggle: "Switch a pin on/off", beep: "Beep the buzzer", custom: "Something I'll write" };

/** What a reading can show (the C expression). */
export const READING_SOURCES = [
  { label: "Something I'll write in loop()", source: "" },
  { label: "Seconds since it started", source: "millis() / 1000" },
  { label: "A knob (POT_PIN)", source: "analogRead(POT_PIN)" },
  { label: "A light sensor (LDR_PIN)", source: "analogRead(LDR_PIN)" },
  { label: "A soil sensor (SOIL_PIN)", source: "analogRead(SOIL_PIN)" },
];

/** What a status light can show. "light" reads back an output the page itself switches. */
export const STATUS_SOURCES = {
  light: { label: "Is a light on?", mode: null },
  button: { label: "Is the button pressed? (BUTTON_PIN)", role: "BUTTON_PIN", mode: "INPUT_PULLUP", expr: "digitalRead(BUTTON_PIN) == LOW" },
  motion: { label: "Is something moving? (PIR_PIN)", role: "PIR_PIN", mode: "INPUT", expr: "digitalRead(PIR_PIN) == HIGH" },
};

/** Friendly names for the pretend parts on the "Try it" bench. */
const PART_NAMES = { POT_PIN: "Knob", LDR_PIN: "Light sensor", SOIL_PIN: "Soil sensor", BUTTON_PIN: "Button", PIR_PIN: "Motion sensor", BUZZER_PIN: "Buzzer" };
export const partName = (role) => PART_NAMES[role] ?? (role.startsWith("RGB_") ? "RGB LED" : role.replace(/_PIN$/, "").replace(/_/g, " ").toLowerCase().replace(/^led\b/, "LED").replace(/^\w/, (c) => c.toUpperCase()));

/** The colour an LED role glows on the bench. */
export function ledColour(role) {
  const m = /(RED|YELLOW|GREEN|BLUE|WHITE)/.exec(role);
  return { RED: "#ff3b30", YELLOW: "#ffcc00", GREEN: "#34c759", BLUE: "#0a84ff", WHITE: "#f5f5f5" }[m?.[1]] ?? "#ff3b30";
}

/** A C name from a label: "Feed the fish!" → "feedTheFish". */
export function cName(label, fallback = "item") {
  const words = String(label ?? "").normalize("NFKD").replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/).filter(Boolean);
  let n = words.map((w, i) => (i ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w.toLowerCase())).join("");
  if (!n) n = fallback;
  if (/^[0-9]/.test(n)) n = `${fallback}${n}`;
  return n.slice(0, 24);
}

const html = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const cstr = (s) => String(s ?? "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
// inside R"( ... )" the only thing that can't appear is )"
const raw = (s) => s.replace(/\)"/g, ') "');
const cap = (s) => s[0].toUpperCase() + s.slice(1);
const kebab = (s) => `/${s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
/** The variable that remembers whether an output is on: LED_PIN → ledPinOn. */
export const onVar = (role) => `${cName(role.replace(/_/g, " "), "pin")}On`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// names a sketch can't use for its own things (Arduino's and C's own functions)
const RESERVED = new Set(["time", "delay", "millis", "micros", "random", "min", "max", "abs", "map", "round", "sin", "cos", "tan", "tone",
  "read", "write", "index", "select", "signal", "sleep", "exit", "free", "log", "exp", "pow", "sqrt", "rand", "printf", "main", "new", "delete",
  "int", "long", "float", "double", "char", "bool", "byte", "word", "string", "class", "struct", "return", "if", "else", "for", "while", "do",
  "switch", "case", "break", "continue", "default", "const", "static", "void", "true", "false", "html", "pin", "value", "hexValue"]);

/** Every item with a unique C name, the function that runs when it's used, and the address it uses. */
export function namedItems(design) {
  const used = new Set(["page", "showPage", "setup", "loop", "server", ...RESERVED]);
  return (design.items ?? []).map((it, i) => {
    let base = cName(it.name || it.label || it.text, it.kind);
    if (RESERVED.has(base)) base = `${base}Value`;
    let n = base;
    for (let k = 2; used.has(n) || used.has(`${n}Text`); k++) n = `${base}${k}`;
    used.add(n);
    // sliders and colours keep their value in cname, so the function that sets it is setCname; a switch is toggleCname
    const handler = it.kind === "slider" || it.kind === "colour" ? `set${cap(n)}` : it.kind === "switch" ? `toggle${cap(n)}` : n;
    if (handler !== n) used.add(handler);
    if (it.kind === "status") used.add(`${n}Text`);
    const path = kebab(it.kind === "switch" || it.kind === "colour" ? handler : n);
    return { ...it, cname: n, handler, path, index: i };
  });
}

// ---------------------------------------------------------------- what each element is wired to

/**
 * What an element connects to on the board: outputs it drives, inputs it reads.
 * @returns {{ dir: "out"|"in", role: string, pin: string, use: string }[]}
 */
export function connections(item, board) {
  const plan = board?.pin_plan ?? {};
  const pin = (role) => String(plan[role] ?? "?");
  const out = (role, use) => ({ dir: "out", role, pin: pin(role), use });
  const inn = (role, use) => ({ dir: "in", role, pin: pin(role), use });
  switch (item.kind) {
    case "button":
      if (item.action === "beep") return [out("BUZZER_PIN", "beep")];
      if (item.action === "custom" || !item.action) return [];
      return [out(item.pin || "LED_PIN", "digital")];
    case "switch": return [out(item.pin || "LED_PIN", "digital")];
    case "slider":
      if (!item.pin) return [];
      return [out(item.pin, item.pin === "BUZZER_PIN" ? "pitch" : "pwm")];
    case "colour": return ["RGB_RED", "RGB_GREEN", "RGB_BLUE"].map((r) => out(r, "pwm"));
    case "reading": return [...new Set(String(item.source ?? "").match(/\b[A-Z][A-Z0-9]*_PIN\b/g) ?? [])].map((r) => inn(r, "analog"));
    case "status": {
      const s = STATUS_SOURCES[item.source] ?? STATUS_SOURCES.light;
      return s.role ? [inn(s.role, "digital")] : [{ dir: "watch", role: item.pin || "LED_PIN", pin: pin(item.pin || "LED_PIN"), use: "state" }];
    }
    default: return [];
  }
}

/** Plain words for a connection badge: "→ LED_PIN (pin 25)", "← Knob (pin 34)". */
export function connectionText(c) {
  const arrow = c.dir === "in" ? "←" : c.dir === "watch" ? "◉" : "→";
  const what = c.dir === "in" ? partName(c.role) : c.role;
  return `${arrow} ${what} (pin ${c.pin})`;
}

/**
 * Two different parts sharing one real pin. (A NodeMCU has only one analog pin, A0, so a knob and a
 * light sensor can't both be on it; on an ESP32 the RGB LED shares pins with the red/yellow/green LEDs.)
 * @returns {{ pin: string, roles: string[], items: number[] }[]}
 */
export function pinClashes(design, board) {
  const byPin = new Map();
  (design.items ?? []).forEach((it, i) => {
    for (const c of connections(it, board)) {
      if (c.dir === "watch" || c.pin === "?") continue;
      const e = byPin.get(c.pin) ?? { pin: c.pin, roles: new Set(), items: new Set() };
      e.roles.add(c.role);
      e.items.add(i);
      byPin.set(c.pin, e);
    }
  });
  return [...byPin.values()].filter((e) => e.roles.size > 1).map((e) => ({ pin: e.pin, roles: [...e.roles], items: [...e.items] }));
}

// ---------------------------------------------------------------- drag and drop, as plain list changes

/** A new element of this kind, ready to drop on the page (picking pins the board has). */
export function defaultItem(kind, board) {
  const plan = board?.pin_plan ?? {};
  const has = (r) => r in plan;
  const led = has("LED_PIN") ? "LED_PIN" : Object.keys(plan).find((r) => r.startsWith("LED_")) ?? "";
  switch (kind) {
    case "heading": return { kind, text: "A heading" };
    case "text": return { kind, text: "Some words about my project." };
    case "button": return { kind, label: "Press me", action: led ? "toggle" : "custom", pin: led };
    case "switch": return { kind, label: "Light", pin: led };
    case "slider": return { kind, label: "Brightness", min: 0, max: 100, start: 50, pin: led };
    case "colour": return { kind, label: "Lamp colour", start: "#19c1ca" };
    case "reading": return { kind, label: "Knob", source: has("POT_PIN") ? "analogRead(POT_PIN)" : "millis() / 1000", style: "bar", max: board?.analog_max ?? 1023 };
    case "status": return { kind, label: "Light", source: "light", pin: led, onText: "On", offText: "Off" };
    default: throw new Error(`no element called ${kind}`);
  }
}

/** A copy of items with one moved from one place to another (the index is where it should end up). */
export function moveItem(items, from, to) {
  const list = [...items];
  if (from < 0 || from >= list.length) return list;
  const [it] = list.splice(from, 1);
  list.splice(clamp(to, 0, list.length), 0, it);
  return list;
}

/** A copy of items with a new one put in at index. */
export function insertItem(items, index, item) {
  const list = [...items];
  list.splice(clamp(index, 0, list.length), 0, item);
  return list;
}

/** Where a dragged thing lands: the gap above the first element whose middle is below the pointer. */
export function dropIndex(middles, y) {
  const i = middles.findIndex((m) => y < m);
  return i < 0 ? middles.length : i;
}

// ---------------------------------------------------------------- the page

/** The page's HTML, with %name% where today's numbers and states go. No scripts: it works in any phone browser. */
export function pageHTML(design) {
  const t = THEMES[design.theme] ?? THEMES.teal;
  const items = namedItems(design);
  const body = items.map((it) => {
    switch (it.kind) {
      case "heading": return `  <h2>${html(it.text)}</h2>`;
      case "text": return `  <p>${html(it.text)}</p>`;
      case "button": return `  <p><a class="btn" href="${it.path}">${html(it.label || "Press me")}</a></p>`;
      case "switch": return `  <p><a class="switch sw-%${it.cname}%" href="${it.path}"><span class="track"><span class="knob"></span></span> ${html(it.label || "Switch")} <b>%${it.cname}%</b></a></p>`;
      case "slider": return `  <form action="${it.path}">\n    <label>${html(it.label || "Slider")} <b>%${it.cname}%</b><br><input type="range" name="value" min="${Number(it.min ?? 0)}" max="${Number(it.max ?? 100)}" value="%${it.cname}%"></label>\n    <button class="btn">Set</button>\n  </form>`;
      case "colour": return `  <form action="${it.path}">\n    <label>${html(it.label || "Colour")}<br><input type="color" name="value" value="%${it.cname}%"></label>\n    <button class="btn">Set</button>\n  </form>`;
      case "reading": {
        const bar = it.style === "bar" ? `<br><meter min="0" max="${Number(it.max ?? 100)}" value="%${it.cname}%"></meter>` : "";
        return `  <p class="reading">${html(it.label || "Reading")}: <b>%${it.cname}%</b>${it.unit ? ` ${html(it.unit)}` : ""}${bar}</p>`;
      }
      case "status": return `  <p class="status st-%${it.cname}%"><span class="dot"></span> ${html(it.label || "Status")}: <b>%${it.cname}Text%</b></p>`;
      default: return "";
    }
  }).filter(Boolean).join("\n");
  const live = items.some((it) => it.kind === "reading" || (it.kind === "status" && it.source && it.source !== "light"));
  const refresh = live ? `\n<meta http-equiv="refresh" content="${clamp(Number(design.refresh ?? 5), 2, 60)}">` : "";
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">${refresh}
<title>${html(design.title || "My page")}</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 16px; background: ${t.bg}; color: ${t.ink}; text-align: center; }
  main { max-width: 420px; margin: 0 auto; padding: 16px; border-radius: 16px; background: ${t.card}; }
  h1 { color: ${t.accent}; }
  .btn { display: inline-block; min-width: 60%; padding: 14px 20px; border: 0; border-radius: 999px; background: ${t.accent}; color: ${t.accentInk}; font-size: 1.2em; text-decoration: none; }
  input[type=range], meter { width: 90%; }
  input[type=color] { width: 80px; height: 48px; border: 0; }
  .reading b { font-size: 1.6em; color: ${t.accent}; }
  .switch { color: inherit; text-decoration: none; font-size: 1.2em; }
  .switch .track { display: inline-block; vertical-align: middle; width: 52px; height: 28px; border-radius: 14px; background: #bbb; position: relative; }
  .switch .knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; }
  .switch.sw-on .track { background: ${t.accent}; }
  .switch.sw-on .knob { left: 27px; }
  .switch b { text-transform: uppercase; }
  .status .dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: #bbb; vertical-align: middle; }
  .status.st-on .dot { background: #34c759; box-shadow: 0 0 8px #34c759; }
</style>
</head>
<body>
<main>
  <h1>${html(design.title || "My page")}</h1>
${body}
</main>
</body>
</html>`;
}

// ---------------------------------------------------------------- the sketch

/**
 * The whole sketch.
 * @param {object} design  { title, theme, wifi: { mode: "hotspot"|"join", name, password }, refresh, items }
 * @param {object} board   content/arduinopath/boards/<id>.json (an ESP board)
 */
export function generateSketch(design, board) {
  const esp8266 = board?.family === "esp8266";
  const items = namedItems(design);
  const wifi = design.wifi ?? {};
  const join = wifi.mode === "join";
  const plan = board?.pin_plan ?? {};
  const all = items.flatMap((it) => connections(it, board).map((c) => ({ ...c, it })));
  // outputs the page switches on and off (their on/off is remembered in a variable, so the page can show it)
  const digitalOut = [...new Set(all.filter((c) => (c.dir === "out" && c.use === "digital") || c.dir === "watch").map((c) => c.role))];
  const otherOut = [...new Set(all.filter((c) => c.dir === "out" && c.use !== "digital").map((c) => c.role))].filter((r) => !digitalOut.includes(r));
  const inputs = [...new Set(all.filter((c) => c.dir === "in").map((c) => c.role))];
  const inputMode = (role) => Object.values(STATUS_SOURCES).find((s) => s.role === role)?.mode ?? "INPUT";
  const lines = [];
  const L = (...s) => lines.push(...s);

  L(`// ${design.title || "My page"}: a web page made with ArduinoPath's Web Page Designer.`,
    join
      ? `// Your board joins the WiFi called "${cstr(wifi.name)}". Open the address it prints in the Serial Monitor.`
      : `// On a phone, join the WiFi called "${cstr(wifi.name || "ArduinoPath")}", then open the address in the Serial Monitor.`,
    "");
  const roles = [...digitalOut, ...otherOut, ...inputs];
  for (const role of roles) L(`#define ${role} ${plan[role] ?? "2"}`);
  if (roles.length) L("");
  L(esp8266 ? "#include <ESP8266WiFi.h>" : "#include <WiFi.h>", esp8266 ? "#include <ESP8266WebServer.h>" : "#include <WebServer.h>", "");
  L("// ---- 1. WiFi ----",
    `const char* WIFI_NAME = "${cstr(wifi.name || (join ? "SchoolWiFi" : "ArduinoPath"))}";`,
    `const char* WIFI_PASSWORD = "${cstr(wifi.password || "circuit123")}";  // at least 8 characters`,
    "",
    esp8266 ? "ESP8266WebServer server(80);" : "WebServer server(80);",
    "");
  const values = items.filter((it) => it.kind === "slider" || it.kind === "reading" || it.kind === "colour");
  if (values.length || digitalOut.length) {
    L("// ---- 2. What the page remembers and shows (change readings in loop) ----");
    for (const role of digitalOut) L(`bool ${onVar(role)} = false;  // is ${role} on?`);
    for (const it of values) {
      if (it.kind === "colour") L(`String ${it.cname} = "${cstr(/^#[0-9a-fA-F]{6}$/.test(it.start ?? "") ? it.start : "#000000")}";`);
      else L(`int ${it.cname} = ${it.kind === "slider" ? Number(it.start ?? it.min ?? 0) : 0};`);
    }
    L("");
  }
  L("// ---- 3. The page ----", `const char PAGE[] = R"(${raw(pageHTML(design))}\n)";`, "",
    "// The page, with today's numbers put in where %name% is.",
    "String page() {",
    "  String html = PAGE;");
  for (const it of items) {
    if (it.kind === "slider" || it.kind === "reading") L(`  html.replace("%${it.cname}%", String(${it.cname}));`);
    else if (it.kind === "colour") L(`  html.replace("%${it.cname}%", ${it.cname});`);
    else if (it.kind === "switch") L(`  html.replace("%${it.cname}%", ${onVar(it.pin || "LED_PIN")} ? "on" : "off");`);
    else if (it.kind === "status") {
      const s = STATUS_SOURCES[it.source] ?? STATUS_SOURCES.light;
      L(`  bool ${it.cname} = ${s.expr ?? onVar(it.pin || "LED_PIN")};`,
        `  html.replace("%${it.cname}%", ${it.cname} ? "on" : "off");`,
        `  html.replace("%${it.cname}Text%", ${it.cname} ? "${cstr(it.onText || "Yes")}" : "${cstr(it.offText || "No")}");`);
    }
  }
  L("  return html;", "}", "", "void showPage() {", '  server.send(200, "text/html", page());', "}", "");

  if (items.some((it) => it.kind === "colour")) {
    L("// A colour like #ff8000 is three numbers in hexadecimal: red ff, green 80, blue 00.",
      "int hexValue(String colour, int at) {",
      "  int v = 0;",
      "  for (int i = at; i < at + 2; i++) {",
      "    char c = colour.charAt(i);",
      "    v = v * 16 + (c >= 'a' ? c - 'a' + 10 : (c >= 'A' ? c - 'A' + 10 : c - '0'));",
      "  }",
      "  return v;",
      "}", "");
  }

  const handlers = items.filter((it) => ["button", "switch", "slider", "colour"].includes(it.kind));
  if (handlers.length) L("// ---- 4. What happens when someone uses the page ----");
  const setOut = (role, on) => [`  ${onVar(role)} = ${on};`, `  digitalWrite(${role}, ${onVar(role)} ? HIGH : LOW);`];
  for (const it of handlers) {
    L(`void ${it.handler}() {`);
    const pin = it.pin || "LED_PIN";
    if (it.kind === "button") {
      if (it.action === "on") L(...setOut(pin, "true"));
      else if (it.action === "off") L(...setOut(pin, "false"));
      else if (it.action === "toggle") L(...setOut(pin, `!${onVar(pin)}`));
      else if (it.action === "beep") L("  tone(BUZZER_PIN, 880, 300);  // 880 beats a second, for 300 ms");
      else L(`  // What should "${cstr(it.label || "the button")}" do? Write it here.`);
      L(`  Serial.println("${cstr(it.label || "Button")} was pressed");`);
    } else if (it.kind === "switch") {
      L(...setOut(pin, `!${onVar(pin)}`), `  Serial.print("${cstr(it.label || "Switch")}: ");`, `  Serial.println(${onVar(pin)} ? "on" : "off");`);
    } else if (it.kind === "slider") {
      L(`  ${it.cname} = server.arg("value").toInt();`);
      if (it.pin === "BUZZER_PIN") L(`  if (${it.cname} > 0) tone(BUZZER_PIN, ${it.cname});  // a higher number is a higher note`, "  else noTone(BUZZER_PIN);");
      else if (it.pin) L(`  analogWrite(${it.pin}, map(${it.cname}, ${Number(it.min ?? 0)}, ${Number(it.max ?? 100)}, 0, 255));`);
      else L(`  // Use ${it.cname} here (it's between ${Number(it.min ?? 0)} and ${Number(it.max ?? 100)}).`);
      L(`  Serial.print("${cstr(it.label || "Slider")}: ");`, `  Serial.println(${it.cname});`);
    } else if (it.kind === "colour") {
      L(`  ${it.cname} = server.arg("value");`,
        `  analogWrite(RGB_RED, hexValue(${it.cname}, 1));`,
        `  analogWrite(RGB_GREEN, hexValue(${it.cname}, 3));`,
        `  analogWrite(RGB_BLUE, hexValue(${it.cname}, 5));`,
        `  Serial.print("${cstr(it.label || "Colour")}: ");`, `  Serial.println(${it.cname});`);
    }
    L("  showPage();", "}", "");
  }

  L("void setup() {", "  Serial.begin(115200);");
  for (const role of [...digitalOut, ...otherOut]) L(`  pinMode(${role}, OUTPUT);`);
  for (const role of inputs) L(`  pinMode(${role}, ${inputMode(role)});`);
  if (join) {
    L("  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);", '  Serial.print("Joining the WiFi");', "  while (WiFi.status() != WL_CONNECTED) {", "    delay(500);", '    Serial.print(".");', "  }", "  Serial.println();");
  } else {
    L("  WiFi.softAP(WIFI_NAME, WIFI_PASSWORD);");
  }
  L('  server.on("/", showPage);');
  for (const it of handlers) L(`  server.on("${it.path}", ${it.handler});`);
  L("  server.begin();", '  Serial.print("Open http://");', `  Serial.println(${join ? "WiFi.localIP()" : "WiFi.softAPIP()"});`, "}", "",
    "void loop() {", "  server.handleClient();");
  for (const it of items.filter((x) => x.kind === "reading")) {
    L(it.source ? `  ${it.cname} = ${it.source};` : `  // ${it.cname} = ...;  // what should "${cstr(it.label || "Reading")}" show? e.g. analogRead(POT_PIN)`);
  }
  L("}");
  return lines.join("\n") + "\n";
}

// ---------------------------------------------------------------- try it, before uploading

/**
 * A pretend board for the designer's "Try it" mode: the outputs the page drives, the inputs it reads,
 * and the values the page shows. It follows what the generated sketch would do.
 */
export function tryIt(design, board) {
  const analogMax = board?.analog_max ?? 1023;
  const state = { outputs: {}, rgb: null, beep: 0, pitch: 0, values: {}, inputs: {}, seconds: 0 };
  for (const it of namedItems(design)) {
    for (const c of connections(it, board)) {
      if (c.dir === "in") state.inputs[c.role] ??= c.use === "analog" ? Math.round(analogMax / 2) : false;
      else if (c.role.startsWith("RGB_")) state.rgb ??= { r: 0, g: 0, b: 0 };
      else if (c.role !== "BUZZER_PIN") state.outputs[c.role] ??= 0;
    }
    if (it.kind === "slider") state.values[it.cname] = Number(it.start ?? it.min ?? 0);
    if (it.kind === "colour") state.values[it.cname] = /^#[0-9a-f]{6}$/i.test(it.start ?? "") ? it.start : "#000000";
  }
  const named = () => namedItems(design);
  return {
    state,
    analogMax,
    /** Someone used element index on the page. value: a slider's number or a colour. */
    use(index, value) {
      const it = named()[index];
      if (!it) return;
      const pin = it.pin || "LED_PIN";
      if (it.kind === "button") {
        if (it.action === "on") state.outputs[pin] = 1;
        else if (it.action === "off") state.outputs[pin] = 0;
        else if (it.action === "toggle") state.outputs[pin] = state.outputs[pin] ? 0 : 1;
        else if (it.action === "beep") state.beep++;
      } else if (it.kind === "switch") {
        state.outputs[pin] = state.outputs[pin] ? 0 : 1;
      } else if (it.kind === "slider") {
        const min = Number(it.min ?? 0);
        const max = Number(it.max ?? 100);
        const v = clamp(Number(value), Math.min(min, max), Math.max(min, max));
        state.values[it.cname] = v;
        if (pin === "BUZZER_PIN" && it.pin) state.pitch = v;
        else if (it.pin) state.outputs[pin] = max === min ? 0 : (v - min) / (max - min);
      } else if (it.kind === "colour" && /^#[0-9a-f]{6}$/i.test(value)) {
        state.values[it.cname] = value;
        state.rgb = { r: parseInt(value.slice(1, 3), 16), g: parseInt(value.slice(3, 5), 16), b: parseInt(value.slice(5, 7), 16) };
      }
    },
    /** A pretend part was changed on the bench (a knob turned, the button held...). */
    setInput(role, v) { state.inputs[role] = v; },
    tick(seconds = 1) { state.seconds += seconds; },
    /** What element index shows right now: a number, "on"/"off", or a colour. */
    show(index) {
      const it = named()[index];
      if (!it) return null;
      switch (it.kind) {
        case "slider": case "colour": return state.values[it.cname];
        case "switch": return state.outputs[it.pin || "LED_PIN"] ? "on" : "off";
        case "reading": {
          const src = String(it.source ?? "");
          if (/millis\(\)\s*\/\s*1000/.test(src)) return state.seconds;
          const role = /analogRead\((\w+)\)/.exec(src)?.[1];
          return role ? Math.round(state.inputs[role] ?? 0) : 0;
        }
        case "status": {
          const s = STATUS_SOURCES[it.source] ?? STATUS_SOURCES.light;
          const on = s.role ? Boolean(state.inputs[s.role]) : Boolean(state.outputs[it.pin || "LED_PIN"]);
          return on ? "on" : "off";
        }
        default: return null;
      }
    },
  };
}

// ---------------------------------------------------------------- starting points

/** A starting design for students. */
export function starterDesign() {
  return structuredClone(TEMPLATES.light.design);
}

/** Ideas to start from: each is a whole page that works with the class kit. */
export const TEMPLATES = {
  light: {
    name: "Smart light",
    design: {
      title: "My Smart Light", theme: "teal", wifi: { mode: "hotspot", name: "MySmartLight", password: "circuit123" }, refresh: 5,
      items: [
        { kind: "text", text: "Control my light from your phone." },
        { kind: "button", label: "Turn it on", action: "on", pin: "LED_PIN" },
        { kind: "button", label: "Turn it off", action: "off", pin: "LED_PIN" },
        { kind: "reading", label: "Seconds since it started", source: "millis() / 1000" },
      ],
    },
  },
  plant: {
    name: "Plant monitor",
    design: {
      title: "Plant Buddy", theme: "teal", wifi: { mode: "hotspot", name: "PlantBuddy", password: "circuit123" }, refresh: 5,
      items: [
        { kind: "heading", text: "How is my plant?" },
        { kind: "reading", label: "Soil", source: "analogRead(SOIL_PIN)", style: "bar", max: 4095 },
        { kind: "switch", label: "Grow light", pin: "LED_PIN" },
        { kind: "status", label: "Grow light", source: "light", pin: "LED_PIN", onText: "Shining", offText: "Off" },
      ],
    },
  },
  party: {
    name: "Party lights",
    design: {
      title: "Party Lights", theme: "dark", wifi: { mode: "hotspot", name: "PartyLights", password: "circuit123" }, refresh: 5,
      items: [
        { kind: "text", text: "Pick a colour for the party." },
        { kind: "colour", label: "Light colour", start: "#ff00aa" },
        { kind: "slider", label: "Beep pitch", min: 0, max: 2000, start: 0, pin: "BUZZER_PIN" },
        { kind: "button", label: "Beep!", action: "beep" },
      ],
    },
  },
  alarm: {
    name: "Door alarm",
    design: {
      title: "Door Alarm", theme: "purple", wifi: { mode: "hotspot", name: "DoorAlarm", password: "circuit123" }, refresh: 3,
      items: [
        { kind: "status", label: "Movement", source: "motion", onText: "Someone's there!", offText: "All clear" },
        { kind: "status", label: "Doorbell", source: "button", onText: "Ringing", offText: "Quiet" },
        { kind: "button", label: "Sound the alarm", action: "beep" },
        { kind: "switch", label: "Warning light", pin: "LED_PIN" },
      ],
    },
  },
  blank: { name: "Empty page", design: { title: "My page", theme: "teal", wifi: { mode: "hotspot", name: "MyPage", password: "circuit123" }, refresh: 5, items: [] } },
};
