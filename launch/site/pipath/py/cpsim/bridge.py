"""What the page asks PiPath's own Coach engine (hints.py, levels.py, review.py, adapt.py). Everything is JSON in, JSON out."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from pipath import adapt, hints, levels, review  # noqa: F401  (adapt and review are used by the page too)

_engine: hints.HintEngine | None = None


def set_errors(errors_json: str) -> None:
    global _engine
    _engine = hints.HintEngine(json.loads(errors_json))


def precheck(code: str, starter: str) -> str:
    e = hints.precheck(code, starter)
    return json.dumps(asdict(e) if e else None)


def lint(code: str) -> str:
    return json.dumps(hints.gpio_lint(code))


def runaway(kind: str) -> str:
    """The Coach's explanation when a program was stopped for running away ("output", "busy" or "busy_gpio")."""
    d = _engine.diagnose(hints.ErrorInfo("PiPathRunaway", kind))
    return json.dumps(asdict(d))


def diagnose(stderr: str, filename: str, code: str, step_json: str) -> str:
    """The Coach's card for a crash (None if stderr has no Python error in it)."""
    err = hints.parse_traceback(stderr, filename, code)
    if err is None:
        return json.dumps(None)
    step = json.loads(step_json) if step_json else None
    return json.dumps(asdict(_engine.diagnose(err, step)))


def evaluate(checks_json: str, code: str, output: str, crashed: bool, runs: int, confirmed_json: str,
             folder: str, since: float) -> str:
    confirmed = json.loads(confirmed_json)
    res = hints.evaluate_checks(json.loads(checks_json), code, output, crashed, runs_this_step=runs,
                                confirmed=None if confirmed is None else set(confirmed),
                                folder=Path(folder) if folder else None, since=since or None)
    return json.dumps([asdict(r) for r in res])


# ---------------------------------------------------------------- the code review and the adaptive coach

def review_code(code: str) -> str:
    return json.dumps([asdict(t) for t in review.review(code)])


_adapter: adapt.Adapter | None = None


def _offer(o):
    return json.dumps(asdict(o) if o else None)


def adapt_new(level: str, saved_json: str, enabled: bool, context: str) -> None:
    global _adapter
    _adapter = adapt.Adapter(level, json.loads(saved_json) if saved_json else None, enabled, context)


def adapt_start(now: float, done: bool) -> None:
    _adapter.start_step(now, done)


def adapt_edit(now: float) -> None:
    _adapter.on_edit(now)


def adapt_hint() -> None:
    _adapter.on_hint()


def adapt_after_run(now: float, passed: bool, error_id: str, failing: str) -> str:
    return _offer(_adapter.after_run(now, passed, error_id or None, failing or None))


def adapt_tick(now: float) -> str:
    return _offer(_adapter.tick(now))


def adapt_hints_early(now: float) -> str:
    return json.dumps(bool(_adapter.hints_early(now)))


def adapt_step_done(now: float) -> str:
    return _offer(_adapter.step_done(now))


def adapt_state() -> str:
    return json.dumps(_adapter.state())


def adapt_set_level(level: str) -> None:
    _adapter.level = level if level in levels.LEVELS else levels.LEVELS[0]
