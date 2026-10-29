"""Tests for the Pi Link. Run: python3 -m unittest discover pi-bridge   (no Pi needed)"""
import base64
import io
import json
import shutil
import tempfile
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


class RunnerTests(unittest.TestCase):
    """The student's program, run for real (with this computer's Python)."""

    def setUp(self):
        self.events = []
        self.bridge = bridge()
        self.runner = pi.Runner(self.bridge, lambda ev, reliable=False: self.events.append(ev),
                                base_dir=tempfile.mkdtemp(), max_seconds=6, idle_seconds=60)

    def tearDown(self):
        self.runner.shutdown()
        shutil.rmtree(self.runner.base_dir, ignore_errors=True)

    def run_program(self, code, wait=15, rid=1, **extra):
        self.runner.start({"op": "run", "rid": rid, "name": "program.py", "code": code, **extra})
        end = time.time() + wait
        while time.time() < end and not any(e["type"] == "exit" for e in self.events):
            time.sleep(0.05)
        return self.exit_event()

    def exit_event(self):
        ex = [e for e in self.events if e["type"] == "exit"]
        return ex[-1]["data"] if ex else None

    def printed(self, stream="out"):
        return "".join(e["data"]["text"] for e in self.events if e["type"] == "out" and e["data"]["stream"] == stream)

    def test_a_program_runs_and_its_output_comes_back(self):
        ex = self.run_program("print('Hello', 6 * 7)\n")
        self.assertEqual((ex["rc"], ex["stopped"]), (0, False))
        self.assertEqual(self.printed(), "Hello 42\n")
        self.assertEqual([e["data"]["state"] for e in self.events if e["type"] == "run"], ["started"])

    def test_a_crash_has_a_traceback_that_names_the_students_file(self):
        ex = self.run_program("x = 1\nprint(undefined_name)\n")
        self.assertNotEqual(ex["rc"], 0)
        err = self.printed("err")
        self.assertIn('File "program.py", line 2', err)
        self.assertIn("NameError", err)
        self.assertNotIn(self.runner.base_dir, err)

    def test_input_gets_the_students_typed_lines(self):
        self.runner.start({"op": "run", "rid": 3, "name": "program.py", "code": "name = input('Name? ')\nprint('Hi', name)\n"})
        for _ in range(100):
            if any(e["type"] == "run" and e["data"]["state"] == "started" for e in self.events):
                break
            time.sleep(0.05)
        self.runner.stdin({"op": "stdin", "rid": 3, "text": "Mia"})
        for _ in range(200):
            if self.exit_event():
                break
            time.sleep(0.05)
        self.assertIn("Hi Mia", self.printed())
        self.assertEqual(self.exit_event()["rc"], 0)

    def test_stop_ends_a_forever_loop_quietly(self):
        self.runner.start({"op": "run", "rid": 4, "name": "program.py", "code": "import time\nwhile True:\n    time.sleep(0.1)\n"})
        for _ in range(100):
            if any(e["type"] == "run" and e["data"]["state"] == "started" for e in self.events):
                break
            time.sleep(0.05)
        self.runner.stop({"op": "stop", "rid": 4})
        for _ in range(200):
            if self.exit_event():
                break
            time.sleep(0.05)
        ex = self.exit_event()
        self.assertEqual((ex["stopped"], ex["reason"], ex["rc"]), (True, "stop", 130))
        self.assertEqual(self.printed("err"), "", "Ctrl+C's traceback shouldn't be shown when the student pressed Stop")

    def test_a_program_that_ignores_ctrl_c_is_still_stopped(self):
        code = "import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('ready', flush=True)\nwhile True:\n    time.sleep(0.1)\n"
        self.runner.start({"op": "run", "rid": 5, "name": "program.py", "code": code})
        for _ in range(100):
            if "ready" in self.printed():
                break
            time.sleep(0.05)
        self.runner.stop({"op": "stop", "rid": 5})
        for _ in range(200):
            if self.exit_event():
                break
            time.sleep(0.05)
        self.assertTrue(self.exit_event()["stopped"])

    def test_a_program_that_runs_too_long_is_stopped(self):
        ex = self.run_program("import time\nwhile True:\n    time.sleep(0.1)\n", wait=20)
        self.assertEqual(ex["reason"], "timeout")
        self.assertIn("stopped your program", self.printed())

    def test_a_page_that_stops_answering_stops_the_program(self):
        self.runner.idle_seconds = 0.5
        ex = self.run_program("import time\nwhile True:\n    time.sleep(0.1)\n")
        self.assertEqual(ex["reason"], "idle")

    def test_a_program_that_prints_forever_is_cut_off(self):
        ex = self.run_program("while True:\n    print('spam' * 50)\n")
        self.assertEqual(ex["reason"], "output")
        self.assertLessEqual(len(self.printed()), pi.RUN_OUTPUT_LIMIT + 4096)

    def test_big_output_arrives_in_pieces_the_page_can_take(self):
        ex = self.run_program("print('x' * 7000)\n")
        self.assertEqual(ex["rc"], 0)
        self.assertEqual(len(self.printed()), 7001)
        self.assertTrue(all(len(e["data"]["text"]) <= pi.OUT_CHUNK for e in self.events if e["type"] == "out"))

    def test_data_files_and_helper_modules_are_there_and_new_files_are_reported(self):
        self.runner.fetch = lambda path: b"VALUE = 'from the helper'\n"
        code = "import pipath_computer\nprint(open('words/list.txt').read().strip(), pipath_computer.VALUE)\nopen('score.txt', 'w').write('7 points')\n"
        ex = self.run_program(code, files={"words/list.txt": base64.b64encode(b"cat").decode()}, support=["pipath_computer"])
        self.assertEqual(self.printed(), "cat from the helper\n")
        self.assertEqual(ex["files"]["score.txt"], {"size": 8, "text": "7 points"})
        self.assertNotIn("words/list.txt", ex["files"], "files the page sent aren't news")
        self.assertFalse(os.listdir(self.runner.base_dir), "the temporary folder is deleted")

    def test_the_program_gets_a_clean_environment(self):
        os.environ["CP_TEST_SECRET"] = "hunter2"
        try:
            self.run_program("import os\nprint(sorted(os.environ))\nprint(os.environ.get('PIPATH_CAMERA_OBJECT'))\n", camera_object="red ball")
        finally:
            del os.environ["CP_TEST_SECRET"]
        self.assertNotIn("CP_TEST_SECRET", self.printed())
        self.assertIn("red ball", self.printed())

    def test_it_will_not_run_when_switched_off_or_given_bad_things(self):
        self.runner.enabled = False
        with self.assertRaises(pi.BadCommand):
            self.runner.start({"op": "run", "rid": 1, "name": "program.py", "code": "print(1)"})
        self.runner.enabled = True
        base = {"op": "run", "rid": 1, "name": "program.py", "code": "print(1)"}
        for bad in [{"rid": 0}, {"rid": True}, {"name": "../x.py"}, {"name": "x.sh"}, {"name": "a b.py"}, {"code": ""}, {"code": "x" * (pi.MAX_CODE + 1)},
                    {"files": {"../x": "eA=="}}, {"files": {"/etc/passwd": "eA=="}}, {"files": {"a": 5}}, {"support": ["os"]}, {"camera_object": "a;b"}]:
            with self.assertRaises(pi.BadCommand, msg=str(bad)):
                self.runner.start({**base, **bad})
        self.assertFalse(self.runner.active)

    def test_one_program_at_a_time(self):
        self.runner.start({"op": "run", "rid": 1, "name": "program.py", "code": "import time\ntime.sleep(5)\n"})
        with self.assertRaises(pi.BadCommand):
            self.runner.start({"op": "run", "rid": 2, "name": "program.py", "code": "print(2)"})
        self.runner.stop({"op": "stop", "rid": 1})

    def test_the_program_owns_the_pins_while_it_runs(self):
        self.bridge.handle({"op": "mode", "pin": 17, "mode": "out"})
        self.runner.start({"op": "run", "rid": 1, "name": "program.py", "code": "import time\ntime.sleep(5)\n"})
        for _ in range(100):
            if self.bridge.program_running:
                break
            time.sleep(0.05)
        self.assertEqual(self.bridge.snapshot(), {}, "the Pi let go of its pins")
        with self.assertRaises(pi.BadCommand):
            self.bridge.handle({"op": "mode", "pin": 18, "mode": "out"})
        self.assertIn("pong", self.bridge.handle({"op": "ping"})["type"])
        self.runner.stop({"op": "stop", "rid": 1})
        for _ in range(200):
            if not self.bridge.program_running:
                break
            time.sleep(0.05)
        self.bridge.handle({"op": "mode", "pin": 18, "mode": "out"})

    def test_losing_the_website_stops_the_program(self):
        self.runner.start({"op": "run", "rid": 1, "name": "program.py", "code": "import time\ntime.sleep(30)\n"})
        for _ in range(100):
            if self.runner.proc:
                break
            time.sleep(0.05)
        self.runner.stop_all("offline")
        for _ in range(200):
            if self.exit_event():
                break
            time.sleep(0.05)
        self.assertEqual(self.exit_event()["reason"], "offline")


