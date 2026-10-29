"""Tests for the Pi Link. Run: python3 -m unittest discover pi-bridge   (no Pi needed)"""
import io
import json
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import os
import sys

sys.dont_write_bytecode = True  # never leave cache files inside the website folder
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "pipath", "remote"))
import circuitpathways_pi as pi


def bridge():
    return pi.Bridge(pi.MockGpio())


class CommandTests(unittest.TestCase):
    def test_an_output_pin_goes_on_and_off(self):
        b = bridge()
        b.handle({"op": "mode", "pin": 17, "mode": "out"})
        ev = b.handle({"op": "write", "pin": 17, "value": 1})
        self.assertEqual(ev["data"]["pins"]["17"], {"mode": "out", "value": 1, "duty": 0.0})
        self.assertEqual(b.handle({"op": "write", "pin": 17, "value": 0})["data"]["pins"]["17"]["value"], 0)

    def test_pwm(self):
        b = bridge()
        b.handle({"op": "mode", "pin": 18, "mode": "pwm"})
        ev = b.handle({"op": "pwm", "pin": 18, "duty": 0.25, "freq": 200})
        self.assertEqual(ev["data"]["pins"]["18"]["duty"], 0.25)

    def test_inputs_follow_the_wire_and_pull_ups_default_high(self):
        g = pi.MockGpio()
        b = pi.Bridge(g)
        b.handle({"op": "mode", "pin": 4, "mode": "in"})
        b.handle({"op": "mode", "pin": 5, "mode": "in_up"})
        self.assertEqual((b.snapshot()["4"]["value"], b.snapshot()["5"]["value"]), (0, 1))
        g.inputs[4] = 1
        g.inputs[5] = 0
        self.assertEqual((b.snapshot()["4"]["value"], b.snapshot()["5"]["value"]), (1, 0))

    def test_only_allowed_commands_get_through(self):
        b = bridge()
        bad = [
            {}, {"op": "shell", "cmd": "rm -rf /"}, {"op": "mode", "pin": 1, "mode": "out"}, {"op": "mode", "pin": 28, "mode": "out"},
            {"op": "mode", "pin": "17", "mode": "out"}, {"op": "mode", "pin": True, "mode": "out"}, {"op": "mode", "pin": 17, "mode": "wat"},
            {"op": "write", "pin": 17, "value": 1},                      # not an output yet
            {"op": "pwm", "pin": 18, "duty": 0.5},                       # not PWM yet
            "hello", None, 5,
        ]
        for cmd in bad:
            with self.assertRaises(pi.BadCommand, msg=str(cmd)):
                b.handle(cmd)
        b.handle({"op": "mode", "pin": 17, "mode": "out"})
        for cmd in [{"op": "write", "pin": 17, "value": 2}, {"op": "write", "pin": 17, "value": True}, {"op": "write", "pin": 17}]:
            with self.assertRaises(pi.BadCommand, msg=str(cmd)):
                b.handle(cmd)
        b.handle({"op": "mode", "pin": 18, "mode": "pwm"})
        for cmd in [{"op": "pwm", "pin": 18, "duty": 1.5}, {"op": "pwm", "pin": 18, "duty": -0.1}, {"op": "pwm", "pin": 18, "duty": 0.5, "freq": 99999}, {"op": "pwm", "pin": 18, "duty": "x"}]:
            with self.assertRaises(pi.BadCommand, msg=str(cmd)):
                b.handle(cmd)

    def test_all_off_switches_every_output_off_and_leaves_inputs_alone(self):
        b = bridge()
        for pin in (17, 22):
            b.handle({"op": "mode", "pin": pin, "mode": "out"})
            b.handle({"op": "write", "pin": pin, "value": 1})
        b.handle({"op": "mode", "pin": 18, "mode": "pwm"})
        b.handle({"op": "pwm", "pin": 18, "duty": 1})
        b.handle({"op": "mode", "pin": 4, "mode": "in_up"})
        snap = b.handle({"op": "all_off"})["data"]["pins"]
        self.assertEqual([snap[p]["value"] for p in ("17", "22", "18")], [0, 0, 0])
        self.assertEqual(snap["4"]["mode"], "in_up")

    def test_release_lets_a_pin_go(self):
        b = bridge()
        b.handle({"op": "mode", "pin": 17, "mode": "out"})
        self.assertNotIn("17", b.handle({"op": "release", "pin": 17})["data"]["pins"])

    def test_too_many_commands_a_second_are_refused(self):
        t = [0.0]
        b = pi.Bridge(pi.MockGpio(), clock=lambda: t[0])
        for _ in range(pi.MAX_COMMANDS_PER_SECOND):
            b.handle({"op": "ping"})
        with self.assertRaises(pi.BadCommand):
            b.handle({"op": "ping"})
        t[0] += 1.1
        b.handle({"op": "ping"})

    def test_hello_says_what_this_is(self):
        h = bridge().hello_event()["data"]
        self.assertEqual((h["backend"], h["pins"]), ("mock", [2, 27]))

    def test_shutdown_lets_every_pin_go(self):
        g = pi.MockGpio()
        b = pi.Bridge(g)
        b.handle({"op": "mode", "pin": 17, "mode": "out"})
        b.shutdown()
        self.assertEqual(g.pins, {})


