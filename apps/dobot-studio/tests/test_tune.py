"""Camera adjustments, the camera's own controls, and teaching the camera the X and O pieces."""
from unittest import mock
from types import SimpleNamespace
import subprocess
import unittest

import cv2
import numpy as np

import tests.test_tictactoe as fixture
from dobot_studio import camera_tune
from dobot_studio.camera_tune import (
    CameraControls, Tune, apply, device_path, interesting, parse_controls,
)
from dobot_studio.pieces import CAP, Learned, closeup_mark, diverse, mat_marks
from dobot_studio.tictactoe import NOUGHT_INNER, NOUGHT_OUTER, O, PIECE_RADIUS, SMALL_MAT, X
from dobot_studio.tictactoe_vision import lock_view, read_position, rectify, retuned
from tests.test_tictactoe import camera_view

LISTING = """
User Controls

                     brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=0
                       contrast 0x00980901 (int)    : min=0 max=64 step=1 default=32 value=32
                     saturation 0x00980902 (int)    : min=0 max=128 step=1 default=64 value=64
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
                           gain 0x00980913 (int)    : min=0 max=100 step=1 default=0 value=0
           white_balance_temperature 0x0098091a (int)    : min=2800 max=6500 step=1 default=4600 value=4600 flags=inactive

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3 (Aperture Priority Mode)
         exposure_time_absolute 0x009a0902 (int)    : min=1 max=5000 step=1 default=157 value=157 flags=inactive
     focus_automatic_continuous 0x009a090c (bool)   : default=1 value=1
                 focus_absolute 0x009a090a (int)    : min=0 max=250 step=5 default=0 value=0 flags=inactive
"""


class Recorder:
    def __init__(self, output=LISTING, returncode=0, error=None):
        self.calls, self.output, self.returncode, self.error = [], output, returncode, error

    def __call__(self, command, **options):
        self.calls.append(command)
        if self.error:
            raise self.error
        return SimpleNamespace(returncode=self.returncode, stdout=self.output, stderr="" if not self.returncode else "VIDIOC_S_CTRL: failed")


class TuneTests(unittest.TestCase):
    def setUp(self):
        self.grey = np.tile(np.arange(0, 256, 16, dtype=np.uint8)[:, None], (1, 16))
        self.image = np.dstack([self.grey] * 3)

    def test_neutral_changes_nothing_and_never_changes_its_input(self):
        self.assertIs(apply(self.image, Tune()), self.image)
        before = self.image.copy()
        for tune in (Tune(brightness=30), Tune(contrast=2), Tune(gamma=1.8), Tune(sharpen=2)):
            apply(self.image, tune)
        self.assertTrue(np.array_equal(self.image, before))

    def test_each_adjustment_does_what_its_name_says(self):
        middle = np.full((8, 8, 3), 128, np.uint8)
        self.assertGreater(apply(middle, Tune(brightness=40))[0, 0, 0], 128)
        self.assertLess(apply(middle, Tune(brightness=-40))[0, 0, 0], 128)
        spread = apply(self.image, Tune(contrast=2)).astype(int)
        self.assertGreater(spread.max() - spread.min(), int(self.image.max()) - int(self.image.min()) - 1)
        self.assertLess(apply(self.image, Tune(contrast=0.5)).std(), self.image.std())
        shadows = np.full((8, 8, 3), 50, np.uint8)
        self.assertGreater(apply(shadows, Tune(gamma=1.8))[0, 0, 0], 50)
        self.assertLess(apply(shadows, Tune(gamma=0.6))[0, 0, 0], 50)
        edge = np.zeros((32, 32, 3), np.uint8)
        edge[:, 16:] = 200
        sharp = apply(edge, Tune(sharpen=2)).astype(int)
        self.assertGreater(sharp.max(), 200)                    # an edge overshoots, which is what sharpening is
        self.assertEqual(apply(self.image, Tune(sharpen=1)).shape, self.image.shape)

    def test_values_are_kept_to_sensible_limits(self):
        tune = Tune(brightness=900, contrast=0, gamma=99, sharpen=-4).clamped()
        self.assertEqual((tune.brightness, tune.contrast, tune.gamma, tune.sharpen), (100.0, 0.5, 2.5, 0.0))
        self.assertTrue(apply(self.image, Tune(brightness=900, contrast=0, gamma=99)).dtype == np.uint8)

    def test_a_washed_out_picture_reads_with_more_contrast_and_not_without(self):
        contents = {"A1": X, "B2": O, "C3": X, "X1": X, "X2": O, "O1": O, "O2": X}

        def washed(image):
            return (128 + (image.astype(np.float32) - 128) * 0.12).clip(0, 255).astype(np.uint8)

        empty = washed(camera_view({}, layout=SMALL_MAT, solid=True))
        played = washed(camera_view(contents, layout=SMALL_MAT, solid=True))

        def wrong(tune):
            base = rectify(empty, tune)
            view = lock_view(played, base, tune)
            position = read_position(view.grey, base.grey, SMALL_MAT)
            return sum(mark != contents.get(name, "") for name, mark in zip(SMALL_MAT.positions, (*position.board, *position.reserve)))

        self.assertGreater(wrong(None), 0)
        self.assertEqual(wrong(Tune(contrast=2.5)), 0)

    def test_a_view_can_be_looked_at_again_through_new_adjustments_without_a_new_picture(self):
        frame = camera_view({}, layout=SMALL_MAT, solid=True)
        view = rectify(frame)
        self.assertTrue(np.array_equal(view.source, frame))
        again = retuned(view, Tune(brightness=50))
        self.assertGreater(again.grey.mean(), view.grey.mean())
        self.assertTrue(np.array_equal(again.matrix, view.matrix))
        self.assertTrue(np.array_equal(retuned(again, Tune()).grey, view.grey))
        self.assertIsNone(retuned(None, Tune()))


