"""The small A4 mat: it fits the Dobot's reach, the camera reads it, and its PDF is the right size."""
from pathlib import Path
from xml.etree import ElementTree as ET
import unittest

import numpy as np
from pypdf import PdfReader

from dobot_studio.robot import Magician, Pose, RobotError
from dobot_studio.tictactoe import (
    COMPACT_CENTRE, COMPACT_MAT, MAT_LAYOUTS, O, SMALL_MAT, SMALL_PLACEMENT, SMALL_SUGGESTED_DISTANCE, X,
)
from dobot_studio.tictactoe_vision import read_position, rectify
from tests.test_tictactoe import camera_view

SET = Path(__file__).resolve().parents[1] / "printables" / "tictactoe"
SVG = "{http://www.w3.org/2000/svg}"


def placed(layout, distance, degrees):
    """Every circle's (x, y) in the arm's frame, with the mat's middle ``distance`` mm out and the sheet turned."""
    turn = np.radians(degrees)
    rotation = np.array([[np.cos(turn), -np.sin(turn)], [np.sin(turn), np.cos(turn)]])
    offsets = np.array([(x - COMPACT_CENTRE[0], y - COMPACT_CENTRE[1]) for x, y in layout.positions.values()])
    return {name: (distance + point[0], point[1]) for name, point in zip(layout.positions, offsets @ rotation.T)}


def reachable(layout, distance, degrees, margin=8):
    try:
        for x, y in placed(layout, distance, degrees).values():
            Magician.check_reach(Pose(x, y, -40, 0))
        radii = [np.hypot(x, y) for x, y in placed(layout, distance, degrees).values()]
        return min(radii) >= 130 + margin and max(radii) <= 310 - margin
    except RobotError:
        return False


class SmallMatTests(unittest.TestCase):
    def test_the_pieces_and_markers_are_the_same_sizes_as_the_other_paper_mats(self):
        self.assertEqual(SMALL_MAT.anchor_size, COMPACT_MAT.anchor_size)
        self.assertEqual(SMALL_MAT.piece_scale, COMPACT_MAT.piece_scale)
        self.assertEqual((SMALL_MAT.width, SMALL_MAT.height), (297, 210))
        self.assertEqual(len(SMALL_MAT.positions), 19)

    def test_circles_leave_room_for_a_piece_and_the_markers_sit_clear_of_them(self):
        points = np.array(list(SMALL_MAT.positions.values()))
        for i, a in enumerate(points):
            for b in points[i + 1:]:
                self.assertGreaterEqual(np.hypot(*(a - b)), 30 - 1e-9, "two circles are closer than 30 mm")
        for x, y in SMALL_MAT.anchors.values():
            # the marker, its white margin, and a circle's black disc (12.5 mm radius for a piece) must not overlap
            self.assertGreater(np.min(np.hypot(points[:, 0] - x, points[:, 1] - y)), 8 + 3 + 12.5)
        xs, ys = points[:, 0], points[:, 1]
        self.assertAlmostEqual((xs.min() + xs.max()) / 2, COMPACT_CENTRE[0])
        self.assertAlmostEqual((ys.min() + ys.max()) / 2, COMPACT_CENTRE[1])
        printable = (5, 5, 292, 205)         # an office printer cannot print to the edge of the sheet
        for x, y in SMALL_MAT.anchors.values():
            self.assertTrue(printable[0] <= x - 11 and x + 11 <= printable[2] and printable[1] <= y - 11 and y + 11 <= printable[3])

    def test_every_circle_is_within_the_arms_reach_in_the_recommended_placements(self):
        for facing, (low, high) in SMALL_PLACEMENT.items():
            degrees = 90 if facing == "long" else 0
            for distance in range(low, high + 1):
                with self.subTest(facing, distance=distance):
                    self.assertTrue(reachable(SMALL_MAT, distance, degrees))
            for distance in (low - 3, high + 3):
                with self.subTest(facing, outside=distance):
                    self.assertFalse(reachable(SMALL_MAT, distance, degrees))
        for facing, degrees in (("long", 90), ("long", 270), ("short", 0), ("short", 180)):
            self.assertTrue(reachable(SMALL_MAT, SMALL_SUGGESTED_DISTANCE, degrees), facing)
        for turn in (-15, 15):
            self.assertTrue(reachable(SMALL_MAT, SMALL_SUGGESTED_DISTANCE, 90 + turn), "turned 15 degrees")

    def test_the_compact_mat_cannot_be_placed_so_that_it_fits_in_most_directions_the_small_one_can(self):
        def good(layout):
            return sum(any(reachable(layout, d, t) for d in range(150, 300)) for t in range(0, 360, 5))
        self.assertGreater(good(SMALL_MAT), good(COMPACT_MAT))
        self.assertFalse(reachable(COMPACT_MAT, SMALL_SUGGESTED_DISTANCE, 0))

    def test_the_camera_picks_the_small_mat_from_its_markers_and_reads_pieces(self):
        self.assertIn(SMALL_MAT, MAT_LAYOUTS)
        self.assertEqual(len({marker for layout in MAT_LAYOUTS for marker in layout.anchors}), 4 * len(MAT_LAYOUTS),
                         "no two mats share a marker")
        base = rectify(camera_view({}, layout=SMALL_MAT, solid=True))
        self.assertIs(base.layout, SMALL_MAT)
        contents = {"A1": X, "B2": O, "C3": X, "X2": X, "O4": O}
        played = rectify(camera_view(contents, layout=SMALL_MAT, solid=True))
        position = read_position(played.grey, base.grey, SMALL_MAT)
        self.assertEqual(position.board, tuple(contents.get(cell, "") for cell in ("A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3")))
        self.assertEqual(position.reserve, tuple(contents.get(slot, "") for slot in SMALL_MAT.reserve))


