"""The guided setup, end to end: a real program, real arm commands on a fake Dobot, and a fake camera."""
from pathlib import Path
from shutil import rmtree
from struct import unpack
from tempfile import mkdtemp
from time import monotonic, sleep
from types import SimpleNamespace
import os
import sys
import tkinter as tk
import unittest
from tkinter import messagebox
from unittest import mock

import cv2
import numpy as np
from PIL import Image

from dobot_studio import robot as R
from dobot_studio import tictactoe_program
from dobot_studio.matcalib import PARK, outer_points
from dobot_studio.tictactoe import O, SMALL_MAT, X
from tests.fake_dobot import FakeDobot
from tests.test_matcalib import TruePlacement
from tests.test_tictactoe import camera_view

needs_display = unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "needs a display")
LAYOUT = SMALL_MAT          # the mat that fits the arm: with the Dobot facing a long edge, 220 mm from its middle
# Where the mat really is, as the arm would find out by touching it. The software is never told.
TRUTH = TruePlacement(LAYOUT, angle=90, scale=0.99, offset=(220, 0), tilt=(0.0008, -0.0005), surface=-38.0)
BANKS = {**{f"X{i}": X for i in range(1, 6)}, **{f"O{i}": O for i in range(1, 6)}}


@needs_display
class WizardTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.app import Studio

        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.addCleanup(lambda: self.root.eval("foreach id [after info] {after cancel $id}"))
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        self.studio = Studio(self.root, Path("/nonexistent"), Path(folder))
        patcher = mock.patch.object(messagebox, "askokcancel", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dobot = FakeDobot()
        self.dobot.start()
        self.dobot.pose = [190.0, 0.0, 40.0, 0.0]
        self.dobot.speed = 6.0
        self.addCleanup(self.close_arm)
        self.frames = {"empty": camera_view({}, layout=LAYOUT, solid=True),
                       "banks": camera_view(BANKS, layout=LAYOUT, solid=True),
                       "game": camera_view({**BANKS, "A1": X, "B2": O}, layout=LAYOUT, solid=True)}
        self.current = {"frame": self.frames["empty"]}

    def close_arm(self):
        self.pump(8, lambda: self.studio.busy is None)
        program = getattr(self, "program", None)
        if program is not None and program.tune_dialog is not None:
            program.tune_dialog.close()
        self.dialog = None
        if program is not None and program.window.winfo_exists():
            self.pump(8, lambda: not program.busy)
            program.window.destroy()
        if self.studio.robot:
            self.studio.robot.close()
            self.studio.robot = None
        self.dobot.close()
        import gc

        gc.collect()                          # drop pictures and variables here, on the main thread, while Tk still runs

    def pump(self, seconds=1.0, until=None):
        end = monotonic() + seconds
        while monotonic() < end:
            self.root.update()
            sleep(0.01)
            if until and until():
                return True
        return until() if until else None

    def open_program(self, connect=True):
        studio = self.studio
        studio.set_mode(False)
        if connect:
            studio.port.set(self.dobot.path)
            studio.connect()
            self.assertTrue(self.pump(5, lambda: studio.robot is not None))
            studio.home()
            self.assertTrue(self.pump(40, lambda: studio.homed and studio.busy is None))
        self.program = tictactoe_program.TicTacToeProgram(studio)
        self.program.window.geometry("1050x666+0+0")
        self.camera()
        self.wizard = self.program.wizard
        return self.program

    def camera(self):
        self.program.camera = SimpleNamespace(
            read=lambda: (SimpleNamespace(timestamp=monotonic()), Image.fromarray(self.current["frame"])),
            close=lambda: None, thread=SimpleNamespace(is_alive=lambda: False))

    def touch(self, point, rotation=0.0):
        pose = TRUTH.surface_pose(point, rotation=rotation)
        self.dobot.pose = [pose.x, pose.y, pose.z, pose.r]

    def walk_to_corners(self):
        wizard = self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))          # step 1: good to go
        wizard.next()
        wizard.capture()                                                          # step 2: the empty mat
        self.assertIsNotNone(self.program.reference)
        wizard.next()
        self.touch(LAYOUT.park)                                                   # step 3: the centre mark
        wizard.save_centre()
        self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and self.studio.busy is None and not self.program.busy))
        wizard.next()
        for name in outer_points(LAYOUT):                                         # step 4: the four corners
            self.touch(LAYOUT.positions[name])
            wizard.save_corner()
            self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))

    def test_show_the_mat_says_good_to_go_only_when_all_four_markers_are_seen(self):
        self.open_program()
        wizard = self.wizard
        self.program.camera = None
        self.pump(0.3)
        self.assertFalse(wizard._ready_to_leave())
        self.assertIn("Start the camera", wizard.status.get())
        self.camera()
        self.assertTrue(self.pump(4, lambda: wizard._ready_to_leave()))
        self.assertIn("Good to go", wizard.status.get())
        self.current["frame"] = cv2.rectangle(self.frames["empty"].copy(), (90, 0), (640, 480), (40, 44, 52), -1)
        self.assertTrue(self.pump(4, lambda: not wizard._ready_to_leave()))
        self.assertIn("Looking for the four markers", wizard.status.get())

    def test_the_arm_steps_need_a_connected_and_homed_arm(self):
        self.open_program(connect=False)
        wizard = self.wizard
        self.pump(0.5)
        wizard.step = 2
        wizard._show_step()
        self.pump(0.3)
        self.assertIn("not connected", wizard.status.get())
        self.assertIn("disabled", wizard.centre_button.state())
        self.assertTrue(wizard.connection_button.winfo_ismapped())

    def test_the_whole_setup_the_arm_finds_every_circle_from_only_five_touches(self):
        self.open_program()
        wizard, program = self.wizard, self.program
        self.walk_to_corners()
        self.assertIsNotNone(wizard.calibration)
        self.assertEqual(wizard.calibration.problems(), [])
        self.assertEqual(len(wizard.touched), 5, "only the centre and the four corners were touched")
        derived = wizard.calibration.poses()
        self.assertEqual(set(derived), {*LAYOUT.positions, PARK, "Rest"})
        worst = max(np.hypot(derived[name].x - TRUTH.xy(point)[0], derived[name].y - TRUTH.xy(point)[1])
                    for name, point in LAYOUT.positions.items())
        self.assertLess(worst, 0.5, "a circle the arm was never touched on is more than 0.5 mm out")
        self.assertAlmostEqual(wizard.calibration.scale, 0.99, places=3)
        self.assertFalse(program.setup_done)
        wizard.next()
        self.assertEqual(wizard.step, 4)

    def test_a_refused_move_keeps_the_arm_connected_and_homed_and_says_why(self):
        """Check all points once reported "not connected and homed" when the arm only refused a point."""
        self.open_program()
        wizard = self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.calibration.adjust("A1", dx=300)                 # a point far beyond the arm's reach
        self.program.poses = wizard.calibration.poses()
        self.dobot.log.clear()
        wizard.run_check()
        self.assertTrue(self.pump(10, lambda: wizard.notice and not self.program.busy))
        self.pump(0.4)
        self.assertTrue(self.studio.homed)
        self.assertIsNotNone(self.studio.robot)
        self.assertNotIn("not connected", wizard.status.get())
        self.assertIn("mm from the arm's base", wizard.status.get())
        self.assertEqual([c for c, _, _ in self.dobot.log if c == R.MOVE], [], "nothing moved")
        self.assertNotIn("disabled", wizard.tour_button.state())
        wizard.calibration.adjustments.clear()                  # fix it and the check works again
        self.program.poses = wizard.calibration.poses()
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not self.program.busy))
        self.assertEqual(wizard.notice, "")

    def test_an_unconfirmed_stop_does_ask_for_homing_again(self):
        self.open_program()
        wizard = self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.pending = ("B2", False)
        wizard.finished("visit", None, R.StopUnconfirmed("Stop could not be confirmed."))
        self.assertFalse(self.studio.homed)

    def to_corners(self):
        wizard = self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        self.touch(LAYOUT.park)
        wizard.save_centre()
        self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not self.program.busy))
        wizard.next()

    def test_quick_setup_needs_only_the_centre_and_one_corner(self):
        self.open_program()
        wizard = self.wizard
        self.to_corners()
        wizard.mode.set("quick")
        wizard.set_mode()
        corner = outer_points(LAYOUT)[0]
        self.assertEqual(wizard.target(), corner)
        self.pump(0.3)
        self.assertIn("1 of 1", wizard.status.get())
        self.touch(LAYOUT.positions[corner])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: corner in wizard.touched and not self.program.busy))
        self.pump(0.4)
        self.assertEqual(len(wizard.touched), 2)
        self.assertTrue(wizard.calibration.quick)
        self.assertIn("Quick setup done", wizard.status.get())
        self.assertNotIn("disabled", wizard.next_button.state())
        derived = wizard.calibration.poses()
        worst = max(np.hypot(derived[name].x - TRUTH.xy(point)[0], derived[name].y - TRUTH.xy(point)[1])
                    for name, point in LAYOUT.positions.items())
        self.assertLess(worst, 0.6)
        wizard.next()                                                             # every circle can still be visited
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not self.program.busy))
        self.assertEqual(wizard.notice, "")

    def test_a_quick_setup_is_made_more_accurate_by_touching_more_corners(self):
        self.open_program()
        wizard = self.wizard
        self.to_corners()
        wizard.mode.set("quick")
        wizard.set_mode()
        first, second = outer_points(LAYOUT)[:2]
        for name in (first, second):
            wizard.picked(name)
            self.touch(LAYOUT.positions[name])
            wizard.save_corner()
            self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))
        self.assertFalse(wizard.calibration.quick, "three spread touches give the full fit")

    def test_switching_to_accurate_asks_for_the_other_corners(self):
        self.open_program()
        wizard = self.wizard
        self.to_corners()
        wizard.mode.set("quick")
        wizard.set_mode()
        corner = outer_points(LAYOUT)[0]
        self.touch(LAYOUT.positions[corner])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: corner in wizard.touched and not self.program.busy))
        wizard.mode.set("full")
        wizard.set_mode()
        self.pump(0.4)
        self.assertIsNone(wizard.calibration)
        self.assertIn("2 of 4", wizard.status.get())
        self.assertEqual(wizard.target(), outer_points(LAYOUT)[1])
        self.assertIn("disabled", wizard.next_button.state())

    def quick_with_one_corner(self):
        self.to_corners()
        wizard = self.wizard
        wizard.mode.set("quick")
        wizard.set_mode()
        corner = outer_points(LAYOUT)[0]
        self.touch(LAYOUT.positions[corner])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: corner in wizard.touched and not self.program.busy))
        return corner

    def test_go_near_carries_the_cup_just_above_the_circle_and_the_arrows_finish_the_job(self):
        self.open_program()
        wizard = self.wizard
        self.quick_with_one_corner()
        second = outer_points(LAYOUT)[1]
        wizard.picked(second)
        wizard.go_near()
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        truth = TRUTH.surface_pose(LAYOUT.positions[second])
        height = wizard.touched[PARK].z
        self.assertAlmostEqual(self.dobot.pose[0], truth.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[1], truth.y, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[2], height + 12, delta=0.4)
        wizard.lower_to_mat()
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertAlmostEqual(self.dobot.pose[2], height, delta=0.4)
        self.assertAlmostEqual(self.dobot.pose[0], truth.x, delta=0.6)
        self.assertEqual(wizard.notice, "")

    def test_each_arrow_moves_the_cup_that_way_on_the_map_and_turned_when_viewed_from_the_dobot(self):
        self.open_program()
        wizard = self.wizard
        self.quick_with_one_corner()
        wizard.picked(outer_points(LAYOUT)[1])
        wizard.go_near()
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        wizard.move_step.set("5 mm")
        point = np.asarray(LAYOUT.positions[outer_points(LAYOUT)[1]], float)
        for turned in (False, True):
            wizard.p.dobot_side.set(turned)
            for key, (dx, dy) in {"right": (1, 0), "up": (0, -1), "left": (-1, 0), "down": (0, 1)}.items():
                before = np.array(self.dobot.pose[:2])
                wizard.move_cup(key)
                self.assertTrue(self.pump(30, lambda: not self.program.busy))
                sign = -1 if turned else 1
                expected = TRUTH.xy(point + (sign * dx, sign * dy)) - TRUTH.xy(point)
                expected = expected / np.hypot(*expected) * 5
                moved = np.array(self.dobot.pose[:2]) - before
                self.assertLess(np.hypot(*(moved - expected)), 0.4, f"{key} (turned {turned})")
        before = self.dobot.pose[2]
        wizard.move_cup("raise")
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertAlmostEqual(self.dobot.pose[2], before + 5, delta=0.4)

    def test_a_corner_saved_with_the_cup_above_the_mat_still_uses_the_centre_marks_height(self):
        self.open_program()
        wizard = self.wizard
        self.to_corners()
        wizard.mode.set("quick")
        wizard.set_mode()
        corner = outer_points(LAYOUT)[0]
        self.touch(LAYOUT.positions[corner])
        self.dobot.pose[2] += 9                                  # the cup is held above the mat
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: corner in wizard.touched and not self.program.busy))
        self.assertAlmostEqual(wizard.touched[corner].z, wizard.touched[PARK].z, places=3)
        wizard.lock_height.set(False)                            # by hand, the height touched is kept
        wizard.picked(outer_points(LAYOUT)[1])
        self.touch(LAYOUT.positions[outer_points(LAYOUT)[1]])
        self.dobot.pose[2] += 9
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: outer_points(LAYOUT)[1] in wizard.touched and not self.program.busy))
        self.assertAlmostEqual(wizard.touched[outer_points(LAYOUT)[1]].z - wizard.touched[PARK].z, 9, delta=1.5)

    def test_go_near_with_only_the_centre_moves_the_arm_somewhere_safe_and_the_buttons_need_the_centre(self):
        self.open_program()
        wizard = self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        wizard.step = 3
        wizard._show_step()
        self.pump(0.3)
        self.assertIn("disabled", wizard.near_button.state())
        wizard.step = 2
        wizard._show_step()
        self.touch(LAYOUT.park)
        wizard.save_centre()
        self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not self.program.busy))
        wizard.next()
        self.pump(0.3)
        self.assertNotIn("disabled", wizard.near_button.state())
        wizard.go_near()
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertEqual(wizard.notice, "")
        self.assertAlmostEqual(self.dobot.pose[2], wizard.height() + 12, delta=0.4)

    def test_the_measured_print_line_is_allowed_for(self):
        self.open_program()
        wizard = self.wizard
        self.assertIsNone(wizard.print_scale())
        self.assertIn("Optional", wizard.print_note.get())
        for bad in ("abc", "250", "12", "0"):
            wizard.print_mm.set(bad)
            self.assertIsNone(wizard.print_scale(), bad)
            self.assertIn("not a length near 100", wizard.print_note.get())
        wizard.print_mm.set("99,0 mm")
        self.assertAlmostEqual(wizard.print_scale(), 0.99)
        self.assertIn("99.0% of full size", wizard.print_note.get())
        self.to_corners()
        wizard.mode.set("quick")
        wizard.set_mode()
        corner = outer_points(LAYOUT)[0]
        self.touch(LAYOUT.positions[corner])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: corner in wizard.touched and not self.program.busy))
        self.assertEqual(wizard.calibration.print_scale, 0.99)
        self.assertAlmostEqual(wizard.calibration.scale, 1.0)
        derived = wizard.calibration.poses()
        worst = max(np.hypot(derived[name].x - TRUTH.xy(point)[0], derived[name].y - TRUTH.xy(point)[1])
                    for name, point in LAYOUT.positions.items())
        self.assertLess(worst, 0.4, "the real size of the print is 99%, as measured")
        wizard.print_mm.set("")                                   # taking the measurement away refits without it
        self.assertIsNone(wizard.calibration.print_scale)

    def test_a_mat_on_a_low_table_is_not_refused_for_being_below_the_usual_floor(self):
        """The mat can be lower than the arm's usual -60 mm floor: the touches say where the table is."""
        self.open_program()
        wizard = self.wizard
        low = TruePlacement(LAYOUT, angle=90, scale=0.99, offset=(220, 0), tilt=(0, 0), surface=-68.0)
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        for name, point in (("centre", LAYOUT.park), *((n, LAYOUT.positions[n]) for n in outer_points(LAYOUT))):
            pose = low.surface_pose(point)
            self.dobot.pose = [pose.x, pose.y, pose.z, pose.r]
            if name == "centre":
                wizard.save_centre()
                self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not self.program.busy))
                wizard.next()
            else:
                wizard.save_corner()
                self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))
        self.pump(0.4)
        self.assertEqual(wizard.unreachable(), [])
        self.assertNotIn("cannot reach", wizard.status.get())
        self.assertNotIn("disabled", wizard.next_button.state())
        wizard.next()
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not self.program.busy))
        self.assertEqual(wizard.notice, "")
        wizard.picked("B2")
        wizard.visit(True)
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertEqual(wizard.notice, "")
        self.assertAlmostEqual(self.dobot.pose[2], low.surface_pose(LAYOUT.positions["B2"]).z + 3.2, delta=0.6)

    def test_a_mat_placed_out_of_reach_is_named_when_the_corners_are_saved(self):
        self.open_program()
        wizard = self.wizard
        far = TruePlacement(LAYOUT, angle=90, scale=0.99, offset=(330, 0), tilt=(0, 0), surface=-38.0)
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        for name, point in (("centre", LAYOUT.park), *((n, LAYOUT.positions[n]) for n in outer_points(LAYOUT))):
            pose = far.surface_pose(point)
            self.dobot.pose = [pose.x, pose.y, pose.z, pose.r]
            if name == "centre":
                wizard.save_centre()
                self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not self.program.busy))
                wizard.next()
            else:
                wizard.save_corner()
                self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))
        self.pump(0.4)
        self.assertTrue(wizard.unreachable())
        self.assertIn("cannot reach", wizard.status.get())
        self.assertIn("disabled", wizard.next_button.state())

    def test_the_arm_visits_every_point_and_a_point_can_be_lowered_and_nudged(self):
        self.open_program()
        wizard = self.wizard
        self.walk_to_corners()
        wizard.next()
        self.dobot.log.clear()
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not self.program.busy))
        visited = [unpack("<B4f", params)[1:3] for command, _, params in self.dobot.log if command == R.MOVE]
        for name, point in LAYOUT.positions.items():
            expected = TRUTH.xy(point)
            self.assertTrue(any(np.hypot(x - expected[0], y - expected[1]) < 0.6 for x, y in visited), f"{name} was not visited")
        self.assertIn("Every point", self.program.status.get())
        self.assertTrue(self.pump(3, lambda: wizard.next_button.instate(["!disabled"])))
        # Look at one circle: lower the cup onto it. It lands on the top of a piece, 3.2 mm above the surface.
        wizard.picked("B2")
        self.assertEqual(wizard.selected, "B2")
        wizard.visit(True)
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        centre = TRUTH.surface_pose(LAYOUT.positions["B2"])
        self.assertAlmostEqual(self.dobot.pose[0], centre.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[1], centre.y, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[2], centre.z + 3.2, delta=0.6)
        before = list(self.dobot.pose)
        wizard.nudge_step.set("2 mm")
        wizard.nudge((1, 0, 0))                       # forward, away from the arm
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertAlmostEqual(self.dobot.pose[0] - before[0], 2.0, delta=0.4)
        self.assertAlmostEqual(self.dobot.pose[1], before[1], delta=0.4)
        self.assertEqual(wizard.calibration.adjustments["B2"], (2.0, 0.0, 0.0))
        self.assertAlmostEqual(self.program.poses["B2"].x, wizard.calibration.pick("B2").x)
        wizard.reset_adjustment()
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertNotIn("B2", wizard.calibration.adjustments)
        self.assertAlmostEqual(self.dobot.pose[0], before[0], delta=0.4)

    def test_the_piece_thickness_is_shown_adjustable(self):
        self.open_program()
        wizard = self.wizard
        self.walk_to_corners()
        wizard.next()
        self.pump(0.3)
        self.assertIn("3.2 mm", wizard.thickness_text.get())
        wizard.picked("B2")
        wizard.visit(True)
        self.assertTrue(self.pump(30, lambda: not self.program.busy))
        centre = TRUTH.surface_pose(LAYOUT.positions["B2"])
        self.assertAlmostEqual(self.dobot.pose[2], centre.z + 3.2, delta=0.6)
        for _ in range(5):
            wizard.change_thickness(0.2)                 # 5 presses on +: the pieces are 4.2 mm thick
            self.assertTrue(self.pump(30, lambda: not self.program.busy))
        self.assertIn("4.2 mm", wizard.thickness_text.get() if self.pump(0.3) is None else "")
        self.assertAlmostEqual(self.dobot.pose[2], centre.z + 4.2, delta=0.6, msg="the lowered cup follows the thickness")
        self.assertAlmostEqual(self.program.poses["A1"].z - TRUTH.surface_pose(LAYOUT.positions["A1"]).z, 4.2, delta=0.6)
        for _ in range(60):
            wizard.change_thickness(0.2)                  # it stops at a sensible limit
        self.assertLessEqual(wizard.calibration.piece_height, 12.0)

    def touch_corners(self, slip, bad=2):
        """Touch the centre and the four corners, with the cup slipping by ``slip`` mm on one of them."""
        wizard = self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        self.touch(LAYOUT.park)
        wizard.save_centre()
        self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not self.program.busy))
        wizard.next()
        corners = outer_points(LAYOUT)
        for index, name in enumerate(corners):
            self.touch(LAYOUT.positions[name])
            if index == bad:
                self.dobot.pose[0] += slip[0]
                self.dobot.pose[1] += slip[1]
            wizard.save_corner()
            self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))
        self.pump(0.4)
        return corners

    def test_the_camera_shows_a_close_up_of_the_point_being_taught(self):
        self.open_program()
        wizard, program = self.wizard, self.program
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        wizard.next()
        program.window.update_idletasks()
        self.pump(0.5)
        texts = lambda: [program.preview.itemcget(item, "text") for item in program.preview.find_all()
                         if program.preview.type(item) == "text"]
        self.assertIn("Close-up of Park", texts())
        self.assertIsNotNone(getattr(program, "loupe_photo", None))
        self.touch(LAYOUT.park)
        wizard.save_centre()
        self.assertTrue(self.pump(5, lambda: PARK in wizard.touched and not program.busy))
        wizard.next()
        self.pump(0.5)
        self.assertIn(f"Close-up of {outer_points(LAYOUT)[0]}", texts())
        wizard.step = 0                                # no close-up when nothing is being touched
        wizard._entered()
        self.pump(0.3)
        self.assertFalse([text for text in texts() if text.startswith("Close-up")])

    def test_a_small_slip_is_a_warning_and_the_setup_goes_on(self):
        self.open_program()
        wizard = self.wizard
        corners = self.touch_corners((7, -4))
        self.assertEqual(wizard.calibration.errors(), [])
        self.assertTrue(wizard.calibration.warnings())
        self.assertIn(corners[2], wizard.status.get())
        self.assertIn("⚠", wizard.status.get())
        self.assertEqual(wizard.status_label.cget("fg"), "#8a5a00")
        self.assertNotIn("disabled", wizard.next_button.state())
        self.assertFalse(wizard.anyway_button.winfo_ismapped())

    def test_a_gross_slip_is_named_blocks_next_and_can_be_touched_again(self):
        self.open_program()
        wizard = self.wizard
        corners = self.touch_corners((25, -14))
        self.assertTrue(wizard.calibration.errors())
        self.assertIn(corners[2], wizard.status.get())
        self.assertIn("disabled", wizard.next_button.state())
        wizard.picked(corners[2])
        self.assertEqual(wizard.target(), corners[2])
        self.touch(LAYOUT.positions[corners[2]])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: not wizard.calibration.errors() and not self.program.busy))
        self.pump(0.4)
        self.assertNotIn("disabled", wizard.next_button.state())

    def test_a_gross_slip_can_be_used_anyway(self):
        self.open_program()
        wizard = self.wizard
        self.touch_corners((25, -14))
        self.assertTrue(wizard.anyway_button.winfo_ismapped())
        window = self.program.window
        self.assertLessEqual(wizard.anyway_button.winfo_rooty() + wizard.anyway_button.winfo_height(),
                             window.winfo_rooty() + window.winfo_height(), "the button must be on screen")
        self.assertIn("disabled", wizard.next_button.state())
        wizard.use_anyway()
        self.pump(0.4)
        self.assertNotIn("disabled", wizard.next_button.state())
        self.assertFalse(wizard.anyway_button.winfo_ismapped())
        self.assertIn("⚠", wizard.status.get())
        self.program.setup_done = True
        self.program._check_setup()                           # the arm's own checks accept the choice
        wizard.accepted = False
        with self.assertRaises(ValueError):
            self.program._check_setup()
        wizard.accepted = True
        wizard.picked(outer_points(LAYOUT)[2])                # touching a corner again asks again
        self.touch(LAYOUT.positions[outer_points(LAYOUT)[2]])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: not self.program.busy))
        self.assertFalse(wizard.accepted or wizard.calibration.errors())

    def test_finishing_parks_the_arm_takes_a_second_look_and_reads_the_pieces(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertEqual(wizard.step, 5)
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy))
        rest = wizard.calibration.rest()
        self.assertAlmostEqual(self.dobot.pose[0], rest.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[1], rest.y, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[2], rest.z, delta=0.6)
        self.assertGreater(wizard.calibration.rest_gap()[0], 15, "the resting place is off the mat")
        self.assertGreaterEqual(float(np.hypot(rest.x, rest.y)), 137.9)
        self.assertTrue(self.pump(4, lambda: wizard.reference_waiting is None))
        self.current["frame"] = self.frames["game"]
        self.pump(1.6)
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.pump(0.3)
        self.assertIn("All 5 X and 5 O pieces are in place", wizard.status.get())
        wizard.next()
        self.assertTrue(program.setup_done)
        self.assertEqual(wizard.step, 6)
        self.assertEqual(program.poses, wizard.calibration.poses())
        self.assertEqual(program.status.get().startswith("Setup is finished"), True)

    def to_pieces(self):
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy and wizard.reference_waiting is None))

    def capture(self, contents, **options):
        self.current["frame"] = camera_view(contents, layout=LAYOUT, solid=True, **options)
        self.pump(1.6)
        self.wizard.capture_pieces()
        self.pump(0.3)

    def test_the_pieces_step_checks_only_the_two_banks_and_ignores_the_grid(self):
        self.open_program()
        wizard = self.wizard
        self.to_pieces()
        self.capture(BANKS)
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertEqual(wizard.grid_note, "")
        self.assertEqual(set(wizard.bank_report), {*(f"X{i}" for i in range(1, 6)), *(f"O{i}" for i in range(1, 6))})
        self.assertNotIn("disabled", wizard.next_button.state())
        # A smudge or a piece in the grid does not stop setup. It is only mentioned.
        self.capture({**BANKS, "C2": "?", "A1": X})
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertIn("A1", wizard.grid_note)
        self.assertIn("grid should be clear", wizard.text.get())

    def test_an_empty_bank_circle_is_named(self):
        self.open_program()
        wizard = self.wizard
        self.to_pieces()
        self.capture({name: mark for name, mark in BANKS.items() if name not in ("X2", "O5")})
        self.assertFalse(wizard.pieces_ok)
        self.assertEqual(wizard.bad_slots(), ["X2", "O5"])
        self.assertIn("X2 has no piece", wizard.status.get())
        self.assertIn("O5 has no piece", wizard.status.get())
        self.assertIn("disabled", wizard.next_button.state())
        self.assertEqual(wizard.target(), "X2")
        self.capture(BANKS)                                   # fixed
        self.assertTrue(wizard.pieces_ok)
        self.assertNotIn("disabled", wizard.next_button.state())

    def test_a_piece_of_the_other_mark_in_a_bank_is_mentioned_but_does_not_stop_the_setup(self):
        """What a piece is comes from the bank it is in. The camera only has to see that the circle is covered."""
        self.open_program()
        wizard = self.wizard
        self.to_pieces()
        self.capture({**BANKS, "X3": O, "O1": X})
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertEqual(wizard.bad_slots(), [])
        self.assertEqual(len(wizard.mark_notes), 2)
        self.assertIn("X3 looks like an O, but it is in the X bank", wizard.mark_notes)
        self.assertIn("Check: X3 looks like an O", wizard.text.get())
        self.assertNotIn("disabled", wizard.next_button.state())

    def test_a_piece_the_camera_cannot_make_out_is_still_a_piece_and_does_not_stop_the_setup(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        self.capture({**BANKS, "X4": "?"})
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertNotIn("disabled", wizard.next_button.state())

    def test_an_empty_circle_shows_it_now_and_when_empty(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        self.capture({name: mark for name, mark in BANKS.items() if name != "X4"})
        self.assertFalse(wizard.pieces_ok)
        self.assertIn("X4 has no piece", wizard.status.get())
        self.assertFalse(program.setup_done)
        self.pump(0.5)
        words = [program.preview.itemcget(item, "text") for item in program.preview.find_all()
                 if program.preview.type(item) == "text"]
        self.assertIn("X4 now", words)
        self.assertIn("X4 when empty", words)

    def test_the_banks_still_read_when_the_camera_changes_its_exposure_or_the_picture_shifts_a_little(self):
        self.open_program()
        wizard = self.wizard
        self.to_pieces()
        dim = camera_view(BANKS, layout=LAYOUT, solid=True)
        self.current["frame"] = np.clip(dim.astype(np.float32) * 0.7, 0, 255).astype(np.uint8)     # the camera dims itself
        self.pump(1.6)
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.current["frame"] = np.roll(camera_view(BANKS, layout=LAYOUT, solid=True), 1, axis=1)
        self.pump(1.6)
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, wizard.status.get())

    def test_the_overlay_is_only_drawn_on_the_screen_never_on_the_picture_the_camera_reads(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        self.current["frame"] = camera_view(BANKS, layout=LAYOUT, solid=True)
        self.pump(1.6)
        before = np.asarray(program.feed).copy()
        wizard.capture_pieces()
        program._draw_camera()
        self.assertTrue(np.array_equal(before, np.asarray(program.feed)))
        self.assertTrue(np.array_equal(before, self.current["frame"]))
        colours = {program.preview.itemcget(item, "outline") for item in program.preview.find_all()
                   if program.preview.type(item) == "oval"}
        self.assertIn("#8df0a8", colours, "the banks are marked green once they are right")

    # ---- Camera and pieces: only during setup
    def open_tune(self, listing=None):
        from tests.test_tune import LISTING, Recorder

        self.recorder = Recorder(LISTING if listing is None else listing)
        from dobot_studio.camera_tune import CameraControls

        with mock.patch("dobot_studio.tune_dialog.CameraControls", lambda device: CameraControls(device, self.recorder)):
            self.program.open_tune()
        self.dialog = self.program.tune_dialog
        self.pump(0.3)
        return self.dialog

    def test_the_camera_and_pieces_button_is_only_in_the_setup_steps(self):
        self.open_program()
        wizard = self.wizard
        self.pump(0.4)
        self.assertTrue(wizard.tune_button.winfo_ismapped())
        self.assertNotIn("disabled", wizard.tune_button.state())
        wizard.step = 5
        wizard._show_step()
        self.pump(0.3)
        self.assertTrue(wizard.tune_button.winfo_ismapped())
        wizard.step = 6                                          # ready to play
        wizard._show_step()
        self.pump(0.3)
        self.assertFalse(wizard.tune_button.winfo_ismapped())
        self.program.camera = None
        self.program.feed = None
        wizard.step = 0
        wizard._show_step()
        self.pump(0.3)
        self.assertIn("disabled", wizard.tune_button.state(), "no picture to adjust yet")

    def test_the_pi_reads_an_adjusted_picture_while_the_live_view_stays_the_cameras_own(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.pump(1.0)
        dialog = self.open_tune()
        raw = np.asarray(program.feed).copy()
        grey_before = program.found.grey.copy()
        dialog.variables["brightness"].set(60)
        dialog.variables["contrast"].set(2.0)
        self.pump(0.5)
        self.assertEqual((program.tune.brightness, program.tune.contrast), (60.0, 2.0))
        self.assertTrue(np.array_equal(np.asarray(program.feed), raw), "the live picture is never adjusted")
        self.assertFalse(np.array_equal(program.found.grey, grey_before), "what the Pi reads is")
        self.assertEqual(len(dialog.photos), 2)
        dialog.reset_tune()
        self.pump(0.4)
        self.assertTrue(program.tune.is_neutral())
        self.assertTrue(np.array_equal(program.found.grey, grey_before))

    def test_changing_the_adjustments_after_the_empty_mat_was_captured_keeps_the_setup(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()
        before = program.reference.grey.copy()
        dialog = self.open_tune()
        dialog.variables["gamma"].set(1.6)
        self.pump(0.5)
        self.assertIsNotNone(program.reference)
        self.assertFalse(np.array_equal(program.reference.grey, before), "the empty mat is seen through the same adjustment")
        self.assertFalse(program.camera_moved)
        wizard.next()                                            # setup carries on
        self.assertEqual(wizard.step, 2)

    def test_the_cameras_own_controls_are_listed_and_changed_from_the_dialog(self):
        self.open_program()
        dialog = self.open_tune()
        names = set(dialog.hardware)
        self.assertTrue({"auto_exposure", "exposure_time_absolute", "brightness", "focus_automatic_continuous"} <= names)
        self.assertTrue(dialog.hardware["auto_exposure"].get(), "automatic exposure is on to begin with")
        dialog.hardware["auto_exposure"].set(False)
        control = next(c for c in dialog.listed if c.name == "auto_exposure")
        dialog._toggle(control, dialog.hardware["auto_exposure"])
        self.assertEqual(self.recorder.calls[-1][-1], "auto_exposure=1")
        exposure = next(c for c in dialog.listed if c.name == "exposure_time_absolute")
        dialog.hardware["auto_exposure"].set(True)
        dialog.hardware["exposure_time_absolute"].set(321)
        label = tk.Label(dialog.window)
        dialog._slide(exposure, dialog.hardware["exposure_time_absolute"], label)
        sent = [call[-1] for call in self.recorder.calls if "--set-ctrl" in call][-2:]
        self.assertEqual(sent, ["auto_exposure=1", "exposure_time_absolute=321"], "hand-set exposure turns automatic exposure off first")
        self.assertFalse(dialog.hardware["auto_exposure"].get())

    def test_lock_stops_automatic_exposure_focus_and_colour(self):
        self.open_program()
        dialog = self.open_tune()
        self.recorder.calls.clear()
        dialog.lock_camera()
        sent = {call[-1] for call in self.recorder.calls if "--set-ctrl" in call}
        self.assertEqual(sent, {"auto_exposure=1", "focus_automatic_continuous=0", "white_balance_automatic=0"})
        self.assertIn("locked", dialog.message.get())

    def test_a_camera_that_cannot_be_controlled_says_why_and_the_pi_reading_still_works(self):
        from tests.test_tune import Recorder

        self.open_program()
        dialog = self.open_tune(listing="")
        self.assertEqual(dialog.hardware, {})
        dialog.variables["gamma"].set(1.4)                       # the software side does not need the camera's help
        self.pump(0.3)
        self.assertEqual(self.program.tune.gamma, 1.4)

    def test_teaching_the_pieces_from_the_mat_and_from_close_up(self):
        from tests.test_tune import disc_picture

        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        dialog = self.open_tune()
        # nothing on the mat to learn from
        self.current["frame"] = self.frames["empty"]
        self.pump(1.2)
        dialog.teach(X, "distance")
        self.assertIn("cannot see any pieces", dialog.message.get())
        self.assertEqual(program.learned.count(X), 0)
        # only X pieces on the mat
        self.current["frame"] = camera_view({f"X{i}": X for i in range(1, 6)}, layout=LAYOUT, solid=True)
        self.pump(1.2)
        for _ in range(3):
            dialog.teach(X, "distance")
        self.assertEqual(program.learned.count(X, "distance"), 3)
        self.assertIn("3 of 3", dialog.teach_buttons[(X, "distance")][0].cget("text"))
        self.assertIn("Learned from 5 X pieces", dialog.message.get())
        # a close-up needs a piece in the picture
        self.current["frame"] = np.full((480, 640, 3), 20, np.uint8)
        self.pump(0.6)
        dialog.teach(O, "close")
        self.assertIn("cannot find a piece", dialog.message.get())
        self.current["frame"] = disc_picture(O)
        self.pump(0.6)
        dialog.teach(O, "close")
        self.assertEqual(program.learned.count(O, "close"), 1)
        self.assertNotIn("disabled", dialog.forget_button.state())
        dialog.forget()
        self.assertFalse(program.learned.ready())
        self.assertIn("disabled", dialog.forget_button.state())

    def test_pieces_taught_are_used_to_read_marks_that_the_built_in_shapes_do_not_know(self):
        """Thicker crosses than the ideal one read as "?" until the camera has been shown them. Only the marks need that."""
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        import tests.test_tictactoe as fixture

        with mock.patch.object(fixture, "CROSS_HALF_WIDTH", 3.0):
            fat = camera_view({**{f"X{i}": X for i in range(1, 6)}}, layout=LAYOUT, solid=True)
            both = camera_view(BANKS, layout=LAYOUT, solid=True)
        self.current["frame"] = both
        self.pump(1.6)
        self.assertEqual(set(program.reading.reserve[:5]), {"?"}, "the fat crosses are not known to the built-in shapes")
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, "but they are pieces, and that is what the setup needs")
        self.current["frame"] = fat
        self.pump(1.2)
        program.teach_piece(X, "distance")
        self.current["frame"] = camera_view({f"O{i}": O for i in range(1, 6)}, layout=LAYOUT, solid=True)
        self.pump(1.2)
        program.teach_piece(O, "distance")
        self.current["frame"] = both
        self.pump(1.6)
        self.assertEqual(set(program.reading.reserve[:5]), {X})
        self.assertEqual(set(program.reading.reserve[5:]), {O})

    def test_the_dialog_closes_cleanly_and_the_program_window_gets_back_control(self):
        self.open_program()
        program = self.program
        dialog = self.open_tune()
        self.assertTrue(dialog.window.winfo_exists())
        dialog.close()
        self.pump(0.2)
        self.assertIsNone(program.tune_dialog)
        self.assertFalse(dialog.window.winfo_exists())
        self.assertTrue(program.window.winfo_exists())
        self.assertEqual(self.root.grab_current(), program.window)

    def test_the_arm_waits_off_the_mat_the_tour_ends_there_and_the_camera_looks_with_it_there(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not program.busy))
        rest = wizard.calibration.rest()
        self.assertAlmostEqual(self.dobot.pose[0], rest.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[2], rest.z, delta=0.6)
        self.assertIn("Rest", program.poses)
        self.assertEqual(program.poses["Rest"], rest)
        for name, pose in program.poses.items():
            if name not in ("Park", "Rest"):
                self.assertGreater(np.hypot(pose.x - rest.x, pose.y - rest.y), 25, f"the resting place is on {name}")

    def test_the_resting_place_can_be_nudged_and_the_camera_looks_again_with_the_arm_there(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        before = wizard.calibration.rest()
        wizard.move_step.set("10 mm")
        wizard.nudge_rest("left")
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy))
        after = wizard.calibration.rest()
        self.assertAlmostEqual(np.hypot(after.x - before.x, after.y - before.y), 10.0, delta=0.05)
        self.assertAlmostEqual(self.dobot.pose[0], after.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[1], after.y, delta=0.6)
        self.assertEqual(program.poses["Rest"], after)
        self.assertTrue(self.pump(4, lambda: wizard.reference_waiting is None))
        self.pump(0.4)
        self.assertIn("keep that area clear", wizard.text.get().lower())
        self.assertEqual(wizard.rest_shift, wizard.calibration.rest_shift)

    def test_the_arm_goes_up_before_it_goes_across_to_rest(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        rest = wizard.calibration.rest()
        low = wizard.calibration.pick("B2")
        self.dobot.pose = [low.x, low.y, low.z, low.r]            # the cup is down on a piece
        self.dobot.log.clear()
        self.studio.robot.to_rest(rest, program.abort)
        moves = [unpack("<B4f", params)[1:4] for command, _, params in self.dobot.log if command == R.MOVE]
        self.assertGreaterEqual(len(moves), 2)
        self.assertAlmostEqual(moves[0][0], low.x, delta=0.5)      # the first move is straight up
        self.assertAlmostEqual(moves[0][1], low.y, delta=0.5)
        self.assertAlmostEqual(moves[0][2], rest.z, delta=0.5)
        self.assertAlmostEqual(self.dobot.pose[0], rest.x, delta=0.6)
        self.dobot.log.clear()
        self.studio.robot.to_rest(rest, program.abort)             # already there: nothing to do
        self.assertEqual([c for c, _, _ in self.dobot.log if c == R.MOVE], [])

    def test_the_size_of_the_mat_in_the_picture_is_reported_and_advice_is_given_when_it_is_small(self):
        self.open_program()
        wizard = self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        self.pump(0.3)
        self.assertRegex(wizard.text.get(), r"The mat is \d\.\d pixels for every millimetre")
        self.assertIn("Move the camera closer", wizard.text.get())          # the test picture is 1.8 pixels per millimetre
        self.assertEqual(wizard.status_label.cget("fg"), "#8a5a00", "amber, because it is small")

    def test_the_dialog_shows_what_the_pi_sees_on_each_bank_circle_and_why_one_is_wrong(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        dialog = self.open_tune()
        dialog.tabs.select(dialog.pieces_tab)
        self.current["frame"] = camera_view({**BANKS, "X2": "?", "O3": None}, layout=LAYOUT, solid=True)
        self.pump(1.4)
        dialog.look_at_banks()
        words = [dialog.seen.itemcget(item, "text") for item in dialog.seen.find_all() if dialog.seen.type(item) == "text"]
        self.assertIn("X1: X", words)
        self.assertIn("X2: ?", words)
        self.assertIn("O3: empty", words)
        self.assertIn("O5: O", words)
        self.assertEqual(len(dialog.seen_photos), 10)
        colours = [dialog.seen.itemcget(item, "outline") for item in dialog.seen.find_all() if dialog.seen.type(item) == "rectangle"]
        from dobot_studio.theme import GREEN, RED

        self.assertEqual((colours.count(GREEN), colours.count(RED)), (8, 2), "right ones green, the two wrong ones red")
        dialog.watching.set(False)
        dialog.look_at_banks()
        self.assertEqual(dialog.seen.find_all(), ())

    def test_the_camera_and_pieces_window_fits_a_720p_screen(self):
        self.open_program()
        self.to_pieces()
        dialog = self.open_tune()
        for tab in (dialog.camera_tab, dialog.pieces_tab):
            dialog.tabs.select(tab)
            dialog.window.update_idletasks()
            self.pump(0.3)
            self.assertLessEqual(dialog.window.winfo_reqheight(), 660, "the dialog is too tall for a 1280 x 720 screen")
            self.assertTrue(dialog.close_button.winfo_ismapped())
            bottom = dialog.close_button.winfo_rooty() + dialog.close_button.winfo_height()
            self.assertLessEqual(bottom, dialog.window.winfo_rooty() + dialog.window.winfo_height())

    def test_paper_tokens_are_a_fraction_of_a_millimetre_thick_and_the_arm_follows(self):
        self.open_program()
        wizard = self.wizard
        self.walk_to_corners()
        wizard.next()
        before = wizard.calibration.pick("B2")
        wizard.paper_tokens()
        self.assertAlmostEqual(wizard.calibration.piece_height, 0.4, places=3)
        self.assertAlmostEqual(self.program.poses["B2"].z, before.z - (3.2 - 0.4), delta=0.05)
        for _ in range(10):
            wizard.change_thickness(-0.2)
        self.assertGreaterEqual(wizard.calibration.piece_height, 0.2)

    def test_coloured_tokens_are_taught_from_a_distance_and_colour_reads_them_when_the_marks_are_wiped_out(self):
        """A reflection wipes the marks out. Once the camera has learned the colours, each token still reads."""
        from tests.test_tune import COLOURS, PINK, YELLOW

        self.open_program()
        program, wizard = self.program, self.wizard
        self.to_pieces()
        dialog = self.open_tune()
        dialog.tabs.select(dialog.pieces_tab)
        # glare: every token's mark is gone, so nothing can be read from the marks
        glare = {**{f"X{i}": "blank" for i in range(1, 6)}, **{f"O{i}": "blank" for i in range(1, 6)}}
        self.current["frame"] = camera_view(glare, layout=LAYOUT, solid=True, colours={"blank": PINK})
        self.pump(1.6)
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, "every circle is covered, whatever the marks look like")
        self.assertEqual(set(program.reading.reserve), {"?"}, "but no mark can be made out")
        # teach the colours from a distance: only X tokens on the mat, then only O tokens
        self.current["frame"] = camera_view({f"X{i}": X for i in range(1, 6)}, layout=LAYOUT, solid=True, colours=COLOURS)
        self.pump(1.2)
        dialog.teach(X, "distance")
        self.assertIn("learned their colour", dialog.message.get().lower())
        self.current["frame"] = camera_view({f"O{i}": O for i in range(1, 6)}, layout=LAYOUT, solid=True, colours=COLOURS)
        self.pump(1.2)
        dialog.teach(O, "distance")
        self.assertIn("colour tells x from o", dialog.message.get().lower())
        self.assertTrue(program.learned.colours_ready())
        fills = {mark: dialog.swatches[mark].itemcget(dialog.swatches[mark].find_all()[0], "fill") for mark in (X, O)}
        self.assertNotEqual(fills[X], fills[O])
        self.assertTrue(all(fill.startswith("#") for fill in fills.values()))
        # the marks are still wiped out, each token carrying its own colour: now they read
        view_x = camera_view({f"X{i}": "blank" for i in range(1, 6)}, layout=LAYOUT, solid=True, colours={"blank": PINK})
        both = np.maximum(view_x, camera_view({f"O{i}": "blank" for i in range(1, 6)}, layout=LAYOUT, solid=True, colours={"blank": YELLOW}))
        self.current["frame"] = both
        self.pump(1.6)
        self.assertEqual(program.reading.reserve, (X,) * 5 + (O,) * 5, "now the colours say which is which")
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertEqual(wizard.mark_notes, [])
        self.pump(0.4)
        self.assertIn("All 5 X and 5 O pieces are in place", wizard.status.get())
        dialog.forget()
        self.assertFalse(program.learned.colours_ready())
        self.assertTrue(all(not dialog.swatches[mark].find_all() or dialog.swatches[mark].itemcget(dialog.swatches[mark].find_all()[0], "fill") == "" for mark in (X, O)))

    # ---- keeping the setup, going back into it, the pick depth and the speed
    def finish_everything(self):
        """Set up the whole mat and finish, as a person would, leaving the program ready for a game."""
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy and wizard.reference_waiting is None))
        self.current["frame"] = self.frames["banks"]
        self.pump(1.6)
        wizard.capture_pieces()
        wizard.next()
        self.assertTrue(program.setup_done)

    def test_the_setup_is_saved_by_itself_and_comes_back_after_a_restart(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.assertTrue(program.autosave_enabled, "nothing saved yet, so saving starts at once")
        self.finish_everything()
        wizard.change_thickness(0.4)
        wizard.change_pick(1.5)
        program.speed.set(150)
        wizard.nudge_rest("left")
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy))
        program.autosave(force=True)
        self.assertTrue(program.store.has())
        poses, height, reference = dict(program.poses), wizard.calibration.piece_height, program.reference.grey.copy()
        rest_shift = wizard.rest_shift
        saved_text = (program.store.folder / "latest" / "setup.json").read_text()
        program.close()
        self.assertFalse(program.window.winfo_exists())
        # the program is opened again, as after a restart or a crash
        self.open_program(connect=False)
        program, wizard = self.program, self.wizard
        self.assertFalse(program.autosave_enabled, "a saved setup is there, so it is not written over yet")
        self.assertFalse(program.autosave(force=True))
        self.assertEqual((program.store.folder / "latest" / "setup.json").read_text(), saved_text)
        self.pump(0.5)
        self.assertTrue(wizard.saved_banner.winfo_ismapped(), "the saved setup is offered")
        self.assertIn("minute" if "minute" in wizard.saved_text.get() else "moment", wizard.saved_text.get())
        wizard.use_saved()
        self.pump(0.5)
        self.assertTrue(program.setup_done)
        self.assertEqual(wizard.step, 6)
        self.assertEqual(program.poses, poses)
        self.assertAlmostEqual(wizard.calibration.piece_height, height)
        self.assertEqual(program.pick_press, 1.5)
        self.assertEqual(program.speed_percent, 150.0)
        self.assertEqual(wizard.rest_shift, rest_shift)
        self.assertTrue(np.array_equal(program.reference.grey, reference), "the empty mat the camera reads against is back")
        self.assertTrue(program.autosave_enabled)
        self.assertFalse(wizard.saved_banner.winfo_ismapped())
        self.assertEqual(wizard.status_label.cget("fg") != "", True)
        self.assertIn("must not have been moved", program.status.get())

    def test_a_new_setup_puts_the_saved_one_aside_instead_of_writing_over_it(self):
        self.open_program()
        self.finish_everything()
        self.program.autosave(force=True)
        store = self.program.store
        self.program.close()
        self.open_program(connect=False)
        program, wizard = self.program, self.wizard
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.capture()                                   # beginning again, without using the saved setup
        self.assertTrue(program.autosave_enabled)
        self.assertTrue(store.has("backup"), "the saved setup was kept")
        program.autosave(force=True)
        self.assertTrue(store.has("latest") and store.has("backup"))
        self.assertEqual(store.load("backup")[0]["setup_done"], True)
        self.assertFalse(store.load("latest")[0]["setup_done"])
        wizard.use_saved("backup")                          # and it can be brought back
        self.assertTrue(program.setup_done)

    def test_reset_keeps_the_saved_setup_aside_or_throws_it_away(self):
        for answer, kept in ((True, True), (False, False)):
            with self.subTest(answer=answer):
                self.current["frame"] = self.frames["empty"]
                self.open_program(connect=self.studio.robot is None)
                self.finish_everything()
                self.program.autosave(force=True)
                store = self.program.store
                store.discard("backup")
                with mock.patch.object(messagebox, "askyesnocancel", return_value=answer):
                    self.wizard.reset_setup()
                self.pump(1.0)
                self.assertFalse(store.has("latest"))
                self.assertEqual(store.has("backup"), kept)
                self.pump(1.5, lambda: self.studio.workcell is not None and self.studio.workcell is not self.program)
                new = self.studio.workcell
                self.assertIsNotNone(new, "the program is opened again, fresh")
                self.assertFalse(new.setup_done)
                self.assertTrue(new.autosave_enabled)
                new.close()
                self.pump(0.5)
        with mock.patch.object(messagebox, "askyesnocancel", return_value=None):          # cancel
            self.open_program(connect=self.studio.robot is None)
            self.program.autosave(force=True) if self.program.wizard.touched else None
            self.wizard.reset_setup()
            self.assertTrue(self.program.window.winfo_exists())

    def test_any_step_reached_can_be_gone_back_to_and_the_game_returned_to_without_setting_up_again(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.finish_everything()
        self.assertEqual(wizard.step, 6)
        wizard.jump(4)                                       # back to look at the points
        self.assertEqual(wizard.step, 4)
        self.assertTrue(program.setup_done, "going back changes nothing")
        wizard.selected = "B2"
        wizard.change_thickness(0.2)
        wizard.nudge_step.set("1 mm")
        wizard.change_pick(1.0)
        self.assertTrue(self.pump(30, lambda: not program.busy))
        self.assertTrue(program.setup_done, "thickness, nudges and pick depth do not need the setup done again")
        wizard.jump(5)
        self.assertEqual(wizard.step, 5)
        wizard.return_to_game()
        self.assertEqual(wizard.step, 6)
        self.assertEqual(self.program.side_tabs.select(), str(program.match_tab))
        # a step that was never reached cannot be jumped to, and a touch that matters does need the setup finished again
        self.pump(0.3)
        wizard.jump(3)
        self.assertEqual(wizard.step, 3)
        wizard.picked(outer_points(LAYOUT)[0])
        self.touch(LAYOUT.positions[outer_points(LAYOUT)[0]])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: not program.busy))
        self.assertFalse(program.setup_done, "a corner was touched again")
        wizard.return_to_game()
        self.assertNotEqual(wizard.step, 6, "not until it is finished again")

    def test_a_step_that_was_never_reached_is_not_jumped_to(self):
        self.open_program()
        wizard = self.wizard
        wizard.jump(4)
        self.assertEqual(wizard.step, 0)
        self.assertTrue(self.pump(3, lambda: wizard._ready_to_leave()))
        wizard.next()
        wizard.jump(0)
        self.assertEqual(wizard.step, 0)
        wizard.jump(1)
        self.assertEqual(wizard.step, 1)
        wizard.jump(5)
        self.assertEqual(wizard.step, 1)

    def test_the_pick_depth_is_changed_by_hand_kept_in_range_and_used_to_pick(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.finish_everything()
        for _ in range(40):
            wizard.change_pick(0.5)
        self.assertEqual(program.pick_press, 12.0)
        for _ in range(60):
            wizard.change_pick(-0.5)
        self.assertEqual(program.pick_press, -5.0)
        wizard.change_pick(5.0)
        wizard.change_pick(1.5)
        self.assertEqual(program.pick_press, 1.5)
        wizard.jump(4)
        self.pump(0.4)
        self.assertIn("+1.5 mm", wizard.pick_text.get())
        # the test pick goes down by that much more, holds the piece with suction, and puts it back
        slot = LAYOUT.bank(program.dobot)[0]
        pick = wizard.calibration.pick(slot)
        self.dobot.log.clear()
        wizard.test_pick()
        self.assertTrue(self.pump(60, lambda: not program.busy and self.dobot.log))
        self.assertTrue(self.pump(60, lambda: not program.busy))
        suction = [params[1] for command, _, params in self.dobot.log if command == R.SUCTION]
        self.assertEqual(suction, [1, 0], "suction went on and then off")
        lowest = min(unpack("<B4f", params)[3] for command, _, params in self.dobot.log if command == R.MOVE)
        self.assertAlmostEqual(lowest, pick.z - 1.5, delta=0.3)
        rest = wizard.calibration.rest()
        self.assertAlmostEqual(self.dobot.pose[0], rest.x, delta=0.6)
        self.assertIn("Test pick done", program.status.get())

    def test_the_arm_speed_is_set_on_a_slider_and_the_moves_follow_it(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.assertEqual(program.speeds(), (25.0, 60.0))
        program.speed.set(200)
        self.assertEqual(program.speeds(), (50.0, 120.0))
        program.speed.set(5)
        self.assertEqual(program.speeds(), (7.5, 18.0), "never slower than 30%")
        program.speed.set(200)
        self.assertEqual(program.speed_text.get(), "Arm speed 200%")
        self.walk_to_corners()
        wizard.next()
        self.dobot.log.clear()
        wizard.run_check()
        self.assertTrue(self.pump(90, lambda: wizard.checked and not program.busy))
        asked = {unpack("<4f", params)[0] for command, _, params in self.dobot.log if command == R.COORDINATE_SPEED}
        self.assertEqual(asked, {120.0}, "the tour moves at the quick speed for 200%")

    def test_the_arm_in_front_of_the_markers_does_not_disturb_the_setup(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy and wizard.reference_waiting is None))
        for marker in range(4):
            corner = ((120, 25), (555, 35), (540, 455), (100, 440))[marker]
            frame = cv2.rectangle(self.frames["banks"].copy(), (corner[0] - 40, corner[1] - 40), (corner[0] + 40, corner[1] + 40), (40, 44, 52), -1)
            self.current["frame"] = frame
            self.pump(1.0)
            self.assertIsNotNone(program.reference)
            self.assertIsNotNone(wizard.calibration)
            self.assertFalse(program.camera_moved)
        self.assertEqual(wizard.step, 5)

    def test_the_setup_is_never_saved_so_every_run_starts_again(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy and wizard.reference_waiting is None))
        self.current["frame"] = self.frames["banks"]
        self.pump(1.6)
        wizard.capture_pieces()
        wizard.next()
        self.assertTrue(program.setup_done)
        program.close()
        self.assertFalse(program.window.winfo_exists())
        self.assertFalse(hasattr(self.studio, "tictactoe_saved"))
        self.open_program(connect=False)
        self.assertFalse(self.program.setup_done)
        self.assertEqual(self.wizard.step, 0)
        self.assertIsNone(self.wizard.calibration)
        self.assertIsNone(self.program.reference)


if __name__ == "__main__":
    unittest.main()