class LinkRunTests(unittest.TestCase):
    def test_commands_for_programs_go_to_the_runner_and_errors_name_the_run(self):
        events = []
        b = bridge()
        link = pi.Link(b, pi.Server("http://x", "CPK1-K7M2QX9P-AB12CD34EF"))
        link.runner = pi.Runner(b, lambda ev, reliable=False: events.append(ev), enabled=False)
        with self.assertRaises(pi.BadCommand):
            link.dispatch({"op": "run", "rid": 9, "name": "program.py", "code": "print(1)"})
        self.assertEqual(link.dispatch({"op": "stop", "rid": 9}), None)
        self.assertEqual(link.dispatch({"op": "ping"})["type"], "pong")
        self.assertFalse(b.hello_event(can_run=False)["data"]["can_run"])
        self.assertTrue(b.hello_event(can_run=True)["data"]["can_run"])

    def test_chatty_output_is_sent_in_fewer_messages(self):
        out = lambda text, stream="out", rid=1: {"type": "out", "data": {"rid": rid, "stream": stream, "text": text}}
        first, rest = out("a"), [out("b"), out("c"), out("d", "err"), out("e", rid=2), {"type": "state", "data": {}}, out("f")]
        batch = pi.Link._batch(first, rest)
        self.assertEqual([e["data"].get("text") for e in batch], ["abc", "d", "e", None, "f"])
        big = [out("x" * pi.OUT_CHUNK), out("y")]
        self.assertTrue(all(len(e["data"]["text"]) <= pi.OUT_CHUNK for e in pi.Link._batch(out("z"), big)), "a message never grows past the chunk size")


