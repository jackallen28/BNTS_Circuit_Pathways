from threading import Event
import unittest

import cv2
import numpy as np

from dobot_studio.learning import SYMBOL, Examples, new_symbol_descriptor, symbol_features, train
from dobot_studio.robot import Magician, Pose, RobotError
from dobot_studio.tabletop import Calibration, find_chips, inspect_assembly, same_chip


def calibration():
    return Calibration(((90, 405), (550, 405), (320, 45)),
                       (Pose(185, -55, 35, 0), Pose(185, 55, 35, 0), Pose(267, 0, 35, 0)))


class TabletopTests(unittest.TestCase):
    def test_find_and_calibrate_two_coloured_chips(self):
        empty = np.zeros((480, 640, 3), dtype=np.uint8) + 30
        view = empty.copy()
        cv2.circle(view, (270, 260), 25, (227, 15, 25), -1)
        cv2.circle(view, (365, 300), 25, (15, 50, 225), -1)
        cv2.circle(view, (50, 260), 20, (227, 15, 25), -1)
        cal = calibration()
        chips = find_chips(view, empty, cal, {"Red": "A", "Blue": "B"})
        self.assertEqual([(chip.label, chip.bin_name) for chip in chips], [("Red", "A"), ("Blue", "B")])
        self.assertTrue(same_chip(chips[0], chips[0]))
        self.assertGreater(chips[0].area_mm2, 0)
        pose = cal.pick((320, 285), 0)
        self.assertAlmostEqual(pose.x, 185 + 82/3)
        self.assertAlmostEqual(pose.y, 0)
        self.assertFalse(cal.contains_robot(Pose(140, 0, 50, 0)))
        with self.assertRaises(ValueError):
            cal.pick((50, 50), 0)

    def test_trained_printed_label_routes_a_tabletop_chip(self):
        descriptor = new_symbol_descriptor()
        card = np.full((128, 128, 3), 238, dtype=np.uint8)
        blank = symbol_features(card, (0, 0, 128), descriptor)[0]
        cv2.putText(card, "1", (43, 97), cv2.FONT_HERSHEY_SIMPLEX, 2.7, (10, 10, 10), 9)
        one = symbol_features(card, (0, 0, 128), descriptor)[0]
        classes = {"Neutral": Examples("No action", [blank.tolist() for _ in range(8)]),
                   "One": Examples("Position B", [one.tolist() for _ in range(8)])}
        learner, _, _ = train(SYMBOL, classes)
        empty = np.full((480, 640, 3), 25, dtype=np.uint8)
        view = empty.copy()
        view[230:358, 256:384] = card
        chips = find_chips(view, empty, calibration(), None, learner, descriptor)
        self.assertEqual([(chip.label, chip.bin_name) for chip in chips], [("One", "B")])

    def test_inspection_flags_missing_and_extra_zones(self):
        empty = np.zeros((180, 180, 3), dtype=np.uint8)
        expected = empty.copy()
        current = empty.copy()
        expected[8:44, 8:44] = [200, 40, 40]
        current[130:170, 128:168] = [30, 210, 180]
        self.assertEqual(inspect_assembly(current, expected, empty),
                         [("A1", "Possible missing material"), ("C3", "Possible extra material")])
        self.assertEqual(inspect_assembly(expected, expected, empty), [])

    def test_transfer_goes_via_clearance_and_turns_suction_off_at_the_bin(self):
        park = Pose(150, 0, 70, 0)
        pick = Pose(200, 0, 35, 0)
        drop = Pose(165, 55, 40, 0)
        actions = []
        arm = Magician.__new__(Magician)
        arm.check_alarms = lambda: None
        arm.pose = lambda: park
        arm._run = lambda command, params, target, stop, timeout: actions.append(target)
        arm.set_suction = lambda enabled: actions.append(enabled)
        self.assertEqual(arm.sort_chip(pick, drop, park, Event()), park)
        self.assertEqual(actions, [
            Pose(200, 0, 70, 0), pick, True, Pose(200, 0, 70, 0),
            Pose(165, 55, 70, 0), drop, False, Pose(165, 55, 70, 0), park,
        ])
        arm.pose = lambda: pick
        with self.assertRaises(RobotError):
            arm.sort_chip(pick, drop, park, Event())


if __name__ == "__main__":
    unittest.main()
