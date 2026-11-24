from fractions import Fraction
import unittest

import cv2
import numpy as np

from dobot_studio.block_vision import anchors_stable, calibrate, locate, square
from dobot_studio.blocks import ANCHORS, CHALLENGES, LEFT_BASE, UPPER, BlockPlan, block_colour, demo_scene, exposed, goals
from dobot_studio.equations import evaluate, split_chips
from dobot_studio.microbit_link import jog, parse_frame
from dobot_studio.robot import GRIPPER, GRIPPER_TOOL, SUCTION, SUCTION_TOOL, WRITE, Magician, Pose, RobotError
from dobot_studio.tabletop import Chip
from dobot_studio.teach_program import read_path


class LabProgramsTests(unittest.TestCase):
    def test_challenges_only_move_exposed_blocks_and_reach_their_goals(self):
        for challenge, count in zip(CHALLENGES, (5, 8, 16)):
            with self.subTest(challenge=challenge):
                board, plan = demo_scene(challenge), BlockPlan(challenge)
                transfers = 0
                while item := plan.next_transfer(board):
                    self.assertTrue(exposed(board, item.source))
                    self.assertNotIn(item.target, board)
                    del board[item.source]
                    board[item.target] = item.marker
                    plan.confirm(item, board)
                    transfers += 1
                    self.assertLessEqual(transfers, count)
                self.assertEqual(transfers, count)
                for slot, expected in goals(challenge).items():
                    self.assertIn(slot, board)
                    if expected:
                        self.assertEqual(block_colour(board[slot]), expected)

    def test_two_camera_planes_identify_a_top_layer_even_when_rotated(self):
        model = (
            np.array([[2.4, -0.06, 300], [-0.01, -1.9, 295], [0.0005, 0.0015, 1]]),
            np.array([[2.6, -0.06, 303], [-0.01, -2.1, 264], [0.0005, 0.0015, 1]]),
        )

        def projected(matrix, x, y):
            return cv2.perspectiveTransform(np.array([square(x, y)], np.float32), matrix)[0]

        references = [{marker: projected(matrix, x, y) for marker, (x, y) in ANCHORS.items()}
                      for matrix in model]
        planes = {i: calibrate(ref) for i, ref in enumerate(references)}
        self.assertTrue(anchors_stable(references[0], planes[0]))
        self.assertFalse(anchors_stable(references[1], planes[0]))
        upper = UPPER[LEFT_BASE[0]]
        observed = {**references[0], 5: np.roll(projected(model[1], upper.x, upper.y), 2, axis=0)}
        result, errors = locate(observed, planes)
        self.assertFalse(errors)
        self.assertEqual(result, {upper: 5})
        observed[6] = projected(model[0], 60, 20)
        self.assertTrue(locate(observed, planes)[1])

    def test_equations_are_exact_and_use_precedence(self):
        self.assertEqual(evaluate(["1", "2", "plus", "4", "×", "2", "="])[1], 20)
        self.assertEqual(evaluate(["3", "minus", "7"])[1], -4)
        self.assertEqual(evaluate(["5", "divide", "2"])[1], Fraction(5, 2))
        with self.assertRaises(ValueError):
            evaluate(["3", "/", "0"])
        with self.assertRaises(ValueError):
            evaluate(["1", "Unknown", "2"])
        with self.assertRaises(ValueError):
            evaluate(["2", "equals", "2"])
        def chip(x, y, label):
            return Chip((x,y), (x-10,y-10,20,20), label, None, 100)
        rows, bank = split_chips([chip(30,40,"+"), chip(10,40,"1"), chip(50,41,"2"), chip(40,100,"3")], 75)
        self.assertEqual([c.label for c in rows[0]], ["1", "+", "2"])
        self.assertEqual(bank[0].label, "3")

    def test_tool_commands_and_microbit_path_validation(self):
        arm = Magician.__new__(Magician)
        calls = []
        arm._request = lambda *args: calls.append(args)
        arm.set_attachment(SUCTION_TOOL, True)
        arm.set_attachment(GRIPPER_TOOL, False)
        self.assertEqual(calls, [(SUCTION, WRITE, b"\1\1"), (GRIPPER, WRITE, b"\1\0")])
        with self.assertRaises(RobotError):
            arm.set_attachment("unsupported", True)
        self.assertEqual(parse_frame(b"DT1,200,-400,1100,1,-\n").x, 200)
        self.assertIsNone(parse_frame(b"DT1,9999,0,0,0,A\n"))
        origin = Pose(200, 0, 40, 0)
        self.assertEqual(jog(origin, origin, (200, -300)), Pose(203,-3,40,0))
        self.assertIsNone(jog(Pose(232,0,40,0), origin, (500,0)))
        content = {"version": 1, "tool": GRIPPER_TOOL, "origin": list(origin.wire()),
                   "steps": [["tool", True], ["move", [203,0,40,0]]]}
        self.assertEqual(read_path(content)[1], GRIPPER_TOOL)
        content["steps"].append(["move", [232,0,40,0]])
        with self.assertRaises(ValueError):
            read_path(content)


if __name__ == "__main__":
    unittest.main()
