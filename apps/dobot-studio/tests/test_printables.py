"""The 3D mats match the paper mats and the software's layouts, print flat in two colours, and fit the beds."""
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import unittest

import cv2
import numpy as np

from dobot_studio.tictactoe import A3_MAT, A3_PARK, PAPER_MAT, PAPER_PARK

PRINTABLES = Path(__file__).resolve().parents[1] / "printables"
SET = PRINTABLES / "tictactoe"
SVG = "{http://www.w3.org/2000/svg}"
THICKNESS, MARK_DEPTH = 2.8, 0.6
H2D_BED = (325, 320)       # Bambu H2D
SMALL_BED = (256, 256)     # Bambu P1, X1 and A1

# name: (layout, width, height, park, ring radius, park ring radius)
MATS = {
    "mat-300x300": (PAPER_MAT, 300, 300, PAPER_PARK, 10.9, 2.3),
    "mat-a3": (A3_MAT, 420, 297, A3_PARK, 10.9 * 1.6, 3.2),
}
# file: (mat, x offset, y offset of the piece in the full model, width, height)
PIECES = {
    "mat-300x300": ("mat-300x300", 0, 0, 300, 300),
    # The cut runs 160 mm from the top, between reserve rings, so the top tiles are 160 mm tall.
    "tiles/mat-top-left": ("mat-300x300", 150, 140, 150, 160),
    "tiles/mat-top-right": ("mat-300x300", 0, 140, 150, 160),
    "tiles/mat-bottom-left": ("mat-300x300", 150, 0, 150, 140),
    "tiles/mat-bottom-right": ("mat-300x300", 0, 0, 150, 140),
    "mat-a3": ("mat-a3", 0, 0, 420, 297),
    "a3-halves/mat-left": ("mat-a3", 265, 0, 155, 297),
    "a3-halves/mat-right": ("mat-a3", 0, 0, 265, 297),
}


def read_obj(path):
    """Return {object name: (vertices, faces)} with each object's faces indexed locally."""
    objects, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("o "):
            current = line.split()[1]
            objects[current] = ([], [])
        elif line.startswith("v "):
            objects[current][0].append([float(value) for value in line.split()[1:]])
        elif line.startswith("f "):
            objects[current][1].append([int(value) for value in line.split()[1:]])
    result, offset = {}, 0
    for name, (vertices, faces) in objects.items():
        result[name] = (np.array(vertices), np.array(faces) - 1 - offset)
        offset += len(vertices)
    return result


def watertight(faces):
    """Every edge is used once in each direction: a closed, consistently wound solid."""
    edges = {}
    for a, b, c in faces:
        for start, end in ((a, b), (b, c), (c, a)):
            edges[(start, end)] = edges.get((start, end), 0) + 1
    return all(count == 1 and edges.get((end, start)) == 1 for (start, end), count in edges.items())


def level_triangles(vertices, faces, z):
    corners = vertices[faces]
    return corners[np.all(np.abs(corners[:, :, 2] - z) < 1e-6, axis=1)][:, :, :2]


def area(triangles):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    return float(np.sum(np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])) / 2)


def volume(vertices, faces):
    a, b, c = (vertices[faces][:, i] for i in range(3))
    return float(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6)


def inside(triangles, points):
    """True for each point lying in any of the triangles."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    v0, v1, v2 = c - a, b - a, np.asarray(points)[:, None, :] - a
    d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
    d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
    denominator = d00 * d11 - d01 * d01
    with np.errstate(divide="ignore", invalid="ignore"):
        u, v = (d11 * d20 - d01 * d21) / denominator, (d00 * d21 - d01 * d20) / denominator
    return ((u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (denominator > 1e-12)).any(axis=1)


class Mat:
    """One printed file, with a way to ask what is on its first layer at a point of the finished mat."""

    def __init__(self, name):
        self.name = name
        self.mat, self.x0, self.y0, self.width, self.height = PIECES[name]
        self.layout, self.full_width, self.full_height, self.park, self.ring, self.park_ring = MATS[self.mat]
        parts = read_obj(SET / f"{name}.obj")
        self.body, self.mark = parts["Body"], parts["Mark"]
        self.mark_triangles = level_triangles(*self.mark, 0)

    def model(self, points):
        """Finished-mat coordinates (y down) to this file's coordinates: printed face-down, so turned end for end."""
        points = np.asarray(points, dtype=float)
        return np.column_stack((self.full_width - points[:, 0] - self.x0, self.full_height - points[:, 1] - self.y0))

    def has(self, point):
        x, y = self.model([point])[0]
        return 0 <= x <= self.width and 0 <= y <= self.height

    def marked(self, points):
        return inside(self.mark_triangles, self.model(points))


