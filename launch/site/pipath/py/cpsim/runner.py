"""Runs one student program: the browser's version of PiPath's gpio_shim."""
from __future__ import annotations

import builtins
import json
import os
import sys
import time
import traceback
import types
from pathlib import Path

import _cp_host as host

from . import core, gpiozero_sim

_real_time = time.time  # kept so file checks can compare with the real clock


def _install_modules(allow_camera: bool = True) -> None:
    gpiozero_sim.install()
    if "fcntl" not in sys.modules:                      # the camera helper imports it; the Simulator camera never uses it
        sys.modules["fcntl"] = types.ModuleType("fcntl")
    shim = types.ModuleType("pipath_shim")                # the camera helper tells PiPath about photos through this
    shim.send = lambda msg: host.emit(json.dumps(msg))
    shim.camera_view = {"object": os.environ.get("PIPATH_CAMERA_OBJECT", "face")}
    sys.modules["pipath_shim"] = shim
    turtle = types.ModuleType("turtle")

    def _no_turtle(*a, **k):
        raise ModuleNotFoundError("Turtle graphics isn't in the browser version of PiPath yet. Use PiPath on a Raspberry Pi for this one.")

    turtle.__getattr__ = lambda name: _no_turtle()
    sys.modules["turtle"] = turtle


def _input(prompt=""):
    """input(): the page puts the cursor in the answer box; the program carries on looking after the board while it waits."""
    sys.stdout.write(str(prompt))
    sys.stdout.flush()
    host.emit(json.dumps({"t": "input"}))
    while True:
        core.pump()
        state = host.input_state()
        if state == 1:
            return host.read_line()
        if state == 2:
            raise EOFError("EOF when reading a line")
        host.sleep(core.SLICE * 1000.0)


def _print_student_traceback(exc: BaseException, student: str) -> None:
    """Print the traceback starting at the student's file, without the runner's frames."""
    tb = exc.__traceback__
    while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) != student:
        tb = tb.tb_next
    te = traceback.TracebackException(type(exc), exc, tb)
    sys.stderr.write("".join(te.format()))
    sys.stderr.flush()


started_real = 0.0  # time.time() (real) when the last program started


def run_student(code: str, filename: str, cwd: str, env: dict | None = None, seed: int | None = None) -> int:
    """Run code as <cwd>/<filename>. Returns the exit code (0 fine, 1 crashed, 130 Stop)."""
    global started_real
    cwd_path = Path(cwd)
    cwd_path.mkdir(parents=True, exist_ok=True)
    path = str((cwd_path / filename).resolve())
    Path(path).write_text(code, encoding="utf-8")

    saved = {"sleep": time.sleep, "monotonic": time.monotonic, "perf_counter": time.perf_counter, "time": time.time,
             "input": builtins.input, "cwd": os.getcwd(), "argv": sys.argv, "path0": list(sys.path), "env": dict(os.environ)}
    import signal
    saved["pause"] = getattr(signal, "pause", None)
    for name in [m for m in list(sys.modules) if m in ("gpiozero", "gpiozero.exc", "gpiozero.tones", "turtle") or m.startswith("student_")]:
        del sys.modules[name]
    core.reset()
    _install_modules()
    started_real = _real_time()
    os.environ.update({"PIPATH_CAMERA": "sim", "PIPATH_DEMO": "1"})
    os.environ.update({k: str(v) for k, v in (env or {}).items()})
    time.sleep = core.sleep
    time.monotonic = lambda: 1000.0 + core.now()
    time.perf_counter = lambda: 1000.0 + core.now()
    time.time = lambda: core._epoch + core.now()
    builtins.input = _input
    signal.pause = core.pause
    if seed is not None:
        import random
        random.seed(seed)
    os.chdir(cwd)
    sys.argv = [path]
    sys.path.insert(0, str(cwd_path))
    host.emit(json.dumps({"t": "hello", "mode": "sim"}))
    rc = 0
    try:
        exec(compile(code, path, "exec"), {"__name__": "__main__", "__file__": path, "__builtins__": builtins})
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if isinstance(e.code, str):
            sys.stderr.write(e.code + "\n")
    except KeyboardInterrupt:
        rc = 130
    except BaseException as e:  # noqa: BLE001 - every crash is shown, then the Coach explains it
        _print_student_traceback(e, path)
        rc = 1
    finally:
        try:
            core.close_all()
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            time.sleep, time.monotonic, time.perf_counter, time.time = saved["sleep"], saved["monotonic"], saved["perf_counter"], saved["time"]
            builtins.input = saved["input"]
            if saved["pause"] is not None:
                signal.pause = saved["pause"]
            os.chdir(saved["cwd"])
            sys.argv = saved["argv"]
            sys.path[:] = saved["path0"]
            for k in [k for k in os.environ if k.startswith("PIPATH_") and k not in saved["env"]]:
                del os.environ[k]
    return rc
