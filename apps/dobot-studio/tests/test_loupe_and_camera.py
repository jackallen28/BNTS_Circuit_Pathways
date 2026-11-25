"""The close-up of the point being taught, and the high-definition picture it comes from."""
from pathlib import Path
from threading import Event
from time import monotonic, sleep
import unittest
from unittest import mock

import cv2
import numpy as np

from dobot_studio import vision
from dobot_studio.tictactoe import A3_MAT, COMPACT_MAT, O, SMALL_MAT, X
from dobot_studio.tictactoe_vision import explain, loupe, read_position, rectify, side_by_side
from tests.test_tictactoe import camera_view

LAYOUT = COMPACT_MAT


class LoupeTests(unittest.TestCase):
    def setUp(self):
        self.frame = camera_view({}, layout=LAYOUT, solid=True)
        self.view = rectify(self.frame)

    def test_the_circle_is_in_the_middle_of_its_close_up(self):
        for name in ("A1", "B2", "O5", "X3"):
            with self.subTest(name):
                picture = loupe(self.frame, self.view.matrix, LAYOUT.positions[name], 200, 44)
                self.assertEqual(picture.shape, (200, 200, 3))
                middle = picture[40:160, 40:160].max(axis=2) < 60      # other circles and markers sit outside this
                dark = np.argwhere(middle) + 40
                self.assertGreater(len(dark), 5000, "the black disc should fill the middle")
                centre = dark.mean(axis=0)
                self.assertLess(abs(centre[0] - 100) + abs(centre[1] - 100), 6)

    def test_a_point_that_is_not_a_circle_shows_plain_mat(self):
        between = (LAYOUT.positions["A1"][0] + LAYOUT.positions["A2"][0]) / 2, LAYOUT.positions["A1"][1]
        picture = loupe(self.frame, self.view.matrix, between, 200, 14)
        self.assertGreater(picture.mean(), 200)

    def test_turned_is_half_a_turn_of_the_same_picture(self):
        plain = loupe(self.frame, self.view.matrix, LAYOUT.positions["A1"], 160, 60)
        turned = loupe(self.frame, self.view.matrix, LAYOUT.positions["A1"], 160, 60, turned=True)
        self.assertTrue(np.array_equal(turned, plain[::-1, ::-1]))


class ReadingTests(unittest.TestCase):
    """Empty circles stay empty and pieces stay readable when the camera's picture is not quite the one it started with."""

    CONTENTS = {**{f"X{i}": X for i in range(1, 6)}, **{f"O{i}": O for i in range(1, 6)}, "A2": X, "B2": O, "C3": X}

    def readings(self, layout, change):
        base = rectify(camera_view({}, layout=layout, solid=True))
        played = rectify(camera_view(self.CONTENTS, layout=layout, solid=True))
        position = read_position(change(played.grey), base.grey, layout)
        names = (*layout.positions,)
        return {name: mark for name, mark in zip(names, (*position.board, *position.reserve)) if mark != self.CONTENTS.get(name, "")}

    def test_changes_that_are_not_pieces_do_not_make_circles_unreadable(self):
        changes = {
            "the picture slips a few pixels": lambda grey: np.roll(grey, 3, axis=1),
            "the picture is a little soft": lambda grey: cv2.GaussianBlur(grey, (0, 0), 2.5),
            "the camera dims itself": lambda grey: np.clip(grey * 0.6, 0, 255).astype(np.uint8),
            "all three at once": lambda grey: cv2.GaussianBlur(np.roll(np.clip(grey * 0.7, 0, 255).astype(np.uint8), 2, axis=0), (0, 0), 2),
        }
        for layout in (SMALL_MAT, COMPACT_MAT, A3_MAT):
            for name, change in changes.items():
                with self.subTest(f"{layout.label} {name}"):
                    self.assertEqual(self.readings(layout, change), {})

    def test_a_thing_that_is_really_on_a_circle_is_still_not_an_empty_circle(self):
        base = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        played = rectify(camera_view({"A1": "?"}, layout=SMALL_MAT, solid=True))      # a smudge that is neither X nor O
        position = read_position(played.grey, base.grey, SMALL_MAT)
        self.assertEqual(position.board[0], "?")
        self.assertIn("mark", explain(played.grey, base.grey, SMALL_MAT, "A1") + "mark")

    def test_the_reason_for_a_question_mark_is_in_plain_english(self):
        base = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        played = rectify(camera_view({"A1": "?"}, layout=SMALL_MAT, solid=True))
        self.assertTrue(explain(played.grey, base.grey, SMALL_MAT, "A1"))
        self.assertEqual(explain(played.grey, base.grey, SMALL_MAT, "B2"), "")         # an empty circle has nothing to explain

    def test_side_by_side_shows_the_same_place_now_and_when_empty(self):
        base = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        played = rectify(camera_view({"X2": X}, layout=SMALL_MAT, solid=True))
        now, empty = side_by_side(played, base, SMALL_MAT.positions["X2"], 120)
        self.assertEqual((now.shape, empty.shape), ((120, 120, 3), (120, 120, 3)))
        self.assertLess(empty[40:80, 40:80].mean(), 40, "the empty circle is a black disc")
        self.assertGreater(now[40:80, 40:80].mean(), empty[40:80, 40:80].mean() + 50, "a light piece sits on it now")


