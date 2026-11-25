"""The cut-out tokens: they match the 3D pieces and the camera's idea of an X and an O, and they read."""
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
import unittest

import cairosvg
import numpy as np
from PIL import Image
from pypdf import PdfReader

from dobot_studio.tictactoe import (
    CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, NOUGHT_INNER, NOUGHT_OUTER, O, PIECE_RADIUS, SMALL_MAT, X,
)
from dobot_studio.tictactoe_vision import RADIUS, DENSITY, inspect, look, pixels_per_mm, rectify
from tests.test_tictactoe import camera_view

SET = Path(__file__).resolve().parents[1] / "printables" / "tictactoe"
SVG = "{http://www.w3.org/2000/svg}"


SHEETS = ("tokens-cutout", "tokens-cutout-colour")


def sheet(name="tokens-cutout"):
    return ET.parse(SET / f"{name}.svg").getroot()


def tokens(root):
    group = next(g for g in root.iter(f"{SVG}g") if g.get("id") == "tokens")
    discs = [c for c in group.iter(f"{SVG}circle") if float(c.get("r")) == PIECE_RADIUS]
    return [(float(c.get("cx")), float(c.get("cy"))) for c in discs]


class TokenSheetTests(unittest.TestCase):
    def test_the_sheets_are_one_a4_portrait_page_each_to_print_at_full_size(self):
        for name in SHEETS:
            with self.subTest(name):
                root = sheet(name)
                self.assertEqual((root.get("width"), root.get("height")), ("210mm", "297mm"))
                reader = PdfReader(SET / f"{name}.pdf")
                box = reader.pages[0].mediabox
                self.assertAlmostEqual(float(box.width) / 72 * 25.4, 210, delta=0.2)
                self.assertAlmostEqual(float(box.height) / 72 * 25.4, 297, delta=0.2)
                self.assertEqual(len(reader.pages), 1)
                self.assertEqual(reader.trailer["/Root"]["/ViewerPreferences"]["/PrintScaling"], "/None")

    def test_there_are_fifteen_of_each_25_mm_disc_with_room_to_cut(self):
        for name in SHEETS:
            with self.subTest(name):
                self.check_discs(name)

    def check_discs(self, name):
        centres = tokens(sheet(name))
        self.assertEqual(len(centres), 30)
        for index, (x, y) in enumerate(centres):
            for other in centres[index + 1:]:
                self.assertGreaterEqual(np.hypot(x - other[0], y - other[1]), 2 * PIECE_RADIUS + 8 - 1e-6)
            self.assertTrue(PIECE_RADIUS + 5 <= x <= 210 - PIECE_RADIUS - 5 and PIECE_RADIUS + 5 <= y <= 297 - PIECE_RADIUS - 5,
                            "a token is too close to the edge of the paper to print")
        group = next(g for g in sheet(name).iter(f"{SVG}g") if g.get("id") == "tokens")
        crosses = [r for r in group.iter(f"{SVG}rect")]
        noughts = [c for c in group.iter(f"{SVG}circle") if float(c.get("r")) == NOUGHT_OUTER]
        self.assertEqual((len(crosses), len(noughts)), (30, 15), "fifteen crosses of two bars each, and fifteen noughts")

    def test_the_marks_are_the_same_size_as_the_3d_pieces(self):
        group = next(g for g in sheet().iter(f"{SVG}g") if g.get("id") == "tokens")
        for bar in group.iter(f"{SVG}rect"):
            self.assertAlmostEqual(float(bar.get("width")), 2 * CROSS_HALF_LENGTH)
            self.assertAlmostEqual(float(bar.get("height")), 2 * CROSS_HALF_WIDTH)
            self.assertEqual(bar.get("fill"), "#000000")
        radii = {float(c.get("r")) for c in group.iter(f"{SVG}circle")}
        self.assertEqual(radii, {PIECE_RADIUS, NOUGHT_OUTER, NOUGHT_INNER})

    def test_every_token_reads_as_its_mark_through_the_cameras_own_reading(self):
        for name in SHEETS:
            with self.subTest(name):
                self.check_reading(name)

    def check_reading(self, name):
        """Each token is drawn onto a black circle at the camera's working scale and read, as a token on the mat would be."""
        pixels = DENSITY
        picture = np.asarray(Image.open(BytesIO(cairosvg.svg2png(
            url=str(SET / f"{name}.svg"), output_width=round(210 * pixels), background_color="white"))).convert("L"))
        size = 2 * RADIUS + 1
        y, x = np.mgrid[:size, :size]
        radius = np.hypot(x - RADIUS, y - RADIUS) / pixels
        baseline = np.where(radius <= 11.725, 0, 255).astype(np.uint8)       # the empty circle: a black disc on white paper
        found = {X: 0, O: 0}
        for index, (cx, cy) in enumerate(tokens(sheet(name))):
            crop = picture[round(cy * pixels) - RADIUS:round(cy * pixels) + RADIUS + 1,
                           round(cx * pixels) - RADIUS:round(cx * pixels) + RADIUS + 1]
            tile = np.where(radius <= PIECE_RADIUS, crop, baseline).astype(np.uint8)
            mark, why = inspect(tile, baseline)
            expected = X if index < 15 else O
            self.assertEqual(mark, expected, f"token {index}: {why}")
            found[mark] += 1
        self.assertEqual(found, {X: 15, O: 15})

    def test_the_sheets_say_how_to_print_and_cut_them(self):
        for name in SHEETS:
            text = " ".join(t.text or "" for t in sheet(name).iter(f"{SVG}text"))
            for words in ("100%", "matte", "Cut along", "25 mm", "foam"):
                self.assertIn(words, text, name)

    def test_the_colour_sheet_has_pink_crosses_and_yellow_noughts_the_camera_can_tell_apart_by_colour(self):
        from dobot_studio.pieces import MIN_SEPARATION, colour_distance
        from dobot_studio.tictactoe_vision import CLEAR_DENSITY, COLOUR_RADIUS, body_colour

        picture = np.asarray(Image.open(BytesIO(cairosvg.svg2png(
            url=str(SET / "tokens-cutout-colour.svg"), output_width=round(210 * CLEAR_DENSITY), background_color="white"))).convert("RGB"))
        centres = tokens(sheet("tokens-cutout-colour"))
        labs = {}
        for index in (0, 15):
            cx, cy = centres[index]
            x, y = round(cx * CLEAR_DENSITY), round(cy * CLEAR_DENSITY)
            tile = picture[y - COLOUR_RADIUS:y + COLOUR_RADIUS + 1, x - COLOUR_RADIUS:x + COLOUR_RADIUS + 1]
            labs[index] = body_colour(tile)[0]
        self.assertGreater(colour_distance(labs[0], labs[15]), MIN_SEPARATION * 2)
        fills = {c.get("fill") for c in next(g for g in sheet("tokens-cutout-colour").iter(f"{SVG}g")
                                             if g.get("id") == "tokens").iter(f"{SVG}circle") if float(c.get("r")) == PIECE_RADIUS}
        self.assertEqual(fills, {"#f06496", "#fadc3c"})


