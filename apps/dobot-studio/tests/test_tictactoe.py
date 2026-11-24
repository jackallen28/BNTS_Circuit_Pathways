from math import dist
from random import Random
from threading import Event
import unittest

import cv2
import numpy as np

from dobot_studio.robot import Magician, Pose, RobotError, TRANSFER_SEGMENT_MM
from dobot_studio.tictactoe import (
    A3_MAT, A3_PARK, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, EMPTY, NOUGHT_INNER,
    NOUGHT_OUTER, O, PAPER_MAT, PIECE_RADIUS, STANDARD_MAT, UNKNOWN, X,
    EASY, HARD, LEVELS, MEDIUM, human_change, outcome, robot_move, score, with_move,
)
from dobot_studio.tictactoe_program import TurnDelay
from dobot_studio.tictactoe_vision import DENSITY, Position, mat_clear, read_position, rectify


def camera_view(contents, shift=0, layout=STANDARD_MAT):
    """An angled, 640 px camera view of the mat and the supplied glyphs."""
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
        cx, cy = round(x*density), round(y*density)
        if layout is STANDARD_MAT:
            cv2.circle(rgb, (cx, cy), round(13.6*density), (31, 49, 58), -1, cv2.LINE_AA)
        else:
            cv2.circle(rgb, (cx, cy), round(10.9*piece_density), (34, 54, 74),
                       round(1.65*piece_density), cv2.LINE_AA)
        glyph = contents.get(label)
        if not glyph:
            continue
        cv2.circle(rgb, (cx, cy), round(PIECE_RADIUS*piece_density), (230, 233, 225), -1, cv2.LINE_AA)
        if glyph == O:
            cv2.circle(rgb, (cx, cy), round(NOUGHT_OUTER*piece_density), (23, 29, 34), -1, cv2.LINE_AA)
            cv2.circle(rgb, (cx, cy), round(NOUGHT_INNER*piece_density), (230, 233, 225), -1, cv2.LINE_AA)
        elif glyph == X:
            for sign in (-1, 1):
                theta = np.radians(24 + sign*45)
                vx, vy = np.cos(theta), np.sin(theta)
                wx, wy = -vy, vx
                vertices = [(round(cx + (vx*u*CROSS_HALF_LENGTH + wx*v*CROSS_HALF_WIDTH)*piece_density),
                             round(cy + (vy*u*CROSS_HALF_LENGTH + wy*v*CROSS_HALF_WIDTH)*piece_density))
                            for u,v in ((-1,-1), (1,-1), (1,1), (-1,1))]
                cv2.fillConvexPoly(rgb, np.asarray(vertices), (23,29,34), cv2.LINE_AA)
        elif glyph == UNKNOWN:
            cv2.rectangle(rgb, (cx-16,cy-16), (cx+16,cy+16), (23,29,34), -1)
    h, w = rgb.shape[:2]
    src = np.float32([(0, 0), (w-1, 0), (w-1, h-1), (0, h-1)])
    if layout is A3_MAT:
        dst = np.float32([(62, 53), (590, 62), (584, 432), (47, 411)])
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
        arm._run = lambda command, params, pose, stop, timeout: actions.append(pose)
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
        arm._run = lambda command, params, pose, stop, timeout: moves.append(pose)
        arm.set_suction = lambda enabled: suction.append((enabled, moves[-1]))
        arm.sort_chip(pick, drop, park, Event(), via_park=True)
        self.assertEqual(moves[0], Pose((park.x+pick.x)/2, (park.y+pick.y)/2, park.z, park.r))
        self.assertEqual(moves[-1], park)
        self.assertEqual(suction, [(True, pick), (False, drop)])
        self.assertTrue(all(dist(a.xyz(), b.xyz()) <= TRANSFER_SEGMENT_MM
                            for a, b in zip((park, *moves), moves)))


if __name__ == "__main__":
    unittest.main()
