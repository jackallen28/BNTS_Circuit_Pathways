"""The arm's map of the mat, worked out from a few touched points."""
from math import cos, radians, sin
from random import Random
import unittest

import numpy as np

from dobot_studio.matcalib import CLEARANCE, HOVER, MatCalibration, PARK, fit_plane, fit_similarity, outer_points
from dobot_studio.robot import Pose
from dobot_studio.tictactoe import A3_MAT, COMPACT_MAT, PAPER_MAT, PIECE_HEIGHT, STANDARD_MAT


class TruePlacement:
    """Where a mat really lies in the arm's coordinates. The camera and the layout do not know this."""

    def __init__(self, layout, angle=23, scale=0.985, offset=(215, -20), tilt=(0.004, -0.002), surface=-38.0, mirror=True):
        self.layout, self.scale, self.offset, self.tilt, self.surface = layout, scale, np.array(offset, float), tilt, surface
        a = radians(angle)
        self.rotation = np.array(((cos(a), -sin(a)), (sin(a), cos(a)))) @ (np.diag([1, -1]) if mirror else np.eye(2))

    def xy(self, point):
        centre = np.array((self.layout.width / 2, self.layout.height / 2))
        return self.scale * self.rotation @ (np.asarray(point, float) - centre) + self.offset

    def surface_pose(self, point, noise=0.0, rng=None, rotation=0.0):
        x, y = self.xy(point)
        if rng:
            x, y = x + rng.gauss(0, noise), y + rng.gauss(0, noise)
        return Pose(x, y, self.surface + self.tilt[0] * x + self.tilt[1] * y, rotation)

    def touched(self, noise=0.0, seed=1):
        rng = Random(seed)
        names = [*outer_points(self.layout), PARK]
        return {name: self.surface_pose(self.layout.park if name == PARK else self.layout.positions[name], noise, rng)
                for name in names}


class FitTests(unittest.TestCase):
    def test_a_rotated_scaled_and_mirrored_placement_is_recovered_exactly(self):
        for mirror in (True, False):
            with self.subTest(mirror=mirror):
                rng = np.random.default_rng(3)
                mat = rng.uniform(0, 200, (6, 2))
                angle = radians(41)
                truth = 0.97 * np.array(((cos(angle), -sin(angle)), (sin(angle), cos(angle)))) @ (np.diag([1, -1]) if mirror else np.eye(2))
                robot = mat @ truth.T + (300, -40)
                scale, linear, offset = fit_similarity(mat, robot)
                self.assertAlmostEqual(scale, 0.97, places=6)
                np.testing.assert_allclose(linear, truth, atol=1e-6)
                np.testing.assert_allclose(offset, (300, -40), atol=1e-6)

    def test_points_in_a_line_or_too_few_are_refused(self):
        with self.assertRaises(ValueError):
            fit_similarity([(0, 0), (1, 1)], [(0, 0), (2, 2)])
        with self.assertRaises(ValueError):
            fit_similarity([(0, 0), (1, 1), (2, 2)], [(0, 0), (2, 2), (4, 4)])

    def test_plane_fit_recovers_a_slope(self):
        points = [(x, y, 5 + 0.01 * x - 0.02 * y) for x, y in ((0, 0), (100, 0), (0, 100), (100, 100), (50, 30))]
        a, b, c = fit_plane(points)
        self.assertTrue(np.allclose((a, b, c), (0.01, -0.02, 5)))


class CalibrationTests(unittest.TestCase):
    def test_the_outer_points_are_the_four_corners_of_the_layout(self):
        self.assertEqual(outer_points(COMPACT_MAT), ["X1", "O1", "O5", "X5"])
        self.assertEqual(outer_points(A3_MAT), ["X1", "O1", "O5", "X5"])
        self.assertEqual(outer_points(PAPER_MAT), ["X1", "O1", "O5", "X5"])
        self.assertEqual(len(set(outer_points(STANDARD_MAT))), 4)

    def test_every_other_circle_is_found_from_only_the_outer_points_and_the_centre(self):
        for layout in (COMPACT_MAT, PAPER_MAT, A3_MAT, STANDARD_MAT):
            with self.subTest(layout.label):
                truth = TruePlacement(layout)
                calibration = MatCalibration(layout, truth.touched(noise=0.3))
                self.assertEqual(calibration.problems(), [])
                worst = 0.0
                for name, point in layout.positions.items():
                    expected = truth.surface_pose(point)
                    pick = calibration.pick(name)
                    worst = max(worst, np.hypot(pick.x - expected.x, pick.y - expected.y))
                    self.assertAlmostEqual(pick.z, expected.z + PIECE_HEIGHT * layout.piece_scale, delta=0.8)
                self.assertLess(worst, 1.0, "a derived circle is more than 1 mm from where it really is")

    def test_the_mats_real_size_and_slope_are_measured(self):
        truth = TruePlacement(COMPACT_MAT, scale=0.985)
        calibration = MatCalibration(COMPACT_MAT, truth.touched(noise=0.05))
        self.assertAlmostEqual(calibration.scale, 0.985, places=2)
        self.assertAlmostEqual(calibration.tilt, np.degrees(np.hypot(0.004, 0.002)), delta=0.05)

    def test_a_mat_printed_far_too_small_or_on_a_slope_is_reported(self):
        small = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, scale=0.9).touched())
        self.assertTrue(any("printed size" in problem for problem in small.problems()))
        steep = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, tilt=(0.1, 0.0)).touched())
        self.assertTrue(any("slopes" in problem for problem in steep.problems()))

    def test_one_badly_touched_point_is_named(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        bad = touched["O5"]
        touched["O5"] = Pose(bad.x + 7, bad.y - 4, bad.z, bad.r)
        calibration = MatCalibration(COMPACT_MAT, touched)
        self.assertEqual(calibration.worst[0], "O5")
        self.assertTrue(calibration.problems()[0].startswith("O5 is"))

    def test_heights_follow_the_surface_and_park_is_in_range(self):
        truth = TruePlacement(COMPACT_MAT)
        calibration = MatCalibration(COMPACT_MAT, truth.touched())
        poses = calibration.poses()
        self.assertEqual(set(poses), {*COMPACT_MAT.positions, PARK})
        for name in COMPACT_MAT.positions:
            self.assertAlmostEqual(calibration.hover(name).z - calibration.pick(name).z, HOVER)
            # Park must sit 12 to 75 mm above every pick pose, which sort_chip insists on.
            self.assertTrue(12 <= poses[PARK].z - poses[name].z <= 75, name)
        self.assertAlmostEqual(poses[PARK].z - calibration.pick(PARK).z, CLEARANCE)

    def test_a_hand_nudge_moves_one_point_and_stacks(self):
        calibration = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT).touched())
        before = calibration.pick("B2")
        calibration.adjust("B2", dx=1.0, dz=-0.5)
        calibration.adjust("B2", dx=0.5, dy=-1.0)
        after = calibration.pick("B2")
        self.assertAlmostEqual(after.x - before.x, 1.5, places=1)
        self.assertAlmostEqual(after.y - before.y, -1.0, places=1)
        self.assertAlmostEqual(after.z - before.z, -0.5, places=1)
        self.assertEqual(calibration.pick("B1"), MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT).touched()).pick("B1"))
        with self.assertRaises(KeyError):
            calibration.adjust("Z9", dx=1)

    def test_at_least_three_points_are_needed(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        with self.assertRaises(ValueError):
            MatCalibration(COMPACT_MAT, {name: touched[name] for name in ("X1", "O5")})


if __name__ == "__main__":
    unittest.main()
