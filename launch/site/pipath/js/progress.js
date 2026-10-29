// The rules of the lessons that don't need a screen: help levels, when hints unlock, stars,
// and a lesson's saved progress. The same rules as PiPath's levels.py and storage.py
// (the tests compare them with the Python ones).

export const LEVELS = ["beginner", "moderate", "advanced"];
export const DEFAULT_LEVEL = "beginner";

export const LEVEL_INFO = {
  beginner: ["Beginner", "New to Python. Full explanations, and hints whenever you want them."],
  moderate: ["Moderate", "You've done some Python. Help fades as you go: have a try, then hints unlock. Code reviews after each step."],
  advanced: ["Advanced", "I've used Python before (Year 9-10). Tutorial off: just the goal, fewer hints, Python's real error messages, code reviews, and you can skip ahead."],
};

const SUPPORT_RULES = { guided: [0, 3], scaffolded: [1, 3], brief: [2, 2] };
const GOAL = /\*\*(Your task|Goal|Your goal)\b[^*]*\*\*/;

export const normaliseLevel = (level) => (LEVELS.includes(level) ? level : DEFAULT_LEVEL);

/** [failed runs before hints unlock, how many hint tiers can be seen] */
export function hintRules(level, support) {
  if (level === "beginner") return [0, 3];
  if (level === "advanced") return [2, 2];
  return SUPPORT_RULES[support] ?? SUPPORT_RULES.scaffolded;
}

/** The short version of a step for Advanced: its `goal`, or the text from "Your task" / "Goal" on. */
export function goalText(step) {
  if (step.goal) return step.goal;
  const m = GOAL.exec(step.text ?? "");
  if (!m || m.index === 0) return null; // no shorter version: show the whole text
  return step.text.slice(m.index);
}

export const canSkip = (level) => level === "advanced";
export const offerTour = (level) => level !== "advanced";

/** Independence stars: they count hints, not speed. */
export function starsFor(hintsUsed, config = {}) {
  const three = config.three_star_max_hints ?? 2;
  const two = config.two_star_max_hints ?? 6;
  return hintsUsed <= three ? 3 : hintsUsed <= two ? 2 : 1;
}

export function newLessonProgress(now = Date.now()) {
  return { status: "started", step: 0, steps_done: [], steps_started: [], steps_skipped: [], hints_used: 0, hints_seen: {}, runs: 0, errors: 0, started: now, completed: null };
}

/** A lesson's id as a save-file project name (letters, digits and dashes). */
export const projectKey = (lessonId) => lessonId.replace(/_/g, "-");
export const lessonKey = (key) => key.replace(/-/g, "_");

/** Whether the picker should show a project, given the student's "Show" choice. */
export function shown(project, show) {
  if (!show || show === "all") return true;
  if (show === "hardware") return Boolean(project.gpio || project.camera);
  return project.tier === show;
}

/** Activities that need something the browser can't give (a drawing window). Shown, but not opened. */
export const NOT_IN_BROWSER = {
  m2_turtle: "Turtle drawings need their own window, which isn't in the browser version yet. Use PiPath on a Raspberry Pi for this one.",
};
