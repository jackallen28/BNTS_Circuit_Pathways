#!/usr/bin/env python3
"""Circuit Pathways Pi Link: lets a student's browser control this Raspberry Pi's GPIO pins.

Run it on the Pi:

    python3 circuitpathways_pi.py

It connects OUT to the Circuit Pathways website (so it works on school WiFi that stops
devices talking to each other), prints a short pairing code, and waits. The student types
the code into the PiPath page. The browser then switches pins on and off, reads buttons
and sensors, and fades LEDs with PWM.

It only does what the page asks for with pins 2 to 27, and nothing else: no programs, no
shell commands, no files. If the connection drops, every output is switched off.
Standard library only, plus gpiozero (already on Raspberry Pi OS).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

VERSION = "0.1.0"
DEFAULT_SERVER = os.environ.get("CIRCUITPATHWAYS_URL", "https://circuit-pathways.onrender.com")

MIN_PIN, MAX_PIN = 2, 27
FAILSAFE_SECONDS = 10      # no connection for this long: every output goes off
POLL_HZ = 20               # how often inputs are read
HEARTBEAT_SECONDS = 2      # state is re-sent this often even if nothing changed
MAX_COMMANDS_PER_SECOND = 200

MODES = ("out", "in", "in_up", "in_down", "pwm")


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

    def hello_event(self) -> dict:
        return {"type": "hello", "data": {
            "model": self.gpio.model(), "backend": self.gpio.name, "version": VERSION,
            "pins": [MIN_PIN, MAX_PIN],
        }}


# ---------------------------------------------------------------- talking to the website

class Server:
    def __init__(self, base: str, name: str, opener=urllib.request.urlopen):
        self.base = base.rstrip("/")
        self.name = name
        self.open = opener
        self.code = ""
        self.secret = ""

    def _request(self, path, body=None, headers=None, timeout=20):
        h = {"X-Circuit-Pathways": "1", "User-Agent": f"circuitpathways-pi/{VERSION}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        return self.open(urllib.request.Request(self.base + path, data=data, headers=h), timeout=timeout)

    def register(self):
        with self._request("/api/pi/register", {"name": self.name, "version": VERSION}) as r:
            info = json.load(r)
        self.code, self.secret = info["code"], info["secret"]
        return self.code

    def send(self, event):
        with self._request("/api/pi/pi/send", {"code": self.code, "event": event},
                           {"X-Pi-Secret": self.secret}) as r:
            r.read()

    def commands(self):
        """Yields each command from the website, until the connection ends."""
        resp = self._request(f"/api/pi/pi/events?code={self.code}", headers={"X-Pi-Secret": self.secret}, timeout=45)
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:])
                    except ValueError:
                        continue


def show_code(code, server):
    bar = "=" * 46
    print(f"\n{bar}\n  Circuit Pathways Pi Link\n\n  Type this code on the PiPath page:\n\n        {code}\n\n  ({server})\n{bar}\n", flush=True)


class Link:
    """Keeps the Pi connected: registers, listens, reports, and switches outputs off if it loses the website."""

    def __init__(self, bridge: Bridge, server: Server, log=print, sleep=time.sleep, clock=time.monotonic):
        self.bridge, self.server, self.log, self.sleep, self.clock = bridge, server, log, sleep, clock
        self.out: "queue.Queue[dict]" = queue.Queue(maxsize=200)
        self.stop = threading.Event()
        self.connected = False
        self.lost_at: float | None = None

    # events to the browser: states are replaced, never queued up
    def emit(self, event):
        try:
            self.out.put_nowait(event)
        except queue.Full:
            try:
                self.out.get_nowait()
            except queue.Empty:
                pass

    def _sender(self):
        while not self.stop.is_set():
            try:
                ev = self.out.get(timeout=0.5)
            except queue.Empty:
                continue
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
                self.bridge.all_off()  # the website is gone: nothing stays on
                self.lost_at = None
                self.log("Lost the connection: every output is switched off.")

    def run(self):
        threading.Thread(target=self._sender, daemon=True).start()
        threading.Thread(target=self._poller, daemon=True).start()
        delay = 1.0
        while not self.stop.is_set():
            try:
                if not self.server.code:
                    show_code(self.server.register(), self.server.base)
                self.emit(self.bridge.hello_event())
                self.connected, self.lost_at, delay = True, None, 1.0
                for cmd in self.server.commands():
                    try:
                        reply = self.bridge.handle(cmd)
                    except BadCommand as e:
                        reply = {"type": "error", "data": {"message": str(e), "id": cmd.get("id", 0) if isinstance(cmd, dict) else 0}}
                    if reply:
                        self.emit(reply)
                self.log("The website closed the connection. Reconnecting...")
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):  # the website has forgotten this Pi: get a new code
                    self.log("The website forgot this Pi. Getting a new code...")
                    self.server.code = ""
                else:
                    self.log(f"The website said {e.code}. Trying again...")
            except Exception as e:
                self.log(f"Can't reach the website ({e}). Trying again...")
            finally:
                self.connected = False
                if self.lost_at is None:
                    self.lost_at = self.clock()
            self.sleep(delay)
            delay = min(delay * 2, 15.0)


# ---------------------------------------------------------------- start up

def main(argv=None):
    ap = argparse.ArgumentParser(description="Control this Raspberry Pi's pins from the Circuit Pathways website.")
    ap.add_argument("--server", default=DEFAULT_SERVER, help="the Circuit Pathways website (default: %(default)s)")
    ap.add_argument("--name", default="Raspberry Pi", help="a label shown on the website: no names, please")
    ap.add_argument("--mock", action="store_true", help="pretend pins, to try this on a computer that isn't a Pi")
    args = ap.parse_args(argv)
    if not re.match(r"^https?://", args.server):
        ap.error("--server must start with http:// or https://")

    if args.mock:
        gpio = MockGpio()
    else:
        try:
            gpio = GpioZero()
        except ImportError:
            sys.exit("gpiozero isn't installed. On Raspberry Pi OS it is already there (sudo apt install python3-gpiozero).\n"
                     "To try this on another computer, add --mock.")
    bridge = Bridge(gpio)
    link = Link(bridge, Server(args.server, args.name))
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
        bridge.shutdown()
        print("\nBye! Every pin has been let go.")


if __name__ == "__main__":
    main()