class ControlsTests(unittest.TestCase):
    def test_the_listing_is_read(self):
        controls = {control.name: control for control in parse_controls(LISTING)}
        self.assertEqual(controls["brightness"].minimum, -64)
        self.assertEqual(controls["contrast"].default, 32)
        self.assertEqual(controls["focus_absolute"].step, 5)
        self.assertTrue(controls["exposure_time_absolute"].inactive)
        self.assertFalse(controls["gain"].inactive)
        self.assertEqual(controls["white_balance_automatic"].kind, "bool")
        self.assertEqual(controls["auto_exposure"].kind, "menu")
        self.assertEqual(controls["exposure_time_absolute"].label, "Exposure")
        self.assertEqual(controls["auto_exposure"].label, "Automatic exposure")

    def test_the_useful_controls_come_in_a_sensible_order(self):
        names = [control.name for control in interesting(parse_controls(LISTING))]
        self.assertLess(names.index("auto_exposure"), names.index("exposure_time_absolute"))
        self.assertLess(names.index("exposure_time_absolute"), names.index("brightness"))
        self.assertIn("focus_absolute", names)

    def test_a_device_may_be_a_number_or_a_path(self):
        self.assertEqual(device_path("0"), "/dev/video0")
        self.assertEqual(device_path(" 2 "), "/dev/video2")
        self.assertEqual(device_path("/dev/video4"), "/dev/video4")

    def test_controls_are_listed_and_set_through_v4l2_ctl(self):
        run = Recorder()
        controls = CameraControls("0", run)
        listed = controls.list()
        self.assertEqual(run.calls[0], ["v4l2-ctl", "-d", "/dev/video0", "--list-ctrls"])
        self.assertTrue(controls.set("exposure_time_absolute", 120.0))
        self.assertEqual(run.calls[-1], ["v4l2-ctl", "-d", "/dev/video0", "--set-ctrl", "exposure_time_absolute=120"])
        self.assertTrue(controls.set_auto_exposure(False, listed))
        self.assertEqual(run.calls[-1][-1], "auto_exposure=1")
        self.assertTrue(controls.set_auto_exposure(True, listed))
        self.assertEqual(run.calls[-1][-1], "auto_exposure=3")

    def test_a_missing_tool_or_a_refused_setting_says_so_plainly(self):
        missing = CameraControls("0", Recorder(error=FileNotFoundError()))
        self.assertEqual(missing.list(), [])
        self.assertIn("sudo apt install v4l-utils", missing.problem)
        refused = CameraControls("0", Recorder(returncode=1))
        self.assertFalse(refused.set("gain", 5))
        self.assertIn("failed", refused.problem)
        slow = CameraControls("0", Recorder(error=subprocess.TimeoutExpired("v4l2-ctl", 8)))
        self.assertEqual(slow.list(), [])
        self.assertIn("did not answer", slow.problem)


