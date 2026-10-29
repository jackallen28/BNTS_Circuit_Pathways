// The browser version of PiPath's tests/test_activities.py: every step's model answer
// (its demo) is run in the simulator, with its simulated presses and typed answers, and
// must pass the step's own checks, judged by PiPath's own check engine.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { getEngine, readData } from "./engine.js";

const DEMO_FILES = new URL("../../../site/pipath/data/demo_files/", import.meta.url).pathname;

const catalog = readData("catalog.json");
// Activities that need a screen window the browser can't give (turtle) are listed in the app as "Pi only".
const SKIP = new Set(JSON.parse(readFileSync(new URL("./unsupported.json", import.meta.url))));

/** A lesson's demo_files ("c2/examples.json", "p3/party") copied next to the program, like PiPath does. */
function demoFiles(rels) {
  const out = {};
  for (const rel of rels ?? []) {
    const p = DEMO_FILES + rel;
    const base = rel.split("/").pop();
    if (statSync(p).isDirectory()) {
      for (const f of readdirSync(p, { recursive: true, withFileTypes: true })) {
        if (f.isFile()) out[`${base}/${(f.parentPath + "/" + f.name).slice(p.length + 1)}`] = readFileSync(`${f.parentPath}/${f.name}`);
      }
    } else {
      out[base] = readFileSync(p);
    }
  }
  return out;
}

for (const proj of catalog.projects) {
  if (SKIP.has(proj.id)) continue;
  const lesson = readData(`lessons/${proj.id}.json`);
  test(`${proj.id}: every step's model answer passes its checks`, async () => {
    const e = await getEngine();
    const failures = [];
    for (const [i, step] of lesson.steps.entries()) {
      assert.ok(step.demo, `step ${i + 1} needs a demo`);
      const result = e.run({
        code: step.demo, filename: lesson.file_name ?? "student.py",
        events: step.demo_events, seconds: step.demo_seconds, stdin: step.demo_input ?? "",
        files: demoFiles(step.demo_files),
      });
      const checks = e.evaluate({ checks: step.checks, code: step.demo, result, runs: 3 });
      const bad = checks.filter((c) => !c.passed).map((c) => c.label);
      if (bad.length) failures.push(`step ${i + 1} (${step.title}): failed [${bad.join("; ")}]\n--- stdout:\n${result.stdout.slice(0, 600)}\n--- stderr:\n${result.stderr.slice(0, 600)}`);
    }
    assert.equal(failures.length, 0, failures.join("\n\n"));
  });
}