class SmallMatPrintTests(unittest.TestCase):
    def test_the_svg_has_the_scale_line_and_no_writing_at_all(self):
        root = ET.parse(SET / "mat-a4-small.svg").getroot()
        self.assertEqual(root.get("width"), "297mm")
        self.assertEqual(root.get("height"), "210mm")
        self.assertEqual([element.text for element in root.iter(f"{SVG}text")], [])
        scale = next(group for group in root.iter(f"{SVG}g") if group.get("id") == "print-scale")
        lines = list(scale.iter(f"{SVG}line"))
        longest = max(lines, key=lambda line: abs(float(line.get("x2")) - float(line.get("x1"))))
        self.assertAlmostEqual(abs(float(longest.get("x2")) - float(longest.get("x1"))), 100.0)
        self.assertEqual(longest.get("y1"), longest.get("y2"))

    def test_the_svg_circles_sit_where_the_software_expects_them(self):
        root = ET.parse(SET / "mat-a4-small.svg").getroot()
        grid = next(group for group in root.iter(f"{SVG}g") if group.get("id") == "board-grid")
        drawn = {(round(float(c.get("cx")), 3), round(float(c.get("cy")), 3)) for c in grid.iter(f"{SVG}circle")
                 if float(c.get("r")) > 5}
        self.assertEqual(drawn, {(round(x, 3), round(y, 3)) for x, y in SMALL_MAT.positions.values()})

    def test_the_pdf_is_a_4_landscape_to_be_printed_at_full_size(self):
        reader = PdfReader(SET / "mat-a4-small.pdf")
        box = reader.pages[0].mediabox
        self.assertAlmostEqual(float(box.width) / 72 * 25.4, 297, delta=0.2)
        self.assertAlmostEqual(float(box.height) / 72 * 25.4, 210, delta=0.2)
        self.assertEqual(reader.trailer["/Root"]["/ViewerPreferences"]["/PrintScaling"], "/None")
        self.assertEqual(len(reader.pages), 1)


if __name__ == "__main__":
    unittest.main()
