"""The scheduler: time, events from the board, blinking lights and what is reported to the page."""
from __future__ import annotations

import heapq
import json
import os
import sys
import time as _time

import _cp_host as host

SLICE = 0.02          # the longest a sleep goes without looking at the board (seconds)
_epoch = _time.time()  # wall-clock time at the host clock's zero

devices: list = []     # every device made (including closed ones, until the run ends)
pin_owner: dict = {}   # BCM pin -> the device using it
distance_m: dict = {}  # DistanceSensor echo pin -> what it "sees", in metres
analog: dict = {}      # Grove Base Hat analog channel -> its reading, 0 to 999 (a knob, light or moisture sensor)
_tasks: list = []      # heap of (due, seq, fn)
_seq = 0
_last_devs = None
_last_pins = None
_in_stop = False


def reset():
    global _tasks, _seq, _last_devs, _last_pins
    devices.clear()
    pin_owner.clear()
    distance_m.clear()
    analog.clear()
    _tasks = []
    _seq = 0
    _last_devs = _last_pins = None


def now() -> float:
    """Seconds since the program started, on the host's clock."""
    return host.now_ms() / 1000.0


# ---------------------------------------------------------------- tasks (blinking, fading, holding)

def call_later(delay: float, fn) -> list:
    """Run fn() after delay seconds (while the program sleeps or waits). Returns a handle to cancel."""
    global _seq
    _seq += 1
    entry = [now() + max(0.0, delay), _seq, fn, True]
    heapq.heappush(_tasks, entry)
    return entry


def cancel(handle) -> None:
    if handle:
        handle[3] = False


def _next_due():
    while _tasks and not _tasks[0][3]:
        heapq.heappop(_tasks)
    return _tasks[0][0] if _tasks else None


# ---------------------------------------------------------------- the board talking to the program

def _apply_event(ev: dict) -> None:
    kind = ev.get("t")
    pin = ev.get("pin")
    if kind in ("press", "release") and pin in pin_owner:
        d = pin_owner[pin]
        if hasattr(d, "_board_set"):
            d._board_set(kind == "press")
    elif kind == "distance":
        distance_m[int(ev["pin"])] = max(0.02, float(ev["cm"]) / 100.0)
    elif kind == "analog":
        analog[int(ev["ch"])] = max(0, min(999, int(float(ev["value"]))))
    elif kind == "stat":
        os.environ[f"PIPATH_SIM_{str(ev['name']).upper()}"] = str(float(ev["value"]))
    elif kind == "show":
        os.environ["PIPATH_CAMERA_OBJECT"] = str(ev["object"])
        shim = sys.modules.get("pipath_shim")
        if shim is not None:
            shim.camera_view["object"] = str(ev["object"])


def pump() -> None:
    """Look after everything that is due: stop requests, the board, timers, and report changes."""
    if host.should_stop():                               # Stop was pressed
        raise KeyboardInterrupt()
    for ev in json.loads(host.poll()):
        _apply_event(ev)
    t = now()
    while True:
        due = _next_due()
        if due is None or due > t:
            break
        entry = heapq.heappop(_tasks)
        if entry[3]:
            entry[2]()
    for d in list(devices):
        poll = getattr(d, "_poll", None)
        if poll is not None and not d.closed:
            poll(t)
    report()


def sleep(seconds) -> None:
    """time.sleep(), but the program's lights, buttons and sensors carry on while it waits."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        raise TypeError("'%s' object cannot be interpreted as an integer or float" % type(seconds).__name__) from None
    if seconds < 0:
        raise ValueError("sleep length must be non-negative")
    end = now() + seconds
    while True:
        pump()
        left = end - now()
        if left <= 0:
            return
        step = min(left, SLICE)
        due = _next_due()
        if due is not None:
            step = max(0.0, min(step, due - now()))
        host.sleep(max(step, 0.0) * 1000.0)


def wait_until(condition, timeout=None) -> bool:
    """Wait for condition() to be true (looking after the board). False if timeout seconds pass first."""
    end = None if timeout is None else now() + float(timeout)
    while True:
        pump()
        if condition():
            return True
        if end is not None and now() >= end:
            return False
        step = SLICE if end is None else min(SLICE, max(0.0, end - now()))
        due = _next_due()
        if due is not None:
            step = max(0.0, min(step, due - now()))
        host.sleep(step * 1000.0)


def pause() -> None:
    """signal.pause(): wait for events for ever (until Stop)."""
    while True:
        pump()
        host.sleep(SLICE * 1000.0)


# ---------------------------------------------------------------- telling the page what the pins are doing

def _bcm(pin):
    return pin


def snapshot():
    """(devices, pins): what the board draws, in the same shape the PiPath app uses."""
    devs, pins = [], {}
    for d in devices:
        if d.closed:
            continue
        info = d._board_info()
        if info is None:
            continue
        kind, dpins, values = info
        devs.append({"kind": kind, "pins": dpins})
        pins.update({str(p): v for p, v in values.items()})
    return devs, pins


def report(force: bool = False) -> None:
    global _last_devs, _last_pins
    devs, pins = snapshot()
    if force or devs != _last_devs:
        host.emit(json.dumps({"t": "devices", "devices": devs}))
        _last_devs = devs
    if force or pins != _last_pins:
        host.emit(json.dumps({"t": "pins", "pins": pins}))
        _last_pins = pins


def close_all() -> None:
    """The program ended: every part lets go of its pin (lights go off, like real hardware)."""
    for d in list(devices):
        try:
            d.close()
        except Exception:
            pass
    report(force=True)
