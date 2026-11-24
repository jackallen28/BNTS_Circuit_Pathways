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

    def test_the_centre_and_one_corner_are_enough_when_the_camera_supplies_the_mirror(self):
        """Quick mode: two touches. The top-down camera fixes the mirror, and the mat is taken as flat."""
        for layout in (COMPACT_MAT, PAPER_MAT, A3_MAT):
            for corner in range(4):
                with self.subTest(layout.label, corner=corner):
                    truth = TruePlacement(layout, tilt=(0.0, 0.0))
                    everything = truth.touched()
                    name = outer_points(layout)[corner]
                    calibration = MatCalibration(layout, {PARK: everything[PARK], name: everything[name]})
                    self.assertTrue(calibration.quick)
                    self.assertEqual(calibration.errors(), [])
                    self.assertAlmostEqual(calibration.scale, truth.scale, places=3)
                    for other, point in layout.positions.items():
                        expected = truth.surface_pose(point)
                        pick = calibration.pick(other)
                        self.assertLess(np.hypot(pick.x - expected.x, pick.y - expected.y), 0.05)
                        self.assertAlmostEqual(pick.z, expected.z + PIECE_HEIGHT * layout.piece_scale, delta=0.01)

    def test_quick_mode_is_a_few_mm_out_when_the_touches_are_hand_guided(self):
        worst = 0.0
        truth = TruePlacement(COMPACT_MAT, tilt=(0.0, 0.0))
        for seed in range(200):
            touched = truth.touched(noise=1.0, seed=seed)
            calibration = MatCalibration(COMPACT_MAT, {PARK: touched[PARK], "X1": touched["X1"]})
            for name, point in COMPACT_MAT.positions.items():
                expected = truth.surface_pose(point)
                pick = calibration.pick(name)
                worst = max(worst, np.hypot(pick.x - expected.x, pick.y - expected.y))
        self.assertLess(worst, 8.0)       # measured: about 2 mm rms and 7 mm at worst for a 1 mm touch

    def test_more_touches_make_the_full_fit_and_a_line_of_touches_stays_quick(self):
        truth = TruePlacement(COMPACT_MAT)
        everything = truth.touched()
        corners = outer_points(COMPACT_MAT)
        everything_all = {name: truth.surface_pose(point) for name, point in COMPACT_MAT.positions.items()}
        down_one_side = MatCalibration(COMPACT_MAT, {name: everything_all[name] for name in ("X1", "X3", "X5")})
        self.assertTrue(down_one_side.quick)                                  # three touches in a line
        full = MatCalibration(COMPACT_MAT, {PARK: everything[PARK], **{c: everything[c] for c in corners}})
        self.assertFalse(full.quick)
        with self.assertRaises(ValueError):
            MatCalibration(COMPACT_MAT, {PARK: everything[PARK]})

    def test_the_mats_real_size_and_slope_are_measured(self):
        truth = TruePlacement(COMPACT_MAT, scale=0.985)
        calibration = MatCalibration(COMPACT_MAT, truth.touched(noise=0.05))
        self.assertAlmostEqual(calibration.scale, 0.985, places=2)
        self.assertAlmostEqual(calibration.tilt, np.degrees(np.hypot(0.004, 0.002)), delta=0.05)

    def test_a_mat_printed_far_too_small_or_on_a_slope_is_reported(self):
        small = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, scale=0.8).touched())
        self.assertTrue(any("printed size" in problem for problem in small.errors()))
        steep = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, tilt=(0.2, 0.0)).touched())
        self.assertTrue(any("slopes" in problem for problem in steep.errors()))

    def test_a_slightly_small_or_tilted_mat_is_only_a_warning(self):
        small = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, scale=0.92).touched())
        self.assertEqual(small.errors(), [])
        self.assertTrue(any("printed size" in problem for problem in small.warnings()))
        tilted = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, tilt=(0.07, 0.0)).touched())
        self.assertEqual(tilted.errors(), [])
        self.assertTrue(any("slopes" in problem for problem in tilted.warnings()))

    def test_one_badly_touched_point_is_named(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        bad = touched["O5"]
        touched["O5"] = Pose(bad.x + 25, bad.y - 14, bad.z, bad.r)
        calibration = MatCalibration(COMPACT_MAT, touched)
        self.assertEqual(calibration.worst[0], "O5")
        self.assertTrue(calibration.errors()[0].startswith("O5 is"))

    def test_a_small_miss_is_only_a_warning_and_does_not_stop_the_setup(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        bad = touched["O5"]
        touched["O5"] = Pose(bad.x + 7, bad.y - 4, bad.z, bad.r)         # a hand-guided miss of about 8 mm
        calibration = MatCalibration(COMPACT_MAT, touched)
        self.assertEqual(calibration.errors(), [])
        self.assertTrue(calibration.warnings()[0].startswith("O5 is"))
        self.assertEqual(calibration.problems(), calibration.warnings())

    def test_a_miss_of_a_few_millimetres_passes_quietly(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        bad = touched["O1"]
        touched["O1"] = Pose(bad.x + 2, bad.y - 1.5, bad.z, bad.r)
        calibration = MatCalibration(COMPACT_MAT, touched)
        self.assertEqual((calibration.errors(), calibration.warnings()), ([], []))

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

    def test_picking_and_placing_are_the_surface_plus_the_thickness_of_a_piece(self):
        """The arm is touched onto the surface, which is height zero. A piece adds its thickness."""
        for layout, thickness in ((COMPACT_MAT, 3.2), (PAPER_MAT, 3.2), (A3_MAT, 5.12)):
            with self.subTest(layout.label):
                truth = TruePlacement(layout, tilt=(0.0, 0.0), surface=-41.0)
                calibration = MatCalibration(layout, truth.touched())
                self.assertAlmostEqual(calibration.piece_height, thickness)
                for name in layout.positions:
                    self.assertAlmostEqual(calibration.pick(name).z, -41.0 + thickness, places=1)
                    self.assertAlmostEqual(calibration.hover(name).z, -41.0 + thickness + HOVER, places=1)
                self.assertAlmostEqual(calibration.park().z, -41.0 + thickness + CLEARANCE, places=1)

    def test_thicker_pieces_raise_every_height_by_the_same_amount_and_nothing_else(self):
        truth = TruePlacement(COMPACT_MAT, tilt=(0.0, 0.0))
        calibration = MatCalibration(COMPACT_MAT, truth.touched())
        before = calibration.poses()
        calibration.set_piece_height(5.0)
        for name, pose in calibration.poses().items():
            self.assertAlmostEqual(pose.z - before[name].z, 1.8, places=1, msg=name)
            self.assertEqual((pose.x, pose.y), (before[name].x, before[name].y))
        for bad in (0.5, 13):
            with self.assertRaises(ValueError):
                calibration.set_piece_height(bad)
        self.assertEqual(calibration.piece_height, 5.0)
        self.assertAlmostEqual(MatCalibration(COMPACT_MAT, truth.touched(), piece_height=4.1).piece_height, 4.1)

    def test_a_piece_is_set_down_at_the_height_it_was_picked_up(self):
        """Placing uses the same height as picking, so a piece held by its top lands with its underside on the mat."""
        level = TruePlacement(COMPACT_MAT, tilt=(0.0, 0.0))
        calibration = MatCalibration(COMPACT_MAT, level.touched())
        poses = calibration.poses()
        heights = {round(poses[name].z, 1) for name in COMPACT_MAT.positions}
        self.assertEqual(len(heights), 1, "on a level mat every pick and place height matches")
        # On a sloping mat each circle has its own height, because the arm measured the slope.
        sloped = MatCalibration(COMPACT_MAT, TruePlacement(COMPACT_MAT, tilt=(0.004, -0.002)).touched()).poses()
        self.assertGreater(len({round(sloped[name].z, 1) for name in COMPACT_MAT.positions}), 3)
        # sort_chip insists Park is 12 to 75 mm above both the pick and the drop pose.
        self.assertTrue(12 <= poses[PARK].z - poses["A1"].z <= 75 and 12 <= poses[PARK].z - poses["O5"].z <= 75)

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

    def test_at_least_two_points_are_needed(self):
        touched = TruePlacement(COMPACT_MAT).touched()
        with self.assertRaises(ValueError):
            MatCalibration(COMPACT_MAT, {"X1": touched["X1"]})
        self.assertTrue(MatCalibration(COMPACT_MAT, {name: touched[name] for name in ("X1", "O5")}).quick)


if __name__ == "__main__":
    unittest.main()
