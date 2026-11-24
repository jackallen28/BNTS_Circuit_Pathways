"""Jogging and travelling, against a fake Dobot that speaks the real serial protocol."""
from threading import Event, Timer
import unittest

from dobot_studio.robot import JOG_LIMIT_MM, Magician, MotionStopped, Pose, RobotError, TRANSFER_SEGMENT_MM
from tests.fake_dobot import FakeDobot


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.dobot = FakeDobot()
        self.dobot.start()
        self.dobot.pose = [220.0, 0.0, 40.0, 0.0]
        self.robot = Magician(self.dobot.path)
        self.addCleanup(self.close)

    def close(self):
        self.robot.close()
        self.dobot.alive = False

    def test_a_jog_moves_the_tool_by_the_step_and_nothing_else(self):
        pose = self.robot.jog((10, -5, 3), Event())
        self.assertTrue(pose.near(Pose(230, -5, 43, 0)), pose)
        pose = self.robot.jog((0, 0, -3), Event())
        self.assertTrue(pose.near(Pose(230, -5, 40, 0)), pose)

    def test_a_jog_larger_than_the_step_limit_is_refused_before_anything_moves(self):
        moved = len(self.dobot.log)
        with self.assertRaises(RobotError):
            self.robot.jog((JOG_LIMIT_MM + 1, 0, 0), Event())
        self.assertEqual(self.dobot.pose, [220.0, 0.0, 40.0, 0.0])
        self.assertLessEqual(len(self.dobot.log) - moved, 0)

    def test_points_the_arm_cannot_reach_or_that_are_too_low_are_refused(self):
        for target in (Pose(50, 0, 40, 0), Pose(400, 0, 40, 0), Pose(220, 0, -200, 0), Pose(220, 0, 400, 0),
                       Pose(float("nan"), 0, 40, 0)):
            with self.subTest(target=target):
                with self.assertRaises(RobotError):
                    self.robot.check_reach(target)
        self.robot.check_reach(Pose(220, 0, -40, 0))
        with self.assertRaises(RobotError):
            self.robot.check_reach(Pose(220, 0, -40, 0), floor=-20)

    def test_a_jog_that_would_leave_the_safe_area_does_not_move(self):
        self.dobot.pose = [305.0, 0.0, 40.0, 0.0]
        with self.assertRaises(RobotError):
            self.robot.jog((10, 0, 0), Event())
        self.assertEqual(self.dobot.pose[0], 305.0)

    def test_travel_visits_every_point_in_order_and_reports_each(self):
        arrived = []
        path = [Pose(220, 60, 60, 0), Pose(240, -40, 40, 0), Pose(200, 0, 40, 0)]
        pose = self.robot.travel(path, Event(), arrived=lambda index, goal: arrived.append((index, goal)))
        self.assertEqual([index for index, _ in arrived], [0, 1, 2])
        self.assertTrue(pose.near(path[-1]))

    def test_a_long_leg_is_split_so_no_single_move_exceeds_the_limit(self):
        self.dobot.pose = [150.0, -150.0, 40.0, 0.0]
        self.dobot.log.clear()
        self.robot.travel([Pose(150, 150, 40, 0)], Event())
        from dobot_studio import robot
        import struct
        moves = [struct.unpack("<B4f", params)[1:3] for command, ctrl, params in self.dobot.log if command == robot.MOVE]
        self.assertGreaterEqual(len(moves), 2)
        previous = (150.0, -150.0)
        for x, y in moves:
            self.assertLessEqual(((x - previous[0]) ** 2 + (y - previous[1]) ** 2) ** 0.5, TRANSFER_SEGMENT_MM + 0.5)
            previous = (x, y)

    def test_a_stop_ends_the_journey_where_it_is_and_clears_the_queue(self):
        stop = Event()
        Timer(0.25, stop.set).start()
        with self.assertRaises(MotionStopped):
            self.robot.travel([Pose(220, 120, 40, 0), Pose(220, -120, 40, 0)], stop, speed=25)
        self.assertFalse(self.dobot.running)
        self.assertEqual(self.dobot.queue, [])
        self.assertLess(self.dobot.pose[1], 120)

    def test_travel_checks_the_whole_path_before_moving(self):
        with self.assertRaises(RobotError):
            self.robot.travel([Pose(220, 40, 40, 0), Pose(500, 0, 40, 0)], Event())
        self.assertEqual(self.dobot.pose, [220.0, 0.0, 40.0, 0.0])


if __name__ == "__main__":
    unittest.main()