class WhoRunsTheProgramTests(unittest.TestCase):
    def test_root_never_runs_a_students_program_as_root(self):
        self.assertEqual(pi.decide_run(True, None, euid=0, user_exists=lambda n: True)[0], False)
        self.assertEqual(pi.decide_run(True, "ghost", euid=0, user_exists=lambda n: False)[0], False)
        self.assertEqual(pi.decide_run(True, "cprun", euid=0, user_exists=lambda n: True), (True, ""))
        self.assertEqual(pi.decide_run(True, None, euid=1000), (True, ""))
        self.assertEqual(pi.decide_run(False, "cprun", euid=0, user_exists=lambda n: True), (False, ""))

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "needs root to switch user")
    def test_the_program_runs_as_the_unprivileged_user_and_cannot_read_the_key(self):
        import pwd
        try:
            pwd.getpwnam("nobody")
        except KeyError:
            self.skipTest("no 'nobody' user")
        secret = tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf")
        secret.write("KEY=CPK1-SECRET\n")
        secret.close()
        os.chmod(secret.name, 0o600)
        events = []
        base = tempfile.mkdtemp()
        os.chmod(base, 0o755)
        r = pi.Runner(bridge(), lambda ev, reliable=False: events.append(ev), base_dir=base, run_user="nobody")
        code = ("import os\nprint('uid', os.getuid() != 0)\n"
                "try:\n    open(%r).read()\n    print('READ THE KEY')\nexcept PermissionError:\n    print('no access')\n"
                "open('mine.txt', 'w').write('ok')\n") % secret.name
        try:
            r.start({"op": "run", "rid": 1, "name": "program.py", "code": code})
            for _ in range(200):
                if any(e["type"] == "exit" for e in events):
                    break
                time.sleep(0.05)
            text = "".join(e["data"]["text"] for e in events if e["type"] == "out")
            self.assertIn("uid True", text)
            self.assertIn("no access", text)
            self.assertNotIn("READ THE KEY", text)
            self.assertIn("mine.txt", [e for e in events if e["type"] == "exit"][0]["data"]["files"])
        finally:
            os.unlink(secret.name)
            shutil.rmtree(base, ignore_errors=True)