def disc_picture(mark, rotation=24, pixels=8, background=(15, 15, 15)):
    """A close-up: a light piece with its mark, on a dark surface."""
    image = np.full((480, 640, 3), background, np.uint8)
    cx, cy = 320, 240
    cv2.circle(image, (cx, cy), round(PIECE_RADIUS * pixels), (230, 233, 225), -1, cv2.LINE_AA)
    if mark == O:
        cv2.circle(image, (cx, cy), round(NOUGHT_OUTER * pixels), (23, 29, 34), -1, cv2.LINE_AA)
        cv2.circle(image, (cx, cy), round(NOUGHT_INNER * pixels), (230, 233, 225), -1, cv2.LINE_AA)
    else:
        for sign in (-1, 1):
            theta = np.radians(rotation + sign * 45)
            vx, vy = np.cos(theta), np.sin(theta)
            wx, wy = -vy, vx
            half_length, half_width = fixture.CROSS_HALF_LENGTH, fixture.CROSS_HALF_WIDTH
            corners = [(round(cx + (vx * u * half_length + wx * v * half_width) * pixels),
                        round(cy + (vy * u * half_length + wy * v * half_width) * pixels)) for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cv2.fillConvexPoly(image, np.asarray(corners), (23, 29, 34), cv2.LINE_AA)
    return image


class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True))

    def mat(self, contents, **options):
        return rectify(camera_view(contents, layout=SMALL_MAT, solid=True, **options))

    def test_a_close_up_gives_the_shape_of_the_mark_at_any_size_and_place(self):
        x, o = closeup_mark(disc_picture(X)), closeup_mark(disc_picture(O))
        self.assertGreater(x.sum(), 800)
        self.assertGreater(o.sum(), 800)
        self.assertLess((x & o).sum() / (x | o).sum(), 0.4, "an X and an O are different shapes")
        near = closeup_mark(disc_picture(X, pixels=5))
        self.assertGreater((x & near).sum() / (x | near).sum(), 0.8, "the same piece at another distance gives the same shape")
        self.assertIsNone(closeup_mark(np.full((480, 640, 3), 20, np.uint8)), "there is no piece in an empty picture")

    def test_a_view_of_the_mat_gives_the_marks_of_each_piece_on_it(self):
        self.assertEqual(mat_marks(self.mat({}), self.empty, SMALL_MAT), [])
        masks = mat_marks(self.mat({f"X{i}": X for i in range(1, 6)}), self.empty, SMALL_MAT)
        self.assertEqual(len(masks), 5)

    def test_teaching_makes_a_piece_the_built_in_shapes_do_not_know_readable(self):
        game = {"A1": X, "B2": X, "C3": X, "X1": X, "X2": X, "O1": O, "O2": O}
        with mock.patch.object(fixture, "CROSS_HALF_WIDTH", 3.0):          # fat crosses, much thicker than the ideal
            fat_x = self.mat({f"X{i}": X for i in range(1, 6)})
            played = self.mat(game)
        noughts = self.mat({f"O{i}": O for i in range(1, 6)})
        plain = read_position(played.grey, self.empty.grey, SMALL_MAT)
        self.assertIn("?", plain.board + plain.reserve, "the built-in reading does not know these crosses")
        learned = Learned()
        learned.add(X, mat_marks(fat_x, self.empty, SMALL_MAT), "distance")
        learned.add(O, mat_marks(noughts, self.empty, SMALL_MAT), "distance")
        taught = read_position(played.grey, self.empty.grey, SMALL_MAT, learned)
        self.assertEqual(taught.board[0], X)
        self.assertEqual(taught.board[4], X)
        self.assertEqual(taught.board[8], X)
        self.assertEqual(taught.reserve[:2], (X, X))
        self.assertEqual(taught.reserve[5:7], (O, O))
        self.assertEqual(learned.warnings(), [])

    def test_teaching_never_changes_a_reading_that_already_works(self):
        game = {"A1": X, "B2": O, "C3": X, "X1": X, "X2": X, "O1": O, "O2": O}
        view = self.mat(game)
        learned = Learned()
        learned.add(X, [closeup_mark(disc_picture(X))], "close")
        learned.add(O, [closeup_mark(disc_picture(O))], "close")
        self.assertEqual(read_position(view.grey, self.empty.grey, SMALL_MAT, learned),
                         read_position(view.grey, self.empty.grey, SMALL_MAT))

    def test_the_other_mark_is_still_told_apart_after_teaching(self):
        learned = Learned()
        learned.add(X, [closeup_mark(disc_picture(X))], "close")
        learned.add(O, [closeup_mark(disc_picture(O))], "close")
        view = self.mat({"A1": O, "A2": X, "X1": O, "O1": X})
        position = read_position(view.grey, self.empty.grey, SMALL_MAT, learned)
        self.assertEqual((position.board[0], position.board[1], position.reserve[0], position.reserve[5]), (O, X, O, X))

    def test_an_x_and_an_o_that_look_alike_are_flagged(self):
        learned = Learned()
        mask = closeup_mark(disc_picture(O))
        learned.add(X, [mask], "close")
        learned.add(O, [mask], "close")
        self.assertTrue(learned.warnings())

    def test_pictures_are_counted_shapes_are_capped_and_everything_can_be_forgotten(self):
        learned = Learned()
        mask = closeup_mark(disc_picture(X))
        for _ in range(5):
            learned.add(X, [mask], "close")
        self.assertEqual(learned.count(X, "close"), 5)
        self.assertEqual(sum(1 for _, kind in learned.shapes[X] if kind == "close"), CAP["close"])
        self.assertEqual(learned.summary()[X], {"close": 5, "distance": 0})
        self.assertTrue(learned.ready())
        self.assertFalse(learned.has(O))
        learned.clear()
        self.assertFalse(learned.ready())
        self.assertEqual(learned.count(X), 0)
        with self.assertRaises(ValueError):
            learned.add("Z", [mask], "close")
        with self.assertRaises(ValueError):
            learned.add(X, [mask], "far")

    def test_a_picture_of_many_pieces_teaches_the_most_different_few(self):
        masks = [np.pad(np.ones((k, k), bool), 20) for k in range(3, 14)]
        chosen = diverse(masks)
        self.assertEqual(len(chosen), 3)
        sizes = sorted(int(mask.sum()) for mask in chosen)
        self.assertEqual(sizes[0], 9)
        self.assertEqual(sizes[-1], 169)


if __name__ == "__main__":
    unittest.main()
