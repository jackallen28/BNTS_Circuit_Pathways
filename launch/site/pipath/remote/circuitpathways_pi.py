#!/usr/bin/env python3
"""Circuit Pathways Pi Link: lets a student's browser control this Raspberry Pi's GPIO pins.

Run it on the Pi:

    python3 circuitpathways_pi.py --key CPK1-K7M2QX9P-AB12CD34EF
    python3 circuitpathways_pi.py --config /etc/circuitpathways-pi.conf

It connects OUT to the Circuit Pathways website (so it works on school WiFi that stops
devices talking to each other) using this Pi's own key. It shows the Pi's ID (such as
K7M2-QX9P). The student types the ID into the PiPath page. The browser then switches pins
on and off, reads buttons and sensors, and fades LEDs with PWM.

Each Pi has its own key, kept in a config file (the installer makes it). To start this at
boot, run the installer for this Pi once instead of running this file by hand.

It does two things, and nothing else:
  * switches pins 2 to 27 on and off for the Pi Link page (no shell commands, no files);
  * runs the student's own Python program when the PiPath page's "Run on my Pi" is chosen:
    one program at a time, as an unprivileged user, with time, memory and file limits, in a
    temporary folder that is deleted afterwards. A teacher can switch this off with RUN=no in
    the config file (or --no-run).
If the connection drops, every output is switched off and the program is stopped.
Standard library only, plus gpiozero (already on Raspberry Pi OS).
"""
from __future__ import annotations

import argparse
import base64
import codecs
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

VERSION = "0.2.0"
DEFAULT_SERVER = os.environ.get("CIRCUITPATHWAYS_URL", "https://circuit-pathways.onrender.com")
KEY_RE = re.compile(r"^CPK1-([0-9A-Z]{8})-([0-9A-Z]{10})$")

MIN_PIN, MAX_PIN = 2, 27
FAILSAFE_SECONDS = 10      # no connection for this long: every output goes off
POLL_HZ = 20               # how often inputs are read
HEARTBEAT_SECONDS = 2      # state is re-sent this often even if nothing changed
MAX_COMMANDS_PER_SECOND = 200

MODES = ("out", "in", "in_up", "in_down", "pwm")

# Running a student's program
RUN_MAX_SECONDS = 600      # a program is stopped after this long
RUN_IDLE_SECONDS = 25      # ...or when the page it belongs to stops answering for this long
RUN_OUTPUT_LIMIT = 200_000  # characters a program may print before it is stopped
OUT_CHUNK = 2000           # characters per message to the page
MAX_CODE = 40 << 10
MAX_FILES = 8
MAX_FILES_B64 = 40 << 10
RETURN_NAMES = 30          # file names reported back when a program ends (for the lesson checks)
RETURN_TEXT_EACH = 4096
RETURN_TEXT_TOTAL = 8192
LIMITS = {"RLIMIT_CPU": 600, "RLIMIT_AS": 2 << 30, "RLIMIT_FSIZE": 10 << 20, "RLIMIT_NOFILE": 128, "RLIMIT_NPROC": 64, "RLIMIT_CORE": 0}
PROGRAM_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}\.py$")
FILE_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}$")
CAMERA_NAME = re.compile(r"^[a-z ]{0,30}$")
# PiPath's helper modules, fetched from the website itself (never from anywhere else)
SUPPORT = {"pipath_camera": "/pipath/py/pipath_camera.py", "pipath_computer": "/pipath/py/pipath_computer.py"}


class BadCommand(Exception):
    """A command that isn't allowed, with a message a student can read."""


# ---------------------------------------------------------------- the pins

class MockGpio:
    """Pretend pins, for trying the app on a computer that isn't a Pi."""

    name = "mock"

    def __init__(self):
        self.pins: dict[int, dict] = {}
        self.inputs: dict[int, int] = {}  # what the pretend wires are feeding each input

    def set_mode(self, pin, mode):
        self.pins[pin] = {"mode": mode, "value": 0, "duty": 0.0}

    def write(self, pin, value):
        self.pins[pin]["value"] = value

    def pwm(self, pin, duty, freq):
        self.pins[pin].update(duty=duty, value=1 if duty > 0 else 0)

    def read(self, pin):
        p = self.pins[pin]
        if p["mode"] in ("in", "in_up", "in_down"):
            return self.inputs.get(pin, 1 if p["mode"] == "in_up" else 0)
        return p["value"]

    def release(self, pin):
        self.pins.pop(pin, None)

    def close(self):
        self.pins.clear()

    def model(self):
        return "Pretend Pi (no real pins)"


