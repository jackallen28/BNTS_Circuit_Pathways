// The Web Page Designer's code maker: a page design (a title, a colour theme, and a list of
// headings, text, buttons, sliders and readings) becomes a complete, commented ESP sketch with a
// web server. Pure (tested in Node and in the simulator); dialogs/webpage.js is the designer.
//
//   generateSketch(design, board) → C++ code

export const THEMES = {
  teal: { name: "Teal", bg: "#e8fbfc", card: "#ffffff", ink: "#08363a", accent: "#19c1ca", accentInk: "#ffffff" },
  purple: { name: "Purple", bg: "#f3eef8", card: "#ffffff", ink: "#2e1d3b", accent: "#704988", accentInk: "#ffffff" },
  dark: { name: "Night", bg: "#111827", card: "#1f2937", ink: "#f3f4f6", accent: "#22d3ee", accentInk: "#0b1220" },
};

export const ITEM_KINDS = {
  heading: "Heading",
  text: "Text",
  button: "Button",
  slider: "Slider",
  reading: "Reading",
};

export const BUTTON_ACTIONS = { on: "Turn a pin ON", off: "Turn a pin OFF", toggle: "Switch a pin on/off", custom: "Something I'll write" };

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

/** Every item with a unique C name (and the address its button or slider uses). */
// names a sketch can't use for its own things (Arduino's and C's own functions)
const RESERVED = new Set(["time", "delay", "millis", "micros", "random", "min", "max", "abs", "map", "round", "sin", "cos", "tan", "tone",
  "read", "write", "index", "select", "signal", "sleep", "exit", "free", "log", "exp", "pow", "sqrt", "rand", "printf", "main", "new", "delete",
  "int", "long", "float", "double", "char", "bool", "byte", "word", "string", "class", "struct", "return", "if", "else", "for", "while", "do",
  "switch", "case", "break", "continue", "default", "const", "static", "void", "true", "false", "html", "pin", "value"]);

export function namedItems(design) {
  const used = new Set(["page", "showPage", "setup", "loop", "server", ...RESERVED]);
  return (design.items ?? []).map((it, i) => {
    let base = cName(it.name || it.label || it.text, it.kind);
    if (RESERVED.has(base)) base = `${base}Value`;
    let n = base;
    for (let k = 2; used.has(n); k++) n = `${base}${k}`;
    used.add(n);
    const path = `/${n.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`;
    // a slider keeps its number in cname, so the function that sets it is setCname
    const handler = it.kind === "slider" ? `set${n[0].toUpperCase()}${n.slice(1)}` : n;
    if (handler !== n) used.add(handler);
    return { ...it, cname: n, handler, path, index: i };
  });
}

