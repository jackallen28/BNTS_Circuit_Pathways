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
from dobot_studio.pieces import CAP, Learned, MIN_SEPARATION, closeup_mark, colour_distance, diverse, mat_marks, mat_pieces
from dobot_studio.tictactoe import COMPACT_MAT, NOUGHT_INNER, NOUGHT_OUTER, O, PIECE_RADIUS, SMALL_MAT, X
from dobot_studio.tictactoe_vision import _patch_colour, body_colour, lock_view, read_position, rectify, retuned
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


PINK, YELLOW = (240, 100, 150), (250, 220, 60)           # the X and O tokens, as in a typical coloured set
COLOURS = {X: PINK, O: YELLOW, "blank": PINK}


class ColourTests(unittest.TestCase):
    """Tokens of different colours: the camera learns the colours from a distance and tells X from O by them too."""

    def setUp(self):
        self.empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True, colours=COLOURS))

    def mat(self, contents, **options):
        return rectify(camera_view(contents, layout=SMALL_MAT, solid=True, colours=COLOURS, **options))

    def taught(self):
        learned = Learned()
        learned.add(X, [], "distance", [lab for _, lab in mat_pieces(self.mat({f"X{i}": X for i in range(1, 6)}), self.empty, SMALL_MAT)])
        learned.add(O, [], "distance", [lab for _, lab in mat_pieces(self.mat({f"O{i}": O for i in range(1, 6)}), self.empty, SMALL_MAT)])
        return learned

    def read(self, view, learned):
        position = read_position(view.grey, self.empty.grey, SMALL_MAT, learned, view.colour)
        return dict(zip(SMALL_MAT.positions, (*position.board, *position.reserve)))

    def test_a_pieces_colour_is_the_same_whatever_the_camera_does_to_the_whole_picture(self):
        view = self.mat({"X1": X})
        centre = SMALL_MAT.positions["X1"]
        plain, _ = body_colour(_patch_colour(view.colour, centre, 1.0))
        for name, change in {"dimmed": lambda c: (c * 0.6).astype(np.uint8),
                             "warm": lambda c: np.clip(c * np.array([1.1, 1.0, 0.8]), 0, 255).astype(np.uint8),
                             "brighter": lambda c: np.clip(c * 1.1, 0, 255).astype(np.uint8)}.items():
            with self.subTest(name):
                other, _ = body_colour(_patch_colour(change(view.colour), centre, 1.0))
                self.assertLess(colour_distance(plain, other), 8.0)
        x, o = (body_colour(_patch_colour(self.mat({f"{m}1": m}).colour, SMALL_MAT.positions[f"{m}1"], 1.0))[0] for m in (X, O))
        self.assertGreater(colour_distance(x, o), 40, "pink and yellow are a long way apart")

    def test_teaching_from_a_distance_learns_the_colour_of_each_mark(self):
        learned = self.taught()
        self.assertTrue(learned.colours_ready())
        self.assertGreater(learned.separation(), MIN_SEPARATION)
        self.assertEqual(len(learned.colours[X]), 5)
        self.assertEqual(learned.warnings(), [])
        pink = body_colour(_patch_colour(self.mat({"A1": X}).colour, SMALL_MAT.positions["A1"], 1.0))[0]
        yellow = body_colour(_patch_colour(self.mat({"A1": O}).colour, SMALL_MAT.positions["A1"], 1.0))[0]
        self.assertEqual((learned.colour_vote(pink), learned.colour_vote(yellow)), (X, O))
        grey = np.array((70.0, 0.0, 0.0), np.float32)
        self.assertIsNone(learned.colour_vote(grey), "a colour that is neither is not guessed")

    def test_colour_reads_a_piece_whose_mark_cannot_be_made_out(self):
        """A reflection wipes the marks out. Without colours they are a question mark. With them the colour decides."""
        contents = {"A1": "blank", "B2": "blank", "X1": "blank", "O1": "blank"}
        view = self.mat(contents)
        without = self.read(view, Learned())
        self.assertEqual({without[name] for name in contents}, {"?"})
        learned = self.taught()
        view = rectify(camera_view({"A1": "blank", "B2": "blank", "X1": "blank", "O1": "blank"}, layout=SMALL_MAT, solid=True,
                                   colours={**COLOURS, "blank": PINK}))
        got = self.read(view, learned)
        self.assertEqual({got[name] for name in contents}, {X}, "every blank pink piece reads as an X by its colour")
        yellow_view = rectify(camera_view({"A1": "blank", "X1": "blank"}, layout=SMALL_MAT, solid=True,
                                          colours={**COLOURS, "blank": YELLOW}))
        got = self.read(yellow_view, learned)
        self.assertEqual({got["A1"], got["X1"]}, {O})

    def test_a_mark_that_disagrees_with_the_colour_is_flagged_not_trusted(self):
        learned = self.taught()
        wrong = rectify(camera_view({"A1": O}, layout=SMALL_MAT, solid=True, colours={**COLOURS, O: PINK}))
        got = self.read(wrong, learned)
        self.assertEqual(got["A1"], "?", "a nought mark on a pink (cross) piece")
        from dobot_studio.tictactoe_vision import look
        _, why, report = look(wrong.grey, self.empty.grey, SMALL_MAT, "A1", learned, wrong.colour)
        self.assertIn("looks like an O but the piece's colour is that of an X", why)
        self.assertEqual(report["colour_vote"], X)

    def test_colour_does_not_change_what_already_reads_and_is_not_used_when_colours_are_alike(self):
        learned = self.taught()
        game = {"A1": X, "B2": O, "C3": X, "X1": X, "O1": O}
        view = self.mat(game)
        self.assertEqual(self.read(view, learned), self.read(view, Learned()))
        alike = Learned()
        for mark, colour in ((X, PINK), (O, (236, 104, 150))):
            moved = rectify(camera_view({f"{mark}1": mark}, layout=SMALL_MAT, solid=True, colours={mark: colour}))
            alike.add(mark, [], "distance", [lab for _, lab in mat_pieces(moved, self.empty, SMALL_MAT)])
        self.assertFalse(alike.colours_ready())
        self.assertTrue(any("too alike in colour" in warning for warning in alike.warnings()))
        self.assertIsNone(alike.colour_vote(np.array((60.0, 50.0, 0.0), np.float32)))

    def test_pieces_of_a_mark_that_are_not_all_one_colour_are_flagged(self):
        learned = Learned()
        learned.add(X, [], "distance", [np.array((60.0, 60.0, 0.0), np.float32), np.array((60.0, -60.0, 0.0), np.float32)])
        learned.add(O, [], "distance", [np.array((90.0, -5.0, 70.0), np.float32)])
        self.assertTrue(any("not all one colour" in warning for warning in learned.warnings()))

    def test_forgetting_forgets_the_colours_too(self):
        learned = self.taught()
        learned.clear()
        self.assertFalse(learned.colours_ready())
        self.assertEqual(learned.colours, {X: [], O: []})

    def test_pieces_are_found_with_their_colour_even_when_the_mark_does_not_show(self):
        pieces = mat_pieces(self.mat({"A1": "blank", "B2": X}), self.empty, SMALL_MAT)
        self.assertEqual(len(pieces), 2)
        self.assertEqual(sum(mask is None for mask, _ in pieces), 1)


