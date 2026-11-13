// Asks the server for the first K lines of a file, for K = whole file down to 1, and reports the first K that a
// web filter blocks. (Only the TEST version has the server's /pipath/dev/prefix.)
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(file, n, plain) {
  const r = await fetch(`/pipath/dev/prefix?file=${encodeURIComponent(file)}&n=${n}${plain ? "&plain=1" : ""}&t=${Date.now()}`, { credentials: "omit", cache: "no-store" });
  return { status: r.status, type: r.headers.get("content-type") || "", text: r.status === 200 ? await r.text() : "" };
}

$("go").addEventListener("click", async () => {
  const file = $("file").value.trim();
  const log = (t) => { $("log").textContent = t; };
  const out = [];
  try {
    log("Getting the whole file...");
    const whole = await get(file, 100000, false);
    out.push(`whole file as JavaScript: ${whole.status} ${whole.type}`);
    const plainWhole = await get(file, 100000, true);
    out.push(`whole file as plain text: ${plainWhole.status} ${plainWhole.type}`);
    if (whole.status === 200 && plainWhole.status === 200) { out.push("Neither was blocked on this check."); $("result").textContent = out.join("\n"); log("Done."); return; }
    const reference = plainWhole.status === 200 ? plainWhole.text : "";
    const count = (reference || "").split("\n").length || 80;
    // the first K lines that are blocked: go up from 1 and stop at the first block
    let lo = 0;
    for (let k = 1; k <= Math.max(count, 120); k++) {
      log(`Checking the first ${k} lines...`);
      const r = await get(file, k, false);
      if (r.status !== 200) {
        out.push(`First blocked at line ${k} (status ${r.status}).`);
        const line = (reference.split("\n")[k - 1] ?? "(line not available: the plain copy was blocked too)");
        out.push(`That line is:\n${line}`);
        break;
      }
      lo = k;
      await sleep(120);
    }
    out.push(`Lines 1 to ${lo} were fine.`);
  } catch (e) {
    out.push(`Problem: ${e.message}`);
  }
  $("result").textContent = out.join("\n");
  log("Done.");
});
