from math import dist
from random import Random
from threading import Event
import unittest

import cv2
import numpy as np

from dobot_studio.robot import Magician, Pose, RobotError, TRANSFER_SEGMENT_MM
from dobot_studio.tictactoe import (
    A3_MAT, A3_PARK, COMPACT_CENTRE, COMPACT_MAT, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, EMPTY, NOUGHT_INNER,
    NOUGHT_OUTER, O, PAPER_MAT, PIECE_RADIUS, STANDARD_MAT, UNKNOWN, X,
    EASY, HARD, LEVELS, MEDIUM, human_change, outcome, robot_move, score, with_move,
)
from dobot_studio.tictactoe_program import TurnDelay
from dobot_studio.tictactoe_vision import DENSITY, Position, mat_clear, read_position, rectify


def camera_view(contents, shift=0, layout=STANDARD_MAT, solid=False, colours=None, offsets=None, circle_shift=(0, 0)):
    """An angled, 640 px camera view of the mat and the supplied glyphs.

    ``solid`` draws the circles as solid black discs, as on the current printed mats, instead of rings.
    ``colours`` maps X and O to the colour (RGB) of that mark's pieces, instead of the usual light grey. A piece whose
    content is "blank" has a body but no mark, as when a reflection wipes the mark out. ``offsets`` maps a position
    to how far (dx, dy, in mm) its piece sits from the middle of the circle. ``circle_shift`` moves every circle (not
    the markers) by (dx, dy) mm, as a lens that bends the picture between the markers does.
    """
    density = 3
    piece_density = layout.piece_scale * density
    background = (43, 68, 75) if layout is STANDARD_MAT else (250, 250, 250)
    rgb = np.full((layout.height*density, layout.width*density, 3), background, np.uint8)
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    for key, (x, y) in layout.anchors.items():
        cx, cy = round(x*density), round(y*density)
        radius = round(layout.anchor_size*density/2)
        border = radius + density*2
        rgb[cy-border:cy+border, cx-border:cx+border] = 251
        image = aruco.generateImageMarker(dictionary, key, 2*radius)
        rgb[cy-radius:cy+radius, cx-radius:cx+radius] = image[:, :, None]
    for label, (x, y) in layout.positions.items():
        cx, cy = round((x + circle_shift[0])*density), round((y + circle_shift[1])*density)
        if layout is STANDARD_MAT:
            cv2.circle(rgb, (cx, cy), round(13.6*density), (31, 49, 58), -1, cv2.LINE_AA)
        elif solid:
            cv2.circle(rgb, (cx, cy), round((10.9 + 0.825)*piece_density), (0, 0, 0), -1, cv2.LINE_AA)
        else:
            cv2.circle(rgb, (cx, cy), round(10.9*piece_density), (34, 54, 74),
                       round(1.65*piece_density), cv2.LINE_AA)
        glyph = contents.get(label)
        if not glyph:
            continue
        dx, dy = (offsets or {}).get(label, (0, 0))      # a piece is never exactly on its circle
        px, py = cx + round(dx*density), cy + round(dy*density)
        body = tuple((colours or {}).get(glyph, (230, 233, 225)))
        cv2.circle(rgb, (px, py), round(PIECE_RADIUS*piece_density), body, -1, cv2.LINE_AA)
        if glyph == O:
            cv2.circle(rgb, (px, py), round(NOUGHT_OUTER*piece_density), (23, 29, 34), -1, cv2.LINE_AA)
            cv2.circle(rgb, (px, py), round(NOUGHT_INNER*piece_density), body, -1, cv2.LINE_AA)
        elif glyph == X:
            for sign in (-1, 1):
                theta = np.radians(24 + sign*45)
                vx, vy = np.cos(theta), np.sin(theta)
                wx, wy = -vy, vx
                vertices = [(round(px + (vx*u*CROSS_HALF_LENGTH + wx*v*CROSS_HALF_WIDTH)*piece_density),
                             round(py + (vy*u*CROSS_HALF_LENGTH + wy*v*CROSS_HALF_WIDTH)*piece_density))
                            for u,v in ((-1,-1), (1,-1), (1,1), (-1,1))]
                cv2.fillConvexPoly(rgb, np.asarray(vertices), (23,29,34), cv2.LINE_AA)
        elif glyph == UNKNOWN:
            cv2.rectangle(rgb, (px-16,py-16), (px+16,py+16), (23,29,34), -1)
    h, w = rgb.shape[:2]
    src = np.float32([(0, 0), (w-1, 0), (w-1, h-1), (0, h-1)])
    if layout.width > layout.height:      # a wide sheet: A3 or the compact A4 mat
        dst = np.float32([(62+shift, 53), (590+shift, 62), (584+shift, 432), (47+shift, 411)])
    else:
        dst = np.float32([(120+shift,23),(559+shift,34),(543+shift,458),(100+shift,443)])
    return cv2.warpPerspective(rgb, cv2.getPerspectiveTransform(src,dst), (640,480),
                               borderValue=(24, 28, 33))


