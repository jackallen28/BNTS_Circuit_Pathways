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
    function next() {
      if (!queue.length || count > 60) return Promise.resolve(lines);
      var url = queue.shift();
      if (seen[url]) return next();
      seen[url] = true;
      count++;
      return fetch(url, { credentials: "omit", cache: "no-store" }).then(function (r) {
        var type = r.headers.get("content-type") || "";
        if (!r.ok || !/javascript/i.test(type)) { lines.push(url + " -> " + r.status + " " + type); return null; }
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
    [
      "Try these, in order:",
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
    probe().then(function (lines) { tech.textContent = base + "\n" + (lines.length ? lines.join("\n") : "All of PiPath's files loaded when checked."); });
  }, 8000);
})();