def ring_points(centre, radius, count=12):
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    return [(centre[0] + radius * np.cos(t), centre[1] + radius * np.sin(t)) for t in angles]


class FlatFirstLayerTests(unittest.TestCase):
    def test_every_file_is_a_body_and_a_flush_mark(self):
        for name in PIECES:
            with self.subTest(name):
                mat = Mat(name)
                for vertices, faces in (mat.body, mat.mark):
                    self.assertTrue(watertight(faces))
                    self.assertGreater(volume(vertices, faces), 0)
                self.assertAlmostEqual(mat.body[0][:, 2].min(), 0)
                self.assertAlmostEqual(mat.body[0][:, 2].max(), THICKNESS)
                self.assertAlmostEqual(mat.mark[0][:, 2].max(), MARK_DEPTH)
                self.assertTrue((SET / f"{name}.3mf").is_file())
                with ZipFile(SET / f"{name}.3mf") as package:
                    model = package.read("3D/3dmodel.model").decode("utf-8")
                self.assertIn('name="Body"', model)
                self.assertIn('name="Mark"', model)

    def test_the_first_layer_is_solid_with_no_gaps_or_overlaps(self):
        for name in PIECES:
            with self.subTest(name):
                mat = Mat(name)
                first_layer = area(level_triangles(*mat.body, 0)) + area(mat.mark_triangles)
                self.assertAlmostEqual(first_layer, area(level_triangles(*mat.body, THICKNESS)), delta=0.01)
                self.assertAlmostEqual(area(level_triangles(*mat.mark, MARK_DEPTH)),
                                       area(level_triangles(*mat.body, MARK_DEPTH)), delta=0.01)
                self.assertAlmostEqual(area(level_triangles(*mat.mark, MARK_DEPTH)), area(mat.mark_triangles), delta=0.01)
                slab = area(level_triangles(*mat.body, THICKNESS)) * THICKNESS
                self.assertAlmostEqual(volume(*mat.body) + volume(*mat.mark), slab, delta=0.5)

    def test_marks_never_touch_the_edge_of_a_piece(self):
        for name in PIECES:
            with self.subTest(name):
                mat = Mat(name)
                xs, ys = mat.mark_triangles[:, :, 0], mat.mark_triangles[:, :, 1]
                self.assertGreater(xs.min(), 0.1)
                self.assertGreater(ys.min(), 0.1)
                self.assertLess(xs.max(), mat.width - 0.1)
                self.assertLess(ys.max(), mat.height - 0.1)


