// Runs PiPath's Python (the simulator and the Coach) in real Pyodide, in Node, with a
// virtual clock. Slow to start (a couple of seconds), so tests share one engine.

import { loadPyodide } from "../../../node_modules/pyodide/pyodide.mjs";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { VirtualHost } from "../../../site/pipath/js/runtime/virtual-host.js";

const PY_ROOT = new URL("../../../site/pipath/py/", import.meta.url).pathname;
const DATA = new URL("../../../site/pipath/data/", import.meta.url).pathname;

function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? (n === "__pycache__" ? [] : walk(p)) : [p];
  });
}

export const readData = (rel) => JSON.parse(readFileSync(join(DATA, rel), "utf8"));

let enginePromise;
export function getEngine() {
  enginePromise ??= (async () => {
    const py = await loadPyodide();
    const host = new VirtualHost();
    py.registerJsModule("_cp_host", host);
    // the Python code, where `import cpsim` / `import pipath` / `from pipath_computer import ...` find it
    py.FS.mkdirTree("/cp");
    for (const f of walk(PY_ROOT)) {
      const dest = "/cp/" + relative(PY_ROOT, f);
      py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
      py.FS.writeFile(dest, readFileSync(f));
    }
    py.runPython("import sys; sys.path.insert(0, '/cp')");
    let out = "";
    let err = "";
    const dec = new TextDecoder();
    py.setStdout({ write: (b) => { out += dec.decode(b); return b.length; } });
    py.setStderr({ write: (b) => { err += dec.decode(b); return b.length; } });
    py.runPython("from cpsim import runner, bridge");
    const errors = JSON.stringify(readData("errors.json"));
    py.globals.get("bridge").set_errors(errors);

    let n = 0;
    const engine = {
      py, host,
      /** Runs a program like the page does. Returns what it printed and how it ended. */
      run({ code, filename = "student.py", events = [], seconds = 0, stdin = "", env = {}, files = {}, seed = 1 }) {
        out = "";
        err = "";
        host.reset({ events, seconds, stdin });
        const cwd = `/student/run${++n}`;
        py.FS.mkdirTree(cwd);
        for (const [name, data] of Object.entries(files)) {
          const dest = `${cwd}/${name}`;
          py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
          py.FS.writeFile(dest, data);
        }
        const run = py.globals.get("runner").run_student;
        const rc = run(code, filename, cwd, py.toPy(env), seed);
        const started = py.globals.get("runner").started_real;
        return { stdout: out, stderr: err, rc, stopped: host.stopped, messages: host.messages, cwd, started, virtualMs: host.t };
      },
      /** PiPath's own check engine. */
      evaluate({ checks, code, result, runs = 3, confirmed = null }) {
        const crashed = (result.rc !== 0 && !result.stopped) || result.stderr.includes("Traceback");
        const bridge = py.globals.get("bridge");
        return JSON.parse(bridge.evaluate(JSON.stringify(checks), code, result.stdout, crashed, runs, JSON.stringify(confirmed), result.cwd, result.started - 1));
      },
      diagnose({ stderr, filename = "student.py", code, step = null }) {
        return JSON.parse(py.globals.get("bridge").diagnose(stderr, filename, code, step ? JSON.stringify(step) : ""));
      },
      precheck: (code, starter) => JSON.parse(py.globals.get("bridge").precheck(code, starter)),
      lint: (code) => JSON.parse(py.globals.get("bridge").lint(code)),
    };
    return engine;
  })();
  return enginePromise;
}