KEY = "CPK1-K7M2QX9P-AB12CD34EF"


class FakeWebsite(BaseHTTPRequestHandler):
    """Just enough of the website's /api/pi/pi/ to test the Pi's side of the conversation."""
    sent, commands = [], []
    refuse = False

    def log_message(self, *a):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        assert self.headers["X-Circuit-Pathways"] == "1"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if type(self).refuse or self.headers["X-Pi-Key"] != KEY:
            return self._json(403, {"error": "pi_key"})
        type(self).sent.append(body["event"])
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        assert self.path == "/api/pi/pi/events"
        if type(self).refuse or self.headers["X-Pi-Key"] != KEY:
            return self._json(403, {"error": "pi_key"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b"retry: 3000\n\n")
        for c in type(self).commands:
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
        self.wfile.write(b": keep-alive\n\ndata: not json\n\n")
        self.wfile.flush()
        time.sleep(0.4)  # then the connection ends


class LinkTests(unittest.TestCase):
    def setUp(self):
        FakeWebsite.sent, FakeWebsite.refuse = [], False
        FakeWebsite.commands = [
            {"op": "mode", "pin": 17, "mode": "out"},
            {"op": "write", "pin": 17, "value": 1},
            {"op": "write", "pin": 99, "value": 1},      # refused, and the browser is told
            {"op": "ping", "id": 7},
        ]
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), FakeWebsite)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"

    def tearDown(self):
        self.http.shutdown()

    def test_connects_with_its_key_runs_commands_and_reports_back(self):
        logs = []
        b = bridge()
        link = pi.Link(b, pi.Server(self.base, KEY, "Pi 4"), log=logs.append)
        threading.Thread(target=link.run, daemon=True).start()
        deadline = time.time() + 5
        while time.time() < deadline and not any(e["type"] == "pong" for e in FakeWebsite.sent):
            time.sleep(0.05)
        link.stop.set()
        types = [e["type"] for e in FakeWebsite.sent]
        self.assertEqual(types[0], "hello")
        self.assertEqual(FakeWebsite.sent[0]["data"]["name"], "Pi 4")
        self.assertIn("pong", types)
        errors = [e for e in FakeWebsite.sent if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("GPIO 99", errors[0]["data"]["message"])
        self.assertEqual(b.snapshot()["17"]["value"], 1, "the command from the website switched the pin on")

    def test_a_key_the_website_refuses_is_explained_and_retried_slowly(self):
        FakeWebsite.refuse = True
        logs, sleeps = [], []
        link = pi.Link(bridge(), pi.Server(self.base, KEY), sleep=lambda s: (sleeps.append(s), time.sleep(0.01)), log=logs.append)
        threading.Thread(target=link.run, daemon=True).start()
        deadline = time.time() + 5
        while time.time() < deadline and not any("key isn't valid" in l for l in logs):
            time.sleep(0.05)
        link.stop.set()
        self.assertTrue(any("key isn't valid" in l for l in logs))
        self.assertIn(60.0, sleeps)

    def test_losing_the_website_switches_outputs_off(self):
        b = bridge()
        b.handle({"op": "mode", "pin": 17, "mode": "out"})
        b.handle({"op": "write", "pin": 17, "value": 1})
        t = [0.0]
        logs = []
        link = pi.Link(b, pi.Server("http://127.0.0.1:1", KEY), log=logs.append, clock=lambda: t[0], sleep=lambda s: time.sleep(0.01))
        link.lost_at = 0.0
        t[0] = pi.FAILSAFE_SECONDS + 1
        threading.Thread(target=link._poller, daemon=True).start()
        deadline = time.time() + 3
        while time.time() < deadline and b.snapshot()["17"]["value"] == 1:
            time.sleep(0.02)
        link.stop.set()
        self.assertEqual(b.snapshot()["17"]["value"], 0)
        self.assertTrue(any("switched off" in l for l in logs))


class KeyAndConfigTests(unittest.TestCase):
    def test_the_id_on_the_label_comes_from_the_key(self):
        self.assertEqual(pi.pi_id(KEY), "K7M2-QX9P")
        self.assertEqual(pi.pi_id("  " + KEY.lower() + " "), "K7M2-QX9P")
        for bad in ["", "hello", "CPK2-K7M2QX9P-AB12CD34EF", "CPK1-K7M2QX9-AB12CD34EF", "CPK1-K7M2QX9P-AB12"]:
            with self.assertRaises(ValueError):
                pi.pi_id(bad)

    def test_config_file_lines(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write('# made by the installer\nKEY=%s\nSERVER="https://example.org"\nNAME=Lab Pi 3\n' % KEY)
        self.assertEqual(pi.read_config(f.name), {"KEY": KEY, "SERVER": "https://example.org", "NAME": "Lab Pi 3"})
        with self.assertRaises(SystemExit):
            pi.read_config("/nonexistent/file.conf")

    def test_start_up_checks(self):
        for argv in (["--mock"], ["--mock", "--key", "nope"], ["--mock", "--key", KEY, "--server", "file:///etc/passwd"]):
            with self.assertRaises(SystemExit, msg=str(argv)):
                pi.main(argv)


if __name__ == "__main__":
    unittest.main()