class SameAsThePaperMatTests(unittest.TestCase):
    def test_every_cell_and_reserve_slot_has_its_ring_at_the_layout_position(self):
        for name in ("mat-300x300", "mat-a3"):
            mat = Mat(name)
            self.assertEqual(len(mat.layout.positions), 19)
            for label, centre in mat.layout.positions.items():
                with self.subTest(f"{name} {label}"):
                    self.assertTrue(mat.marked(ring_points(centre, mat.ring)).all(), "ring is missing or off position")
                    self.assertFalse(mat.marked([centre]).any(), "the ring must be hollow")
                    self.assertFalse(mat.marked(ring_points(centre, mat.ring * 0.6)).any())

    def test_x_pieces_are_on_the_left_and_o_pieces_on_the_right(self):
        for name in ("mat-300x300", "mat-a3"):
            layout = Mat(name).layout
            self.assertLess(max(layout.positions[slot][0] for slot in layout.cross_bank),
                            min(layout.positions[cell][0] for cell in ("A1", "B1", "C1")))
            self.assertGreater(min(layout.positions[slot][0] for slot in layout.nought_bank),
                               max(layout.positions[cell][0] for cell in ("A3", "B3", "C3")))

    def test_the_park_ring_is_where_the_software_expects_it(self):
        for name in ("mat-300x300", "mat-a3"):
            mat = Mat(name)
            self.assertTrue(mat.marked(ring_points(mat.park, mat.park_ring)).all())
            self.assertFalse(mat.marked([mat.park]).any())

    def test_each_camera_marker_has_the_right_id_and_orientation(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for name in ("mat-300x300", "mat-a3"):
            mat = Mat(name)
            for marker, (x, y) in mat.layout.anchors.items():
                bits = cv2.aruco.generateImageMarker(dictionary, marker, 6)
                size = mat.layout.anchor_size
                cell = size / 6
                centres = [(x - size / 2 + (column + 0.5) * cell, y - size / 2 + (row + 0.5) * cell)
                           for row in range(6) for column in range(6)]
                with self.subTest(f"{name} marker {marker}"):
                    self.assertEqual(list(mat.marked(centres)), [bool(bit == 0) for bit in bits.flatten()])
                    # A quiet zone of plain Body surrounds the marker so the camera can find it.
                    border = [(x + sign * (size / 2 + 1.5), y + offset) for sign in (-1, 1)
                              for offset in (-size / 3, 0, size / 3)]
                    self.assertFalse(mat.marked(border).any())

    def test_the_mats_have_no_printed_position_names(self):
        """Positions are named on screen during setup, so the artwork carries no lettering."""
        for svg in ("mat-300x300.svg", "mat-a3.svg"):
            root = ET.parse(SET / svg).getroot()
            texts = {group.attrib.get("id"): [e.text for e in group.iter(f"{SVG}text")]
                     for group in root.iter(f"{SVG}g")}
            self.assertEqual({key: value for key, value in texts.items() if value},
                             {"print-scale": ["100 mm"]} if svg == "mat-a3.svg" else {}, svg)
        for pdf in ("mat-a3.pdf",):
            with ZipFile(SET / "mat-a3.3mf") as package:      # the 3D files hold no text at all
                self.assertNotIn(b"<text", package.read("3D/3dmodel.model"))
            self.assertTrue((SET / pdf).read_bytes().startswith(b"%PDF"))


class PrintabilityTests(unittest.TestCase):
    def test_no_detail_is_too_fine_for_a_04_mm_nozzle(self):
        try:
            from shapely import union_all
            from shapely.geometry import Polygon
        except ImportError:
            self.skipTest("needs shapely")
        for name in ("mat-300x300", "mat-a3"):
            with self.subTest(name):
                shape = union_all([Polygon(triangle).buffer(0.001) for triangle in Mat(name).mark_triangles])
                opened = shape.buffer(-0.29, join_style="mitre").buffer(0.29, join_style="mitre")
                self.assertLess(shape.difference(opened).area, 1.5)

    def test_the_pieces_fit_the_printers(self):
        for name, (_, _, _, width, height) in PIECES.items():
            if name == "mat-a3":
                continue      # the whole A3 mat is for printers with a bed over 420 mm; the H2D prints its halves
            with self.subTest(name):
                bounds = Mat(name).body[0]
                self.assertAlmostEqual(np.ptp(bounds[:, 0]), width, delta=0.01)
                self.assertAlmostEqual(np.ptp(bounds[:, 1]), height, delta=0.01)
                bed = SMALL_BED if name.startswith("tiles/") else H2D_BED
                self.assertLessEqual(width, bed[0])
                self.assertLessEqual(height, bed[1])

    def test_tiles_hold_the_circles_that_belong_to_them(self):
        for name in PIECES:
            mat = Mat(name)
            expected = 0
            for label, centre in mat.layout.positions.items():
                if mat.has(centre):
                    expected += 1
                    with self.subTest(f"{name} {label}"):
                        self.assertTrue(mat.marked(ring_points(centre, mat.ring)).all())
            self.assertGreater(expected, 0, name)
        # Every circle is in exactly one piece of each split mat.
        for pieces in (("tiles/mat-top-left", "tiles/mat-top-right", "tiles/mat-bottom-left", "tiles/mat-bottom-right"),
                       ("a3-halves/mat-left", "a3-halves/mat-right")):
            mats = [Mat(piece) for piece in pieces]
            for label, centre in mats[0].layout.positions.items():
                self.assertEqual(sum(mat.has(centre) for mat in mats), 1, label)


class DownloadTests(unittest.TestCase):
    def test_the_zip_matches_the_print_files(self):
        with ZipFile(PRINTABLES / "tictactoe-300mm.zip") as package:
            archived = {name for name in package.namelist() if not name.endswith("/")}
            expected = {f"tictactoe/{path.relative_to(SET).as_posix()}"
                        for path in SET.rglob("*") if path.is_file()}
            self.assertEqual(archived, expected)
            for name in sorted(archived):
                self.assertEqual(package.read(name), (PRINTABLES / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
