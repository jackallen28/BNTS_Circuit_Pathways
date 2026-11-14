#!/usr/bin/env node
// Writes the Web Page Designer's sketches (every starting idea, and one page with every element) for every ESP board
// into internal/arduino/testdata/webpage/, so CI compiles them with the real compilers (TestCompileEveryBoardForReal).
//
//   node tools/make_compile_fixtures.mjs          # write them (after changing js/webpage.js)
//   node tools/make_compile_fixtures.mjs --check  # fail if they are out of date (the JS tests do this)
import { readFileSync, readdirSync, writeFileSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { generateSketch, TEMPLATES, ELEMENTS, defaultItem } from "../site/arduinopath/js/webpage.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
export const OUT = join(ROOT, "internal", "arduino", "testdata", "webpage");

/** One design that uses every element, so every bit of generated code gets compiled. */
export function everyElement(board) {
  return {
    title: "Every element", theme: "teal", wifi: { mode: "join", name: "SchoolWiFi", password: "circuit123" }, refresh: 5,
    items: [
      ...Object.keys(ELEMENTS).map((k) => defaultItem(k, board)),
      { kind: "button", label: "On", action: "on", pin: "LED_PIN" },
      { kind: "button", label: "Off", action: "off", pin: "LED_PIN" },
      { kind: "button", label: "Beep", action: "beep" },
      { kind: "button", label: "Mine", action: "custom" },
      { kind: "slider", label: "Pitch", min: 0, max: 2000, pin: "BUZZER_PIN" },
      { kind: "slider", label: "Number", min: 0, max: 10 },
      { kind: "reading", label: "Mine", source: "" },
      { kind: "status", label: "Doorbell", source: "button" },
      { kind: "status", label: "Motion", source: "motion" },
    ],
  };
}

/** file name → sketch, for every ESP board. */
export function fixtures() {
  const boardsDir = join(ROOT, "content", "arduinopath", "boards");
  const out = {};
  for (const f of readdirSync(boardsDir).filter((x) => x.endsWith(".json")).sort()) {
    const board = JSON.parse(readFileSync(join(boardsDir, f), "utf8"));
    if (!/^esp/.test(board.family ?? "")) continue;
    for (const [id, t] of Object.entries(TEMPLATES)) out[`${board.id}--${id}.ino`] = generateSketch(t.design, board);
    out[`${board.id}--every-element.ino`] = generateSketch(everyElement(board), board);
  }
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const want = fixtures();
  if (process.argv.includes("--check")) {
    const stale = Object.entries(want).filter(([name, code]) => !existsSync(join(OUT, name)) || readFileSync(join(OUT, name), "utf8") !== code).map(([n]) => n);
    const extra = existsSync(OUT) ? readdirSync(OUT).filter((n) => n.endsWith(".ino") && !(n in want)) : [];
    if (stale.length || extra.length) {
      console.error(`out of date (run node tools/make_compile_fixtures.mjs): ${[...stale, ...extra].join(", ")}`);
      process.exit(1);
    }
    console.log(`${Object.keys(want).length} sketches up to date`);
  } else {
    if (existsSync(OUT)) for (const n of readdirSync(OUT).filter((x) => x.endsWith(".ino"))) rmSync(join(OUT, n));
    mkdirSync(OUT, { recursive: true });
    for (const [name, code] of Object.entries(want)) writeFileSync(join(OUT, name), code);
    console.log(`wrote ${Object.keys(want).length} sketches to ${OUT}`);
  }
}
