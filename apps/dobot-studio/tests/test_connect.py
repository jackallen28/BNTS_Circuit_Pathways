"""The first screen: connect, home and try the arm before choosing a program."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from time import monotonic, sleep
import os
import sys
import tkinter as tk
import unittest
from tkinter import messagebox
from unittest import mock

from tests.fake_dobot import FakeDobot

needs_display = unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "needs a display")


@needs_display
class ConnectScreenTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.app import Studio

        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.addCleanup(lambda: self.root.eval("foreach id [after info] {after cancel $id}"))
        self.addCleanup(self.settle)
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        self.studio = Studio(self.root, Path("/nonexistent"), Path(folder))
        patcher = mock.patch.object(messagebox, "askokcancel", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dobot = FakeDobot()
        self.dobot.start()
        self.dobot.pose = [220.0, 0.0, 40.0, 0.0]
        self.addCleanup(self.dobot.close)

    def pump(self, seconds=3.0, until=None):
        end = monotonic() + seconds
        while monotonic() < end:
            self.root.update()
            sleep(0.01)
            if until and until():
                return True
        return until() if until else None

    def settle(self):
        """Let every arm job finish before the window goes, so nothing touches Tk from another thread."""
        self.pump(5, lambda: self.studio.busy is None)
        if self.studio.robot:
            self.studio.robot.close()
            self.studio.robot = None

    def connected_and_homed(self):
        studio = self.studio
        studio.show_connect()
        studio.port.set(self.dobot.path)
        studio.connect()
        self.assertTrue(self.pump(5, lambda: studio.robot is not None))
        studio.home()
        self.assertTrue(self.pump(40, lambda: studio.homed and studio.busy is None))
        return studio.connect_screen

    def test_it_comes_first_in_hardware_mode_and_nothing_can_be_chosen_yet(self):
        studio = self.studio
        studio.show_connect()
        screen = studio.connect_screen
        self.assertIsNotNone(screen)
        self.assertFalse(studio.demo)
        self.assertIs(studio.program_menu, screen.canvas)
        for button in (screen.continue_button, screen.home_button, screen.hold_button, *screen.move_buttons.values()):
            self.assertIn("disabled", button.state())
        self.assertIn("Not connected", screen.connection_label.cget("text"))

    def test_connecting_and_homing_unlock_the_test_pad_and_the_programs_page(self):
        screen = self.connected_and_homed()
        self.assertIn("Connected", screen.connection_label.cget("text"))
        self.assertIn("Homed", screen.home_label.cget("text"))
        for button in (screen.continue_button, screen.hold_button, screen.release_button, *screen.move_buttons.values()):
            self.assertNotIn("disabled", button.state())
        self.assertIn("Tool position", screen.position_text.get())

    def test_the_arm_can_be_moved_in_steps_and_the_suction_tried(self):
        screen = self.connected_and_homed()
        self.dobot.pose = [220.0, 0.0, 40.0, 0.0]
        screen.step.set("10 mm")
        screen.move((1, 0, 0))
        self.assertTrue(self.pump(10, lambda: abs(self.dobot.pose[0] - 230) < 0.5 and self.studio.busy is None))
        screen.step.set("5 mm")
        screen.move((0, 1, 1))
        self.assertTrue(self.pump(10, lambda: abs(self.dobot.pose[1] - 5) < 0.5 and self.studio.busy is None))
        self.assertAlmostEqual(self.dobot.pose[2], 45, delta=0.5)
        self.assertIn("5.0", self.studio.position.label())
        for tool, holding, seen in (("Suction cup", True, lambda: self.dobot.suction == 1),
                                    ("Suction cup", False, lambda: self.dobot.suction == 0),
                                    ("Gripper", True, lambda: self.dobot.gripper == 1)):
            screen.tool.set(tool)
            screen.hold(holding)
            self.assertTrue(self.pump(5, lambda: seen() and self.studio.busy is None))

    def test_a_move_outside_the_safe_area_is_refused_and_the_arm_stays_homed(self):
        screen = self.connected_and_homed()
        self.dobot.pose = [305.0, 0.0, 40.0, 0.0]
        self.studio.position = None
        screen.step.set("10 mm")
        screen.move((1, 0, 0))
        self.assertTrue(self.pump(10, lambda: self.studio.busy is None and "reach" in self.studio.status_text.get().lower()))
        self.assertEqual(self.dobot.pose[0], 305.0)
        self.assertTrue(self.studio.homed)

    def test_continue_opens_the_programs_page_and_the_connection_can_be_reopened(self):
        screen = self.connected_and_homed()
        screen.finish()
        self.assertIsNone(self.studio.connect_screen)
        self.assertIsNotNone(self.studio.program_menu)
        self.assertFalse(self.studio.demo)
        self.studio.show_connect()
        self.assertIsNotNone(self.studio.connect_screen)
        self.assertTrue(self.studio.robot is not None and self.studio.homed)
        self.assertNotIn("disabled", self.studio.connect_screen.continue_button.state())

    def test_demo_mode_skips_the_dobot_and_goes_straight_to_the_programs(self):
        studio = self.studio
        studio.show_connect()
        studio.connect_screen.use_demo()
        self.assertTrue(studio.demo)
        self.assertIsNone(studio.connect_screen)
        self.assertIsNotNone(studio.program_menu)

    def test_continue_does_nothing_until_the_arm_is_homed(self):
        studio = self.studio
        studio.show_connect()
        studio.connect_screen.finish()
        self.assertIsNotNone(studio.connect_screen)

    def test_escape_stops_a_move_in_progress(self):
        screen = self.connected_and_homed()
        self.dobot.pose = [220.0, 0.0, 40.0, 0.0]
        screen.step.set("20 mm")
        screen.move((0, 1, 0))
        self.pump(0.12)
        self.studio.stop("Stopped from the keyboard.")
        self.assertTrue(self.pump(10, lambda: self.studio.busy is None))
        self.assertFalse(self.dobot.running)
        self.assertLess(self.dobot.pose[1], 19.5)

    def test_unplugging_the_arm_shows_a_message_and_does_not_crash(self):
        screen = self.connected_and_homed()
        self.dobot.drop_next = 50
        screen.move((1, 0, 0))
        self.assertTrue(self.pump(15, lambda: self.studio.busy is None))
        self.assertIn("did not answer", self.studio.status_text.get())


@needs_display
class ConnectLayoutTests(unittest.TestCase):
    def test_every_button_fits_inside_the_card_on_a_720p_screen(self):
        from dobot_studio.app import Studio

        root = tk.Tk()
        self.addCleanup(root.destroy)
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        root.geometry("1280x720+0+0")
        studio = Studio(root, Path("/nonexistent"), Path(folder))
        studio.show_connect()
        for _ in range(20):
            root.update()
            sleep(0.01)
        screen = studio.connect_screen
        card = screen.continue_button.nametowidget(screen.continue_button.winfo_parent()).nametowidget(
            screen.continue_button.nametowidget(screen.continue_button.winfo_parent()).winfo_parent())
        right = card.winfo_rootx() + card.winfo_width()
        bottom = card.winfo_rooty() + card.winfo_height()
        for name in ("scan_button", "connect_button", "home_button", "hold_button", "release_button",
                     "continue_button", "demo_button", "stop_button"):
            widget = getattr(screen, name)
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right, f"{name} is cut off at the right")
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom, f"{name} is cut off at the bottom")
        for key, widget in screen.move_buttons.items():
            parent = widget.nametowidget(widget.winfo_parent())
            self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), parent.winfo_width(), f"{key} is cut off")
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right, f"{key} is outside the card")


if __name__ == "__main__":
    unittest.main()
