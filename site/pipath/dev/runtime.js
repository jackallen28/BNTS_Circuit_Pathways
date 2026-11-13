// A bare page for trying the Python runtime. Output goes in #out, board messages in #board.
import { PyRunner } from "../js/runtime/runner.js";

const $ = (s) => document.querySelector(s);
const runner = new PyRunner();
window.pyRunner = runner;

runner.addEventListener("output", (e) => { $("#out").textContent += e.detail.text; });
runner.addEventListener("board", (e) => {
  const { bytes, ...rest } = e.detail;
  $("#board").textContent += JSON.stringify(rest) + "\n";
});
runner.addEventListener("board", (e) => { if (e.detail.t === "input") $("#state").textContent = "Waiting for you to type..."; });

const errors = await (await fetch("../data/errors.json")).text();
try {
  const version = await runner.start(errors);
  $("#state").textContent = `Python ${version.split(" ")[0]} is ready. isolated=${crossOriginIsolated}`;
  $("#run").disabled = false;
} catch (err) {
  $("#state").textContent = `Couldn't start: ${err.message}`;
}

$("#run").addEventListener("click", async () => {
  $("#out").textContent = "";
  $("#board").textContent = "";
  $("#run").disabled = true;
  const res = await runner.run({ code: $("#code").value, filename: "dev.py" });
  $("#state").textContent = `Finished: rc=${res.rc} stopped=${res.stopped} reason=${res.reason}`;
  $("#run").disabled = false;
});
$("#stop").addEventListener("click", () => runner.stop());
