// Grove kits: projects made from modules and ports become circuits the simulator, the bench, the
// drawing and the Wiring Wizard's test all understand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readJSON, catalogue, boards, projects } from "./circuit/helpers.js";
import { expandGrove, withGrove, pickPort, shieldFor, fits } from "../../site/shared/grove/grove.js";
import { layoutCircuit } from "../../site/arduinopath/js/circuit/layout.js";
import { Bench } from "../../site/arduinopath/js/bench.js";
import { testSketch } from "../../site/arduinopath/js/wiring-test.js";
import { validateCircuit } from "../../site/arduinopath/js/circuit/netlist.js";

const grove = readJSON("site/shared/grove/grove.json");
const parts = catalogue();
const uno = boards().find((b) => b.id === "uno");
const groveProjects = projects().filter((p) => p.kit === "grove");

test("every Grove module has a part the simulator knows, and its art's socket", () => {
  for (const [type, mod] of Object.entries(grove.modules)) {
    const def = parts.types[type];
    assert.ok(def, `${type} has a part.json (run node tools/grove_art.mjs)`);
    assert.equal(def.behaviour, mod.sim.behaviour);
    assert.deepEqual(def.legs.map((l) => l.id), mod.sim.legs);
    assert.equal(def.grove.socket.length, 4);
    assert.ok(readJSON("content/arduinopath/parts/index.json").parts[type], `${type} has a name for "Meet the parts"`);
  }
});

test("each Grove project's modules fit their ports, and its code uses the roles it plugs in", () => {
  assert.ok(groveProjects.length >= 5);
  for (const p of groveProjects) {
    const x = expandGrove(grove, p.grove);
    assert.deepEqual(x.problems, [], p.id);
    const shield = grove.shields[p.grove.shield];
    assert.ok(shield.boards.every((b) => p.boards.includes(b)) || p.boards.every((b) => shield.boards.includes(b)), `${p.id}: boards suit the shield`);
    for (const m of x.modules) assert.ok(fits(grove, m.type, m.portDef), `${p.id}: ${m.type} fits ${m.port}`);
    for (const s of p.steps) {
      for (const role of new Set([...s.demo.matchAll(/\b([A-Z][A-Z0-9]*_PIN)\b/g)].map((m) => m[1]))) {
        assert.ok(x.pins[role], `${p.id} "${s.title}": ${role} is plugged in`);
      }
    }
  }
});