/** The page's HTML, with %name% where readings and slider values go. */
export function pageHTML(design) {
  const t = THEMES[design.theme] ?? THEMES.teal;
  const items = namedItems(design);
  const body = items.map((it) => {
    switch (it.kind) {
      case "heading": return `  <h2>${html(it.text)}</h2>`;
      case "text": return `  <p>${html(it.text)}</p>`;
      case "button": return `  <p><a class="btn" href="${it.path}">${html(it.label || "Press me")}</a></p>`;
      case "slider": return `  <form action="${it.path}">\n    <label>${html(it.label || "Slider")} <b>%${it.cname}%</b><br><input type="range" name="value" min="${Number(it.min ?? 0)}" max="${Number(it.max ?? 100)}" value="%${it.cname}%"></label>\n    <button class="btn">Set</button>\n  </form>`;
      case "reading": return `  <p class="reading">${html(it.label || "Reading")}: <b>%${it.cname}%</b>${it.unit ? ` ${html(it.unit)}` : ""}</p>`;
      default: return "";
    }
  }).filter(Boolean).join("\n");
  const refresh = items.some((it) => it.kind === "reading") ? `\n<meta http-equiv="refresh" content="${Math.max(2, Math.min(60, Number(design.refresh ?? 5)))}">` : "";
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
  input[type=range] { width: 90%; }
  .reading b { font-size: 1.6em; color: ${t.accent}; }
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

/**
 * The whole sketch.
 * @param {object} design  { title, theme, wifi: { mode: "hotspot"|"join", name, password }, refresh, items }
 * @param {object} board   content/boards/<id>.json (an ESP board)
 */
export function generateSketch(design, board) {
  const esp8266 = board?.family === "esp8266";
  const items = namedItems(design);
  const wifi = design.wifi ?? {};
  const join = wifi.mode === "join";
  const plan = board?.pin_plan ?? {};
  const pinsUsed = [...new Set(items.filter((it) => (it.kind === "button" && it.action !== "custom") || (it.kind === "slider" && it.pin)).map((it) => it.pin || "LED_PIN"))];
  // pins a reading uses (analogRead(POT_PIN)) need their #define too, but not pinMode(OUTPUT)
  const inputPins = [...new Set(items.filter((it) => it.kind === "reading" && it.source).flatMap((it) => it.source.match(/\b[A-Z][A-Z0-9]*_PIN\b/g) ?? []))].filter((r) => !pinsUsed.includes(r));
  const lines = [];
  const L = (...s) => lines.push(...s);

  L(`// ${design.title || "My page"}: a web page made with ArduinoPath's Web Page Designer.`,
    join
      ? `// Your board joins the WiFi called "${cstr(wifi.name)}". Open the address it prints in the Serial Monitor.`
      : `// On a phone, join the WiFi called "${cstr(wifi.name || "ArduinoPath")}", then open the address in the Serial Monitor.`,
    "");
  for (const role of [...pinsUsed, ...inputPins]) L(`#define ${role} ${plan[role] ?? "2"}`);
  if (pinsUsed.length + inputPins.length) L("");
  L(esp8266 ? "#include <ESP8266WiFi.h>" : "#include <WiFi.h>", esp8266 ? "#include <ESP8266WebServer.h>" : "#include <WebServer.h>", "");
  L("// ---- 1. WiFi ----",
    `const char* WIFI_NAME = "${cstr(wifi.name || (join ? "SchoolWiFi" : "ArduinoPath"))}";`,
    `const char* WIFI_PASSWORD = "${cstr(wifi.password || "circuit123")}";  // at least 8 characters`,
    "",
    esp8266 ? "ESP8266WebServer server(80);" : "WebServer server(80);",
    "");
  const values = items.filter((it) => it.kind === "slider" || it.kind === "reading");
  if (values.length) {
    L("// ---- 2. The numbers your page shows (change readings in loop) ----");
    for (const it of values) L(`int ${it.cname} = ${it.kind === "slider" ? Number(it.start ?? it.min ?? 0) : 0};`);
    L("");
  }
  L("// ---- 3. The page ----", `const char PAGE[] = R"(${raw(pageHTML(design))}\n)";`, "",
    "// The page, with today's numbers put in where %name% is.",
    "String page() {",
    "  String html = PAGE;");
  for (const it of values) L(`  html.replace("%${it.cname}%", String(${it.cname}));`);
  L("  return html;", "}", "", "void showPage() {", '  server.send(200, "text/html", page());', "}", "");

  const handlers = items.filter((it) => it.kind === "button" || it.kind === "slider");
  if (handlers.length) L("// ---- 4. What happens when someone presses a button or sets a slider ----");
  for (const it of handlers) {
    L(`void ${it.handler}() {`);
    if (it.kind === "button") {
      const pin = it.pin || "LED_PIN";
      if (it.action === "on") L(`  digitalWrite(${pin}, HIGH);`);
      else if (it.action === "off") L(`  digitalWrite(${pin}, LOW);`);
      else if (it.action === "toggle") L(`  digitalWrite(${pin}, !digitalRead(${pin}));`);
      else L(`  // What should "${cstr(it.label || "the button")}" do? Write it here.`);
      L(`  Serial.println("${cstr(it.label || "Button")} was pressed");`);
    } else {
      L(`  ${it.cname} = server.arg("value").toInt();`);
      if (it.pin) L(`  analogWrite(${it.pin}, map(${it.cname}, ${Number(it.min ?? 0)}, ${Number(it.max ?? 100)}, 0, 255));`);
      else L(`  // Use ${it.cname} here (it's between ${Number(it.min ?? 0)} and ${Number(it.max ?? 100)}).`);
      L(`  Serial.print("${cstr(it.label || "Slider")}: ");`, `  Serial.println(${it.cname});`);
    }
    L("  showPage();", "}", "");
  }

  L("void setup() {", "  Serial.begin(115200);");
  for (const role of pinsUsed) L(`  pinMode(${role}, OUTPUT);`);
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

/** A starting design for students. */
export function starterDesign() {
  return {
    title: "My Smart Light",
    theme: "teal",
    wifi: { mode: "hotspot", name: "MySmartLight", password: "circuit123" },
    refresh: 5,
    items: [
      { kind: "text", text: "Control my light from your phone." },
      { kind: "button", label: "Turn it on", action: "on", pin: "LED_PIN" },
      { kind: "button", label: "Turn it off", action: "off", pin: "LED_PIN" },
      { kind: "reading", label: "Seconds since it started", source: "millis() / 1000" },
    ],
  };
}

/** What a reading can show (the C expression), for the designer's list. */
export const READING_SOURCES = [
  { label: "Something I'll write in loop()", source: "" },
  { label: "Seconds since it started", source: "millis() / 1000" },
  { label: "A knob (POT_PIN)", source: "analogRead(POT_PIN)" },
  { label: "A light sensor (LDR_PIN)", source: "analogRead(LDR_PIN)" },
  { label: "A soil sensor (SOIL_PIN)", source: "analogRead(SOIL_PIN)" },
];