class WhatThePiSeesTests(unittest.TestCase):
    def test_the_size_of_the_mat_in_the_picture_is_measured_from_its_markers(self):
        view = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        self.assertAlmostEqual(pixels_per_mm(view), 1.77, delta=0.1)
        near = rectify(camera_view({}, layout=SMALL_MAT, solid=True, shift=0))
        self.assertGreater(pixels_per_mm(near), 1.0)

    def test_looking_at_a_circle_gives_the_picture_the_mark_and_how_well_it_matched(self):
        base = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        played = rectify(camera_view({"X1": X, "O1": O, "A1": "?"}, layout=SMALL_MAT, solid=True))
        mark, why, report = look(played.grey, base.grey, SMALL_MAT, "X1")
        self.assertEqual((mark, why), (X, ""))
        self.assertEqual(report["tile"].shape, (2 * RADIUS + 1, 2 * RADIUS + 1))
        self.assertEqual(report["ink"].dtype, bool)
        self.assertGreater(report["scores"][X], 0.6)
        self.assertGreater(report["scores"][X], report["scores"][O] + 0.3)
        mark, why, report = look(played.grey, base.grey, SMALL_MAT, "O1")
        self.assertEqual(mark, O)
        mark, why, report = look(played.grey, base.grey, SMALL_MAT, "A1")
        self.assertEqual(mark, "?")
        self.assertTrue(why)
        mark, why, report = look(played.grey, base.grey, SMALL_MAT, "B2")
        self.assertEqual((mark, why), ("", ""))
        self.assertLess(report["changed"], 0.17)


if __name__ == "__main__":
    unittest.main()
