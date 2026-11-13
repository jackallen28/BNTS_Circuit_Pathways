// Grove kits: shields with ports, and modules that plug into them with one cable. Pure functions,
// no DOM: the same code runs in both apps and in Node (the tests).
//
// A project (or Free Play) says which modules plug into which ports:
//   "kit": "grove",
//   "grove": { "shield": "base-shield", "modules": [ { "id": "led", "type": "grove-led", "port": "D4", "role": "LED_PIN" } ] }
// expandGrove() turns that into what the rest of ArduinoPath already understands: a circuit (the
// modules as parts, the Grove cables to draw, and hidden wires that join each module's signal, power
// and GND to the right board pins, so the simulator and the Wiring Wizard's test work unchanged),
// the wiring steps, and the role → pin numbers for the code's #defines.

/** @typedef {{ id: string, kind: string, sig?: string, sig2?: string }} Port */

export const GROVE_PINS = ["sig", "sig2", "vcc", "gnd"];

/** The shield for an app and board, or null. */
export function shieldFor(grove, app, boardId) {
  for (const [id, s] of Object.entries(grove.shields)) {
    if (s.app === app && (!boardId || s.boards.includes(boardId))) return { id, ...s };
  }
  return null;
}

/** Can this module go in this port? */
export function fits(grove, type, port) {
  const mod = grove.modules[type];
  return Boolean(mod && port && mod.ports.includes(port.kind));
}

/**
 * Picks a free port for a module: the one asked for if it fits and is free, else the first that does.
 * @param {object} grove  grove.json
 * @param {object} shield
 * @param {string} type   module type
 * @param {string[]} used port ids already taken
 * @param {string} [want] a port the project asks for
 * @returns {Port|null}
 */
export function pickPort(grove, shield, type, used = [], want) {
  const taken = new Set(used);
  const asked = shield.ports.find((p) => p.id === want);
  if (asked && fits(grove, type, asked) && !taken.has(asked.id)) return asked;
  // a digital module's second wire (SIG2) is the next port's signal, so leave a gap where possible
  const free = shield.ports.filter((p) => fits(grove, type, p) && !taken.has(p.id));
  return free[0] ?? null;
}

/** "Plug the Grove LED into port D4" steps, as the Wiring Wizard shows them. */
export function groveSteps(grove, shield, modules, { boardName = "board" } = {}) {
  const steps = [{
    title: `Put the ${shield.name} on`,
    text: [shield.what, shield.fit.replace("your Arduino", `your ${boardName}`), shield.switch].filter(Boolean).join("\n"),
  }];
  for (const m of modules) {
    const mod = grove.modules[m.type];
    const label = m.label ? ` (the ${m.label})` : "";
    steps.push({
      title: `Plug in the ${mod.name}${label}`,
      text: `Take a Grove cable. Push one end into the socket on the ${mod.name} and the other end into port ${m.port} on the ${shield.name}.\n` +
        "The plugs only fit one way round: if one won't go in, turn it over. Don't force it.",
    });
  }
  return steps;
}

/**
 * A Grove project (or Free Play's Grove parts) as a circuit, wiring steps and pins.
 * @param {object} grove     grove.json
 * @param {{ shield: string, modules: { id, type, port?, role?, label?, color? }[] }} spec
 * @param {{ app?: string, boardName?: string }} [o]
 * @returns {{ circuit: object, wiring_steps: object[], pins: Record<string,string>, modules: object[], problems: string[] }}
 */