class TicTacToeTests(unittest.TestCase):
    def test_the_robot_does_not_lose_with_either_mark(self):
        for robot, human in ((O, X), (X, O)):
            with self.subTest(robot=robot):
                visited = set()

                def play(board, turn):
                    if board in visited:
                        return
                    visited.add(board)
                    if outcome(board):
                        self.assertNotEqual(outcome(board), human)
                        return
                    if turn == robot:
                        play(with_move(board, robot_move(board, robot), robot), human)
                    else:
                        for spot, value in enumerate(board):
                            if not value:
                                play(with_move(board, spot, human), robot)

                play(EMPTY, X)
                self.assertGreater(len(visited), 25)

    def test_every_level_takes_a_win_and_only_plays_free_cells(self):
        board = (O, O, "", X, X, "", "", "", "")
        for level in LEVELS:
            for seed in range(20):
                self.assertEqual(robot_move(board, O, level, Random(seed)), 2)
        for level in LEVELS:
            for seed in range(40):
                board = (X, "", O, "", X, "", "", "", "")
                spot = robot_move(board, O, level, Random(seed))
                self.assertEqual(board[spot], "")

    def test_medium_and_hard_block_but_easy_does_not_always(self):
        board = (X, X, "", "", O, "", "", "", "")
        for level in (MEDIUM, HARD):
            for seed in range(20):
                self.assertEqual(robot_move(board, O, level, Random(seed)), 2)
        self.assertGreater({robot_move(board, O, EASY, Random(seed)) for seed in range(60)} - {2}, set())

    def test_easy_varies_its_moves_and_the_level_is_the_default_for_hard(self):
        self.assertGreater(len({robot_move(EMPTY, O, EASY, Random(seed)) for seed in range(60)}), 4)
        self.assertEqual(robot_move(EMPTY, O), robot_move(EMPTY, O, HARD))

    def test_easy_and_medium_can_be_beaten_but_hard_cannot(self):
        def best_human_result(level, seed):
            rng = Random(seed)

            def play(board, turn):
                result = outcome(board)
                if result:
                    return result
                if turn == O:
                    return play(with_move(board, robot_move(board, O, level, rng), O), X)
                free = [i for i in range(9) if not board[i]]
                # A perfect human always picks the best-scoring move.
                best = min(free, key=lambda i: score(with_move(board, i, X), O))
                return play(with_move(board, best, X), O)

            return play(EMPTY, X)

        for level in (EASY, MEDIUM):
            wins = sum(best_human_result(level, seed) == X for seed in range(200))
            self.assertGreater(wins, 0, level)
        self.assertEqual(sum(best_human_result(HARD, seed) == X for seed in range(20)), 0)

    def test_camera_reads_known_cells_and_rejects_changed_or_ambiguous_marks(self):
        base = rectify(camera_view({}))
        contents = {"A1":X, "B2":O, "C3":X, "Reserve 2":O, "Reserve 4":UNKNOWN}
        view = rectify(camera_view(contents))
        self.assertIs(view.layout, STANDARD_MAT)
        position = read_position(view.grey, base.grey, view.layout)
        self.assertEqual(position, Position((X,"","","",O,"","","",X), ("",O,"",UNKNOWN,"")))
        self.assertEqual(human_change(EMPTY, with_move(EMPTY, 4, X)), 4)
        with self.assertRaises(ValueError):
            human_change(EMPTY, position.board)

    def test_paper_mat_reads_both_reserve_banks(self):
        base = rectify(camera_view({}, layout=PAPER_MAT))
        contents = {"A1":X, "C3":O, "X2":X, "X3":X, "O1":O, "O3":O}
        view = rectify(camera_view(contents, layout=PAPER_MAT))
        self.assertIs(view.layout, PAPER_MAT)
        position = read_position(view.grey, base.grey, view.layout)
        self.assertEqual(position, Position((X,"","","","","","","",O), ("",X,X,"","",O,"",O,"","")))
        self.assertEqual(human_change(EMPTY, with_move(EMPTY, 4, O), O), 4)
        for mark in (X, O):
            ys = [PAPER_MAT.positions[slot][1] for slot in PAPER_MAT.bank(mark)]
            self.assertEqual(np.diff(ys).tolist(), [30] * 4)

    def test_clear_check_detects_an_obstruction_between_the_cells(self):
        for layout in (PAPER_MAT, STANDARD_MAT):
            with self.subTest(layout=layout.label):
                reserve = layout.bank(O)[1]
                base = rectify(camera_view({}, layout=layout))
                rgb = camera_view({"A1": X, reserve: O}, layout=layout)
                clear = rectify(rgb)
                position = read_position(clear.grey, base.grey, layout)
                self.assertTrue(mat_clear(clear, base, position))

                # The hand is visible between the cells even though the pieces still read correctly.
                cv2.ellipse(rgb, (325, 166), (8, 15), -15, 0, 360, (190, 144, 115), -1)
                blocked = rectify(rgb)
                self.assertEqual(read_position(blocked.grey, base.grey, layout), position)
                self.assertFalse(mat_clear(blocked, base, position))

    def test_solid_black_circles_read_as_well_as_rings_at_any_camera_angle(self):
        contents = {"paper": {"A1": X, "B2": O, "C3": X, "X2": X, "X5": X, "O1": O, "O4": O},
                    "A3": {"A1": X, "B2": O, "C3": X, "X2": X, "X5": X, "O1": O, "O4": O}}
        expected_board = (X, "", "", "", O, "", "", "", X)
        for layout, key in ((PAPER_MAT, "paper"), (A3_MAT, "A3")):
            for turn, name in ((None, "as printed"), (cv2.ROTATE_180, "camera behind the mat"),
                               (cv2.ROTATE_90_CLOCKWISE, "turned a quarter")):
                with self.subTest(f"{layout.label} {name}"):
                    def view(items, turn=turn):
                        image = camera_view(items, layout=layout, solid=True)
                        return image if turn is None else cv2.rotate(image, turn)

                    base = rectify(view({}))
                    played = rectify(view(contents[key]))
                    self.assertIs(played.layout, layout)
                    position = read_position(played.grey, base.grey, layout)
                    self.assertEqual(position.board, expected_board)
                    expected_reserve = tuple(contents[key].get(slot, "") for slot in layout.reserve)
                    self.assertEqual(position.reserve, expected_reserve)
                    self.assertTrue(mat_clear(played, base, position))

    def test_solid_circles_still_show_an_obstruction_and_an_empty_mat_reads_empty(self):
        for layout in (PAPER_MAT, A3_MAT):
            with self.subTest(layout.label):
                base = rectify(camera_view({}, layout=layout, solid=True))
                self.assertEqual(read_position(base.grey, base.grey, layout),
                                 Position(EMPTY, ("",) * len(layout.reserve)))
                rgb = camera_view({"A1": X}, layout=layout, solid=True)
                clear = rectify(rgb)
                position = read_position(clear.grey, base.grey, layout)
                self.assertTrue(mat_clear(clear, base, position))
                cv2.ellipse(rgb, (325, 166), (8, 15), -15, 0, 360, (190, 144, 115), -1)
                blocked = rectify(rgb)
                self.assertEqual(read_position(blocked.grey, base.grey, layout), position)
                self.assertFalse(mat_clear(blocked, base, position))

    def test_the_compact_mat_is_centred_with_the_circle_and_marker_sizes_unchanged(self):
        layout = COMPACT_MAT
        radius = 11.725
        xs = [x for x, _ in layout.positions.values()]
        ys = [y for _, y in layout.positions.values()]
        # The grid and both banks are centred on the sheet, and the banks are centred on the grid.
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, COMPACT_CENTRE[0])
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, COMPACT_CENTRE[1])
        for bank in (layout.cross_bank, layout.nought_bank):
            self.assertAlmostEqual(sum(layout.positions[name][1] for name in bank) / 5, COMPACT_CENTRE[1])
        self.assertAlmostEqual(layout.park[0], COMPACT_CENTRE[0])
        # The markers are symmetric about the centre and 16 mm, as on the printed marker cards.
        anchors = list(layout.anchors.values())
        self.assertEqual(layout.anchor_size, STANDARD_MAT.anchor_size)
        self.assertEqual(layout.anchor_size, PAPER_MAT.anchor_size)
        self.assertEqual({(round(2 * COMPACT_CENTRE[0] - x, 6), round(2 * COMPACT_CENTRE[1] - y, 6)) for x, y in anchors},
                         {(round(x, 6), round(y, 6)) for x, y in anchors})
        # Pieces and the Park ring are in reach, and a marker keeps 3 mm clear of every circle and the grid.
        self.assertLessEqual(max(dist(layout.park, p) for p in layout.positions.values()), layout.park_limit)
        grid = (COMPACT_CENTRE[0] - 81 - 0.7, COMPACT_CENTRE[1] - 82.5 - 0.7, COMPACT_CENTRE[0] + 81 + 0.7, COMPACT_CENTRE[1] + 82.5 + 0.7)
        for x, y in anchors:
            half = layout.anchor_size / 2
            for cx, cy in layout.positions.values():
                nearest = dist((cx, cy), (min(max(cx, x - half), x + half), min(max(cy, y - half), y + half)))
                self.assertGreaterEqual(nearest - radius, 3, "a marker is too close to a circle")
            self.assertTrue(x + half + 3 <= grid[0] or x - half - 3 >= grid[2] or y + half + 3 <= grid[1]
                            or y - half - 3 >= grid[3], "a marker is too close to the grid")

    def test_every_layout_has_its_own_marker_ids_and_none_collide_with_the_block_lab(self):
        from dobot_studio.blocks import ANCHORS as BLOCK_ANCHORS
        from dobot_studio.tictactoe import MAT_LAYOUTS
        seen = {}
        for layout in MAT_LAYOUTS:
            for marker in layout.anchors:
                self.assertNotIn(marker, seen, f"marker {marker} is used by {layout.label} and {seen.get(marker)}")
                self.assertNotIn(marker, BLOCK_ANCHORS)
                self.assertNotIn(marker, range(10))
                self.assertLess(marker, 50)
                seen[marker] = layout.label
        # What was printed keeps its size and IDs.
        self.assertEqual((sorted(STANDARD_MAT.anchors), STANDARD_MAT.anchor_size), ([44, 45, 46, 47], 16))
        self.assertEqual((sorted(PAPER_MAT.anchors), PAPER_MAT.anchor_size), ([36, 37, 38, 39], 16))
        self.assertEqual((sorted(A3_MAT.anchors), A3_MAT.anchor_size), ([32, 33, 34, 35], 20))

    def test_compact_mat_reads_both_banks_with_solid_circles_at_any_camera_angle(self):
        contents = {"A1": X, "B2": O, "C3": X, "X1": X, "X5": X, "O2": O, "O4": O}
        for turn, name in ((None, "as printed"), (cv2.ROTATE_180, "camera behind the mat"), (cv2.ROTATE_90_CLOCKWISE, "turned")):
            with self.subTest(name):
                def view(items, turn=turn):
                    image = camera_view(items, layout=COMPACT_MAT, solid=True)
                    return image if turn is None else cv2.rotate(image, turn)

                base = rectify(view({}))
                played = rectify(view(contents))
                self.assertIs(played.layout, COMPACT_MAT)
                position = read_position(played.grey, base.grey, COMPACT_MAT)
                self.assertEqual(position.board, (X, "", "", "", O, "", "", "", X))
                self.assertEqual(position.reserve, tuple(contents.get(slot, "") for slot in COMPACT_MAT.reserve))
                self.assertTrue(mat_clear(played, base, position))

    def test_compact_mat_detects_a_hand_over_a_reserve_bank_and_a_marker_is_not_mistaken_for_another_mat(self):
        base = rectify(camera_view({}, layout=COMPACT_MAT, solid=True))
        rgb = camera_view({"A2": X}, layout=COMPACT_MAT, solid=True)
        position = read_position(rectify(rgb).grey, base.grey, COMPACT_MAT)
        self.assertTrue(mat_clear(rectify(rgb), base, position))
        # A hand over the left edge of the X bank, which lies at the edge of the marker rectangle.
        point = np.float32([[COMPACT_MAT.positions["X3"]]]) * DENSITY
        x, y = cv2.perspectiveTransform(point, np.linalg.inv(rectify(rgb).matrix))[0, 0]
        cv2.circle(rgb, (round(x) - 3, round(y)), 9, (190, 144, 115), -1)
        blocked = rectify(rgb)
        self.assertEqual(read_position(blocked.grey, base.grey, COMPACT_MAT).board, position.board)
        self.assertFalse(mat_clear(blocked, base, position))

    def test_a3_mat_reads_40_mm_pieces_across_the_wide_layout(self):
        base = rectify(camera_view({}, layout=A3_MAT))
        rgb = camera_view({"A3": X, "C1": O, "X1": X, "O5": O}, layout=A3_MAT)
        view = rectify(rgb)
        self.assertIs(view.layout, A3_MAT)
        self.assertEqual(view.grey.shape, (297 * DENSITY, 420 * DENSITY))
        position = read_position(view.grey, base.grey, A3_MAT)
        self.assertEqual(position.board, with_move(with_move(EMPTY, 2, X), 6, O))
        self.assertEqual(position.reserve, (X, "", "", "", "", "", "", "", "", O))
        self.assertTrue(mat_clear(view, base, position))

        park = np.float32([[A3_PARK]]) * DENSITY
        x, y = cv2.perspectiveTransform(park, np.linalg.inv(view.matrix))[0, 0]
        cv2.circle(rgb, (round(x), round(y)), 8, (190, 144, 115), -1)
        blocked = rectify(rgb)
        self.assertEqual(read_position(blocked.grey, base.grey, A3_MAT), position)
        self.assertFalse(mat_clear(blocked, base, position))

    def test_turn_delay_restarts_for_changes_obstructions_and_missing_frames(self):
        delay = TurnDelay()
        first = Position(with_move(EMPTY, 0, X), ())
        second = Position(with_move(EMPTY, 3, X), ())
        self.assertEqual(delay.remaining(first, 10), 1.5)
        self.assertEqual(delay.remaining(first, 10.5), 1)
        self.assertEqual(delay.remaining(second, 10.75), 1.5)
        self.assertEqual(delay.remaining(second, 11.75), 1.5)

        delay.reset()  # Obstruction encountered before the move.
        self.assertEqual(delay.remaining(second, 12), 1.5)
        self.assertEqual(delay.remaining(second, 12.5), 1)
        self.assertEqual(delay.remaining(second, 13), 0.5)
        self.assertEqual(delay.remaining(second, 13.5), 0)

    def test_long_pick_and_place_can_go_via_the_taught_clearance_point(self):
        arm = Magician.__new__(Magician)
        actions = []
        park = Pose(200,0,70,0)
        pick = Pose(195,90,40,0)
        drop = Pose(210,-85,40,0)
        arm.check_alarms = lambda: None
        arm.pose = lambda: park
        arm._run = lambda command, params, pose, stop, timeout, speed=None: actions.append(pose)
        arm.set_suction = lambda enabled: actions.append(enabled)
        with self.assertRaises(RobotError):
            arm.sort_chip(pick, drop, park, Event())
        arm.sort_chip(pick, drop, park, Event(), via_park=True)
        self.assertEqual(actions[4], park)
        self.assertEqual(actions.count(park), 2)
        self.assertTrue(actions.index(True) < actions.index(park) < actions.index(False))

    def test_a3_transfer_splits_long_clearance_legs_at_park_height(self):
        arm = Magician.__new__(Magician)
        moves = []
        suction = []
        park = Pose(*A3_PARK, 70, 0)
        pick = Pose(*A3_MAT.positions["X1"], 40, 0)
        drop = Pose(*A3_MAT.positions["C3"], 40, 0)
        arm.check_alarms = lambda: None
        arm.pose = lambda: park
        arm._run = lambda command, params, pose, stop, timeout, speed=None: moves.append(pose)
        arm.set_suction = lambda enabled: suction.append((enabled, moves[-1]))
        arm.sort_chip(pick, drop, park, Event(), via_park=True)
        self.assertEqual(moves[0], Pose((park.x+pick.x)/2, (park.y+pick.y)/2, park.z, park.r))
        self.assertEqual(moves[-1], park)
        self.assertEqual(suction, [(True, pick), (False, drop)])
        self.assertTrue(all(dist(a.xyz(), b.xyz()) <= TRANSFER_SEGMENT_MM
                            for a, b in zip((park, *moves), moves)))


if __name__ == "__main__":
    unittest.main()