test("ports: a module goes where it's asked if it fits, else the next free port of its kind", () => {
  const base = { id: "base-shield", ...grove.shields["base-shield"] };
  assert.equal(pickPort(grove, base, "grove-led", [], "D4").id, "D4");
  assert.equal(pickPort(grove, base, "grove-rotary", [], "D4").id, "A0", "a knob can't go in a digital port");
  assert.equal(pickPort(grove, base, "grove-led", ["D2", "D3"]).id, "D4");
  assert.equal(shieldFor(grove, "pipath", "pi").id, "base-hat");
  const x = expandGrove(grove, { shield: "base-shield", modules: [{ id: "a", type: "grove-led", port: "D4" }, { id: "b", type: "grove-led", port: "D4" }] });
  assert.equal(x.modules[1].port, "D2");
  assert.match(x.problems[0], /can't use port D4/);
});

test("the Smart Bin: the drawing puts the shield on the board and a cable from each module to its port", () => {
  const p = withGrove(groveProjects.find((x) => x.id === "grove-smart-bin"), grove, uno);
  assert.equal(p.wiring_steps.length, 5);
  assert.match(p.wiring_steps[0].title, /Base Shield/);
  assert.match(p.wiring_steps[1].text, /port D7/);
  const layout = layoutCircuit({ board: uno, circuit: p.circuit, parts, pins: p.pins.all });
  assert.deepEqual(layout.problems, []);
  assert.equal(layout.wires.length, 0, "the electrical wires are hidden");
  assert.equal(layout.grove.cables.length, 4);
  for (const c of layout.grove.cables) assert.equal(c.paths.length, 4, "four wires in a Grove cable");
  assert.ok(layout.grove.ports.D7 && layout.grove.ports.A0);
  // modules sit outside the board
  for (const item of layout.parts) {
    const b = layout.board.box;
    const inside = item.box.x > b.x && item.box.y > b.y && item.box.x + item.box.w < b.x + b.w && item.box.y + item.box.h < b.y + b.h;
    assert.equal(inside, false, `${item.part.id} isn't on top of the board`);
  }
  assert.deepEqual(validateCircuit(p.circuit, uno, parts, (n) => ({ code: p.pins.all[n] ?? n })).filter((e) => e.level === "error"), []);
});

test("the bench: a Grove button is LOW until pressed, the ranger gives echo times, and the test sketch knows each module", () => {
  const p = withGrove(groveProjects.find((x) => x.id === "grove-smart-bin"), grove, uno);
  const bench = new Bench({ board: uno, circuit: p.circuit, parts, pins: p.pins.all });
  const sw = bench.inputsFor(bench.active.find((x) => x.id === "switch"));
  assert.deepEqual(sw.digital, { 2: 0 }, "the micro switch reads LOW (its own pull-down) when not pressed");
  assert.deepEqual(bench.control("switch", "press", true).inputs.digital, { 2: 1 });
  assert.deepEqual(bench.control("ranger", "distance", 10).inputs.pulse, { 7: 580 });
  const tp = bench.testParts();
  assert.deepEqual(Object.fromEntries(tp.map((x) => [x.id, x.pins.signal ?? x.pins.anode ?? x.pins.signal])), { ranger: "7", lid: "5", led: "4", switch: "2" });
  const sketch = testSketch(tp, uno);
  assert.equal(sketch.rows.length, 4);
  assert.match(sketch.code, /pinMode\(2, INPUT\);/);
  assert.match(sketch.code, /pulseIn\(7, HIGH, 30000UL\)/);
  assert.match(sketch.code, /servo_lid\.attach\(5\)/);
  const light = withGrove(groveProjects.find((x) => x.id === "grove-too-dark"), grove, uno);
  const b2 = new Bench({ board: uno, circuit: light.circuit, parts, pins: light.pins.all });
  assert.deepEqual(b2.control("light", "light", 1).inputs.analog, { [b2.pinOf("light", "1")]: Math.round(0.95 * 1023) });
  b2.apply([{ type: "digital", pin: 4, value: 1 }]);
  assert.equal(b2.lights().led.led, 1, "the Grove LED lights when its pin is HIGH (its resistor is on the module)");
});

test("Free Play: adding a module puts its #define, include, helper and setup line in the sketch", async () => {
  const { addGroveCode, freeRole } = await import("../../site/shared/grove/grove.js");
  const port = (id) => grove.shields["base-shield"].ports.find((p) => p.id === id);
  let code = "// Free Play\n\nvoid setup() {\n}\n\nvoid loop() {\n}\n";
  code = addGroveCode(code, grove, { type: "grove-servo", role: "SERVO_PIN", port: port("D5") });
  code = addGroveCode(code, grove, { type: "grove-ultrasonic", role: "RANGER_PIN", port: port("D7") });
  code = addGroveCode(code, grove, { type: "grove-button", role: freeRole("BUTTON_PIN", ["BUTTON_PIN"]), port: port("D2") });
  assert.match(code, /#include <Servo\.h>\n#define SERVO_PIN 5/);
  assert.match(code, /#define BUTTON2_PIN 2/);
  assert.match(code, /long readCm\(int pin\)/);
  assert.match(code, /void setup\(\) \{\n  pinMode\(BUTTON2_PIN, INPUT\);\n  servo\.attach\(SERVO_PIN\);/);
  assert.match(code, /long cm = readCm\(RANGER_PIN\);/);
  assert.match(code, /if \(digitalRead\(BUTTON2_PIN\) == HIGH\)/);
  const { runHeadless } = await import("../../site/arduinopath/js/sim/headless.js");
  const uno = boards().find((b) => b.id === "uno");
  assert.equal(runHeadless(code, { board: uno, ms: 200 }).ok, true, "the sketch runs");
});