class GpioZero:
    """The real pins, through gpiozero."""

    name = "gpiozero"

    def __init__(self):
        import gpiozero  # noqa: F401  (raises ImportError on a computer without it)
        self.g = gpiozero
        self.devices: dict[int, object] = {}
        self.modes: dict[int, str] = {}

    def set_mode(self, pin, mode):
        self.release(pin)
        g = self.g
        if mode == "out":
            dev = g.DigitalOutputDevice(pin, initial_value=False)
        elif mode == "pwm":
            dev = g.PWMOutputDevice(pin, initial_value=0, frequency=100)
        elif mode == "in":
            dev = g.DigitalInputDevice(pin, pull_up=None, active_state=True)
        else:
            dev = g.DigitalInputDevice(pin, pull_up=(mode == "in_up"))
        self.devices[pin], self.modes[pin] = dev, mode

    def write(self, pin, value):
        self.devices[pin].value = value

    def pwm(self, pin, duty, freq):
        dev = self.devices[pin]
        if freq:
            dev.frequency = freq
        dev.value = duty

    def read(self, pin):
        dev = self.devices[pin]
        if self.modes[pin] == "pwm":
            return 1 if dev.value > 0 else 0
        if self.modes[pin] == "out":
            return int(dev.value)
        return int(dev.pin.state)  # the real level on the wire, whichever way it is pulled

    def release(self, pin):
        dev = self.devices.pop(pin, None)
        self.modes.pop(pin, None)
        if dev is not None:
            dev.close()

    def close(self):
        for pin in list(self.devices):
            self.release(pin)

    def model(self):
        try:
            return open("/proc/device-tree/model", errors="ignore").read().strip("\x00\n ")
        except OSError:
            return "Raspberry Pi"


# ---------------------------------------------------------------- what the page may ask for

