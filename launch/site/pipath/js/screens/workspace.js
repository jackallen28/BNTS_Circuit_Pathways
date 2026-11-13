// The activity workspace: instructions on the left, the code editor, the board and the Output
// on the right. Used for every lesson, and for Free Play (no steps, no checklist).

import { h, fill } from "../dom.js";
import { markdown } from "../markdown.js";
import { api, lesson as loadLesson, freeplay as loadFreeplay, demoFilesFor } from "../api.js";
import { state } from "../state.js";
import { createEditor } from "../widgets/editor.js";
import { createConsole } from "../widgets/outputpanel.js";
import { createBoard } from "../widgets/board.js";
import { messageBox, dialog } from "../widgets/window.js";
import { getRunner } from "../runtime/shared.js";
import { beta } from "../../../shared/beta.js";
import { getPi, piReady, supportFor, piSummary, savedPiId } from "../runtime/pi.js";
import { linkPiDialog } from "../dialogs/pi.js";
import {
  LEVELS, LEVEL_INFO, hintRules, goalText, canSkip, starsFor, newLessonProgress, projectKey, normaliseLevel,
} from "../progress.js";

const SUPPORT_LABEL = { guided: "GUIDED", scaffolded: "SOME HELP", brief: "ON YOUR OWN" };
const secs = () => performance.now() / 1000;

/**
 * @param {HTMLElement} root
 * @param {{ lessonId: string|null, onHome: () => void, openSettings: () => void, logOut: () => void, onLevelChange?: () => void }} o  lessonId null = Free Play
 * @returns {Promise<() => void>} cleanup
 */