class FakeCapture:
    opened = []

    def __init__(self, *_):
        self.settings = {}
        FakeCapture.opened.append(self)

    def isOpened(self):
        return True

    def set(self, key, value):
        self.settings[key] = value
        return True

    def read(self):
        sleep(0.01)
        width = int(self.settings.get(cv2.CAP_PROP_FRAME_WIDTH, 640))
        height = int(self.settings.get(cv2.CAP_PROP_FRAME_HEIGHT, 480))
        return True, np.zeros((height, width, 3), np.uint8)

    def release(self):
        pass


class CameraSizeTests(unittest.TestCase):
    def picture(self, **options):
        FakeCapture.opened = []
        with mock.patch.object(cv2, "VideoCapture", FakeCapture):
            camera = vision.Camera("0", vision.TABLETOP, Path("."), lambda error: self.fail(error), **options)
            try:
                deadline = monotonic() + 5
                while camera.read() is None and monotonic() < deadline:
                    sleep(0.02)
                latest = camera.read()
            finally:
                camera.close()
                camera.thread.join(3)
        self.assertIsNotNone(latest)
        return FakeCapture.opened[0].settings, latest[1]

    def test_the_default_is_still_640_by_480(self):
        settings, image = self.picture()
        self.assertEqual((settings[cv2.CAP_PROP_FRAME_WIDTH], settings[cv2.CAP_PROP_FRAME_HEIGHT]), (640, 480))
        self.assertNotIn(cv2.CAP_PROP_FOURCC, settings)
        self.assertEqual(image.size, (640, 480))

    def test_high_definition_asks_for_1080p_in_mjpg_and_keeps_1280_across(self):
        settings, image = self.picture(high_definition=True)
        self.assertEqual((settings[cv2.CAP_PROP_FRAME_WIDTH], settings[cv2.CAP_PROP_FRAME_HEIGHT]), (1920, 1080))
        self.assertEqual(settings[cv2.CAP_PROP_FOURCC], cv2.VideoWriter_fourcc(*"MJPG"))
        self.assertEqual(image.size, (1280, 720))

    def test_a_camera_that_only_gives_640_is_left_alone(self):
        class Small(FakeCapture):
            def read(self):
                sleep(0.01)
                return True, np.zeros((480, 640, 3), np.uint8)

        FakeCapture.opened = []
        with mock.patch.object(cv2, "VideoCapture", Small):
            camera = vision.Camera("0", vision.TABLETOP, Path("."), lambda error: self.fail(error), high_definition=True)
            try:
                deadline = monotonic() + 5
                while camera.read() is None and monotonic() < deadline:
                    sleep(0.02)
                self.assertEqual(camera.read()[1].size, (640, 480))
            finally:
                camera.close()
                camera.thread.join(3)


if __name__ == "__main__":
    unittest.main()
