// One Python runner for the whole app, started the first time a program needs it.
import { PyRunner } from "./runner.js";
import { errorsJson } from "../api.js";
import { state } from "../state.js";

let starting;
/** @returns {Promise<PyRunner>} */
export function getRunner(onStatus = () => {}) {
  if (state.runner) return Promise.resolve(state.runner);
  starting ??= (async () => {
    onStatus("Starting Python (the first time takes a few seconds)...");
    const runner = new PyRunner();
    await runner.start(await errorsJson());
    state.runner = runner;
    return runner;
  })().catch((e) => { starting = null; throw e; });
  return starting;
}

/** Start loading Python in the background (when the picker opens), so the first Run is quick. */
export function warmUp() {
  if (PyRunner.supported) getRunner().catch(() => {});
}