class Bridge:
    """Checks each command, does it, and reports the pins."""

    def __init__(self, gpio, clock=time.monotonic):
        self.gpio = gpio
        self.clock = clock
        self.pins: dict[int, dict] = {}      # pin -> {"mode", "duty"}
        self.lock = threading.RLock()
        self._recent: list[float] = []
        self.program_running = False         # while a program runs it owns the pins

    # -- commands ------------------------------------------------------
    @staticmethod
    def _pin(cmd) -> int:
        pin = cmd.get("pin")
        if not isinstance(pin, int) or isinstance(pin, bool) or not MIN_PIN <= pin <= MAX_PIN:
            raise BadCommand(f"GPIO {pin} isn't a pin you can use (2 to 27).")
        return pin

    def _rate_limit(self):
        now = self.clock()
        self._recent = [t for t in self._recent if now - t < 1.0]
        if len(self._recent) >= MAX_COMMANDS_PER_SECOND:
            raise BadCommand("Too many commands at once. Slow down a little.")
        self._recent.append(now)

    def handle(self, cmd):
        """Does one command. Returns an event for the browser (or None). Raises BadCommand."""
        if not isinstance(cmd, dict):
            raise BadCommand("That isn't a command.")
        op = cmd.get("op")
        with self.lock:
            self._rate_limit()
            if op == "ping":
                return {"type": "pong", "data": {"id": cmd.get("id", 0), "t": time.time()}}
            if op == "read":
                return self.state_event()
            if op == "all_off":
                self.all_off()
                return self.state_event()
            pin = self._pin(cmd)
            if self.program_running:
                raise BadCommand("A program is running on this Pi, so it has the pins. Stop it to use the pin buttons.")
            if op == "release":
                self.gpio.release(pin)
                self.pins.pop(pin, None)
            elif op == "mode":
                mode = cmd.get("mode")
                if mode not in MODES:
                    raise BadCommand("That isn't a pin mode.")
                self.gpio.set_mode(pin, mode)
                self.pins[pin] = {"mode": mode, "duty": 0.0}
            elif op == "write":
                value = cmd.get("value")
                if value not in (0, 1) or isinstance(value, bool):
                    raise BadCommand("A pin can be 0 or 1.")
                if self.pins.get(pin, {}).get("mode") != "out":
                    raise BadCommand(f"GPIO {pin} isn't an output yet. Set it to Output first.")
                self.gpio.write(pin, value)
            elif op == "pwm":
                duty, freq = cmd.get("duty", 0), cmd.get("freq", 0) or 0
                if not isinstance(duty, (int, float)) or not 0 <= duty <= 1 or not isinstance(freq, int) or not 0 <= freq <= 10000:
                    raise BadCommand("PWM needs a brightness from 0 to 1.")
                if self.pins.get(pin, {}).get("mode") != "pwm":
                    raise BadCommand(f"GPIO {pin} isn't set to PWM yet.")
                self.gpio.pwm(pin, float(duty), freq)
                self.pins[pin]["duty"] = float(duty)
            else:
                raise BadCommand("That isn't something the Pi can do.")
            return self.state_event()

    def all_off(self):
        with self.lock:
            for pin, p in list(self.pins.items()):
                if p["mode"] == "out":
                    self.gpio.write(pin, 0)
                elif p["mode"] == "pwm":
                    self.gpio.pwm(pin, 0.0, 0)
                    p["duty"] = 0.0

    def hand_over_pins(self):
        """A program is about to run: let go of every pin so it can have them."""
        with self.lock:
            for pin in list(self.pins):
                self.gpio.release(pin)
            self.pins.clear()
            self.program_running = True

    def take_back_pins(self):
        with self.lock:
            self.program_running = False

    def shutdown(self):
        with self.lock:
            self.all_off()
            self.gpio.close()
            self.pins.clear()

    # -- what the browser sees ------------------------------------------
    def snapshot(self) -> dict:
        with self.lock:
            return {str(pin): {"mode": p["mode"], "value": self.gpio.read(pin), "duty": p["duty"]}
                    for pin, p in sorted(self.pins.items())}

    def state_event(self) -> dict:
        return {"type": "state", "data": {"pins": self.snapshot()}}

    def hello_event(self, name="Raspberry Pi", can_run=False) -> dict:
        return {"type": "hello", "data": {
            "model": self.gpio.model(), "backend": self.gpio.name, "version": VERSION,
            "pins": [MIN_PIN, MAX_PIN], "name": name, "can_run": bool(can_run),
            "python": "%d.%d" % sys.version_info[:2],
        }}


# ---------------------------------------------------------------- running a student's program

# Starts the program inside tighter limits (time, memory, file size, processes). The program
# replaces this little launcher, so it is the only thing left running.
_LAUNCH = """import os, sys, resource
for _n, _v in %r:
    try:
        resource.setrlimit(getattr(resource, _n), (_v, _v))
    except (ValueError, OSError, AttributeError):
        pass
os.execv(sys.executable, [sys.executable, "-u", "-s", "-B", sys.argv[1]])
""" % (sorted(LIMITS.items()),)

