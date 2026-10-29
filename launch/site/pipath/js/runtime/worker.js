// The Python worker. Pyodide (Python for the browser) lives here, so a student's program
// can sleep, wait for a button and run in a busy loop without freezing the page. The page
// reaches a running program through shared memory (see ipc.js).

import { Ring, CTL } from "./ipc.js";

let py = null;
let interruptView = null;
let ctl = null;
let events = null;
let stdin = null;
let t0 = 0;
let limitMs = 0;
let scheduled = []; // {at (ms), ev} the page asked for up front (Watch the goal)

const dec = new TextDecoder();
const reply = (msg, transfer) => postMessage(msg, transfer ?? []);

const host = {
  now_ms: () => performance.now() - t0,
  sleep(ms) {
    Atomics.add(ctl, CTL.ACTIVITY, 1);
    if (ms > 0) Atomics.wait(ctl, CTL.WAKE, Atomics.load(ctl, CTL.WAKE), ms); // the page wakes us early with news
  },
  should_stop: () => Atomics.load(ctl, CTL.STOP) !== 0 || (limitMs > 0 && performance.now() - t0 >= limitMs),
  poll() {
    const out = [];
    const now = performance.now() - t0;
    while (scheduled.length && scheduled[0].at <= now) out.push(scheduled.shift().ev);
    for (let m = events.pop(); m !== null; m = events.pop()) out.push(JSON.parse(m));
    return JSON.stringify(out);
  },
  emit(json) {
    Atomics.add(ctl, CTL.ACTIVITY, 1);
    const msg = JSON.parse(json);
    if (msg.t === "photo") {
      try {
        const bytes = py.FS.readFile(msg.path);
        reply({ type: "board", msg: { ...msg, name: msg.path.split("/").pop() }, bytes }, [bytes.buffer]);
        if (msg.preview) {
          const pv = py.FS.readFile(msg.preview);
          reply({ type: "board", msg: { t: "preview" }, bytes: pv }, [pv.buffer]);
        }
        return;
      } catch { /* fall through: tell the page without the picture */ }
    }
    reply({ type: "board", msg });
  },
  input_state: () => (stdin.hasData ? 1 : Atomics.load(ctl, CTL.EOF) ? 2 : 0),
  read_line: () => stdin.pop(),
};

async function init({ sabs, interrupt, base, errorsJson }) {
  ctl = new Int32Array(sabs.ctl);
  events = new Ring(sabs.events);
  stdin = new Ring(sabs.stdin);
  const { loadPyodide } = await import(`${base}vendor/pyodide/pyodide.mjs`);
  py = await loadPyodide({ indexURL: `${base}vendor/pyodide/` });
  interruptView = new Uint8Array(interrupt);
  py.setInterruptBuffer(interruptView);
  py.registerJsModule("_cp_host", host);
  py.setStdout({ write: (b) => { Atomics.add(ctl, CTL.ACTIVITY, 1); reply({ type: "out", stream: "out", text: dec.decode(b) }); return b.length; } });
  py.setStderr({ write: (b) => { Atomics.add(ctl, CTL.ACTIVITY, 1); reply({ type: "out", stream: "err", text: dec.decode(b) }); return b.length; } });
  const manifest = await (await fetch(`${base}py/manifest.json`)).json();
  py.FS.mkdirTree("/cp");
  await Promise.all(manifest.files.map(async (f) => {
    const bytes = new Uint8Array(await (await fetch(`${base}py/${f}`)).arrayBuffer());
    const dest = `/cp/${f}`;
    py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
    py.FS.writeFile(dest, bytes);
  }));
  py.runPython("import sys; sys.path.insert(0, '/cp')");
  py.runPython("from cpsim import runner, bridge");
  py.pyimport("cpsim.bridge").set_errors(errorsJson);
}

function run({ code, filename, env, files, events: timed, seconds, seed }) {
  const cwd = `/student/${filename.replace(/\.py$/, "")}`;
  py.FS.mkdirTree(cwd);
  for (const [name, data] of Object.entries(files ?? {})) {
    const dest = `${cwd}/${name}`;
    py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
    py.FS.writeFile(dest, data);
  }
  Atomics.store(ctl, CTL.STOP, 0);
  events.clear();
  scheduled = (timed ?? []).map((e) => ({ at: e.at * 1000, ev: e.ev })).sort((a, b) => a.at - b.at);
  limitMs = seconds ? seconds * 1000 : 0;
  t0 = performance.now();
  const runner = py.pyimport("cpsim.runner");
  let rc;
  try {
    rc = runner.run_student(code, filename, cwd, py.toPy(env ?? {}), seed ?? undefined);
  } finally {
    interruptView[0] = 0; // an interrupt that arrived too late must not stop the next program
  }
  return { rc, cwd, started: runner.started_real, stopped: Atomics.load(ctl, CTL.STOP) !== 0 || (limitMs > 0 && performance.now() - t0 >= limitMs) };
}

onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "init") {
      await init(m);
      reply({ type: "ready", version: py.version });
    } else if (m.type === "run") {
      reply({ type: "done", id: m.id, ...run(m) });
    } else if (m.type === "call") {
      const bridge = py.pyimport("cpsim.bridge");
      const value = bridge[m.fn](...m.args);
      reply({ type: "result", id: m.id, value: typeof value === "string" ? value : undefined });
    } else if (m.type === "putfiles") {
      py.FS.mkdirTree(m.dir);
      for (const [name, f] of Object.entries(m.files ?? {})) {
        const dest = `${m.dir}/${name}`;
        py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
        py.FS.writeFile(dest, f.text ?? "");
      }
      reply({ type: "result", id: m.id });
    } else if (m.type === "readfile") {
      const bytes = py.FS.readFile(m.path);
      reply({ type: "file", id: m.id, bytes }, [bytes.buffer]);
    } else if (m.type === "listdir") {
      reply({ type: "result", id: m.id, value: JSON.stringify(py.FS.readdir(m.path).filter((n) => n !== "." && n !== "..")) });
    }
  } catch (err) {
    reply({ type: "error", id: m.id, message: String(err?.message ?? err) });
  }
};