class OffCentreTests(unittest.TestCase):
    """A piece is never exactly on the middle of its circle. Pieces 3 mm off made every X "?" until the reading learned to look."""

    CONTENTS = {**{f"X{i}": X for i in range(1, 6)}, **{f"O{i}": O for i in range(1, 6)}, "A1": X, "B2": O, "C3": X, "B1": O, "A3": X}

    def offsets(self, millimetres, seed):
        rng = np.random.default_rng(seed)
        return {name: (millimetres * np.cos(angle), millimetres * np.sin(angle))
                for name, angle in ((name, rng.uniform(0, 2 * np.pi)) for name in self.CONTENTS)}

    def wrong(self, millimetres, seed=0, change=lambda grey: grey, layout=SMALL_MAT):
        empty = rectify(camera_view({}, layout=layout, solid=True))
        view = rectify(camera_view(self.CONTENTS, layout=layout, solid=True, offsets=self.offsets(millimetres, seed)))
        position = read_position(change(view.grey), empty.grey, layout)
        names = (*layout.positions,)
        return {name: mark for name, mark in zip(names, (*position.board, *position.reserve)) if mark != self.CONTENTS.get(name, "")}

    def test_pieces_up_to_5_mm_off_the_middle_of_their_circle_read(self):
        for layout in (SMALL_MAT, COMPACT_MAT):
            for millimetres in (0, 1.5, 3, 4, 5):
                for seed in range(3):
                    with self.subTest(layout=layout.label, millimetres=millimetres, seed=seed):
                        self.assertEqual(self.wrong(millimetres, seed, layout=layout), {})

    def test_off_the_middle_and_soft_and_dim_at_once(self):
        def change(grey):
            return cv2.GaussianBlur(np.clip(grey * 0.7, 0, 255).astype(np.uint8), (0, 0), 1.5)

        for millimetres in (3, 4):
            with self.subTest(millimetres=millimetres):
                self.assertEqual(self.wrong(millimetres, 1, change), {})

    def test_an_empty_circle_is_still_empty_when_the_picture_has_slipped(self):
        empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        view = rectify(camera_view({"A1": X}, layout=SMALL_MAT, solid=True))
        position = read_position(np.roll(view.grey, 4, axis=1), empty.grey, SMALL_MAT)
        got = dict(zip(SMALL_MAT.positions, (*position.board, *position.reserve)))
        self.assertEqual({name: mark for name, mark in got.items() if mark}, {"A1": X})

    def test_the_mark_taught_from_an_off_centre_piece_is_centred(self):
        empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        view = rectify(camera_view({"X3": X}, layout=SMALL_MAT, solid=True, offsets={"X3": (3.0, -2.0)}))
        (mask, _), = mat_pieces(view, empty, SMALL_MAT)
        ys, xs = np.nonzero(mask)
        middle = mask.shape[0] // 2
        self.assertLess(abs(xs.mean() - middle), 3.0, "the taught mark sits on the middle of its patch, not where the piece was")
        self.assertLess(abs(ys.mean() - middle), 3.0)

    def test_a_piece_that_is_really_partly_on_its_circle_is_not_read_as_a_mark(self):
        empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        for millimetres in (9, 12):
            view = rectify(camera_view({"A1": X}, layout=SMALL_MAT, solid=True, offsets={"A1": (millimetres, 0)}))
            position = read_position(view.grey, empty.grey, SMALL_MAT)
            self.assertNotEqual(position.board[0], X, f"{millimetres} mm off the circle is not on it")