STOP_MESSAGES = {
    "timeout": "[The Pi stopped your program: it had been running for %d minutes]" % (RUN_MAX_SECONDS // 60),
    "idle": "[The Pi stopped your program: the PiPath page stopped answering]",
    "offline": "[The Pi stopped your program: it lost its connection]",
}


class Runner:
    """Runs one student program at a time on this Pi, and streams what it prints to the page.

    The program is a plain Python file in its own temporary folder. If this app runs as root it
    switches to `run_user` first; it never runs a student's program as root.
    """

    def __init__(self, bridge, emit, fetch=None, base_dir=None, run_user=None, enabled=True,
                 python=None, clock=time.monotonic, max_seconds=RUN_MAX_SECONDS, idle_seconds=RUN_IDLE_SECONDS):
        self.bridge, self.emit, self.fetch = bridge, emit, fetch
        self.enabled = enabled
        self.python = python or sys.executable
        self.base_dir = base_dir or os.path.join(tempfile.gettempdir(), "circuitpathways-pi-run")
        self.run_user = run_user
        self.clock, self.max_seconds, self.idle_seconds = clock, max_seconds, idle_seconds
        self.lock = threading.RLock()
        self.active = False
        self.rid = 0
        self.proc = None
        self.reason = None
        self.last_touch = clock()
        self._killing = False
        self._support: dict[str, bytes] = {}
        self._pending: list[tuple[str, str]] = []
        self._pending_lock = threading.Lock()
        self._printed = 0

    # -- what the page asks -------------------------------------------
    def touch(self):
        """The page is still there (any command from it counts)."""
        self.last_touch = self.clock()

    def start(self, cmd):
        if not self.enabled:
            raise BadCommand("This Pi isn't set to run programs from the website. Ask your teacher to switch it on.")
        rid, name, code = cmd.get("rid"), cmd.get("name"), cmd.get("code")
        if not isinstance(rid, int) or isinstance(rid, bool) or rid <= 0:
            raise BadCommand("That program has no number.")
        if not isinstance(name, str) or not PROGRAM_NAME.match(name):
            raise BadCommand("That isn't a Python file name.")
        if not isinstance(code, str) or not code or len(code.encode("utf-8")) > MAX_CODE or "\x00" in code:
            raise BadCommand("That program is empty or too big.")
        files = cmd.get("files") or {}
        if not isinstance(files, dict) or len(files) > MAX_FILES or sum(len(v) for v in files.values() if isinstance(v, str)) > MAX_FILES_B64:
            raise BadCommand("Too many data files.")
        for fname, data in files.items():
            segs = fname.split("/") if isinstance(fname, str) else []
            if not segs or len(segs) > 3 or not all(FILE_SEGMENT.match(x) for x in segs) or not isinstance(data, str):
                raise BadCommand("That isn't a file name the Pi can use.")
        support = cmd.get("support") or []
        if not isinstance(support, list) or any(m not in SUPPORT for m in support):
            raise BadCommand("That helper isn't one the Pi knows.")
        cam = cmd.get("camera_object") or ""
        if not isinstance(cam, str) or not CAMERA_NAME.match(cam):
            raise BadCommand("That isn't a camera object.")
        with self.lock:
            if self.active:
                raise BadCommand("A program is already running on this Pi. Press Stop first.")
            self.active, self.rid, self.reason, self._killing = True, rid, None, False
        self.touch()
        threading.Thread(target=self._go, args=(rid, name, code, files, support, cam), daemon=True).start()
        return {"type": "run", "data": {"rid": rid, "state": "starting"}}

    def stdin(self, cmd):
        text = cmd.get("text")
        if not isinstance(text, str) or len(text) > 1000 or "\x00" in text:
            raise BadCommand("That line is too long.")
        with self.lock:
            proc = self.proc
            if proc is None or cmd.get("rid") != self.rid or proc.stdin is None:
                return None
            try:
                proc.stdin.write((text + "\n").encode("utf-8"))
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
        return None

    def stop(self, cmd=None, reason="stop"):
        with self.lock:
            if not self.active or (cmd and cmd.get("rid") not in (0, None, self.rid)):
                return None
            self._terminate(reason)
        return None

    def stop_all(self, reason="offline"):
        return self.stop(None, reason)

    def shutdown(self):
        self.stop(None, "stop")
        for _ in range(60):
            if not self.active:
                break
            time.sleep(0.1)

    # -- one run ---------------------------------------------------------
    def _terminate(self, reason):
        """Asks the program to end: Ctrl+C first, then a firmer word, then no choice."""
        if self.reason is None:
            self.reason = reason
        if self._killing:
            return
        self._killing = True
        proc = self.proc
        if proc is None:
            return  # still setting up: _go notices self.reason

        def sequence():
            for sig, wait in ((signal.SIGINT, 1.5), (signal.SIGTERM, 1.5), (signal.SIGKILL, 0)):
                try:
                    os.killpg(proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    return
                if wait:
                    try:
                        proc.wait(timeout=wait)
                        return
                    except subprocess.TimeoutExpired:
                        continue
        threading.Thread(target=sequence, daemon=True).start()

    def _ids(self):
        if not self.run_user:
            return None
        import pwd
        u = pwd.getpwnam(self.run_user)
        return u.pw_uid, u.pw_gid

    def _make_dir(self, rid):
        os.makedirs(self.base_dir, mode=0o755, exist_ok=True)
        if self.run_user:
            os.chmod(self.base_dir, 0o711)  # the program's user can walk in to its own folder, but not look around
        d = tempfile.mkdtemp(prefix="run%d-" % rid, dir=self.base_dir)
        os.chmod(d, 0o700)
        return d

    def _support_source(self, mod):
        if mod not in self._support:
            if self.fetch is None:
                raise BadCommand("This Pi can't get PiPath's helper files.")
            try:
                self._support[mod] = self.fetch(SUPPORT[mod])
            except Exception as e:
                raise BadCommand("Couldn't get %s from the website (%s)." % (mod, e))
        return self._support[mod]

    def _prepare(self, d, name, code, files, support):
        written = {name}
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(code)
        for fname, b64 in files.items():
            try:
                data = base64.b64decode(b64, validate=True)
            except ValueError:
                raise BadCommand("A data file wasn't readable.")
            dest = os.path.join(d, *fname.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            written.add(fname)
        for mod in support:
            with open(os.path.join(d, mod + ".py"), "wb") as f:
                f.write(self._support_source(mod))
            written.add(mod + ".py")
        ids = self._ids()
        if ids:
            for root, dirs, fnames in os.walk(d):
                for n in dirs + fnames:
                    os.chown(os.path.join(root, n), *ids)
            os.chown(d, *ids)
        return written

    def _say(self, rid, stream, text):
        with self._pending_lock:
            self._pending.append((stream, text))

    def _flush(self, rid):
        with self._pending_lock:
            items, self._pending = self._pending, []
        merged: list[list] = []
        for stream, text in items:
            if self.reason == "stop" and stream == "err":
                continue  # Ctrl+C's traceback isn't wanted when the student pressed Stop
            if merged and merged[-1][0] == stream:
                merged[-1][1] += text
            else:
                merged.append([stream, text])
        for stream, text in merged:
            for i in range(0, len(text), OUT_CHUNK):
                self.emit({"type": "out", "data": {"rid": rid, "stream": stream, "text": text[i:i + OUT_CHUNK]}}, reliable=True)

    def _read(self, fd, stream, rid, folder):
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            text = dec.decode(chunk)
            if stream == "err":
                text = text.replace(folder + "/", "")
            self._printed += len(text)
            if self._printed > RUN_OUTPUT_LIMIT:
                with self.lock:
                    self._terminate("output")
                break
            self._say(rid, stream, text)
        tail = dec.decode(b"", final=True)
        if tail:
            self._say(rid, stream, tail)

    def _collect(self, d, written, since):
        """The files the program made, for the lesson checks: every name, and the words in the small ones."""
        found, budget = {}, RETURN_TEXT_TOTAL
        for root, dirs, fnames in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith((".", "__"))]
            if os.path.relpath(root, d).count(os.sep) >= 2:
                dirs[:] = []
            for n in sorted(fnames):
                full = os.path.join(root, n)
                rel = os.path.relpath(full, d).replace(os.sep, "/")
                if n.startswith(".") or os.path.islink(full) or not os.path.isfile(full):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if rel in written and st.st_mtime < since:
                    continue
                text = None
                if st.st_size <= min(RETURN_TEXT_EACH, budget):
                    try:
                        with open(full, "rb") as f:
                            text = f.read().decode("utf-8")
                        budget -= len(text.encode("utf-8"))
                    except (OSError, UnicodeDecodeError):
                        text = None
                found[rel] = {"size": st.st_size, "text": text}
                if len(found) >= RETURN_NAMES:
                    return found
        return found

    def _go(self, rid, name, code, files, support, cam):
        d, rc, files_out, since = None, 1, {}, time.time() - 1
        self._printed = 0
        self._pending = []
        try:
            try:
                d = self._make_dir(rid)
                written = self._prepare(d, name, code, files, support)
                since = time.time()
                if self.reason:
                    raise BadCommand("Stopped before it began.")
                self.bridge.hand_over_pins()
                env = {"PATH": "/usr/bin:/bin", "HOME": d, "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
                       "PYTHONDONTWRITEBYTECODE": "1", "PIPATH_CAMERA_OBJECT": cam}
                if os.environ.get("GPIOZERO_PIN_FACTORY"):
                    env["GPIOZERO_PIN_FACTORY"] = os.environ["GPIOZERO_PIN_FACTORY"]
                kw = {}
                ids = self._ids()
                if ids:
                    kw.update(user=ids[0], group=ids[1], extra_groups=os.getgrouplist(self.run_user, ids[1]))
                since = time.time()  # files made after this are the program's own
                proc = subprocess.Popen([self.python, "-c", _LAUNCH, name], cwd=d, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                        umask=0o077, close_fds=True, **kw)
            except (BadCommand, OSError, ValueError, KeyError) as e:
                self._say(rid, "err", "Couldn't start your program: %s\n" % e)
                self._flush(rid)
                return
            started = self.clock()
            with self.lock:
                self.proc = proc
                if self.reason:
                    self._killing = False
                    self._terminate(self.reason)
            self.emit({"type": "run", "data": {"rid": rid, "state": "started"}}, reliable=True)
            readers = [threading.Thread(target=self._read, args=(proc.stdout.fileno(), "out", rid, d), daemon=True),
                       threading.Thread(target=self._read, args=(proc.stderr.fileno(), "err", rid, d), daemon=True)]
            for t in readers:
                t.start()
            last_flush = 0.0
            while proc.poll() is None:
                time.sleep(0.05)
                now = self.clock()
                if now - started > self.max_seconds:
                    with self.lock:
                        self._terminate("timeout")
                elif now - self.last_touch > self.idle_seconds:
                    with self.lock:
                        self._terminate("idle")
                if now - last_flush >= 0.1:
                    self._flush(rid)
                    last_flush = now
            for t in readers:
                t.join(2)
            rc = proc.returncode
            if self.reason in STOP_MESSAGES:
                self._say(rid, "out", "\n" + STOP_MESSAGES[self.reason] + "\n")
            self._flush(rid)
            try:
                files_out = self._collect(d, written, since)
            except OSError:
                files_out = {}
        finally:
            with self.lock:
                reason, proc = self.reason, self.proc
                self.proc = None
            if proc is not None:
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    try:
                        pipe.close()
                    except Exception:
                        pass
            if d:
                shutil.rmtree(d, ignore_errors=True)
            self.bridge.take_back_pins()
            if reason == "stop":
                rc = 130
            self.emit({"type": "exit", "data": {"rid": rid, "rc": rc if rc is not None and rc >= 0 else 128 - rc,
                                                  "stopped": reason is not None, "reason": reason, "files": files_out}}, reliable=True)
            with self.lock:
                self.active = False


# ---------------------------------------------------------------- talking to the website

def pi_id(key: str) -> str:
    """The ID on this Pi's label (K7M2-QX9P), from its key. Raises ValueError if the key is badly typed."""
    m = KEY_RE.match(key.strip().upper())
    if not m:
        raise ValueError("That isn't a Pi key. It looks like CPK1-K7M2QX9P-AB12CD34EF.")
    return m.group(1)[:4] + "-" + m.group(1)[4:]


class Server:
    """The Circuit Pathways website, as this Pi sees it. The Pi proves who it is with its own key."""

    def __init__(self, base: str, key: str, name: str = "Raspberry Pi", opener=urllib.request.urlopen):
        self.base = base.rstrip("/")
        self.key = key.strip().upper()
        self.id = pi_id(self.key)
        self.name = name
        self.open = opener

    def _request(self, path, body=None, timeout=20):
        h = {"X-Circuit-Pathways": "1", "X-Pi-Key": self.key, "User-Agent": f"circuitpathways-pi/{VERSION}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        return self.open(urllib.request.Request(self.base + path, data=data, headers=h), timeout=timeout)

    def send(self, event):
        with self._request("/api/pi/pi/send", {"event": event}) as r:
            r.read()

    def fetch(self, path):
        """A file from this website (PiPath's helper modules). Nothing from anywhere else."""
        if not path.startswith("/pipath/py/"):
            raise ValueError("not a helper file")
        with self._request(path, timeout=20) as r:
            return r.read(300_000)

    def commands(self):
        """Yields each command from the website, until the connection ends."""
        resp = self._request("/api/pi/pi/events", timeout=45)
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:])
                    except ValueError:
                        continue


def show_id(pid, server):
    bar = "=" * 46
    print(f"\n{bar}\n  Circuit Pathways Pi Link\n\n  This Pi's ID (type it on the PiPath page):\n\n        {pid}\n\n  ({server})\n{bar}\n", flush=True)


class Link:
    """Keeps the Pi connected: registers, listens, reports, and switches outputs off if it loses the website."""

    def __init__(self, bridge: Bridge, server: Server, log=print, sleep=time.sleep, clock=time.monotonic, runner=None):
        self.bridge, self.server, self.log, self.sleep, self.clock = bridge, server, log, sleep, clock
        self.runner = runner or Runner(bridge, self.emit, enabled=False)
        self.out: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
        self.stop = threading.Event()
        self.connected = False
        self.lost_at: float | None = None

    # events to the browser: pin states are replaced, never queued up. A program's output is
    # never dropped (reliable): it waits a moment for room instead.
    def emit(self, event, reliable=False):
        if reliable:
            try:
                self.out.put(event, timeout=5)
                return
            except queue.Full:
                pass
        try:
            self.out.put_nowait(event)
        except queue.Full:
            try:
                self.out.get_nowait()
            except queue.Empty:
                pass

    def dispatch(self, cmd):
        """Does one command from the page: a pin, or a program. Returns an event for the page (or None)."""
        op = cmd.get("op") if isinstance(cmd, dict) else None
        self.runner.touch()
        if op == "run":
            return self.runner.start(cmd)
        if op == "stdin":
            return self.runner.stdin(cmd)
        if op == "stop":
            return self.runner.stop(cmd)
        return self.bridge.handle(cmd)

    @staticmethod
    def _batch(first, more):
        """Output waiting in the queue goes out in one message, so a chatty program can't fall behind."""
        batch = [first]
        for nxt in more:
            last = batch[-1]
            if (nxt["type"] == "out" and last["type"] == "out" and nxt["data"]["rid"] == last["data"]["rid"]
                    and nxt["data"]["stream"] == last["data"]["stream"]
                    and len(last["data"]["text"]) + len(nxt["data"]["text"]) <= OUT_CHUNK):
                batch[-1] = {"type": "out", "data": {**last["data"], "text": last["data"]["text"] + nxt["data"]["text"]}}
            else:
                batch.append(nxt)
        return batch

    def _sender(self):
        while not self.stop.is_set():
            try:
                ev = self.out.get(timeout=0.5)
            except queue.Empty:
                continue
            more = []
            while len(more) < 100:
                try:
                    more.append(self.out.get_nowait())
                except queue.Empty:
                    break
            for ev in self._batch(ev, more):
                try:
                    self.server.send(ev)
                except Exception as e:  # the listener will notice a dead connection
                    self.log(f"(couldn't send to the website: {e})")

    def _poller(self):
        last, last_sent = None, 0.0
        while not self.stop.is_set():
            self.sleep(1.0 / POLL_HZ)
            now = self.clock()
            if self.connected:
                snap = self.bridge.snapshot()
                if snap != last or now - last_sent >= HEARTBEAT_SECONDS:
                    self.emit({"type": "state", "data": {"pins": snap}})
                    last, last_sent = snap, now
            elif self.lost_at is not None and now - self.lost_at >= FAILSAFE_SECONDS:
                self.runner.stop_all("offline")  # the website is gone: no program keeps running
                self.bridge.all_off()  # ...and nothing stays on
                self.lost_at = None
                self.log("Lost the connection: every output is switched off.")

    def run(self):
        threading.Thread(target=self._sender, daemon=True).start()
        threading.Thread(target=self._poller, daemon=True).start()
        delay = 1.0
        show_id(self.server.id, self.server.base)
        while not self.stop.is_set():
            try:
                self.emit(self.bridge.hello_event(self.server.name, self.runner.enabled))
                self.connected, self.lost_at = True, None
                got_any = False
                for cmd in self.server.commands():
                    if not got_any:
                        got_any, delay = True, 1.0
                    try:
                        reply = self.dispatch(cmd)
                    except BadCommand as e:
                        reply = {"type": "error", "data": {"message": str(e), "id": cmd.get("id", 0) if isinstance(cmd, dict) else 0,
                                                           "rid": cmd.get("rid", 0) if isinstance(cmd, dict) else 0}}
                    if reply:
                        self.emit(reply)
                self.log("The website closed the connection. Reconnecting...")
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    self.log("The website says this Pi's key isn't valid. Ask your teacher for this Pi's key. Trying again in a minute...")
                    delay = 60.0
                else:
                    self.log(f"The website said {e.code}. Trying again...")
            except Exception as e:
                self.log(f"Can't reach the website ({e}). Trying again...")
            finally:
                self.connected = False
                if self.lost_at is None:
                    self.lost_at = self.clock()
            self.sleep(delay)
            delay = min(delay * 2, 15.0) if delay < 60 else 60.0


# ---------------------------------------------------------------- start up

def decide_run(enabled, run_user, euid=None, user_exists=None):
    """Whether students' programs may run. As root there must be an unprivileged user to run them as.
    Returns (enabled, a message to print or "")."""
    if not enabled:
        return False, ""
    euid = os.geteuid() if euid is None and hasattr(os, "geteuid") else euid
    if euid == 0:
        if user_exists is None:
            def user_exists(name):
                try:
                    import pwd
                    pwd.getpwnam(name)
                    return True
                except (KeyError, ImportError):
                    return False
        if not run_user or not user_exists(run_user):
            return False, "Not running students' programs: this app is running as root and has no RUN_USER to run them as."
    return True, ""


def read_config(path):
    """KEY=..., SERVER=... and NAME=... lines, as the installer writes them."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip().upper()] = v.strip().strip('"').strip("'")
    except OSError as e:
        raise SystemExit(f"Can't read {path}: {e}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Control this Raspberry Pi's pins from the Circuit Pathways website.")
    ap.add_argument("--key", default=os.environ.get("CIRCUITPATHWAYS_KEY", ""), help="this Pi's key (CPK1-...)")
    ap.add_argument("--config", help="a file with KEY=, SERVER= and NAME= lines (the installer makes /etc/circuitpathways-pi.conf)")
    ap.add_argument("--server", default=None, help="the Circuit Pathways website (default: %s)" % DEFAULT_SERVER)
    ap.add_argument("--name", default=None, help="a label shown on the website: no names, please")
    ap.add_argument("--mock", action="store_true", help="pretend pins, to try this on a computer that isn't a Pi")
    ap.add_argument("--no-run", action="store_true", help="don't run students' programs (pins only). Same as RUN=no in the config file")
    ap.add_argument("--run-user", default=None, help="the unprivileged user that students' programs run as (needed when this app runs as root)")
    ap.add_argument("--run-dir", default=None, help="where programs get their temporary folders")
    args = ap.parse_args(argv)
    cfg = read_config(args.config) if args.config else {}
    key = args.key or cfg.get("KEY", "")
    server = args.server or cfg.get("SERVER") or DEFAULT_SERVER
    name = args.name or cfg.get("NAME") or "Raspberry Pi"
    if not re.match(r"^https?://", server):
        ap.error("--server must start with http:// or https://")
    if not key:
        ap.error("this Pi needs its key: --key CPK1-... (your teacher has it), or run this Pi's installer")
    try:
        pi_id(key)
    except ValueError as e:
        ap.error(str(e))

    if args.mock:
        gpio = MockGpio()
    else:
        try:
            gpio = GpioZero()
        except ImportError:
            sys.exit("gpiozero isn't installed. On Raspberry Pi OS it is already there (sudo apt install python3-gpiozero).\n"
                     "To try this on another computer, add --mock.")
    bridge = Bridge(gpio)
    srv = Server(server, key, name)
    run_user = args.run_user or cfg.get("RUN_USER") or None
    enabled = not args.no_run and cfg.get("RUN", "yes").lower() not in ("no", "false", "0", "off")
    enabled, why = decide_run(enabled, run_user)
    if why:
        print(why, flush=True)
    link = Link(bridge, srv)
    link.runner = Runner(bridge, link.emit, fetch=srv.fetch, base_dir=args.run_dir or cfg.get("RUN_DIR") or None,
                         run_user=run_user, enabled=enabled)
    if args.mock:  # type "set 4 1" to press a pretend button on pin 4
        def stdin_inputs():
            for line in sys.stdin:
                m = re.match(r"\s*set\s+(\d+)\s+([01])", line)
                if m:
                    gpio.inputs[int(m.group(1))] = int(m.group(2))
        threading.Thread(target=stdin_inputs, daemon=True).start()
    try:
        link.run()
    except KeyboardInterrupt:
        pass
    finally:
        link.stop.set()
        link.runner.shutdown()
        bridge.shutdown()
        print("\nBye! Every pin has been let go.")


if __name__ == "__main__":
    main()
