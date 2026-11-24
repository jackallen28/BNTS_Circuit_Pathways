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
from dobot_studio.tictactoe import COMPACT_MAT, O, X
from tests.fake_dobot import FakeDobot
from tests.test_matcalib import TruePlacement
from tests.test_tictactoe import camera_view

needs_display = unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "needs a display")
LAYOUT = COMPACT_MAT
# Where the mat really is, as the arm would find out by touching it. The software is never told.
TRUTH = TruePlacement(LAYOUT, angle=90, scale=0.99, offset=(200, 0), tilt=(0.0008, -0.0005), surface=-38.0)
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
        if program is not None and program.window.winfo_exists():
            self.pump(8, lambda: not program.busy)
            program.window.destroy()
        if self.studio.robot:
            self.studio.robot.close()
            self.studio.robot = None
        self.dobot.close()

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
        self.assertEqual(set(derived), {*LAYOUT.positions, PARK})
        worst = max(np.hypot(derived[name].x - TRUTH.xy(point)[0], derived[name].y - TRUTH.xy(point)[1])
                    for name, point in LAYOUT.positions.items())
        self.assertLess(worst, 0.5, "a circle the arm was never touched on is more than 0.5 mm out")
        self.assertAlmostEqual(wizard.calibration.scale, 0.99, places=3)
        self.assertFalse(program.setup_done)
        wizard.next()
        self.assertEqual(wizard.step, 4)

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

    def test_a_badly_touched_corner_is_named_and_can_be_touched_again(self):
        self.open_program()
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
            if index == 2:
                self.dobot.pose[0] += 7
                self.dobot.pose[1] -= 4          # the cup slipped on the third corner
            wizard.save_corner()
            self.assertTrue(self.pump(5, lambda name=name: name in wizard.touched and not self.program.busy))
        self.assertTrue(wizard.calibration.problems())
        self.pump(0.4)
        self.assertIn(corners[2], wizard.status.get())
        self.assertIn("disabled", wizard.next_button.state())
        wizard.picked(corners[2])
        self.assertEqual(wizard.target(), corners[2])
        self.touch(LAYOUT.positions[corners[2]])
        wizard.save_corner()
        self.assertTrue(self.pump(5, lambda: not wizard.calibration.problems() and not self.program.busy))
        self.pump(0.4)
        self.assertNotIn("disabled", wizard.next_button.state())

    def test_finishing_parks_the_arm_takes_a_second_look_and_reads_the_pieces(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertEqual(wizard.step, 5)
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy))
        park = wizard.calibration.park()
        self.assertAlmostEqual(self.dobot.pose[0], park.x, delta=0.6)
        self.assertAlmostEqual(self.dobot.pose[2], park.z, delta=0.6)
        self.assertTrue(self.pump(4, lambda: wizard.reference_waiting is None))
        self.current["frame"] = self.frames["game"]
        self.pump(1.6)
        wizard.capture_pieces()
        self.assertTrue(wizard.pieces_ok, wizard.status.get())
        self.assertEqual(wizard.summary, (1, 1, 5, 5))
        self.pump(0.3)
        self.assertIn("I can see", wizard.status.get())
        wizard.next()
        self.assertTrue(program.setup_done)
        self.assertEqual(wizard.step, 6)
        self.assertEqual(program.poses, wizard.calibration.poses())
        self.assertEqual(program.status.get().startswith("Setup is finished"), True)

    def test_a_piece_the_camera_cannot_read_is_named_and_setup_will_not_finish(self):
        self.open_program()
        program, wizard = self.program, self.wizard
        self.walk_to_corners()
        wizard.next()
        wizard.checked = True
        wizard.next()
        self.assertTrue(self.pump(30, lambda: wizard.parked and not program.busy and wizard.reference_waiting is None))
        smudged = camera_view({**BANKS, "C2": "?"}, layout=LAYOUT, solid=True)
        self.current["frame"] = smudged
        self.pump(1.6)
        wizard.capture_pieces()
        self.pump(0.3)
        self.assertFalse(wizard.pieces_ok)
        self.assertIn("C2", wizard.status.get())
        self.assertIn("disabled", wizard.next_button.state())
        self.assertFalse(program.setup_done)

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

    def test_reopening_tic_tac_toe_keeps_the_setup_because_the_mat_has_not_moved(self):
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
        saved = dict(program.poses)
        program.close()
        self.assertFalse(program.window.winfo_exists())
        self.open_program(connect=False)
        self.assertTrue(self.program.setup_done)
        self.assertEqual(self.wizard.step, 6)
        self.assertEqual(self.program.poses, saved)
        self.assertIsNotNone(self.program.reference)


if __name__ == "__main__":
    unittest.main()
