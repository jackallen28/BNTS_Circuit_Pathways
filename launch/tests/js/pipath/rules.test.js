import { test } from "node:test";
import assert from "node:assert/strict";
import { getEngine, readData } from "./engine.js";
import { goalText, hintRules, starsFor, shown, projectKey, lessonKey, LEVELS } from "../../../site/pipath/js/progress.js";
import { markdown } from "../../../site/pipath/js/markdown.js";
import { expandEvents } from "../../../site/pipath/js/events.js";
import { readFileSync } from "node:fs";

const catalog = readData("catalog.json");

test("the page's help-level rules match PiPath's own Python (levels.py) for every step", async () => {
  const e = await getEngine();
  e.py.runPython("from pipath import levels");
  const levels = e.py.globals.get("levels");
  for (const p of catalog.projects) {
    for (const [i, step] of readData(`lessons/${p.id}.json`).steps.entries()) {
      const py = levels.goal_text(e.py.toPy(step));
      assert.equal(goalText(step) ?? null, py ?? null, `${p.id} step ${i + 1}: goal text`);
    }
  }
  for (const level of LEVELS) for (const support of ["guided", "scaffolded", "brief", undefined]) {
    assert.deepEqual(hintRules(level, support), levels.hint_rules(level, support ?? "x").toJs(), `${level}/${support}`);
  }
});

test("demo events expand the way PiPath's gpio.expand_events does", async () => {
  const e = await getEngine();
  e.py.runPython("import sys, types\nsys.modules.setdefault('gpiozero', types.ModuleType('gpiozero'))");
  // the real function, read from the PiPath source (it's pure)
  const src = readFileSync(new URL("../../../content-pipath/expand_events.py", import.meta.url), "utf8");
  e.py.runPython(src);
  const expand = e.py.globals.get("expand_events");
  let n = 0;
  for (const p of catalog.projects) {
    for (const step of readData(`lessons/${p.id}.json`).steps) {
      if (!step.demo_events) continue;
      const want = expand(e.py.toPy(step.demo_events)).toJs().map(([t, cmd]) => `${Math.round(t * 1000)} ${cmd}`);
      const got = expandEvents(step.demo_events).map((x) => `${Math.round(x.at * 1000)} ${x.cmd}`);
      assert.deepEqual(got, want, p.id);
      n++;
    }
  }
  assert.ok(n > 20, "expected plenty of steps with events");
});

test("stars count hints, not speed", () => {
  assert.equal(starsFor(0), 3); assert.equal(starsFor(2), 3); assert.equal(starsFor(3), 2); assert.equal(starsFor(6), 2); assert.equal(starsFor(7), 1);
});

test("the picker's Show filter", () => {
  const led = { tier: "advanced", gpio: true }; const hello = { tier: "simple" };
  assert.equal(shown(led, "all"), true); assert.equal(shown(hello, "hardware"), false); assert.equal(shown(led, "hardware"), true);
  assert.equal(shown(led, "simple"), false); assert.equal(shown(hello, "simple"), true);
});

test("lesson ids survive the trip to a save-file project name", () => {
  for (const p of catalog.projects) {
    assert.match(projectKey(p.id), /^[a-z0-9][a-z0-9-]{0,63}$/);
    assert.equal(lessonKey(projectKey(p.id)), p.id);
  }
});