class CircleCentreTests(unittest.TestCase):
    """The circles are found in the picture of the empty mat, so a bent picture does not matter, and a clear mat stays clear."""

    def test_the_circles_are_found_where_the_empty_mat_shows_them(self):
        from dobot_studio.tictactoe_vision import circle_centres, circle_positions

        flat = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        centres = circle_centres(flat)
        self.assertEqual(len(centres), 19)
        for name, (dx, dy) in centres.items():
            self.assertLess(np.hypot(dx, dy), 0.6, f"{name} is where the markers say, to within a pixel or two")
        bent = rectify(camera_view({}, layout=SMALL_MAT, solid=True, circle_shift=(4.0, -3.0)))
        for name, (dx, dy) in circle_centres(bent).items():
            self.assertAlmostEqual(dx, 4.0, delta=0.7, msg=name)
            self.assertAlmostEqual(dy, -3.0, delta=0.7, msg=name)
        moved = circle_positions(SMALL_MAT, {"A1": (2.0, -1.0)})
        self.assertEqual(moved["A1"], (SMALL_MAT.positions["A1"][0] + 2.0, SMALL_MAT.positions["A1"][1] - 1.0))
        self.assertEqual(moved["B2"], SMALL_MAT.positions["B2"])

    def test_a_mat_with_no_dark_circles_to_measure_is_left_as_the_markers_say(self):
        from dobot_studio.tictactoe import STANDARD_MAT
        from dobot_studio.tictactoe_vision import circle_centres

        self.assertEqual(circle_centres(rectify(camera_view({}, layout=STANDARD_MAT))), {})

    def test_pieces_read_wherever_the_picture_puts_the_circles_once_they_are_measured(self):
        from dobot_studio.tictactoe_vision import circle_centres

        contents = {**{f"X{i}": X for i in range(1, 6)}, **{f"O{i}": O for i in range(1, 6)}, "A1": X, "B2": O}
        for shift in ((6.0, 0.0), (-5.0, 5.0), (0.0, -7.0)):
            with self.subTest(shift=shift):
                empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True, circle_shift=shift))
                view = rectify(camera_view(contents, layout=SMALL_MAT, solid=True, circle_shift=shift,
                                           offsets={name: (2.0, -1.5) for name in contents}))
                position = read_position(view.grey, empty.grey, SMALL_MAT, centres=circle_centres(empty))
                got = dict(zip(SMALL_MAT.positions, (*position.board, *position.reserve)))
                self.assertEqual({name: mark for name, mark in got.items() if mark != contents.get(name, "")}, {})

    def test_the_mat_stays_clear_when_the_camera_changes_its_exposure_or_pieces_sit_off_their_circles(self):
        from dobot_studio.tictactoe_vision import circle_centres, mat_clear

        contents = {**{f"X{i}": X for i in range(1, 6)}, **{f"O{i}": O for i in range(1, 6)}, "A1": X, "B2": O}
        empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True, colours=COLOURS))
        centres = circle_centres(empty)
        offsets = {name: (4.5 * np.cos(i), 4.5 * np.sin(i)) for i, name in enumerate(contents)}     # all a few mm off
        picture = camera_view(contents, layout=SMALL_MAT, solid=True, colours=COLOURS, offsets=offsets)
        for name, change in {"as it is": lambda p: p, "dimmed": lambda p: (p * 0.7).astype(np.uint8),
                             "warm": lambda p: np.clip(p * np.array([1.12, 1.0, 0.85]), 0, 255).astype(np.uint8)}.items():
            with self.subTest(name):
                view = rectify(change(picture))
                position = read_position(view.grey, empty.grey, SMALL_MAT, None, view.colour, centres)
                self.assertTrue(mat_clear(view, empty, position, centres), "a mat with only pieces on it is clear")

    def test_a_hand_or_the_arm_in_the_way_is_still_seen(self):
        from dobot_studio.tictactoe_vision import circle_centres, mat_clear

        empty = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        picture = camera_view({"A1": X}, layout=SMALL_MAT, solid=True)
        cv2.rectangle(picture, (300, 120), (360, 300), (40, 44, 52), -1)          # a dark arm lying over the mat
        view = rectify(picture)
        position = read_position(view.grey, empty.grey, SMALL_MAT, centres=circle_centres(empty))
        self.assertFalse(mat_clear(view, empty, position, circle_centres(empty)))


if __name__ == "__main__":
    unittest.main()
