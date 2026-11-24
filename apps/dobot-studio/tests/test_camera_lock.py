"""The camera's view of the mat is locked at Capture empty mat. The arm passing the markers changes nothing."""
from dataclasses import replace
from pathlib import Path
from shutil import rmtree
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

from dobot_studio import tictactoe_program
from dobot_studio.robot import Pose
from dobot_studio.tictactoe import COMPACT_MAT, O, X
from tests.test_tictactoe import camera_view

needs_display = unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "needs a display")
LAYOUT = COMPACT_MAT
GAME = {"A1": X, "B2": O, "X2": X, "O3": O}


def blocked(image, marker=0, size=70):
    """The arm in front of one corner marker: a dark block over that corner of the picture."""
    out = image.copy()
    corners = ((120, 25), (555, 35), (540, 455), (100, 440))
    x, y = corners[marker]
    cv2.rectangle(out, (x - size // 2, y - size // 2), (x + size // 2, y + size // 2), (40, 44, 52), -1)
    return out


@needs_display
class CameraLockTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.app import Studio

        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.addCleanup(lambda: self.root.eval("foreach id [after info] {after cancel $id}"))
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        self.studio = Studio(self.root, Path("/nonexistent"), Path(folder))
        self.studio.set_mode(False)
        self.studio.homed = True
        patcher = mock.patch.object(messagebox, "askokcancel", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.empty = camera_view({}, layout=LAYOUT, solid=True)
        self.played = camera_view(GAME, layout=LAYOUT, solid=True)
        self.current = {"frame": self.empty}
        self.program = tictactoe_program.TicTacToeProgram(self.studio)
        self.addCleanup(lambda: self.program.window.winfo_exists() and self.program.window.destroy())
        self.program.camera = SimpleNamespace(
            read=lambda: (SimpleNamespace(timestamp=monotonic()), Image.fromarray(self.current["frame"])),
            close=lambda: None)
        self.pump(0.7)
        self.assertIsNotNone(self.program.rectified, "the markers were not found")
        self.program.capture_empty()
        self.assertIsNotNone(self.program.reference)
        self.program.poses.update({"A1": Pose(1, 2, 3, 0), "Park": Pose(4, 5, 6, 0)})   # stand-ins for a taught arm

    def pump(self, seconds):
        end = monotonic() + seconds
        while monotonic() < end:
            self.root.update()
            sleep(0.01)

    def show(self, frame, seconds=0.9):
        self.current["frame"] = frame
        self.pump(seconds)

    def test_the_arm_hiding_a_marker_does_not_lose_the_mat_or_the_pieces(self):
        for marker in range(4):
            with self.subTest(marker=marker):
                self.show(blocked(self.played, marker))
                self.assertIsNotNone(self.program.reference)
                self.assertEqual(set(self.program.poses), {"A1", "Park"})
                self.assertIsNotNone(self.program.latest, "the board stopped being read while a marker was hidden")
                self.assertEqual(self.program.latest.board[0], X)
                self.assertEqual(self.program.latest.board[4], O)
                self.assertFalse(self.program.camera_moved)
                self.assertNotIn("moved", self.program.camera_status.get().lower())

    def test_a_wrong_reading_of_a_marker_for_a_moment_is_ignored(self):
        real = tictactoe_program.rectify
        calls = {"n": 0}

        def wobble(rgb):
            view = real(rgb)
            calls["n"] += 1
            if 3 <= calls["n"] <= 12:          # a partly hidden marker read a few pixels out, for a while
                return replace(view, corners=view.corners + np.float32([[7, -5]] * 4))
            return view

        self.current["frame"] = self.played
        with mock.patch.object(tictactoe_program, "rectify", wobble):
            self.pump(3.0)
        self.assertGreater(calls["n"], 12)
        self.assertIsNotNone(self.program.reference)
        self.assertEqual(set(self.program.poses), {"A1", "Park"})
        self.assertFalse(self.program.camera_moved)

    def test_a_camera_that_really_moved_is_reported_but_the_arm_setup_is_kept(self):
        self.show(camera_view(GAME, layout=LAYOUT, solid=True, shift=35), seconds=5)
        self.assertTrue(self.program.camera_moved)
        self.assertIn("camera", self.program.camera_status.get().lower())
        self.assertIsNotNone(self.program.reference)
        self.assertEqual(set(self.program.poses), {"A1", "Park"})
        with self.assertRaises(ValueError) as caught:
            self.program._steady()
        self.assertIn("camera", str(caught.exception).lower())

    def test_putting_the_camera_back_clears_the_warning_and_a_new_capture_keeps_the_arm_setup(self):
        self.show(camera_view(GAME, layout=LAYOUT, solid=True, shift=35), seconds=5)
        self.assertTrue(self.program.camera_moved)
        self.show(self.played, seconds=1.5)
        self.assertFalse(self.program.camera_moved)
        # Or capture the empty mat again from where the camera now is.
        self.show(camera_view({}, layout=LAYOUT, solid=True, shift=35), seconds=1)
        self.program.capture_empty()
        self.assertFalse(self.program.camera_moved)
        self.assertEqual(set(self.program.poses), {"A1", "Park"}, "recapturing the empty mat must not undo the arm setup")


if __name__ == "__main__":
    unittest.main()