export async function workspaceScreen(root, { lessonId, onHome, openSettings, logOut, nextActivity }) {
  const isFree = lessonId === null;
  const project = isFree ? null : state.catalog.projects.find((p) => p.id === lessonId);
  const les = isFree ? null : await loadLesson(lessonId);
  const fp = isFree ? await loadFreeplay() : null;
  const settings = () => state.me.settings;
  let level = normaliseLevel(settings().help_level);
  const key = isFree ? "freeplay" : projectKey(lessonId);
  const fileName = isFree ? "my_program.py" : (les.file_name ?? "program.py");
  const needsBoard = isFree || Boolean(les.requires_gpio || les.requires_camera);
  const usesStats = !isFree && les.steps.some((s) => /cpu_temp|cpu_load|ram_used/.test(s.demo ?? ""));
  const progressSaved = state.progress[lessonId ?? "freeplay"];
  const lp = isFree ? { hints_used: 0, runs: 0, errors: 0 } : { ...newLessonProgress(), ...(progressSaved ?? {}) };
  if (!isFree && lp.status === "complete") lp.status = "started";

  let stage = isFree ? "free" : lp.steps_started.length || lp.step ? "step" : "intro"; // intro | step | outro | free
  let stepIdx = isFree ? 0 : Math.min(lp.step ?? 0, les.steps.length - 1);
  const step = () => les.steps[stepIdx];
  let runner = null;
  let running = false;
  let runKind = "run";
  let where = !beta && settings().run_where === "pi" ? "pi" : "sim"; // sim: the Simulator in this browser. pi: the student's own Raspberry Pi.
  let piRun = false; // a program is running on the Pi right now
  const pi = getPi();
  let failedRuns = 0; // this step
  let runsThisStep = 0;
  let confirmed = new Set();
  let results = null; // checklist results of the last run
  let clue = null; // { d, shown } the Coach's card
  let offer = null; // an adaptive nudge
  let hintsShown = 0; // step hints revealed on this step
  let fullText = false;
  let stepDone = false;
  let cameraObject = settings().camera_object ?? "face";
  let demoInputs = [];
  let disposed = false;
  let saveTimer = 0;
  let codeTimer = 0;
  let lastReview = [];

  // ---------------------------------------------------------------- the pieces
  const editor = createEditor({ onChange: onEdit, onRun: () => run() });
  const con = createConsole({ onInput: (text) => { if (piRun) { pi.stdin(text); con.setWaiting(false); } else runner?.sendLine(text); } });
  const board = needsBoard
    ? createBoard({ camera: isFree || Boolean(les?.requires_camera), stats: isFree || usesStats, onCommand: (ev) => {
      if (ev.t === "show") cameraObject = ev.object;
      runner?.sendEvent(ev);
    } })
    : null;
  if (board) board.setParts(isFree ? [] : les.wiring ?? []);

  const levelSel = h("select", { class: "input", "aria-label": "Help level", style: { width: "auto" }, onchange: () => setLevel(levelSel.value) },
    LEVELS.map((l) => h("option", { value: l, text: LEVEL_INFO[l][0], selected: l === level })));
  const whereSel = h("select", { class: "input", id: "where", "aria-label": "Where to run your program", style: { width: "auto" }, onchange: () => setWhere(whereSel.value) },
    [["sim", "Simulator (in this browser)"], ["pi", "My Raspberry Pi"]].map(([v, t]) => h("option", { value: v, text: t, selected: v === where })));
  const piChip = h("button", { class: "btn small", type: "button", id: "pi-chip", onclick: () => linkPi() });
  const piPanel = h("section", { class: "win panel pi-panel", id: "pi-panel", "aria-label": "Your Raspberry Pi" },
    h("div", { class: "titlebar" }, h("span", { class: "logo" }), h("span", { class: "title", text: "Your Raspberry Pi" })),
    h("div", { class: "pi-body", id: "pi-body" }));
  const runBtn = h("button", { class: "btn go", type: "button", id: "run", onclick: () => run(), text: "▶ Run" });
  const goalBtn = h("button", { class: "btn", type: "button", id: "goal", onclick: () => watchGoal(), text: "Watch the goal" });
  const resetBtn = h("button", { class: "btn", type: "button", onclick: () => resetStep(), text: "Reset step" });
  const status = h("span", { class: "muted", id: "run-status" });
  const savedNote = h("span", { class: "muted", id: "save-status", text: "" });
  const guide = h("div", { class: "scroll", id: "guide", "aria-live": "polite" });
  const stepsBar = h("div", { class: "steps-bar" });

  const bar = h("div", { class: "bar" },
    h("button", { class: "btn", type: "button", onclick: async () => { await leave(); onHome(); }, text: "◂ Activities" }),
    h("b", { text: isFree ? (state.config.free_play_name ?? "Free Play") : les.title }),
    h("span", { class: "spacer" }),
    h("label", { class: "small" }, "Help: ", levelSel),
    beta ? null : h("label", { class: "small" }, "Run on: ", whereSel), beta ? null : piChip,
    runBtn, goalBtn, isFree ? null : resetBtn,
    h("button", { class: "btn", type: "button", onclick: openSettings, text: "Settings" }),
    h("button", { class: "btn", type: "button", onclick: async () => { await leave(); logOut(); }, text: "Log out" }));

  const guidePanel = h("section", { class: "win panel", "aria-label": "Instructions" },
    h("div", { class: "titlebar" }, h("span", { class: "logo" }), h("span", { class: "title", id: "guide-title" })), stepsBar, guide);
  const editorPanel = h("section", { class: "win panel", "aria-label": "Code editor" },
    h("div", { class: "titlebar" }, h("span", { class: "title", text: fileName }), savedNote, status), editor.el);
  const low = h("div", { class: ["low", !board && "no-board"] }, board?.el, board ? piPanel : null, con.el);
  const ws = h("div", { class: ["ws", isFree && "free"] }, guidePanel, h("div", { class: "work" }, editorPanel, low));
  fill(root, h("div", { class: "win", style: { flex: "1", margin: "0", borderRadius: "0" } },
    bar, ws, h("div", { class: "statusbar" }, h("span", { id: "status-level" }), h("span", { class: "spacer", style: { flex: "1" } }), h("span", { id: "status-where" }))));
  document.documentElement.style.setProperty("--code-size", `${settings().code_size ?? 15}px`);

  // ---------------------------------------------------------------- where it runs
  function layout() {
    const onPi = where === "pi" && runKind !== "goal"; // Watch the goal always plays in the Simulator
    if (board) { board.el.style.display = onPi ? "none" : ""; piPanel.style.display = onPi ? "" : "none"; }
    root.querySelector("#status-where").textContent = where === "pi"
      ? "Your program runs on your Raspberry Pi. It's sent there when you press Run, and the website doesn't keep it."
      : "Python runs in your browser. Nothing you write is sent anywhere.";
    const sum = piSummary(pi);
    piChip.hidden = where !== "pi";
    piChip.textContent = `${{ ok: "●", warn: "●", wait: "◌", none: "○" }[sum.tone]} ${sum.tone === "none" ? "Link to my Pi" : sum.text}`;
    piChip.classList.toggle("pi-ok", sum.tone === "ok");
    const piBody = root.querySelector("#pi-body"); // (activities with no board have no Pi panel)
    if (piBody) fill(piBody,
      h("p", { class: ["pi-line", sum.tone] , text: sum.text }),
      pi.hello ? h("p", { class: "small muted", text: `${pi.hello.model}` }) : null,
      h("p", { text: "When you press Run, your program is sent to your Pi and runs there for real. The LEDs, buttons and sensors you've wired to the Pi are the ones it uses. What it prints appears in the Output." }),
      h("p", { class: "small", text: "Take the blue HAT off before you change any wires, and put it back on after." }),
      h("p", {}, h("button", { class: "btn small", type: "button", id: "pi-link", text: sum.tone === "ok" ? "Change Pi" : "Link to my Pi", onclick: () => linkPi() })));
  }
  const onPiStatus = () => layout();
  pi.addEventListener("status", onPiStatus);
  pi.addEventListener("hello", onPiStatus);

  async function setWhere(v) {
    if (running) { whereSel.value = where; return; }
    where = v;
    state.me.settings = { ...settings(), run_where: v };
    api.saveSettings(state.me.settings).catch(() => {});
    layout();
    if (v === "pi" && !piReady()) await ensurePi();
  }

  async function linkPi() {
    const ok = await linkPiDialog();
    layout();
    return ok;
  }

  /** Is the Pi linked and willing? Tries the Pi remembered in this browser, then asks. */
  async function ensurePi() {
    if (piReady()) return true;
    const saved = savedPiId();
    if (saved && pi.state !== "connecting" && pi.state !== "pi-offline") {
      status.textContent = "Linking to your Pi...";
      try { await pi.connect(saved); } catch { /* the window below explains */ }
      status.textContent = "";
      layout();
      if (piReady()) return true;
    }
    if (pi.state === "pi-offline") {
      await messageBox({ instruction: "Your Pi is offline", text: ["Check that it is switched on and on the WiFi. It can take a minute after it starts.", "Then press Run again."] });
      await pi.connect(pi.code).catch(() => {});
      layout();
      return piReady();
    }
    if (pi.state === "connected" && !pi.canRun) {
      await messageBox({ instruction: "This Pi can't run programs", text: "It is linked, but it has been set to only switch pins. Ask your teacher to turn programs on for it (sudo pilink run on)." });
      return false;
    }
    return linkPi();
  }

  function stopCurrent() {
    if (piRun) pi.stop();
    else runner?.stop();
  }

  // ---------------------------------------------------------------- saving
  function onEdit(code) {
    clearTimeout(codeTimer);
    savedNote.textContent = beta ? "" : "Saving...";
    codeTimer = setTimeout(saveCode, 900);
    if (runner) runner.do("adapt_edit", secs()).catch(() => {});
    scheduleDraft();
  }
  function scheduleDraft() { /* the code is saved by saveCode */ }
  async function saveCode() {
    clearTimeout(codeTimer);
    try {
      await api.saveCode(key, editor.value);
      savedNote.textContent = beta ? "" : "Saved ✓";
    } catch (e) {
      savedNote.textContent = "Couldn't save";
    }
  }
  function saveProgress(now = false) {
    if (isFree) return;
    state.progress[lessonId] = { ...lp };
    clearTimeout(saveTimer);
    const go = () => api.saveProgress(lessonId, { ...lp }).catch(() => {});
    if (now) go(); else saveTimer = setTimeout(go, 300);
  }
  async function saveAdapt() {
    if (!runner) return;
    try {
      const st = await runner.call("adapt_state");
      state.me.settings = { ...settings(), adapt: st };
      await api.saveSettings(state.me.settings);
    } catch { /* not worth bothering the student */ }
  }

  // ---------------------------------------------------------------- the left panel
  function renderGuide() {
    document.getElementById("status-level").textContent = `Help: ${LEVEL_INFO[level][0]}`;
    const title = guidePanel.querySelector("#guide-title");
    if (stage === "free") return renderFree(title);
    title.textContent = stage === "intro" ? `${les.title}: start here` : stage === "outro" ? `${les.title}: well done!` : `Step ${stepIdx + 1} of ${les.steps.length}: ${step().title}`;
    stepsBar.replaceChildren(...les.steps.map((s, i) => h("button", {
      class: ["dot", lp.steps_done.includes(i) && "done", lp.steps_skipped.includes(i) && "skipped", stage === "step" && i === stepIdx && "here"], type: "button",
      title: `Step ${i + 1}: ${s.title}`, "aria-label": `Step ${i + 1}: ${s.title}`, onclick: () => goStep(i),
    })));
    if (stage === "intro") return renderIntro();
    if (stage === "outro") return renderOutro();
    renderStep();
  }

  function renderIntro() {
    fill(guide,
      markdown(les.intro),
      project?.concepts?.length ? h("p", {}, h("b", { text: "You'll use: " }), project.concepts.join(", ")) : null,
      les.requires_gpio ? wiringCard() : null,
      h("p", {}, h("button", { class: "btn default", type: "button", id: "start", text: lp.steps_started.length ? "Carry on ▶" : "Start step 1 ▶", onclick: () => goStep(Math.min(lp.step ?? 0, les.steps.length - 1)) }),
        " ",
        canSkip(level) && les.steps.length > 1 ? h("button", { class: "btn", type: "button", id: "jump", text: "Jump to the challenge", onclick: jumpToChallenge }) : null));
  }

  function wiringCard() {
    const rows = (les.wiring ?? []).filter((r) => r.connect || r.part);
    return h("div", { class: "note" },
      h("b", { text: "Wiring and safety" }),
      h("ul", {}, (les.kit === "grove"
        ? ["Put the Grove Base Hat on with the Pi turned off.", "Plug Grove cables in and out gently: they only fit one way round, so never force one.", "Each module goes in the port the list below says: the port's name is the GPIO number in the code."]
        : ["Take the blue HAT off before you change any wires, and put it back on after.", "Never turn the Pi off to change wires: you'd lose your progress.", "Always put a 330Ω resistor with an LED."]).map((t) => h("li", { text: t }))),
      rows.length ? h("ul", {}, rows.map((r) => h("li", {}, h("b", { text: `${r.part ?? r.kind}: ` }), r.connect ?? ""))) : null,
      h("p", { class: "small" }, "Using a real Pi? Set ", h("b", { text: "Run on: My Raspberry Pi" }), " at the top of the page to run your program on it, or ", h("a", { href: "/pipath/remote/", text: "use Pi Link" }), " to switch its pins by hand."));
  }

  function renderStep() {
    const s = step();
    const goal = canSkip(level) ? goalText(s) : null;
    const [unlockAfter, tiers] = hintRules(level, s.support);
    fill(guide,
      h("p", {}, h("span", { class: ["support", s.support], text: SUPPORT_LABEL[s.support] ?? s.support.toUpperCase() })),
      goal && !fullText ? markdown(goal) : markdown(s.text),
      goal ? h("p", {}, h("button", { class: "btn small", type: "button", onclick: () => { fullText = !fullText; renderGuide(); }, text: fullText ? "Show just the goal" : "▸ Show the full explanation" })) : null,
      checklist(s),
      hintBlock(s, unlockAfter, tiers),
      clueCard(), offerCard(), reviewBlock(),
      stepDone ? doneBlock() : null,
    );
  }

  function checklist(s) {
    const ul = h("ul", { class: "checklist", "aria-label": "Checklist" });
    s.checks.forEach((c, i) => {
      const r = results?.[i];
      const mark = r ? (r.passed ? "✓" : "✗") : "○";
      const li = h("li", { class: r ? (r.passed ? "ok" : "bad") : "" },
        h("span", { class: "mark", text: mark }),
        c.type === "confirm"
          ? h("label", {}, h("input", { type: "checkbox", checked: confirmed.has(i), disabled: runsThisStep === 0 && !stepDone, "aria-label": c.label, onchange: (e) => { e.target.checked ? confirmed.add(i) : confirmed.delete(i); if (results) reevaluate(); } }), " ", c.label ?? "I saw it happen")
          : h("span", { text: c.label ?? c.type }));
      ul.append(li);
    });
    return h("div", {}, h("h3", { text: "Checklist" }), ul, runsThisStep === 0 && !stepDone ? h("p", { class: "small muted", text: "Press Run. The checklist ticks by itself." }) : null);
  }

  function hintBlock(s, unlockAfter, tiers) {
    const hints = (s.hints ?? []).slice(0, tiers);
    if (!hints.length) return null;
    const unlocked = failedRuns >= unlockAfter || earlyHints;
    const shown = hints.slice(0, hintsShown);
    return h("div", {},
      h("h3", { text: "Hints" }),
      shown.length ? h("ol", { class: "hints" }, shown.map((t) => h("li", {}, markdown(t)))) : null,
      hintsShown < hints.length
        ? h("button", { class: "btn small", type: "button", id: "hint", disabled: !unlocked, text: unlocked ? `Show me a hint (${hintsShown + 1} of ${hints.length})` : `Hints unlock after ${unlockAfter} ${unlockAfter === 1 ? "try" : "tries"}`, onclick: () => revealHint() })
        : null);
  }

  function revealHint() {
    const s = step();
    const tiers = hintRules(level, s.support)[1];
    if (hintsShown >= Math.min(tiers, (s.hints ?? []).length)) return;
    hintsShown++;
    lp.hints_used++;
    lp.hints_seen = { ...(lp.hints_seen ?? {}), [s.id]: hintsShown };
    runner?.do("adapt_hint").catch(() => {});
    saveProgress();
    renderGuide();
  }

  function clueCard() {
    if (!clue) return null;
    const { d } = clue;
    const tiers = isFree ? 3 : hintRules(level, step().support)[1];
    const hints = (d.hints ?? []).slice(0, tiers);
    const real = d.error_type && d.error_type !== "PiPathBlanks" && d.error_type !== "PiPathRunaway" ? `${d.error_type}: ${d.message}` : null;
    return h("div", { class: ["coach", d.ok && "good"], role: "alert", id: "clue" },
      h("h4", { text: d.title }),
      level === "advanced" && real ? h("pre", { class: "console", style: { padding: "4px 6px", margin: "0 0 6px", color: "#ff9a9a" }, text: real }) : null,
      markdown(d.explain),
      d.line ? h("p", { class: "small" }, `On line ${d.line}`, d.code_line ? [": ", h("code", { text: d.code_line })] : "") : null,
      level !== "beginner" && d.tech ? h("details", { class: "tech", open: level === "advanced" }, h("summary", { text: "Under the bonnet" }), markdown(d.tech)) : null,
      clue.shown ? h("ol", { class: "hints" }, hints.slice(0, clue.shown).map((t) => h("li", {}, markdown(t)))) : null,
      h("div", { class: "row" },
        d.line ? h("button", { class: "btn small", type: "button", onclick: () => editor.setErrorLine(d.line), text: "Go to the line" }) : null,
        hints.length > (clue.shown ?? 0) ? h("button", { class: "btn small", type: "button", id: "clue-hint", text: "Show me a hint", onclick: () => { clue.shown = (clue.shown ?? 0) + 1; lp.hints_used++; runner?.do("adapt_hint").catch(() => {}); saveProgress(); renderGuide(); } }) : null));
  }

  function offerCard() {
    if (!offer) return null;
    return h("div", { class: "coach", role: "status", id: "offer" },
      h("h4", { text: offer.title }), markdown(offer.text),
      h("div", { class: "row" }, offer.actions.map(([label, action]) => h("button", { class: "btn small", type: "button", text: label, onclick: () => takeOffer(action) }))));
  }

  function takeOffer(action) {
    offer = null;
    if (action === "hint") { earlyHints = true; revealHint(); return; }
    if (action === "goal") watchGoal();
    else if (action === "full") fullText = true;
    else if (action.startsWith("level:")) setLevel(action.slice(6));
    renderGuide();
  }

  function reviewBlock() {
    if (!lastReview.length || level === "beginner") return null;
    return h("div", {}, h("h3", { text: "Code review" }), lastReview.map((t) => h("div", { class: "review" }, h("b", { text: t.title }), markdown(t.text), h("p", { class: "small muted", text: `Computing idea: ${t.idea}` }))));
  }

  function doneBlock() {
    const last = stepIdx === les.steps.length - 1;
    return h("div", { class: "coach good", id: "step-done" }, h("h4", { text: "Step complete ✓" }), markdown(step().success ?? "Well done!"),
      h("div", { class: "row" }, h("button", { class: "btn default", type: "button", id: "next", text: last ? "Finish activity ▶" : "Next step ▶", onclick: () => (last ? finish() : goStep(stepIdx + 1)) })));
  }

  function renderOutro() {
    const stars = starsFor(lp.hints_used, state.config);
    const msg = { 3: "Independence stars: you barely needed any hints!", 2: "Independence stars: you used a few hints and got there.", 1: "Independence stars: hints helped you through. That's what they're for!" }[stars];
    const next = nextActivity?.();
    fill(guide,
      h("p", { class: "stars", style: { fontSize: "28px" }, "aria-label": `${stars} of 3 stars` }, "★".repeat(stars) + "☆".repeat(3 - stars)),
      h("p", { text: msg }),
      markdown(les.outro),
      level === "advanced" && project?.stretch?.length ? h("div", {}, h("h3", { text: "Level up" }), h("ul", {}, project.stretch.map((t) => h("li", { text: t })))) : null,
      h("p", {}, h("button", { class: "btn default", type: "button", id: "back", text: "◂ Back to activities", onclick: async () => { await leave(); onHome(); } }), " ",
        next ? h("button", { class: "btn", type: "button", text: `Next: ${next.title} ▶`, onclick: async () => { await leave(); nextActivity(true); } }) : null));
  }

  // ---------------------------------------------------------------- Free Play's left panel
  function renderFree(title) {
    title.textContent = "Free Play: build anything";
    stepsBar.replaceChildren();
    const mode = settings().free_play_mode ?? "guide";
    fill(guide,
      h("p", { text: "Write any Python you like. Press Run to try it. Add a part to get working code for it." }),
      h("fieldset", {}, h("legend", { text: "Coach" }),
        [["guide", "Guide me: explain errors and give nudges"], ["alone", "On my own: only explain errors"]].map(([v, t]) => h("label", { style: { display: "block" } }, h("input", { type: "radio", name: "fpmode", value: v, checked: mode === v, onchange: async () => { state.me.settings = { ...settings(), free_play_mode: v }; await api.saveSettings(state.me.settings); runner?.do("adapt_new", level, JSON.stringify(settings().adapt ?? {}), v === "guide", "free").catch(() => {}); } }), " ", t))),
      h("h3", { text: "Add a part" }),
      h("div", { class: "row", style: { display: "flex", flexWrap: "wrap", gap: "4px" } }, fp.part.map((p) => h("button", { class: "btn small", type: "button", text: p.title, onclick: () => addPart(p) }))),
      clue ? clueCard() : null, offerCard(), reviewBlock(),
      h("h3", { text: "Need an idea?" }),
      h("ul", { style: { paddingLeft: "18px" } }, fp.idea.map((i) => h("li", {}, h("b", { text: i.title }), ` ${i.blurb} `, h("button", { class: "btn small", type: "button", text: "Use it", onclick: () => useIdea(i) })))));
  }

  const usedPins = () => new Set([...editor.value.matchAll(/\b(?:LED|Button|Buzzer|PWMLED|MotionSensor|Servo)\(\s*(\d+)/g)].map((m) => Number(m[1])));
  function addPart(p) {
    const free = [17, 27, 22, 5, 6, 13, 23, 24, 25, 18, 4, 26].filter((n) => !usedPins().has(n));
    const pin = free[0] ?? 17;
    const n = (editor.value.match(new RegExp(`\\b${p.id}\\d*\\s*=`, "g")) ?? []).length;
    const name = n ? `${p.id}${n + 1}` : p.id;
    const fillIn = (t) => t.replaceAll("{name}", name).replaceAll("{pin}", String(pin));
    let code = editor.value;
    const imports = (p.imports ?? []).filter((i) => !code.includes(i));
    if (imports.length) code = imports.join("\n") + "\n" + code;
    code = code.replace(/\s*$/, "") + (code.trim() ? "\n\n" : "") + fillIn(p.code);
    editor.value = code;
    onEdit(code);
    clue = { d: { title: `Added: ${p.title}`, explain: fillIn(p.tip ?? ""), ok: true, hints: [] }, shown: 0 };
    renderGuide();
  }
  function useIdea(i) { editor.value = i.code; onEdit(i.code); }

  // ---------------------------------------------------------------- moving between steps
  let earlyHints = false;

  async function goStep(i) {
    if (stage === "step" && i === stepIdx) return;
    stage = "step";
    stepIdx = i;
    lp.step = i;
    failedRuns = 0;
    runsThisStep = 0;
    confirmed = new Set();
    results = null;
    clue = null;
    offer = null;
    hintsShown = lp.hints_seen?.[step().id] ?? 0;
    fullText = false;
    stepDone = lp.steps_done.includes(i);
    earlyHints = false;
    lastReview = [];
    editor.clearError();
    const s = step();
    if (!lp.steps_started.includes(i)) {
      lp.steps_started.push(i);
      const old = editor.value;
      if (s.starter_mode === "replace") {
        if (old.trim() && old.trim() !== (s.starter ?? "").trim()) api.saveCode(`${key}-backup${i + 1}`, old).catch(() => {});
        editor.value = (s.starter ?? "").replace(/^\n/, "");
      } else if (s.starter_mode === "append" && s.starter) {
        editor.value = old.replace(/\s*$/, "") + "\n\n" + s.starter.replace(/^\n/, "");
      }
      saveCode();
    }
    saveProgress();
    if (runner) { runner.do("adapt_start", secs(), stepDone).catch(() => {}); runner.do("adapt_set_level", level).catch(() => {}); }
    renderGuide();
  }

  async function jumpToChallenge() {
    const last = les.steps.length - 1;
    for (let i = 0; i < last; i++) if (!lp.steps_done.includes(i) && !lp.steps_skipped.includes(i)) lp.steps_skipped.push(i);
    const prev = les.steps[last - 1];
    const s = les.steps[last];
    if (s.starter_mode !== "replace" && prev?.demo) editor.value = prev.demo.replace(/^\n/, "");
    lp.steps_started.push(...Array.from({ length: last }, (_, i) => i).filter((i) => !lp.steps_started.includes(i)));
    stage = "intro";
    await goStep(last);
  }

  async function resetStep() {
    if (stage !== "step") return;
    const s = step();
    const ok = await messageBox({ instruction: "Start this step's code again?", text: "Your current code is kept in a backup first.", buttons: [{ label: "Reset", value: "yes" }, { label: "Cancel", value: "no", default: true }] });
    if (ok !== "yes") return;
    api.saveCode(`${key}-backup${stepIdx + 1}`, editor.value).catch(() => {});
    editor.value = (s.starter ?? "").replace(/^\n/, "");
    saveCode();
    clue = null; results = null; renderGuide();
  }

  function finish() {
    stage = "outro";
    lp.status = "complete";
    lp.completed = Date.now();
    saveProgress(true);
    renderGuide();
  }

  async function setLevel(l) {
    level = normaliseLevel(l);
    levelSel.value = level;
    state.me.settings = { ...settings(), help_level: level };
    api.saveSettings(state.me.settings).catch(() => {});
    runner?.do("adapt_set_level", level).catch(() => {});
    renderGuide();
  }

  // ---------------------------------------------------------------- running programs
  async function ensureRunner() {
    if (runner) return runner;
    status.textContent = "Starting Python...";
    runner = await getRunner((t) => { status.textContent = t; });
    runner.addEventListener("output", onOutput);
    runner.addEventListener("board", onBoard);
    await runner.do("adapt_new", level, JSON.stringify(settings().adapt ?? {}), settings().adaptive !== false && (!isFree || (settings().free_play_mode ?? "guide") === "guide"), isFree ? "free" : "lesson");
    if (!isFree) await runner.do("adapt_start", secs(), stepDone);
    status.textContent = "";
    return runner;
  }

  const onOutput = (e) => con.write(e.detail.text, e.detail.stream === "err" ? "err" : "");
  function onBoard(e) {
    {
      const m = e.detail;
      board?.apply(m);
      if (m.t === "input") {
        con.setWaiting(true);
        if (runKind === "goal" && demoInputs.length) {
          const text = demoInputs.shift();
          setTimeout(() => { if (running) { con.write(text + "\n", "typed"); runner.sendLine(text); con.setWaiting(false); } }, 700);
        }
      }
    }
  }

  function setRunning(on) {
    running = on;
    runBtn.textContent = on && runKind === "run" ? "■ Stop" : "▶ Run";
    runBtn.classList.toggle("stop", on && runKind === "run");
    runBtn.classList.toggle("go", !(on && runKind === "run"));
    goalBtn.disabled = on && runKind === "run";
    whereSel.disabled = on;
    status.textContent = on ? (runKind === "goal" ? "Watching the goal..." : piRun ? "Running on your Pi..." : "Running...") : "";
    if (!on) con.setWaiting(false);
    layout();
  }

  async function filesFor(extra = []) {
    return demoFilesFor([...(les?.files ?? []), ...extra]);
  }

  async function run() {
    if (running) { stopCurrent(); return; }
    if (isFree === false && stage !== "step") return;
    try { await ensureRunner(); } catch (e) { await messageBox({ instruction: "Python couldn't start", text: e.message }); return; }
    if (where === "pi" && !(await ensurePi())) return;
    board?.ensureAudio();
    const code = editor.value;
    await saveCode();
    clue = null; offer = null; results = results ?? null; lastReview = [];
    editor.clearError();
    con.clear();
    const s = isFree ? null : step();
    runsThisStep++;
    lp.runs = (lp.runs ?? 0) + 1;
    // blanks left in: the Coach says so before running
    if (s) {
      const blank = await runner.call("precheck", code, s.starter ?? "");
      if (blank) {
        failedRuns++;
        const d = await runner.call("diagnose", `Traceback (most recent call last):\n  File "${fileName}", line ${blank.line}, in <module>\nPiPathBlanks: blanks left\n`, fileName, code, JSON.stringify(s));
        showClue(d ?? { title: "Fill in the blanks first", explain: `Your code still has ___ on line ${blank.line}.`, line: blank.line, hints: [] }, blank.line);
        await afterRun(false, "blanks", "");
        return;
      }
    }
    const lint = await runner.call("lint", code);
    for (const w of lint ?? []) con.write(`⚠ Coach tip: ${w}\n`, "tip");
    runKind = "run";
    let res;
    if (where === "pi") {
      res = await runOnPi(code);
    } else {
      board?.resetForRun();
      setRunning(true);
      try {
        res = await runner.run({ code, filename: fileName, env: { PIPATH_CAMERA_OBJECT: cameraObject }, files: await filesFor() });
      } finally {
        setRunning(false);
        board?.switchOff();
      }
    }
    if (disposed) return;
    await handleResult(res, code, s);
  }

  /** Sends the program to the student's Pi and shows what it prints. Gives back the same kind of result the Simulator does. */
  async function runOnPi(code) {
    piRun = true;
    setRunning(true);
    const onOut = (e) => {
      con.write(e.detail.text, e.detail.stream === "err" ? "err" : "");
      if (e.detail.stream === "out" && !e.detail.text.endsWith("\n")) con.setWaiting(true); // a question with no newline: waiting for an answer
    };
    pi.addEventListener("output", onOut);
    const started = Date.now() / 1000;
    let exit;
    try {
      exit = await pi.run({ code, name: fileName, files: await filesFor(), support: supportFor(code), cameraObject });
    } finally {
      pi.removeEventListener("output", onOut);
      piRun = false;
      setRunning(false);
    }
    let cwd = "";
    if (!disposed && Object.keys(exit.files ?? {}).length) {
      try { cwd = await runner.putFiles(`/student/pi_${Math.round(started)}`, exit.files); } catch { /* the file checks just won't see them */ }
    }
    const reason = exit.reason === "output" ? "runaway_output" : exit.reason === "stop" ? "stop" : exit.reason ?? null;
    return { rc: exit.rc, stopped: Boolean(exit.stopped) && !String(reason).startsWith("runaway"), reason, stdout: exit.stdout, stderr: exit.stderr, cwd, started };
  }

  async function handleResult(res, code, s) {
    if (res.reason?.startsWith("runaway")) {
      const kind = res.reason.replace("runaway_", "");
      con.write(`\n[PiPath stopped your program: it was running away]\n`, "err");
      const d = await runner.call("runaway", kind);
      showClue(d);
      lp.errors = (lp.errors ?? 0) + 1;
      failedRuns++;
      return afterRun(false, "runaway", "");
    }
    const crashed = (res.rc !== 0 && !res.stopped) || res.stderr.includes("Traceback");
    if (crashed) {
      const d = await runner.call("diagnose", res.stderr, fileName, code, s ? JSON.stringify(s) : "");
      lp.errors = (lp.errors ?? 0) + 1;
      failedRuns++;
      if (d) showClue(d, d.line);
      else showClue({ title: "Something went wrong", explain: "Python stopped, but I couldn't read why. Read the red text in the Output.", hints: [] });
      return afterRun(false, d?.entry_id ?? "unknown", "");
    }
    if (isFree) {
      if ((settings().free_play_mode ?? "guide") === "guide") {
        const tips = await runner.call("review_code", code);
        lastReview = (tips ?? []).slice(0, 1);
      }
      saveAdapt();
      renderGuide();
      return;
    }
    if (res.stopped && s.run_mode !== "until_stopped") { renderGuide(); return; } // the student ended it: nothing to check
    await evaluate(res, code, s);
  }

  async function evaluate(res, code, s) {
    lastRun = { res, code };
    results = await runner.call("evaluate", JSON.stringify(s.checks), code, res.stdout, false, runsThisStep, JSON.stringify([...confirmed]), res.cwd, res.started - 1);
    const failing = results.find((r) => !r.passed);
    if (!failing) return completeStep();
    const onlyConfirms = results.every((r) => r.passed || r.type === "confirm");
    if (onlyConfirms) {
      clue = { d: { title: "Did you see it happen?", explain: "Your program ran. Tick each “I saw it happen” box when you've seen it in the Simulator (or on your real kit).", ok: true, hints: [] }, shown: 0 };
      renderGuide();
      return;
    }
    failedRuns++;
    clue = failing.fail ? { d: { title: "Not quite yet", explain: failing.fail, hints: [] }, shown: 0 } : null;
    await afterRun(false, "", failing.label);
  }

  let lastRun = null;
  async function reevaluate() {
    if (!lastRun || stepDone) { renderGuide(); return; }
    const s = step();
    results = await runner.call("evaluate", JSON.stringify(s.checks), lastRun.code, lastRun.res.stdout, false, runsThisStep, JSON.stringify([...confirmed]), lastRun.res.cwd, lastRun.res.started - 1);
    if (results.every((r) => r.passed)) { clue = null; return completeStep(); }
    renderGuide();
  }

  async function completeStep() {
    stepDone = true;
    clue = null;
    if (!lp.steps_done.includes(stepIdx)) lp.steps_done.push(stepIdx);
    saveProgress(true);
    if (level !== "beginner") {
      const tips = await runner.call("review_code", editor.value);
      lastReview = tips ?? [];
    }
    offer = await runner.call("adapt_step_done", secs());
    saveAdapt();
    renderGuide();
    guide.querySelector("#step-done")?.scrollIntoView({ block: "nearest" });
  }

  async function afterRun(passed, errorId, failing) {
    if (!runner) return renderGuide();
    offer = await runner.call("adapt_after_run", secs(), passed, errorId, failing);
    earlyHints = earlyHints || (await runner.call("adapt_hints_early", secs())) === true;
    saveProgress();
    saveAdapt();
    renderGuide();
  }

  function showClue(d, line) {
    clue = { d, shown: 0 };
    if (line) editor.setErrorLine(line);
    renderGuide();
    guide.querySelector("#clue")?.scrollIntoView({ block: "nearest" });
  }

  async function watchGoal() {
    if (running) return;
    if (isFree || stage !== "step") { messageBox({ instruction: "Watch the goal needs a step", text: "Open a step of an activity, then press Watch the goal to see what it should do." }); return; }
    try { await ensureRunner(); } catch (e) { await messageBox({ instruction: "Python couldn't start", text: e.message }); return; }
    board?.ensureAudio();
    const s = step();
    con.clear();
    con.write("▶ Watching the goal (your code isn't touched).\n", "sys");
    demoInputs = (s.demo_input ?? "").replace(/\n$/, "") ? (s.demo_input ?? "").replace(/\n$/, "").split("\n") : [];
    runKind = "goal";
    board?.resetForRun();
    setRunning(true);
    try {
      await runner.run({ code: s.demo, filename: `goal_${fileName}`, env: { PIPATH_CAMERA_OBJECT: cameraObject }, files: await demoFilesFor([...(les.files ?? []), ...(s.demo_files ?? [])]), events: s.demo_events, seconds: s.demo_seconds });
    } finally {
      setRunning(false);
      board?.switchOff();
      runKind = "run";
    }
    con.write("\n▶ That's the goal. Now try it yourself!\n", "sys");
  }

  // ---------------------------------------------------------------- getting going
  async function leave() {
    clearInterval(tickTimer);
    stopCurrent();
    await saveCode();
    saveProgress(true);
    await saveAdapt();
  }

  const tickTimer = setInterval(async () => {
    if (!runner || running || disposed || stage === "intro" || stage === "outro") return;
    try {
      const o = await runner.call("adapt_tick", secs());
      if (o && !offer) { offer = o; renderGuide(); }
    } catch { /* the worker was busy */ }
  }, 15_000);

  const onHide = () => { if (document.visibilityState === "hidden") { saveCode(); saveProgress(true); } };
  document.addEventListener("visibilitychange", onHide);

  const saved = await api.code(key);
  editor.value = saved ?? (isFree ? "# Free Play: write any Python you like.\nfrom gpiozero import LED\nfrom time import sleep\n\nprint(\"Hello from Free Play!\")\n" : "");
  if (!isFree && saved === null && stage === "step") stage = "intro";
  if (stage === "step") {
    stepDone = lp.steps_done.includes(stepIdx);
    hintsShown = lp.hints_seen?.[step().id] ?? 0;
    if (!lp.steps_started.includes(stepIdx)) { stage = "intro"; }
  }
  renderGuide();
  layout();
  ensureRunner().catch((e) => { status.textContent = ""; con.write(`Python couldn't start: ${e.message}\n`, "err"); });

  return () => {
    disposed = true;
    clearInterval(tickTimer);
    document.removeEventListener("visibilitychange", onHide);
    runner?.removeEventListener("output", onOutput);
    runner?.removeEventListener("board", onBoard);
    pi.removeEventListener("status", onPiStatus);
    pi.removeEventListener("hello", onPiStatus);
    stopCurrent();
  };
}