export function expandGrove(grove, spec, { boardName } = {}) {
  const shieldDef = grove.shields[spec.shield];
  const problems = [];
  if (!shieldDef) return { circuit: { breadboard: "none", parts: [], wires: [] }, wiring_steps: [], pins: {}, modules: [], problems: [`unknown shield ${spec.shield}`] };
  const shield = { id: spec.shield, ...shieldDef };
  const used = [];
  const modules = [];
  for (const m of spec.modules ?? []) {
    if (!grove.modules[m.type]) { problems.push(`unknown Grove module ${m.type}`); continue; }
    const port = pickPort(grove, shield, m.type, used, m.port);
    if (!port) { problems.push(`no free port for ${m.id}`); continue; }
    if (m.port && m.port !== port.id) problems.push(`${m.id} can't use port ${m.port}: it went in ${port.id}`);
    used.push(port.id);
    modules.push({ ...m, port: port.id, portDef: port, role: m.role ?? grove.modules[m.type].role });
  }
  const parts = [];
  const wires = [];
  const cables = [];
  const pins = {};
  modules.forEach((m, i) => {
    const step = i + 2; // step 1 is the shield
    parts.push({ id: m.id, type: m.type, label: m.label, ...(m.color ? { color: m.color } : {}), step, grove: true });
    cables.push({ part: m.id, port: m.port, step });
    if (m.portDef.sig != null) pins[m.role] = m.portDef.sig;
    // the hidden wires: what the Grove cable joins (signal → the port's pin, red → power, black → GND)
    const [sig, , vcc, gnd] = grove.modules[m.type].sim.legs;
    wires.push({ from: `part:${m.id}:${sig}`, to: `pin:${m.portDef.sig}`, step, hidden: true });
    wires.push({ from: `part:${m.id}:${vcc}`, to: "board:VCC", step, hidden: true });
    wires.push({ from: `part:${m.id}:${gnd}`, to: "board:GND", step, hidden: true });
  });
  return {
    circuit: { breadboard: "none", grove: { shield: shield.id, name: shield.name, ports: shield.ports, cables }, parts, wires },
    wiring_steps: groveSteps(grove, shield, modules, { boardName }),
    pins,
    modules,
    problems,
  };
}

/** A project with "kit": "grove", expanded in place (circuit, wiring_steps, pins.all). */
export function withGrove(project, grove, board) {
  if (!project?.grove) return project;
  const x = expandGrove(grove, project.grove, { boardName: board?.short || board?.name });
  return {
    ...project,
    circuit: x.circuit,
    wiring_steps: project.wiring_steps?.length ? project.wiring_steps : x.wiring_steps,
    pins: { ...(project.pins ?? {}), all: { ...(project.pins?.all ?? {}), ...x.pins } },
    grove_modules: x.modules.map(({ portDef, ...m }) => m),
  };
}

/** A role that isn't used yet: LED_PIN, then LED2_PIN, LED3_PIN... */
export function freeRole(role, taken) {
  if (!taken.includes(role)) return role;
  for (let n = 2; ; n++) {
    const r = role.replace(/(_PIN)?$/, `${n}$1`);
    if (!taken.includes(r)) return r;
  }
}

/**
 * Free Play's "Add a Grove module": puts a module's code into an Arduino sketch. The #define goes at
 * the top, any #include, global and helper function above setup(), its setup line into setup(), and
 * a comment in loop() showing how to use it. Returns the new code.
 * @param {string} code
 * @param {object} grove  grove.json
 * @param {{type: string, role: string, port: Port}} m  the module, its role (LED_PIN) and port
 */
export function addGroveCode(code, grove, m) {
  const mod = grove.modules[m.type];
  const a = mod.arduino ?? {};
  const name = m.role.toLowerCase().replace(/_pin$/, "").replace(/_(\w)/g, (_, c) => c.toUpperCase());
  const fill = (t) => t.replaceAll("{pin}", m.role).replaceAll("{name}", name);
  let lines = code.split("\n");
  const has = (s) => lines.some((l) => l.trim() === s.trim());
  const top = [];
  if (a.include && !has(a.include)) top.push(a.include);
  top.push(`#define ${m.role} ${m.port.sig}  // ${mod.name} in port ${m.port.id}`);
  // after the opening comments
  let at = 0;
  while (at < lines.length && (lines[at].startsWith("//") || lines[at].startsWith("#"))) at++;
  lines.splice(at, 0, ...top);
  const before = [];
  if (a.global) before.push(fill(a.global));
  if (a.helper && !code.includes(a.helper.split("\n")[1] ?? a.helper)) before.push(a.helper);
  const setupAt = lines.findIndex((l) => /^\s*void\s+setup\s*\(\s*\)\s*\{/.test(l));
  if (before.length) lines.splice(setupAt >= 0 ? setupAt : lines.length, 0, ...before, "");
  const s = lines.findIndex((l) => /^\s*void\s+setup\s*\(\s*\)\s*\{/.test(l));
  if (s >= 0 && a.setup) lines.splice(s + 1, 0, `  ${fill(a.setup)}`);
  const l = lines.findIndex((x) => /^\s*void\s+loop\s*\(\s*\)\s*\{/.test(x));
  const read = a.read && fill(a.read);
  const use = a.on ? fill(a.on)
    : read ? (read.includes("==") ? `if (${read}) { ... }` : `${a.helper ? "long cm" : "int value"} = ${read};`)
      : a.use ? fill(a.use) : null;
  if (l >= 0 && use) lines.splice(l + 1, 0, `  // ${mod.name}: ${use}`);
  return lines.join("\n");
}
