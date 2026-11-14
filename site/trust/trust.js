// The trust page: helps a laptop trust the school server's own certificate, so the secure (https) address
// works. (Uploading to boards, and Python programs that wait for input, need a secure address.)

const $ = (s) => document.querySelector(s);
const host = location.hostname;
const secure = `https://${host}/`;
$("#secure-link").href = secure;
$("#secure-link").textContent = `the secure address (${secure.replace(/\/$/, "")})`;
$("#origin-policy").textContent = `http://${host}`;

// pick the right instructions
const ua = navigator.userAgent;
const which = /CrOS/.test(ua) ? "#cros" : /Mac OS X/.test(ua) ? "#mac" : "#win";
for (const id of ["#win", "#mac", "#cros"]) $(id).open = id === which;

fetch("/api/info", { cache: "no-store" }).then((r) => r.json()).then((info) => {
  $("#fingerprint").textContent = info.ca_fingerprint || "(this server has no certificate yet)";
}).catch(() => { $("#fingerprint").textContent = "(the server didn't answer)"; });

/** Does this browser trust the secure address? (A request to it only works if the certificate is trusted.) */
async function trusted() {
  if (location.protocol === "https:") return true;
  try {
    await fetch(`${secure}healthz`, { mode: "no-cors", cache: "no-store" });
    return true;
  } catch {
    return false;
  }
}

async function check(say) {
  const ok = await trusted();
  const status = $("#status");
  status.className = `status${ok ? " good" : ""}`;
  status.textContent = ok
    ? "This computer is set up. Use the secure address from now on."
    : "This computer doesn't trust the school server yet. Follow the steps below (it takes about a minute).";
  if (say) {
    $("#check-note").className = `note ${ok ? "good" : "bad"}`;
    $("#check-note").textContent = ok ? "All good! Opening the secure address..." : "Not yet. Check each step, and close and reopen the browser after step 2.";
    if (ok && location.protocol !== "https:") setTimeout(() => { location.href = secure; }, 1200);
  }
}

$("#check").addEventListener("click", () => check(true));
check(false);
