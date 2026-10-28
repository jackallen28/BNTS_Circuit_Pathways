/* Circuit Pathways showcase. Plain script (no modules), so the site works opened straight from the folder. */
(function () {
  "use strict";
  const D = window.CP_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  };
  const md = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*(.+?)\*/g, "<i>$1</i>");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ the sky: drifting pixel squares
  const sky = $(".sky");
  const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#66d6da"];
  if (!reduced) for (let i = 0; i < 22; i++) {
    const s = 10 + Math.random() * 26;
    sky.append(h("i", { style: `left:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};` +
      `animation-duration:${26 + Math.random() * 30}s;animation-delay:-${Math.random() * 50}s` }));
  }

  // ------------------------------------------------------------ views (home / pipath / arduinopath)
  const ready = {};
  function show(view) {
    const toFinder = view === "finder";
    if (!["home", "pipath", "arduinopath", "compare"].includes(view)) view = "home";
    document.body.dataset.view = view;
    if (!ready[view]) { ready[view] = true; build(view); }
    if (toFinder) setTimeout(() => { const f = $("#finder"); f.classList.add("in"); f.scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); }, 60);
    else window.scrollTo(0, 0);
    pauseHidden();
    document.title = view === "home" ? "Circuit Pathways" : `${{ pipath: "PiPath", arduinopath: "ArduinoPath", compare: "Compare the pair" }[view]} · Circuit Pathways`;
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-go]");
    if (!a) return;
    e.preventDefault();
    const v = a.dataset.go;
    history.pushState(null, "", v === "home" ? location.pathname : "#" + v);
    if (v === "finder" && document.body.dataset.view === "home") { const f = $("#finder"); f.classList.add("in"); f.scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); return; }
    show(v);
  });
  addEventListener("popstate", () => show(location.hash.slice(1) || "home"));
  addEventListener("hashchange", () => show(location.hash.slice(1) || "home"));

  function build(view) {
    if (view === "home") return;
    const root = document.getElementById(view);
    if (view === "compare") { compare(root); observe(root); return; }
    $$(".shot", root).forEach(buildShot);
    $$("[data-levels]", root).forEach(buildLevels);
    $$("[data-fade]", root).forEach(buildFade);
    $$("[data-catalogue]", root).forEach(buildCatalogue);
    buildChapters(root);
    if (view === "pipath") piLab($("#pi-lab"));
    if (view === "arduinopath") { ardLab($("#ard-lab")); textBlocks($("#tb-demo")); boardsDemo($("#boards-demo")); }
    observe(root);
  }

  // ------------------------------------------------------------ reveal + autoplay as you scroll
  const revealer = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); revealer.unobserve(e.target); }
  }), { threshold: 0.12 });
  const player = new IntersectionObserver((es) => es.forEach((e) => {
    const v = e.target;
    if (v.dataset.pinned) return;
    if (e.isIntersecting && e.intersectionRatio > 0.45) {
      if (v.preload !== "auto") { v.preload = "auto"; }
      v.play().catch(() => {});
    } else v.pause();
  }), { threshold: [0, 0.45, 0.8] });
  function observe(root) {
    $$(".reveal", root).forEach((el) => revealer.observe(el));
    $$(".shot video, .bin-loop video", root).forEach((v) => player.observe(v));
  }
  $$(".home .reveal").forEach((el) => revealer.observe(el));
  function pauseHidden() { $$("video").forEach((v) => { if (!v.offsetParent) v.pause(); }); }

  // ------------------------------------------------------------ a snippet in a laptop, with pins
  function buildShot(shot) {
    const name = shot.dataset.snip;
    const notes = shot.dataset.notes ? JSON.parse(shot.dataset.notes) : [];
    const video = h("video", { muted: true, loop: true, playsinline: true, preload: "none", poster: `media/snippets/${name}.jpg`,
      src: `media/snippets/${name}.mp4`, "aria-label": "A short clip from the app (no sound)" });
    video.muted = true;
    const inner = h("div", { class: "screen-in" }, video);
    const pins = notes.map((n, i) => {
      if (!n.box) return null;
      const [x, y, w, hh] = n.box;
      const p = h("div", { class: "pin", style: `left:${x}%;top:${y}%;width:${w}%;height:${hh}%` }, h("b", {}, String(i + 1)));
      inner.append(p);
      return p;
    });
    const pause = h("button", { class: "shot-play", type: "button", onclick: () => {
      if (video.paused) { delete video.dataset.pinned; video.play().catch(() => {}); pause.textContent = "❚❚ Pause"; }
      else { video.dataset.pinned = "1"; video.pause(); pause.textContent = "▶ Play"; }
    } }, "❚❚ Pause");
    shot.append(h("div", { class: "laptop" }, h("div", { class: "screen" }, h("span", { class: "shot-tag" }, shot.dataset.app === "pi" ? "PiPath" : "ArduinoPath"), pause, inner), h("div", { class: "base" })));
    if (!notes.length) return;
    const list = h("ul", { class: "notes" });
    notes.forEach((n, i) => {
      const b = h("button", { type: "button" }, h("i", {}, String(i + 1)), h("span", { html: md(n.t) }));
      const on = () => {
        $$("button", list).forEach((x) => x.classList.toggle("on", x === b));
        pins.forEach((p, k) => p && p.classList.toggle("on", k === i));
        if (pins[i]) {                       // freeze on the frame the box was measured on
          video.dataset.pinned = "1"; video.pause();
          const go = () => { video.currentTime = (video.duration || 10) * 0.6; };
          video.readyState >= 1 ? go() : video.addEventListener("loadedmetadata", go, { once: true });
          if (video.preload !== "auto") { video.preload = "auto"; video.load(); }
          pause.textContent = "▶ Play";
        }
      };
      const off = () => {
        b.classList.remove("on"); pins.forEach((p) => p && p.classList.remove("on"));
        delete video.dataset.pinned; video.play().catch(() => {}); pause.textContent = "❚❚ Pause";
      };
      b.addEventListener("mouseenter", on); b.addEventListener("focus", on);
      b.addEventListener("mouseleave", off); b.addEventListener("blur", off);
      b.addEventListener("click", () => (b.classList.contains("on") ? off() : on()));
      list.append(h("li", {}, b));
    });
    shot.append(list);
  }

  // ------------------------------------------------------------ help levels
  const LEVELS = {
    pi: [
      ["Beginner", "Full explanations, and hints whenever you want them. A quick tour of the workspace is offered the first time."],
      ["Moderate", "Have a try first: hints unlock as the steps get harder. A code review after each step, and a deeper \"under the bonnet\" explanation of errors."],
      ["Advanced", "For Years 9–10 who've used Python before: just the goal, Python's real error messages with a technical explanation, fewer hints, Jump to the challenge, and steps you can skip."],
    ],
    ard: [
      ["Beginner", "Full explanations, hints any time, and the gentlest Coach."],
      ["Moderate", "Each project's own gradual release: hints once you've had a go, plus a code review."],
      ["Advanced", "Goal first, the real compiler messages with a technical explanation, fewer hints, skippable steps and Level up challenges."],
    ],
  };
  function buildLevels(el) {
    LEVELS[el.dataset.levels].forEach(([name, text], i) => {
      const b = h("button", { class: "lvl" + (i === 0 ? " on" : ""), type: "button", "aria-pressed": i === 0 ? "true" : "false",
        onclick: () => { $$(".lvl", el).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); }); } },
        h("h4", {}, name), h("p", {}, text));
      el.append(b);
    });
  }

  // ------------------------------------------------------------ gradual release (fade)
  function buildFade(el) {
    const info = [
      ["GUIDED", "g", "Early steps: the code is given with blanks to fill in, and hints are there straight away."],
      ["SOME HELP", "s", "Middle steps: instructions and examples, students write the code, hints after a first try."],
      ["ON YOUR OWN", "o", "Last steps: just the goal and the checklist. Hints after two tries, and never the full answer."],
    ];
    const text = h("p", { class: "fade-text" });
    const track = h("div", { class: "fade-track" });
    info.forEach(([label, cls, t], i) => {
      const b = h("button", { class: cls + (i === 0 ? " on" : ""), type: "button", onclick: () => pick(i) }, label);
      track.append(b);
    });
    function pick(i) { $$("button", track).forEach((b, k) => b.classList.toggle("on", k === i)); text.textContent = info[i][2]; }
    el.append(h("p", { class: "small" }, "Help fades as students grow. Tap each stage:"), track, text);
    pick(0);
  }

  $$(".flip").forEach((f) => f.addEventListener("click", () => f.classList.toggle("on")));

  // ------------------------------------------------------------ chapter dots
  function buildChapters(root) {
    const nav = $(".chapters", root);
    const chs = $$(".chapter", root);
    chs.forEach((c, i) => {
      c.id = c.id || `${root.id}-ch${i + 1}`;
      nav.append(h("a", { href: "#" + c.id, onclick: (e) => { e.preventDefault(); c.scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); } },
        h("span", {}, `${i + 1} · ${c.dataset.chapter}`)));
    });
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { const i = chs.indexOf(e.target); $$("a", nav).forEach((a, k) => a.classList.toggle("on", k === i)); }
    }), { rootMargin: "-45% 0px -45% 0px" });
    chs.forEach((c) => io.observe(c));
  }

  // ------------------------------------------------------------ "more in the app" catalogues
  const TIER_COLOURS = { simple: "#0b8f96", moderate: "#3f6fb5", computer: "#a8521c", advanced: "#704988", lab: "#9a4f8f", camera: "#2e7d5b",
    "getting-started": "#2e8b57", "sensors-sound": "#a8521c", "displays-lights": "#7a4fb0", games: "#c0392b", "wifi-iot": "#2f6db5", challenge: "#5b5470" };
  function buildCatalogue(el) {
    const app = el.dataset.catalogue;
    const data = D[app];
    const here = app === "pipath" ? "a1_traffic" : "smart-bin";
    const filter = h("div", { class: "cat-filter", role: "group", "aria-label": "Filter by tier" });
    const grid = h("div", { class: "cat-grid" });
    const tiers = [{ id: "all", title: "Everything" }].concat(data.tiers);
    tiers.forEach((t, i) => filter.append(h("button", { type: "button", class: i === 0 ? "on" : "", onclick: (e) => {
      $$("button", filter).forEach((b) => b.classList.toggle("on", b === e.currentTarget)); draw(t.id); } }, t.title)));
    function draw(tier) {
      grid.innerHTML = "";
      data.projects.filter((p) => tier === "all" || p.tier === tier).forEach((p) => {
        const t = data.tiers.find((x) => x.id === p.tier) || { title: p.tier };
        const needs = app === "pipath"
          ? [p.gpio && "GPIO kit", p.camera && "camera"].filter(Boolean).join(" + ")
          : (p.boards && p.boards.length && p.boards.every((b) => /esp|nodemcu|d1/.test(b)) ? "an ESP board (WiFi)" : "");
        grid.append(h("div", { class: "card" + (p.id === here ? " here" : "") },
          h("span", { class: "tier", style: `background:${TIER_COLOURS[p.tier] || "#555"}` }, t.title),
          h("h4", {}, p.title), h("p", {}, p.subtitle || p.intro || ""),
          needs ? h("div", { class: "needs" }, "Needs " + needs) : null,
          h("div", { class: "in-app" }, p.id === here ? "◉ Shown on this page" : `★ In ${app === "pipath" ? "PiPath" : "ArduinoPath"}`)));
      });
    }
    draw("all");
    el.append(filter, grid);
  }

  // ------------------------------------------------------------ full-walkthrough player
  const modal = $("#player"), mv = $("video", modal);
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".play-full");
    if (!b) return;
    $("#player-title").textContent = b.dataset.title;
    mv.src = b.dataset.video; modal.hidden = false; mv.play().catch(() => {}); $(".x", modal).focus();
  });
  const closeModal = () => { mv.pause(); mv.removeAttribute("src"); mv.load(); modal.hidden = true; };
  modal.addEventListener("click", (e) => { if (e.target === modal || e.target.closest("[data-close]")) closeModal(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) closeModal(); });

  // ------------------------------------------------------------ confetti
  function confetti() {
    if (reduced) return;
    for (let i = 0; i < 90; i++) {
      const c = h("i", { class: "confetti", style: `left:${Math.random() * 100}vw;background:${cols[i % 5]};` +
        `animation-duration:${2 + Math.random() * 2.5}s;animation-delay:${Math.random() * .6}s;transform:rotate(${Math.random() * 360}deg)` });
      document.body.append(c);
      setTimeout(() => c.remove(), 5500);
    }
  }

  // ============================================================ PiPath lab: Traffic Lights
  function piLab(root) {
    const win = h("div", { class: "w95 lab95" });
    const bar = h("div", { class: "w95-bar" }, h("span", {}, "Traffic Lights - PiPath"), h("i", { class: "x" }, "✕"));
    const tabs = h("div", { class: "lab-tabs", role: "tablist" });
    const body = h("div", { class: "w95-body" });
    win.append(bar, tabs, body);
    root.append(win);
    const tabWire = h("button", { type: "button", class: "on", role: "tab", onclick: () => go(0) }, "1. Check my wiring");
    const tabStep = h("button", { type: "button", role: "tab", onclick: () => go(1) }, "2. Step 1: Flash one light");
    tabs.append(tabWire, tabStep);
    const wire = wireCheck(() => go(1)), step = stepOne();
    body.append(wire, step);
    function go(i) {
      tabWire.classList.toggle("on", i === 0); tabStep.classList.toggle("on", i === 1);
      wire.hidden = i !== 0; step.hidden = i !== 1;
    }
    go(0);
  }

  function boardPanel() {
    const leds = ["red", "amber", "green"].map((c, i) => h("div", { class: "led " + c }, h("i"), h("span", { class: "legs" }),
      h("span", {}, ["Red LED", "Amber LED", "Green LED"][i]), h("small", {}, ["GPIO17", "GPIO27", "GPIO22"][i])));
    const btn = h("div", { class: "pbtn", role: "button", tabindex: "0", "aria-label": "Pedestrian button" }, h("i"));
    const panel = h("div", { class: "lab-right" },
      h("div", { class: "board-h" }, "BOARD", h("span", {}, "SIMULATOR")),
      h("div", { class: "leds" }, leds), btn, h("small", {}, "Pedestrian button · GPIO23"));
    return { panel, leds, btn, set(i, on) { leds[i].classList.toggle("on", on); } };
  }

  function wireCheck(next) {
    const board = boardPanel();
    const rows = ["Red LED (GPIO17)", "Amber LED (GPIO27)", "Green LED (GPIO22)", "Pedestrian button (GPIO23)"].map((t) =>
      h("div", { class: "wc-row" }, h("i", {}, "○"), h("span", {}, t)));
    const out = h("div", { class: "out", "aria-live": "polite" });
    const run = h("button", { class: "b95 go", type: "button" }, "Check my wiring");
    const nextB = h("button", { class: "b95", type: "button", disabled: true, onclick: next }, "Start step 1 ▸");
    const say = (t, cls) => { out.append(h("div", { class: cls || "" }, t)); out.scrollTop = 1e6; };
    run.addEventListener("click", async () => {
      run.disabled = true; out.innerHTML = ""; rows.forEach((r) => { r.className = "wc-row"; r.firstChild.textContent = "○"; });
      say("▶ Checking your wiring, one part at a time.", "info");
      for (let i = 0; i < 3; i++) {
        rows[i].classList.add("now");
        say(`Watch the ${["Red", "Amber", "Green"][i]} LED: it should blink 3 times.`);
        for (let k = 0; k < 3; k++) { board.set(i, true); await sleep(300); board.set(i, false); await sleep(300); }
        rows[i].classList.remove("now"); rows[i].classList.add("ok"); rows[i].firstChild.textContent = "✓";
      }
      rows[3].classList.add("now");
      say("Press the Pedestrian button (GPIO23) now...");
      board.btn.classList.add("ask");
      await new Promise((res) => {
        const press = () => { board.btn.classList.add("down"); setTimeout(() => board.btn.classList.remove("down"), 200); res(); };
        board.btn.addEventListener("click", press, { once: true });
        board.btn.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") press(); }, { once: true });
      });
      board.btn.classList.remove("ask");
      rows[3].classList.remove("now"); rows[3].classList.add("ok"); rows[3].firstChild.textContent = "✓";
      say("✓ Pedestrian button (GPIO23) works!", "info");
      say("Wiring check finished. Every part works.", "info");
      run.disabled = false; nextB.disabled = false; nextB.focus();
    });
    return h("div", { class: "wirecheck" },
      h("div", {},
        h("p", { style: "margin-top:0" }, h("b", {}, "Check my wiring"), " runs a test program for this activity's parts. (On a real Pi: blue HAT off while you wire, then back on.)"),
        h("div", { class: "wc-rows" }, rows),
        h("div", { class: "lab-tools", style: "border:0;padding:10px 0" }, run, nextB),
        out),
      board.panel);
  }

  function stepOne() {
    let level = "beginner", runs = 0, fails = 0, lastErr = null, hintsUsed = 0, hintsShown = 0, done = false, running = false, value = "";
    const board = boardPanel();
    const HINTS = ["The blank is how many seconds to wait.", "Replace `___` with `2`.", "The line should read `sleep(2)`."];
    const blank = h("input", { class: "blank", "aria-label": "The blank on line 11: how many seconds?", maxlength: "8", value: "___",
      onfocus: (e) => { if (e.target.value === "___") e.target.value = ""; }, oninput: (e) => { value = e.target.value; } });
    const L = (n, html, extra) => h("div", { class: "ln", "data-n": n }, h("span", { class: "n" }, String(n)), h("span", { html }), extra || null);
    const line11 = L(11, `<span class="fn">sleep</span>(`, null);
    line11.lastChild.after(blank, h("span", { html: `)          <span class="cm"># make this flash last 2 seconds</span>` }));
    const code = h("div", { class: "editor", "aria-label": "Code" },
      L(1, `<span class="kw">from</span> gpiozero <span class="kw">import</span> LED`),
      L(2, `<span class="kw">from</span> time <span class="kw">import</span> sleep`), L(3, ""),
      L(4, `red = LED(<span class="num-c">17</span>)       <span class="cm"># the red LED is wired to GPIO17</span>`), L(5, ""),
      L(6, `red.on()`), L(7, `<span class="fn">sleep</span>(<span class="num-c">1</span>)            <span class="cm"># wait 1 second</span>`),
      L(8, `red.off()`), L(9, `<span class="fn">sleep</span>(<span class="num-c">1</span>)`), L(10, `red.on()`), line11,
      L(12, `red.off()`), L(13, `<span class="fn">print</span>(<span class="str">"Done!"</span>)`));
    const out = h("div", { class: "out", "aria-live": "polite" });
    const say = (t, cls) => { out.append(h("div", { class: cls || "" }, t)); out.scrollTop = 1e6; };
    const checks = [["Your program runs"], ["The second flash lasts 2 seconds"], ["Your program gets to the end"]].map(([t]) =>
      h("div", { class: "ck" }, h("i", {}, "○"), h("span", {}, t)));
    const saw = h("input", { type: "checkbox", disabled: true });
    const sawRow = h("div", { class: "ck" }, h("label", {}, saw, h("span", {}, "I saw the red LED flash twice: short, then long")));
    const coach = h("div", { class: "coach", "aria-live": "polite" });
    const task = h("div", { class: "task" });
    const runB = h("button", { class: "b95 go", type: "button" }, "▶ Run");
    const help = h("div", { class: "help-sel" }, "Help:");
    ["beginner", "moderate", "advanced"].forEach((lv) => help.append(h("button", { type: "button", class: lv === level ? "on" : "",
      onclick: (e) => { level = lv; $$("button", help).forEach((b) => b.classList.toggle("on", b === e.currentTarget)); drawTask(); if (!lastErr && !done) idle(); } },
      lv[0].toUpperCase() + lv.slice(1))));
    const stars = h("div", { class: "stars", "aria-label": "stars" });

    function drawTask() {
      const full = level !== "advanced";
      task.innerHTML = "";
      task.append(h("span", { class: "badge", style: "background:#2e8b57" }, "GUIDED"), h("h4", {}, "STEP 1 OF 7 · FLASH ONE LIGHT"));
      if (full) task.append(h("p", { html: md("`LED(17)` makes an **object** that controls the LED on **GPIO17**. `red.on()` and `red.off()` switch it.") }),
        h("p", { html: md("`sleep(1)` pauses your program for 1 second, so there's time to see the light.") }));
      task.append(h("p", { html: md("**Your task:** fill in the blank so the second flash lasts **2 seconds**. Run it and watch the red LED.") }));
      if (!full) task.append(h("button", { class: "b95", type: "button", style: "font-size:11px;padding:2px 8px", onclick: () => { level = "moderate"; drawTask(); level = "advanced"; } }, "▸ Show the full explanation"));
    }
    function hintsAllowed() { return level === "advanced" ? (fails >= 2 ? 2 : 0) : HINTS.length; }
    function hintButton() {
      const max = hintsAllowed();
      if (!max) return h("p", { class: "small" }, level === "advanced" ? "Hints unlock after two tries." : "");
      if (hintsShown >= max) return null;
      return h("button", { class: "b95 hintbtn", type: "button", onclick: () => { hintsShown++; hintsUsed++; coachHints(); } },
        `Show ${hintsShown ? "next" : "first"} hint (${hintsShown + 1} of ${max})`);
    }
    function coachHints() {
      $$(".hint, .hintbtn, .small", coach).forEach((x) => x.remove());
      HINTS.slice(0, hintsShown).forEach((t) => coach.append(h("div", { class: "hint", html: md(t) })));
      const b = hintButton(); if (b) coach.append(b);
    }
    function idle() {
      coach.className = "coach";
      coach.innerHTML = `<h5>COACH</h5><p>Press <b>Run</b> whenever you like. It's not a test: running your code is how you find out what to change.</p>`;
    }
    function clue(title, text, tech) {
      const repeat = lastErr === title;
      lastErr = title;
      coach.className = "coach " + (repeat ? "nudge" : "bad");
      coach.innerHTML = "";
      if (repeat) coach.append(h("h5", {}, "COACH · A NUDGE"), h("h6", {}, "Same clue as last time"),
        h("p", {}, "That's the same clue again, so let's slow down. Look at the highlighted line and read it out loud, character by character."));
      coach.append(h("h5", {}, "COACH · SOMETHING BROKE"), h("h6", { html: md(title) }), h("p", { html: md(text) }));
      if (tech && level !== "beginner") coach.append(h("p", { class: "small", html: (level === "advanced" ? "<b>Under the bonnet:</b> " : "<b>Under the bonnet:</b> ") + md(tech) }));
      coachHints();
      line11.classList.add("hl");
    }

    runB.addEventListener("click", async () => {
      if (running || done) return;
      const v = (blank.value || "").trim();
      runs++;
      out.innerHTML = "";
      checks.forEach((c) => { c.className = "ck"; c.firstChild.textContent = "○"; });
      if (!v || /^_+$/.test(v)) {
        fails++;
        say("Not run yet: there are blanks (___) to fill in first.", "err");
        checks.forEach((c) => { c.className = "ck no"; c.firstChild.textContent = "✗"; });
        clue("There are still blanks to fill in", "Your code still has `___` in it. Those are spaces for you to fill in before Python can run it.",
          "PiPath checks for blanks before running, so Python never sees `___` (it would be a **NameError**: `___` is a valid but undefined name).");
        return;
      }
      line11.classList.remove("hl");
      say("▶ Running traffic_lights.py in the Simulator", "info");
      const num = Number(v);
      if (!/^\d+(\.\d+)?$/.test(v)) {
        fails++;
        await sleep(400);
        const name = (v.match(/^[A-Za-z_]\w*$/) || [])[0];
        if (level === "advanced") say(name ? `NameError: name '${name}' is not defined` : "SyntaxError: invalid syntax", "err");
        else say(`Line 11: ${name ? "Python doesn't know " + name : "Python got confused"}`, "err");
        checks[0].className = "ck no"; checks[0].firstChild.textContent = "✗";
        if (name) clue(`Python doesn't know \`${name}\``, `On line 11 you used \`${name}\`, but Python has never seen it before. \`sleep()\` needs a **number** of seconds, written with digits.`,
          "Python looks names up at **run time** (the LEGB rule). `" + name + "` wasn't bound anywhere, so this is a **NameError**.");
        else clue("Python got confused on line 11", "`sleep()` needs just a number inside the brackets, like `sleep(3)`.",
          "The parser expected a single expression inside the call's brackets, so this is a **SyntaxError**.");
        return;
      }
      running = true; runB.disabled = true; lastErr = null;
      coach.className = "coach"; coach.innerHTML = "<h5>COACH</h5><p>Watch the red LED on the board...</p>";
      const second = Math.min(num, 6);
      board.set(0, true); await sleep(1000); board.set(0, false); await sleep(1000);
      board.set(0, true); await sleep(second * 1000); board.set(0, false);
      say("Done!");
      say("■ Program finished.", "info");
      running = false; runB.disabled = false;
      checks[0].className = "ck ok"; checks[0].firstChild.textContent = "✓";
      checks[2].className = "ck ok"; checks[2].firstChild.textContent = "✓";
      if (num === 2) {
        checks[1].className = "ck ok"; checks[1].firstChild.textContent = "✓";
        saw.disabled = false;
        coach.className = "coach good";
        coach.innerHTML = "<h5>COACH</h5><h6>Did you see it happen?</h6><p>Your code passed the checks. Watch the board and tick the box when you see it:<br><b>I saw the red LED flash twice: short, then long</b></p>";
      } else {
        fails++;
        checks[1].className = "ck no"; checks[1].firstChild.textContent = "✗";
        coach.className = "coach";
        coach.innerHTML = `<h5>COACH · NEARLY THERE</h5><h6>Everything else is working</h6><p>The second flash lasted ${num} second${num === 1 ? "" : "s"}. The task asks for <b>2 seconds</b>.</p>`;
        coachHints();
      }
    });
    saw.addEventListener("change", () => {
      if (!saw.checked || done) return;
      done = true;
      const st = hintsUsed <= 2 ? 3 : hintsUsed <= 6 ? 2 : 1;
      coach.className = "coach good";
      coach.innerHTML = "<h5>COACH · NICE WORK</h5><h6>Step complete!</h6><p>You just controlled a light with code. Every traffic light starts here!</p>";
      stars.textContent = "★".repeat(st) + "☆".repeat(3 - st);
      coach.append(stars, h("p", { class: "small" }, hintsUsed ? `${hintsUsed} hint${hintsUsed > 1 ? "s" : ""} used. Stars count hints, not speed.` : "No hints used: three stars for independence!"),
        h("p", { class: "small" }, "The other 6 steps, and 23 more activities, are waiting in PiPath."),
        h("button", { class: "b95", type: "button", onclick: reset }, "Try again"));
      confetti();
    });
    function reset() {
      runs = fails = hintsUsed = hintsShown = 0; lastErr = null; done = false; saw.checked = false; saw.disabled = true;
      blank.value = "___"; out.innerHTML = ""; line11.classList.remove("hl");
      checks.forEach((c) => { c.className = "ck"; c.firstChild.textContent = "○"; });
      idle();
    }
    drawTask(); idle();
    return h("div", {},
      h("div", { class: "lab-tools" }, runB, h("button", { class: "b95", type: "button", disabled: true, title: "The full app has this button" }, "■ Stop"),
        h("span", { style: "font-size:13px" }, "Run on: ", h("b", {}, "Simulator")), help),
      h("div", { class: "lab-grid" },
        h("div", { class: "lab-left" }, task, h("div", { class: "checklist" }, h("h5", {}, "YOUR CHECKLIST"), checks, sawRow), coach),
        h("div", { class: "lab-mid" }, code, h("div", { style: "font:700 12px var(--w95-font)" }, "OUTPUT"), out),
        board.panel));
  }

  // ============================================================ ArduinoPath lab: the ultrasonic sensor
  // Parts are drawn with the Fritzing parts library's own pictures (img/fritzing/, CC BY-SA 3.0), like the app.
  // Positions are in Fritzing's units (0.01 inch), from the app's part files.
  const FZ = "img/fritzing/";
  const WIRES = [
    { id: "gnd", c: "#3a3a3a", t: "Black wire: GND on the board → GND on the sensor",
      bb: "M128.96,100 C128.96,28 472,232 455.17,160", sch: "M80,250 V272 H392 V140 H339.5" },
    { id: "vcc", c: "#d0202a", t: "Red wire: 5V on the board → VCC on the sensor",
      bb: "M175,290 C175,336 425.17,252 425.17,160", sch: "M70,20 V2 H230 V120 H260.5" },
    { id: "trig", c: "#f29b00", t: "", bb: "M214.96,100 C214.96,48 435.17,222 435.17,160", sch: "M150,120 H210 V140 H260.5" },
    { id: "echo", c: "#1f6fd6", t: "", bb: "M204.96,100 C204.96,38 445.17,232 445.17,160", sch: "M150,130 H190 V192 H370 V120 H339.5" },
  ];
  const ends = (d) => { const n = d.match(/-?[\d.]+/g).map(Number); return [[n[0], n[1]], [n[n.length - 2], n[n.length - 1]]]; };
  function fzWire(d, c, on, dots) {
    let s = `<g opacity="${on ? 1 : .2}"><path d="${d}" fill="none" stroke="rgba(0,0,0,.45)" stroke-width="${on ? 5.6 : 4.4}" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<path d="${d}" fill="none" stroke="${c}" stroke-width="${on ? 3.8 : 3}" stroke-linecap="round" stroke-linejoin="round"/>`;
    if (dots) ends(d).forEach(([x, y]) => { s += `<circle cx="${x}" cy="${y}" r="2.6" fill="${c}" stroke="rgba(0,0,0,.5)" stroke-width="1"/>`; });
    return s + "</g>";
  }
  function bbScene(onId) {
    return `<svg viewBox="0 18 650 320" role="img" aria-label="Breadboard view: an Arduino Uno wired to the distance sensor on a breadboard">
      <image href="${FZ}breadboard.svg" x="320" y="70" width="324.9" height="210"/>
      <image href="${FZ}uno.svg" x="0" y="90" width="294.96" height="210"/>
      <image href="${FZ}hc-sr04.svg" x="352.74" y="29.2" width="177.55" height="92.93"/>
      ${WIRES.map((w) => fzWire(w.bb, w.c, !onId || onId === w.id, true)).join("")}</svg>`;
  }
  function schScene(onId) {
    const lab = (x, y, t, a = "start") => `<text x="${x}" y="${y}" font-size="9" fill="#555" text-anchor="${a}" font-family="Segoe UI, Arial, sans-serif">${t}</text>`;
    return `<svg viewBox="-10 -8 420 292" role="img" aria-label="Schematic view: the Arduino Uno connected to the distance sensor">
      <image href="${FZ}uno-schematic.svg" x="0" y="20" width="150" height="230"/>
      <image href="${FZ}hc-sr04-schematic.svg" x="260" y="100" width="80" height="60"/>
      ${WIRES.map((w) => fzWire(w.sch, w.c, !onId || onId === w.id, false)).join("")}
      ${lab(266, 96, "HC-SR04")}</svg>`;
  }
  function ardLab(root) {
    const parts = D.arduinopath.parts, uno = D.arduinopath.boards.uno;
    WIRES[2].t = `Pin ${uno.pins.TRIG_PIN} → Trig (the sensor's "speaker")`;
    WIRES[3].t = `Pin ${uno.pins.ECHO_PIN} → Echo (the sensor's "ear")`;
    const win = h("div", { class: "vista labv" });
    win.append(h("div", { class: "vista-bar" }, h("span", {}, "Wiring Wizard: Distance Sensor (Uno)"), h("i", { class: "x" }, "✕")));
    const body = h("div", { class: "vista-body" });
    win.append(body);
    root.append(win);
    const names = ["Meet the part", "Wire it", "Test it", "Program it"];
    const dots = h("div", { class: "wiz-steps" });
    names.forEach((n, i) => { if (i) dots.append(h("span", { class: "wiz-sep" })); dots.append(h("span", { class: "wiz-dot" }, h("i", {}, String(i + 1)), n)); });
    const page = h("div", { class: "wiz-page" });
    const back = h("button", { class: "vbtn", type: "button" }, "◂ Back");
    const next = h("button", { class: "vbtn prime", type: "button" }, "Next ▸");
    const note = h("span", { class: "small", style: "color:#556" });
    body.append(dots, page, h("div", { class: "wiz-foot" }, back, note, next));
    let at = 0, tested = false, stopTest = null;

    function goTo(i) {
      if (stopTest) { stopTest(); stopTest = null; }
      at = i;
      $$(".wiz-dot", dots).forEach((d, k) => { d.classList.toggle("on", k === i); d.classList.toggle("done", k < i); });
      page.innerHTML = ""; back.disabled = i === 0; back.hidden = i === 3;
      [meet, wireIt, testIt, program][i]();
    }
    back.onclick = () => goTo(at - 1);
    next.onclick = () => goTo(at + 1);

    function meet() {
      const p = parts["hc-sr04"];
      page.append(h("div", { class: "part-card" },
        h("div", { class: "part-pic fz" }, h("img", { src: FZ + "hc-sr04.svg", alt: "The HC-SR04 ultrasonic distance sensor" }),
          h("div", { class: "legs" }, ["VCC", "Trig", "Echo", "GND"].map((t) => h("span", {}, t)))),
        h("div", {}, h("h4", {}, "Meet the " + p.name),
          h("dl", {}, h("dt", {}, "What it does"), h("dd", {}, p.what), h("dt", {}, "Which leg is which?"), h("dd", {}, p.legs)),
          h("div", { class: "dyk" }, h("b", {}, "Did you know? "), p.did_you_know))));
      next.textContent = "Next ▸"; next.disabled = false; note.textContent = "1 part in this test · real projects have a card for each part";
    }

    function wireIt() {
      let view = "bb", on = null;
      const dia = h("div", { class: "diagram fz-dia" });
      const draw = () => { dia.innerHTML = view === "bb" ? bbScene(on) : schScene(on); };
      const tabs = h("div", { class: "fz-tabs", role: "group", "aria-label": "View" },
        [["bb", "Breadboard"], ["sch", "Schematic"]].map(([k, n]) => h("button", { type: "button", class: k === view ? "on" : "", onclick: (e) => {
          view = k; $$("button", tabs).forEach((b) => b.classList.toggle("on", b === e.currentTarget)); draw(); } }, n)));
      const list = h("ol", { class: "wire-list" });
      WIRES.forEach((wr) => {
        const li = h("li", { tabindex: "0", onclick: () => pick(wr.id, li), onkeydown: (e) => { if (e.key === "Enter") pick(wr.id, li); } },
          h("span", { class: "sw-c", style: "background:" + wr.c }), h("span", {}, wr.t));
        list.append(li);
      });
      function pick(id, li) { on = on === id ? null : id; $$("li", list).forEach((x) => x.classList.toggle("on", x === li && on)); draw(); }
      draw();
      page.append(h("div", { class: "wire-grid" },
        h("div", {}, h("p", { style: "margin-top:0" }, h("b", {}, "Unplug the USB cable"), " before changing wires, and plug it back in after. Tap a wire to highlight it."), list,
          h("div", { class: "warn" }, "⚠ Never connect 5V to an ESP pin: on a 3.3V ESP board the wizard adds two 10kΩ resistors on Echo. And always use a resistor with an LED.")),
        h("div", {}, tabs, dia)));
      next.textContent = "Next: test it ▸"; next.disabled = false; note.textContent = "Fritzing parts, as in the app";
    }

    function testIt() {
      const reading = h("div", { class: "reading", "aria-live": "polite" }, "-- cm");
      const bar = h("i");
      const status = h("span", { class: "small", style: "color:#b3261e;font-weight:700" }, "✗");
      const range = h("input", { type: "range", class: "hand-range", min: "2", max: "400", value: "100", "aria-label": "Something in front: distance (cm)" });
      const label = h("b", {}, "100 cm");
      // the sensor faces up the page; the ping arcs travel up to whatever is in front
      const scene = h("div", { class: "fz-test", html: `<svg viewBox="0 0 400 300" role="img" aria-label="The distance sensor sends a ping up to something in front of it">
        <defs><linearGradient id="fzt-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eef7f9"/><stop offset="1" stop-color="#ffffff"/></linearGradient></defs>
        <rect width="400" height="300" fill="url(#fzt-bg)"/>
        <g stroke="#cfdde2" stroke-width="1">${[50, 100, 150].map((y) => `<line x1="20" x2="380" y1="${y}" y2="${y}" stroke-dasharray="3 5"/>`).join("")}</g>
        <g class="pings" fill="none" stroke="#0fb3bc" stroke-width="4" stroke-linecap="round">
          ${[0, 1, 2].map((k) => `<path class="ping" style="animation-delay:${k * .4}s" d="M168,206 A40,40 0 0 1 232,206"/>`).join("")}</g>
        <g class="thing"><rect x="-70" y="-14" width="140" height="22" rx="11" fill="#7a5c99"/><rect x="-70" y="-14" width="140" height="8" rx="4" fill="#fff" opacity=".25"/>
          <text class="thing-cm" x="82" y="2" font-size="15" font-weight="700" fill="#4b3a63" font-family="Segoe UI, Arial, sans-serif">100 cm</text></g>
        <image href="${FZ}hc-sr04.svg" x="111" y="205" width="177.55" height="92.93"/></svg>` });
      const svg = $("svg", scene), thing = $(".thing", svg), cmText = $(".thing-cm", svg);
      const serial = h("div", { class: "serial", "aria-label": "Serial Monitor" });
      let first = null;
      const place = () => {
        const cm = +range.value, y = 196 - Math.min(1, cm / 400) * 176;
        thing.setAttribute("transform", `translate(200,${y})`);
        cmText.textContent = cm + " cm";
        svg.style.setProperty("--reach", Math.max(.4, (206 - y) / 40).toFixed(2));
        label.textContent = cm + " cm";
      };
      range.addEventListener("input", place);
      place();
      const timer = setInterval(() => {                 // every 400 ms, like the app's test sketch
        const cm = Math.max(2, Math.round(+range.value));
        reading.textContent = cm + " cm"; bar.style.width = Math.min(100, cm / 4) + "%";
        serial.append(h("div", {}, `READ:sonar:${cm}`)); while (serial.childNodes.length > 60) serial.firstChild.remove(); serial.scrollTop = 1e6;
        if (first === null) first = cm;
        if (!tested && cm > 0 && Math.abs(cm - first) > 4) {    // the app ticks it by itself on a change of more than 4 cm
          tested = true; status.style.color = ""; status.className = "ok-msg"; status.textContent = "✓ Working!";
          next.disabled = false; next.focus();
        }
      }, 400);
      stopTest = () => clearInterval(timer);
      if (tested) { status.style.color = ""; status.className = "ok-msg"; status.textContent = "✓ Working!"; }
      page.append(h("div", { class: "test-grid" },
        h("div", {},
          h("p", { style: "margin-top:0" }, "The test program for this part is running ", h("b", {}, "in the simulator"), "."),
          scene,
          h("div", { class: "fz-slider" }, h("div", { class: "fz-slider-top" }, h("span", {}, "Something in front"), label),
            h("div", { class: "fz-slider-row" }, h("span", { class: "small" }, "Distance"), range))),
        h("div", {},
          h("div", { class: "test-row" }, h("h5", {}, "distance sensor", status),
            h("p", { class: "small", style: "margin:0" }, "Drag the distance: closer, then further away."),
            reading, h("div", { class: "bar" }, bar)),
          h("b", { class: "small" }, "Serial Monitor"), serial)));
      next.textContent = "Start programming ▸"; next.disabled = !tested;
      note.textContent = "The row ticks itself when the reading changes";
    }

    function program() {
      if (stopTest) stopTest();
      let hints = 0, lo = null, hi = null, timer = null, finished = false;
      const ticks = [false, false, false];
      const HINTS = ["The distance is stored in a variable on line 6.", "Its name is two letters long: `cm`.", "Type `cm` in the blank."];
      const blank = h("input", { class: "blank", style: "width:5ch", value: "___", "aria-label": "The blank: what to print",
        onfocus: (e) => { if (e.target.value === "___") e.target.value = ""; } });
      const L = (n, html, el) => { const d = h("div", { class: "ln" }, h("span", { class: "n" }, String(n)), h("span", { html })); if (el) d.append(el[0], h("span", { html: el[1] })); return d; };
      const code = h("div", { class: "code-v" },
        L(1, `<span class="cm">// Pins for your Arduino Uno R3 (from the Wiring Wizard)</span>`),
        L(2, `<span class="kw">#define</span> TRIG_PIN <span class="num-c">${uno.pins.TRIG_PIN}</span>`), L(3, `<span class="kw">#define</span> ECHO_PIN <span class="num-c">${uno.pins.ECHO_PIN}</span>`),
        L(4, ""), L(5, `<span class="kw">void</span> loop() {`),
        L(6, `  <span class="kw">long</span> cm = measureCm();`),
        L(7, `  Serial.print(`, [blank, `);`]),
        L(8, `  Serial.println(<span class="str">" cm"</span>);`), L(9, `  delay(<span class="num-c">300</span>);`), L(10, "}"));
      const serial = h("div", { class: "serial" });
      const range = h("input", { type: "range", class: "hand-range", min: "2", max: "400", value: "100", "aria-label": "Something in front: distance (cm)" });
      const dist = h("span", { class: "small" }, "Distance: 100 cm");
      range.addEventListener("input", () => { dist.textContent = `Distance: ${range.value} cm`; });
      const rows = ["It measures 80 cm", "It measures 10 cm", "The distance changes when I move my hand"]
        .map((t) => h("div", { class: "ck" }, h("i", {}, "○"), h("span", {}, t)));
      const coach = h("div", { class: "vcoach" });
      function hintBtn() {
        $$(".hint, .hb", coach).forEach((x) => x.remove());
        HINTS.slice(0, hints).forEach((t) => coach.append(h("div", { class: "hint", html: md(t) })));
        if (hints < HINTS.length && !finished) coach.append(h("button", { class: "vbtn hb", type: "button", style: "margin-top:6px;font-size:13px;padding:4px 12px",
          onclick: () => { hints++; hintBtn(); } }, hints ? "Show me another hint" : "Show me a hint"));
      }
      function intro() {
        coach.className = "vcoach"; coach.innerHTML = "";
        coach.append(h("h6", {}, "Step 2 of 4: Measure the distance"),
          h("p", { html: md("`measureCm()` sends a ping and times the echo. **Your task:** fill in the blank to print the distance, press **Run**, then slide to 80 cm and to 10 cm.") }));
        hintBtn();
      }
      const run = h("button", { class: "vbtn prime", type: "button" }, "▶ Run");
      run.addEventListener("click", () => {
        clearInterval(timer); serial.innerHTML = ""; lo = hi = null;
        const v = blank.value.trim();
        if (!v || /^_+$/.test(v)) {
          coach.className = "vcoach";
          coach.innerHTML = "<h6>Fill in the blanks first</h6><p>Your code still has <code>___</code> on line 7. Replace each <code>___</code> with the right code, then try again.</p>";
          hintBtn(); return;
        }
        if (v !== "cm") {
          const safe = v.replace(/[<&>"']/g, "");
          coach.className = "vcoach";
          coach.innerHTML = /^[A-Za-z_]\w*$/.test(v)
            ? `<h6>'${safe}' was not declared in this scope</h6><p>The compiler has never heard of <code>${safe}</code>. Check the spelling: the distance is saved on line 6.</p>`
            : `<h6>expected primary-expression</h6><p>The compiler expected a value inside <code>Serial.print( )</code>, like a variable's name.</p>`;
          hintBtn(); return;
        }
        if (!finished) intro();
        timer = setInterval(() => {
          if (!document.body.contains(serial)) { clearInterval(timer); return; }
          const cm = Math.max(2, Math.round(+range.value));
          serial.append(h("div", {}, `${cm} cm`)); while (serial.childNodes.length > 60) serial.firstChild.remove(); serial.scrollTop = 1e6;
          lo = lo === null ? cm : Math.min(lo, cm); hi = hi === null ? cm : Math.max(hi, cm);
          [Math.abs(cm - 80) <= 2, Math.abs(cm - 10) <= 2, hi - lo > 4].forEach((ok, i) => {
            if (ok && !ticks[i]) { ticks[i] = true; rows[i].className = "ck ok"; rows[i].firstChild.textContent = "✓"; }
          });
          if (ticks.every(Boolean) && !finished) {
            finished = true;
            const st = hints === 0 ? 3 : hints === 1 ? 2 : 1;
            coach.className = "vcoach good"; coach.innerHTML = "";
            coach.append(h("h6", {}, "Step complete!"), h("p", {}, "Your bin can measure how far away your hand is, with sound!"),
              h("div", { class: "stars", style: "font-size:30px" }, "★".repeat(st) + "☆".repeat(3 - st)),
              h("p", { class: "small" }, st === 3 ? "All on your own!" : "Hints helped you get there."),
              h("p", { class: "small" }, "The lid, the servo and the light are steps 1, 3 and 4 of the Smart Bin in ArduinoPath."));
            confetti();
          }
        }, 300);
      });
      intro();
      page.append(h("div", { class: "prog-grid" },
        h("div", {}, code, h("div", { style: "display:flex;gap:8px;margin-top:10px;align-items:center" }, run, h("span", { class: "small" }, "Simulator · Arduino Uno R3")),
          h("div", { class: "test-row", style: "margin-top:10px" }, h("h5", {}, "Checklist"), rows), coach),
        h("div", {}, h("b", {}, "Serial Monitor"), serial,
          h("div", { style: "display:flex;justify-content:space-between;margin:8px 0 2px" }, h("b", { class: "small" }, "Something in front"), dist), range)));
      next.textContent = "Start again ↺"; next.disabled = false;
      next.onclick = () => { clearInterval(timer); tested = false; next.onclick = () => goTo(at + 1); goTo(0); };
      note.textContent = "";
    }
    goTo(0);
  }

  // ------------------------------------------------------------ text or blocks
  function textBlocks(el) {
    const blocks = () => h("div", { class: "blocks" },
      h("span", { class: "blk hat c-start" }, "when the board starts"),
      h("span", { class: "blk in c-servo" }, "connect servo ", h("em", {}, "lid"), " to pin ", h("em", {}, "SERVO_PIN")),
      h("span", { class: "blk hat c-start", style: "margin-top:10px" }, "forever"),
      h("span", { class: "blk in c-sensor" }, "set ", h("em", {}, "cm"), " to ", h("em", {}, "distance in cm")),
      h("span", { class: "blk in c-logic" }, "if ", h("em", {}, "cm < 30"), " do"),
      h("span", { class: "blk in c-servo", style: "margin-left:36px" }, "turn servo ", h("em", {}, "lid"), " to ", h("em", {}, "0°")),
      h("span", { class: "blk in c-wait", style: "margin-left:36px" }, "wait ", h("em", {}, "5000"), " milliseconds"),
      h("span", { class: "blk in c-servo", style: "margin-left:36px" }, "turn servo ", h("em", {}, "lid"), " to ", h("em", {}, "90°")));
    const text = () => h("div", { class: "code-v", html: [
      `<span class="kw">void</span> setup() {`, `  lid.attach(SERVO_PIN);`, `}`, ``, `<span class="kw">void</span> loop() {`,
      `  <span class="kw">long</span> cm = measureCm();`, `  <span class="kw">if</span> (cm &lt; <span class="num-c">30</span>) {`,
      `    lid.write(<span class="num-c">0</span>);      <span class="cm">// open</span>`, `    delay(<span class="num-c">5000</span>);`,
      `    lid.write(<span class="num-c">90</span>);     <span class="cm">// close</span>`, `  }`, `}`]
      .map((l, i) => `<div class="ln"><span class="n">${i + 1}</span><span>${l}</span></div>`).join("") });
    const tabs = h("div", { class: "tb-tabs", role: "tablist" });
    const bodyEl = h("div", { class: "tb-body" });
    [["Blocks", blocks], ["Text (C++)", text]].forEach(([n, f], i) => tabs.append(h("button", { type: "button", class: i ? "" : "on", onclick: (e) => {
      $$("button", tabs).forEach((b) => b.classList.toggle("on", b === e.currentTarget)); bodyEl.innerHTML = ""; bodyEl.append(f()); } }, n)));
    bodyEl.append(blocks());
    const rows = [
      ["Getting started", "on start", "when the board starts"],
      ["Repeating", "forever", "forever"],
      ["See the real code", "JavaScript or Python", "Arduino C++ (what goes on the board)"],
      ["Hardware", "the micro:bit", "Arduino Uno, Nano, ESP boards and any breadboard part"],
      ["When they're ready", "type JavaScript or Python", "type C++ for the same project"],
    ];
    const table = h("table", { class: "mc" },
      h("tr", {}, h("th", {}, ""), h("th", {}, "MakeCode (micro:bit)"), h("th", {}, "ArduinoPath Blocks")),
      rows.map(([k, a, b]) => h("tr", {}, h("td", {}, k), h("td", {}, a), h("td", {}, b))));
    el.append(tabs, bodyEl, h("p", { class: "small", style: "margin:0;padding:6px 14px 10px;color:#556" }, "The Smart Bin's lid, both ways. The C++ the blocks make is always shown underneath, and that's what runs."),
      h("div", { class: "mc-wrap" }, h("b", {}, "Feels like MakeCode – but it builds real Arduino"), table,
        h("p", { class: "small", style: "margin:8px 0 0;color:#556" }, "The same checklist, Coach and Upload work in both blocks and text, and every project's starter code turns into blocks automatically.")));
  }

  // ------------------------------------------------------------ boards: one project, many boards
  function boardsDemo(el) {
    const bs = Object.entries(D.arduinopath.boards).sort((a, b) => a[1].order - b[1].order);
    bs.forEach(([id, b]) => el.append(h("figure", { class: "bcard" },
      h("div", { class: "bpic" }, h("img", { src: FZ + id + ".svg", alt: b.name, loading: "lazy" })),
      h("figcaption", {}, h("b", {}, b.name.replace(/ \(.*\)$/, "")),
        h("span", { class: "chips" }, h("i", { class: b.volts < 5 ? "v3" : "v5" }, b.volts + "V"), b.wifi ? h("i", { class: "wifi" }, "WiFi") : null)))));
  }

  // ------------------------------------------------------------ compare the pair: highlight what fits
  function compare(root) {
    const chips = $(".cmp-chips", root), table = $(".cmp-table", root), say = $(".cmp-say", root);
    if (!chips) return;
    chips.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      const was = b.classList.contains("on");
      $$("button", chips).forEach((x) => x.classList.remove("on"));
      const fit = was ? [] : b.dataset.fit.split(" ");
      if (!was) b.classList.add("on");
      ["pi", "ard", "mb"].forEach((k) => table.classList.toggle("fit-" + k, fit.includes(k)));
      table.classList.toggle("fitting", fit.length > 0);
      say.textContent = was ? "" : b.dataset.say;
    });
  }

  // ------------------------------------------------------------ the program finder (embedded): size the frame to fit
  addEventListener("message", (e) => {
    const d = e.data;
    if (!d || d.type !== "cp-finder-height") return;
    const f = $("#finder iframe");
    if (f) f.style.height = Math.max(420, Math.ceil(d.height) + 2) + "px";
  });

  // ------------------------------------------------------------ reading progress (inside an app's page)
  const bar = h("div", { class: "progress", "aria-hidden": "true" });
  document.body.append(bar);
  addEventListener("scroll", () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    bar.style.width = (max > 0 ? (scrollY / max) * 100 : 0) + "%";
  }, { passive: true });

  show(location.hash.slice(1) || "home");
})();
