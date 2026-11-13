// If PiPath hasn't drawn anything a few seconds after the page opened, say so (instead of a blank
// screen) and show what went wrong. A classic script on purpose: it runs even when the main
// module can't load.
(function () {
  var problems = [];
  function note(text) { if (problems.length < 6) problems.push(String(text).slice(0, 200)); }
  window.addEventListener("error", function (e) {
    var t = e.target;
    if (t && t !== window && (t.src || t.href)) note("Could not load " + (t.src || t.href));
    else note(e.message || "An error happened");
  }, true);
  window.addEventListener("unhandledrejection", function (e) { note((e.reason && e.reason.message) || e.reason || "An error happened"); });

  // Fetches main.js and every file it imports, and lists the ones that didn't come back as JavaScript.
  function probe() {
    var seen = {}, lines = [], queue = ["/pipath/js/main.js"], count = 0;
    // the Python files PiPath loads once it starts (a filter that blocks one of these breaks running programs)
    function python() {
      return fetch("/pipath/py/manifest.json", { credentials: "omit", cache: "no-store" }).then(function (r) {
        if (!r.ok) { lines.push("/pipath/py/manifest.json -> " + r.status + " " + (r.headers.get("content-type") || "")); return lines; }
        return r.json().then(function (m) {
          return Promise.all((m.files || []).map(function (f) {
            return fetch("/pipath/py/" + f, { credentials: "omit", cache: "no-store" }).then(function (x) {
              if (!x.ok) lines.push("/pipath/py/" + f + " -> " + x.status + " " + (x.headers.get("content-type") || ""));
            }, function () { lines.push("/pipath/py/" + f + " -> could not be fetched"); });
          })).then(function () { return lines; });
        });
      }, function () { lines.push("/pipath/py/manifest.json -> could not be fetched"); return lines; });
    }
    function next() {
      if (!queue.length || count > 60) return python();
      var url = queue.shift();
      if (seen[url]) return next();
      seen[url] = true;
      count++;
      return fetch(url, { credentials: "omit", cache: "no-store" }).then(function (r) {
        var type = r.headers.get("content-type") || "";
        if (!r.ok || !/javascript/i.test(type)) {
          // who said no? the headers and the first words of the page tell us
          var who = ["server", "via", "cf-ray", "x-render-routing", "content-length"].map(function (n) { var v = r.headers.get(n); return v ? n + "=" + v : ""; }).filter(Boolean).join(" ");
          return r.text().then(function (t) {
            lines.push(url + " -> " + r.status + " " + type + " " + who + " body: " + t.replace(/\s+/g, " ").slice(0, 200));
            // is it only this time? try again after a moment, and once with a different ending on the address
            return new Promise(function (done) { setTimeout(done, 1500); }).then(function () {
              return Promise.all([fetch(url, { credentials: "omit", cache: "no-store" }), fetch(url + "?again=1", { credentials: "omit", cache: "no-store" })]);
            }).then(function (rs) {
              lines.push("  again: " + rs[0].status + ", with ?again=1: " + rs[1].status);
              return null;
            }, function () { lines.push("  again: could not be fetched"); return null; });
          });
        }
        return r.text();
      }).then(function (text) {
        if (text) {
          var re = /(?:import|export)[^'"\n;]*?from\s*["']([^"']+)["']|import\s*["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g, m;
          while ((m = re.exec(text))) {
            var spec = m[1] || m[2] || m[3];
            if (spec.charAt(0) === "/") queue.push(spec);
            else if (spec.charAt(0) === ".") queue.push(new URL(spec, location.origin + url).pathname);
          }
        }
        return next();
      }, function (e) { lines.push(url + " -> could not be fetched (" + (e && e.message) + ")"); return next(); });
    }
    return next();
  }

  setTimeout(function () {
    var app = document.getElementById("app");
    if (!app || app.childNodes.length) return;
    var box = document.createElement("div");
    box.style.cssText = "max-width:640px;margin:40px auto;padding:16px;background:#c0c0c0;border:2px outset #fff;font:14px/1.5 Arial,sans-serif;color:#000";
    var h = document.createElement("h2");
    h.textContent = "PiPath didn't start";
    h.style.margin = "0 0 8px";
    box.append(h);
    // a file that wouldn't load is most often a school or office network blocking it
    var netAdvice = document.createElement("p");
    netAdvice.style.cssText = "margin:0 0 10px;padding:8px;background:#ffffcc;border:2px solid #000;font-weight:bold";
    netAdvice.textContent = "This network may be blocking part of PiPath. Try a different network. If you are at the Tech School, connect to 'Tech Guest'.";
    netAdvice.hidden = !problems.some(function (t) { return /Could not load/.test(t); });
    box.append(netAdvice);
    [
      "Try these, in order:",
      "0. Switch to a different WiFi network, then reload this page. At the Tech School, connect to 'Tech Guest'.",
      "1. Hold Ctrl and press F5 (Cmd+Shift+R on a Mac) to load a fresh copy.",
      "2. Use Chrome or Edge on a laptop or computer.",
      "3. If the page is behind a password or a school filter, ask the person who set it up to allow all of this website's files.",
    ].forEach(function (line) {
      var p = document.createElement("p");
      p.textContent = line;
      p.style.margin = "0 0 6px";
      box.append(p);
    });
    var tech = document.createElement("pre");
    tech.style.cssText = "margin:10px 0 0;padding:8px;background:#fff;border:2px inset #fff;white-space:pre-wrap;font:12px/1.4 Consolas,monospace";
    var base = "For the helper:\n" + (problems.length ? problems.join("\n") : "(no error was seen)") +
      "\nsecure=" + window.isSecureContext + " isolated=" + window.crossOriginIsolated + " " + location.protocol + "//" + location.host +
      "\n" + navigator.userAgent;
    tech.textContent = base + "\nChecking PiPath's files...";
    box.append(tech);
    app.append(box);
    probe().then(function (lines) { if (lines.some(function (l) { return / -> 403 /.test(l); })) netAdvice.hidden = false; tech.textContent = base + "\n" + (lines.length ? lines.join("\n") : "All of PiPath's files loaded when checked."); });
  }, 8000);
})();
