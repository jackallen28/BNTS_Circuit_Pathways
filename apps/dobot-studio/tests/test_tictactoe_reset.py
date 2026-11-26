"""The Dobot returns pieces to the reserve at the end of a game."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from time import monotonic, sleep
from types import SimpleNamespace
import tkinter as tk
import unittest

from dobot_studio.matcalib import MatCalibration
from dobot_studio.robot import Pose
from dobot_studio.tictactoe import (
    A3_MAT, CELLS, COMPACT_MAT, EMPTY, MAT_LAYOUTS, O, PAPER_MAT, STANDARD_MAT, X, describe_slot, outcome, tidy_plan,
    with_move,
)
from dobot_studio.tictactoe_vision import Position
from tests.test_matcalib import TruePlacement

FINISHED = (X, O, "", X, O, "", X, "", "")   # X wins the left column
assert outcome(FINISHED) == X


class TidyPlanTests(unittest.TestCase):
    def test_two_bank_mats_return_both_marks_to_their_own_banks(self):
        for layout in (PAPER_MAT, A3_MAT):
            moves, left = tidy_plan(layout, FINISHED, ("",) * len(layout.reserve), O)
            self.assertEqual(left, 0)
            self.assertEqual([(CELLS[c], m, slot) for c, m, slot in moves],
                             [("A1", X, "X1"), ("A2", O, "O1"), ("B1", X, "X2"),
                              ("B2", O, "O2"), ("C1", X, "X3")])

    def test_single_bank_mat_returns_only_the_dobots_pieces(self):
        moves, left = tidy_plan(STANDARD_MAT, FINISHED, ("",) * 5, O)
        self.assertEqual([(m, slot) for _, m, slot in moves],
                         [(O, "Reserve 1"), (O, "Reserve 2")])
        self.assertEqual(left, 3)
        moves, left = tidy_plan(STANDARD_MAT, FINISHED, ("",) * 5, X)
        self.assertEqual((len(moves), left), (3, 2))

    def test_occupied_slots_are_skipped_and_a_full_bank_is_refused(self):
        reserve = (X, "", "", "", "") + ("",) * 5
        moves, _ = tidy_plan(PAPER_MAT, FINISHED, reserve, O)
        self.assertEqual(moves[0][2], "X2")
        with self.assertRaises(ValueError):
            tidy_plan(PAPER_MAT, FINISHED, (X,) * 5 + ("",) * 5, O)

    def test_an_empty_board_needs_no_moves(self):
        self.assertEqual(tidy_plan(PAPER_MAT, EMPTY, ("",) * 10, O), ([], 0))


def make_root(case):
    """A Tk root that cancels its timers before it is destroyed."""
    root = tk.Tk()
    case.addCleanup(root.destroy)
    case.addCleanup(lambda: root.eval("foreach id [after info] {after cancel $id}"))
    return root


def make_studio(case, root):
    from dobot_studio.app import Studio
    folder = mkdtemp()
    case.addCleanup(rmtree, folder, True)
    return Studio(root, Path("/nonexistent"), Path(folder))


class World:
    """A pretend mat: the fake robot moves pieces and the fake camera reports them."""

    def __init__(self, layout, board):
        self.layout, self.board = layout, board
        self.reserve = ["" for _ in layout.reserve]
        self.moves, self.refuse = [], False
        self.placed = []           # (mark, cell) for every piece the Dobot set down

    def position(self):
        return Position(tuple(self.board), tuple(self.reserve))


class FakeRobot:
    def __init__(self, world, poses):
        # a position is found by where it is on the mat, since the pick depth lowers a pick but not its place
        self.world, self.names = world, {(pose.x, pose.y): name for name, pose in poses.items()}
        self.on_move = None
        self.calls = []
        self.rests = []              # every time the tool was sent to its resting place
        self.call_times = []
        self.speeds = []             # the speeds each move was asked for

    def to_rest(self, rest, stop, speed=None, floor=None):
        self.rests.append((rest, monotonic()))
        return rest

    def sort_chip(self, pick, drop, park, stop, attachment=None, *, via_park=False, **speeds):
        self.speeds.append(speeds)
        self.calls.append((pick, drop, park))
        self.call_times.append(monotonic())
        source, target = self.names[(pick.x, pick.y)], self.names[(drop.x, drop.y)]
        self.world.moves.append((source, target))
        if not self.world.refuse and source in self.world.layout.reserve:       # a piece is fetched from its bank and placed
            slot = self.world.layout.reserve.index(source)
            self.world.placed.append((self.world.reserve[slot], target))
            self.world.board = with_move(tuple(self.world.board), CELLS.index(target), self.world.reserve[slot])
            self.world.reserve[slot] = ""
        elif not self.world.refuse:                                              # a piece is taken back to its bank
            cell = CELLS.index(source)
            slot = self.world.layout.reserve.index(target)
            self.world.reserve[slot] = self.world.board[cell]
            self.world.board = with_move(tuple(self.world.board), cell, "")
        if self.on_move:
            self.on_move()
        return park

    def set_suction(self, enabled):
        pass


class DescribeSlotTests(unittest.TestCase):
    def test_every_position_has_a_plain_english_description_in_both_views(self):
        for layout in MAT_LAYOUTS:
            for label in (*layout.positions, "Park"):
                for far in (False, True):
                    with self.subTest(f"{layout.label} {label} {'Dobot' if far else 'player'}"):
                        text = describe_slot(layout, label, far)
                        self.assertTrue(text.startswith(f"{label}:") and text.endswith("."))

    def test_the_wording_turns_when_seen_from_the_dobots_side(self):
        self.assertEqual(describe_slot(A3_MAT, "A1"), "A1: the top row, left cell.")
        self.assertEqual(describe_slot(A3_MAT, "A1", True), "A1: the bottom row, right cell.")
        self.assertEqual(describe_slot(A3_MAT, "B2"), describe_slot(A3_MAT, "B2", True))
        self.assertEqual(describe_slot(PAPER_MAT, "X1"), "X1: the 1st X reserve circle from the top, on the left.")
        self.assertEqual(describe_slot(PAPER_MAT, "X1", True), "X1: the 5th X reserve circle from the top, on the right.")
        self.assertEqual(describe_slot(PAPER_MAT, "O2"), "O2: the 2nd O reserve circle from the top, on the right.")
        self.assertEqual(describe_slot(STANDARD_MAT, "Reserve 1"),
                         "Reserve 1: the 1st reserve circle from the top, on the right.")

    def test_each_description_names_a_distinct_place(self):
        for layout in (PAPER_MAT, A3_MAT, COMPACT_MAT):
            for far in (False, True):
                texts = [describe_slot(layout, label, far).split(": ", 1)[1] for label in layout.positions]
                self.assertEqual(len(set(texts)), len(texts), "two positions share a description")


@unittest.skipUnless(__import__("os").environ.get("DISPLAY") or __import__("sys").platform == "win32",
                     "needs a display")
class PhysicalResetTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.tictactoe_program import TicTacToeProgram

        self.root = make_root(self)
        self.studio = make_studio(self, self.root)
        self.studio.set_mode(False)
        self.studio.homed = True
        self.program_class = TicTacToeProgram

    def program(self, layout, board, human=X):
        studio = self.studio
        # The arm's calibration, as the setup works it out from the touched points.
        calibration = MatCalibration(layout, TruePlacement(layout).touched())
        poses = calibration.poses()
        self.world = World(layout, board)
        studio.robot = FakeRobot(self.world, poses)
        program = self.program_class(studio)
        self.addCleanup(lambda: program.window.winfo_exists() and program.window.destroy())
        program.wizard.calibration = calibration
        program.poses, program.setup_done = poses, True
        program.at_rest = True                     # the arm is waiting at its resting place, as after setup
        program.reference = SimpleNamespace(layout=layout)
        program.human = program.player_choice.set(human) or human
        program.board = tuple(board)
        program.camera = SimpleNamespace(read=lambda: (SimpleNamespace(timestamp=monotonic()), None),
                                         close=lambda: None)

        def read_frame(sample, _image):
            program.timestamp = program.analysed = sample.timestamp
            position = self.world.position()
            clear = program.busy != "place"
            program.seen = program.seen + 1 if position == program.latest and clear else 1
            program.view_clear = clear
            program.latest = position
            return True

        program._read_frame = read_frame
        program.timestamp = 0
        return program

    def pump(self, program, seconds, until=None):
        end = monotonic() + seconds
        while monotonic() < end:
            self.root.update()
            sleep(0.01)
            if until and until():
                return True
        return until() if until else None

    def finish_game(self, program):
        program.ready = False
        program._announce()

    def test_a_finished_game_is_reset_onto_a_two_bank_mat(self):
        program = self.program(A3_MAT, FINISHED)
        program.ready = True
        program._announce()
        self.assertTrue(program.tidy_pending)
        self.assertTrue(self.pump(program, 15, lambda: not program.tidy_pending and not program.tidying and not program.busy))
        self.assertEqual(self.world.board, EMPTY)
        self.assertEqual(self.world.reserve[:3] + self.world.reserve[5:7], [X, X, X, O, O])
        self.assertEqual(len(self.world.moves), 5)
        self.assertIn("Board reset", program.status.get())
        self.assertEqual(program.board, EMPTY)

    def test_every_pick_and_place_is_at_the_mat_surface_plus_the_thickness_of_a_piece(self):
        for layout in (COMPACT_MAT, A3_MAT):
            with self.subTest(layout.label):
                program = self.program(layout, FINISHED)
                program.ready = True
                program._announce()
                self.assertTrue(self.pump(program, 15, lambda: not program.tidy_pending and not program.tidying and not program.busy))
                calibration = program.calibration
                thickness = 3.2 * layout.piece_scale
                self.assertEqual(len(self.studio.robot.calls), 5)
                for pick, drop, park in self.studio.robot.calls:
                    for pose in (pick, drop):
                        surface = calibration.surface_z(pose.x, pose.y)
                        self.assertAlmostEqual(pose.z - surface, thickness, places=1, msg="a pick or place is at the wrong height")
                    self.assertTrue(12 <= park.z - pick.z <= 75 and 12 <= park.z - drop.z <= 75)

    def test_a_finished_game_is_reset_onto_the_compact_mat(self):
        program = self.program(COMPACT_MAT, FINISHED)
        program.ready = True
        program._announce()
        self.assertTrue(self.pump(program, 15, lambda: not program.tidy_pending and not program.tidying and not program.busy))
        self.assertEqual(self.world.board, EMPTY)
        self.assertEqual(self.world.reserve[:3] + self.world.reserve[5:7], [X, X, X, O, O])
        self.assertIn("Board reset", program.status.get())

    def test_single_bank_mat_leaves_the_players_pieces_for_the_player(self):
        program = self.program(STANDARD_MAT, FINISHED, human=X)
        program.ready = True
        program._announce()
        self.assertTrue(self.pump(program, 15, lambda: not program.tidy_pending and not program.tidying and not program.busy))
        self.assertEqual(self.world.board, (X, "", "", X, "", "", X, "", ""))
        self.assertEqual(self.world.reserve[:2], [O, O])
        self.assertIn("Take your 3 pieces", program.status.get())

    def test_a_turn_is_read_then_thought_about_then_carried_out_from_and_back_to_the_resting_place(self):
        from dobot_studio import tictactoe_program

        program = self.program(COMPACT_MAT, (X,) + ("",) * 8)          # the player has just placed a cross at A1
        program.board = EMPTY                                            # as the game knew it before that move
        program.turn, program.ready = X, True
        program.chosen = None
        self.world.reserve = [""] * 5 + [O] * 5
        seen = []
        original = program.status.set
        program.status.set = lambda text: (seen.append((monotonic(), text)), original(text))[1]
        self.assertTrue(self.pump(program, 12, lambda: bool(self.world.moves)))
        moved = monotonic()
        texts = [text for _, text in seen]
        confirming = next(i for i, text in enumerate(texts) if "Confirming the position" in text)
        thinking = next(i for i, text in enumerate(texts) if "is thinking" in text)
        self.assertLess(confirming, thinking, "the camera reads and confirms the mat before the Dobot thinks")
        thought_at = seen[thinking][0]
        self.assertGreaterEqual(self.studio.robot.call_times[0] - thought_at, tictactoe_program.THINK_SECONDS - 0.2,
                                "and it thinks for a moment before it moves")
        self.assertEqual(len(self.studio.robot.rests), 1, "the tool is taken to rest before the move")
        rest, rested_at = self.studio.robot.rests[0]
        self.assertEqual(rest, program.poses["Rest"])
        self.assertLessEqual(rested_at, self.studio.robot.call_times[0])
        pick, drop, park = self.studio.robot.calls[0]
        self.assertEqual(park, program.poses["Rest"], "the move starts and ends at the resting place, off the mat")
        self.assertEqual(program.board[0], X)
        self.assertIn("is thinking", "".join(texts[thinking:thinking + 1]))

    def test_the_board_can_be_reset_in_the_middle_of_a_game(self):
        from unittest import mock

        program = self.program(A3_MAT, (X, O, X, "", O, "", "", "", ""))
        self.world.reserve = [""] * 10
        program.ready, program.turn = True, X
        with mock.patch("dobot_studio.tictactoe_program.messagebox.askokcancel", return_value=False):
            program.reset_board()
            self.assertTrue(program.ready, "the answer was no, so the game goes on")
        with mock.patch("dobot_studio.tictactoe_program.messagebox.askokcancel", return_value=True):
            program.reset_board()
        self.assertFalse(program.ready, "that game is over")
        self.assertTrue(program.tidy_pending)
        self.assertTrue(self.pump(program, 25, lambda: not program.tidy_pending and not program.tidying and not program.busy))
        self.assertEqual(self.world.board, EMPTY)
        self.assertEqual(program.board, EMPTY)
        self.assertEqual(len(self.world.moves), 4)

    def test_the_board_can_be_cleared_by_hand_without_the_arm_moving(self):
        program = self.program(A3_MAT, (X, O, X, "", O, "", "", "", ""))
        program.ready, program.turn = True, O
        program.cleared_by_hand()
        self.assertFalse(program.ready)
        self.assertEqual((program.board, program.turn), (EMPTY, X))
        self.assertIn("cleared", program.status.get())
        self.pump(program, 0.6)
        self.assertEqual(self.world.moves, [])
        self.assertFalse(program.tidy_pending)

    def test_the_pick_depth_and_the_speed_reach_the_arm(self):
        program = self.program(A3_MAT, FINISHED)
        program.pick_press, program.speed_percent = 2.5, 200.0
        program.speed.set(200)
        program.ready = True
        program._announce()
        self.assertTrue(self.pump(program, 15, lambda: bool(self.world.moves)))
        pick, drop, rest = self.studio.robot.calls[0]
        source = next(name for name, pose in program.poses.items() if (pose.x, pose.y) == (pick.x, pick.y))
        self.assertAlmostEqual(pick.z, program.poses[source].z - 2.5, places=6, msg="the cup goes 2.5 mm deeper to pick")
        self.assertEqual(self.studio.robot.speeds[0], {"speed": 50.0, "travel": 120.0})
        self.pump(program, 1.0, lambda: not program.busy)

    def test_the_new_buttons_and_the_speed_slider_fit_a_720p_screen(self):
        program, window = self.program(A3_MAT, EMPTY), None
        window = program.window
        window.geometry("1050x666+0+0")
        for _ in range(20):
            self.root.update()
        program.side_tabs.select(program.match_tab)
        for _ in range(20):
            self.root.update()

        def inside(widget):
            bottom = widget.winfo_rooty() + widget.winfo_height()
            return widget.winfo_ismapped() and bottom <= window.winfo_rooty() + window.winfo_height()

        for name in ("reset_button", "cleared_button", "release_button", "speed_scale", "stop_button"):
            self.assertTrue(inside(getattr(program, name)), f"{name} is outside the window")

    def test_a_flicker_in_one_frame_does_not_unsettle_the_view(self):
        program = self.program(A3_MAT, EMPTY)
        calm = Position(EMPTY, ("X", "X", "X", "X", "X", "O", "O", "O", "O", "O"))
        flicker = Position(("?",) + EMPTY[1:], calm.reserve)
        for frame in (calm, calm, calm, flicker, calm):
            read = program._consensus(frame)
        self.assertEqual(read, calm, "one odd frame in five changes nothing")
        self.assertEqual(program.unsteady, ("A1",), "but the circle that flickered is known")
        program.recent.clear()
        for frame in (calm, flicker, flicker, flicker, flicker):
            read = program._consensus(frame)
        self.assertEqual(read.board[0], "?", "a change that lasts is a change")

    def test_the_steady_view_says_what_is_wrong_and_does_not_blame_the_wrong_thing(self):
        program = self.program(A3_MAT, EMPTY)
        program.analysed = monotonic()
        program.latest = Position(EMPTY, ("",) * 10)
        program.view_clear, program.seen = False, 1
        with self.assertRaises(ValueError) as caught:
            program._steady()
        self.assertIn("in the way", str(caught.exception))
        self.assertIn("resting place", str(caught.exception), "the arm is the usual cause, and it goes to rest")
        program.view_clear = True
        program.unsteady = ("X1", "O2")
        with self.assertRaises(ValueError) as caught:
            program._steady()
        self.assertIn("steady view", str(caught.exception))
        self.assertIn("X1, O2", str(caught.exception))
        program.seen = 2
        self.assertEqual(program._steady(), program.latest)

    def test_a_new_game_first_takes_the_arm_to_its_resting_place_so_the_camera_can_see_the_mat(self):
        program = self.program(A3_MAT, EMPTY)
        program.at_rest = False                                  # the arm was homed and is somewhere else
        self.world.reserve = [X] * 5 + [O] * 5
        program.new_game()
        self.assertTrue(self.pump(program, 4, lambda: bool(self.studio.robot.rests)))
        self.assertEqual(self.studio.robot.rests[0][0], program.poses["Rest"])
        self.assertIn("resting place", program.status.get() + str(self.studio.robot.rests))
        self.assertTrue(self.pump(program, 6, lambda: program.ready), "and then the game starts by itself")
        self.assertTrue(program.at_rest)

    def test_a_new_game_does_not_move_an_arm_that_is_already_resting(self):
        program = self.program(A3_MAT, EMPTY)
        self.world.reserve = [X] * 5 + [O] * 5
        self.pump(program, 0.8)                                  # the camera has had a look
        program.new_game()
        self.assertTrue(self.pump(program, 6, lambda: program.ready))
        self.assertEqual(self.studio.robot.rests, [])

    def test_the_dobot_can_play_itself_both_sides(self):
        from unittest import mock

        from dobot_studio import tictactoe_program

        program = self.program(A3_MAT, EMPTY)
        self.world.reserve = [X] * 5 + [O] * 5
        program.solo.set(True)
        program.auto_reset.set(False)
        self.assertIn("both", program.roles.get() + "both")
        with mock.patch.object(tictactoe_program, "TURN_DELAY", 0.15), mock.patch.object(tictactoe_program, "THINK_SECONDS", 0.1):
            self.pump(program, 0.6)
            program.new_game()
            self.assertTrue(program.solo_game)
            self.assertIn("both X and O", program.roles.get())
            self.assertTrue(self.pump(program, 90, lambda: not program.ready and not program.busy and not program.checking))
        marks = [mark for mark, _ in self.world.placed]
        self.assertGreaterEqual(len(marks), 5)
        self.assertEqual(marks, [X, O, X, O, X, O, X, O, X][:len(marks)], "the sides take turns, X first")
        self.assertTrue(all(source.startswith(mark) for (source, _), (mark, _) in zip(self.world.moves, self.world.placed)),
                        "each side's piece is fetched from its own bank")
        result = outcome(self.world.board)
        self.assertIsNotNone(result, "the game ran to the end")
        self.assertIn(result, (X, O, "Draw"))
        self.assertTrue(program.status.get().startswith(("Draw", "Dobot (")), program.status.get())

    def test_playing_itself_needs_the_pieces_of_both_banks_and_a_mat_with_two_banks(self):
        program = self.program(A3_MAT, EMPTY)
        program.solo.set(True)
        self.world.reserve = [X] * 5 + [O] * 2 + [""] * 3               # too few noughts
        self.pump(program, 0.8)
        program.new_game()
        self.assertFalse(program.ready)
        self.assertIn("at least 4 O", program.status.get())
        single = self.program(STANDARD_MAT, EMPTY)
        single.solo.set(True)
        single.new_game()
        self.assertFalse(single.ready)
        self.assertIn("X bank and an O bank", single.status.get())

    def test_a_game_with_a_person_is_not_changed_by_the_solo_option_being_there(self):
        program = self.program(A3_MAT, EMPTY)
        self.world.reserve = [X] * 5 + [O] * 5
        self.pump(program, 0.8)
        program.new_game()
        self.assertTrue(program.ready)
        self.assertFalse(program.solo_game)
        self.assertEqual(program.mover, program.dobot)
        self.assertEqual(program.solo_check.cget("state"), "disabled", "it cannot be changed in the middle of a game")

    def test_it_waits_for_a_clear_still_mat_before_moving(self):
        program = self.program(A3_MAT, FINISHED)
        program.ready = True
        program._announce()
        self.pump(program, 0.6)
        self.assertEqual(self.world.moves, [])
        self.assertTrue(program.tidy_pending)

    def test_stop_cancels_the_rest_of_the_reset(self):
        program = self.program(A3_MAT, FINISHED)
        program.ready = True
        program._announce()
        self.studio.robot.on_move = program.stop
        self.pump(program, 6, lambda: bool(self.world.moves))
        self.pump(program, 1.5)
        self.assertEqual(len(self.world.moves), 1)
        self.assertFalse(program.tidy_pending or program.tidying)
        self.assertFalse(self.studio.homed)

    def test_an_unconfirmed_move_stops_the_reset(self):
        program = self.program(A3_MAT, FINISHED)
        self.world.refuse = True
        program.ready = True
        program._announce()
        self.pump(program, 6, lambda: program.checking is not None)
        program.deadline = 0
        self.pump(program, 1.0)
        self.assertEqual(len(self.world.moves), 1)
        self.assertFalse(program.tidying)
        self.assertIn("not confirmed", program.status.get())

    def test_a_full_reserve_bank_is_reported_instead_of_moving(self):
        program = self.program(A3_MAT, FINISHED)
        self.world.reserve = [X] * 5 + [""] * 5
        program.ready = True
        program._announce()
        self.pump(program, 6, lambda: not program.tidy_pending)
        self.assertEqual(self.world.moves, [])
        self.assertFalse(program.tidying)
        self.assertIn("reserve", program.status.get())

    def test_the_option_can_be_switched_off(self):
        program = self.program(A3_MAT, FINISHED)
        program.auto_reset.set(False)
        program.ready = True
        program._announce()
        self.assertFalse(program.tidy_pending)
        program.reset_board()
        self.assertTrue(program.tidy_pending)


@unittest.skipUnless(__import__("os").environ.get("DISPLAY") or __import__("sys").platform == "win32",
                     "needs a display")
class MatGuideTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.tictactoe_program import TicTacToeProgram

        self.root = make_root(self)
        self.studio = make_studio(self, self.root)
        self.studio.set_mode(False)
        self.program = TicTacToeProgram(self.studio)
        self.addCleanup(lambda: self.program.window.winfo_exists() and self.program.window.destroy())
        self.program.reference = SimpleNamespace(layout=A3_MAT)
        self.program.window.geometry("1050x720+0+0")
        self.settle()

    def settle(self):
        for _ in range(15):
            self.root.update()
            sleep(0.01)

    def circle(self, name):
        item = self.program.guide.find_withtag(f"slot:{name}")[0]
        x0, y0, x1, y1 = self.program.guide.coords(item)
        return (x0 + x1) / 2, (y0 + y1) / 2, self.program.guide.itemcget(item, "fill")

    def test_the_position_being_taught_is_named_and_highlighted(self):
        self.program.teaching.set("X3")
        self.settle()
        self.assertEqual(self.program.guide_text.get(), "X3: the 3rd X reserve circle from the top, on the left.")
        self.assertEqual(self.circle("X3")[2], "#ffd997")
        self.assertEqual(self.circle("X4")[2], "#f6faff")
        self.program.teaching.set("Park")
        self.settle()
        self.assertTrue(self.program.guide_text.get().startswith("Park:"))
        self.assertEqual(self.circle("Park")[2], "#ffd997")

    def test_taught_positions_are_marked(self):
        self.program.poses["A1"] = Pose(0, 0, 0, 0)
        self.program.teaching.set("A2")
        self.settle()
        self.assertEqual(self.circle("A1")[2], "#bfeee9")
        self.assertEqual(self.circle("A3")[2], "#f6faff")

    def test_clicking_a_circle_chooses_it_for_checking_and_empty_space_does_nothing(self):
        wizard = self.program.wizard
        wizard.step = 4                       # Check every point
        self.program.teaching.set("A1")
        self.settle()
        x, y, _ = self.circle("O4")
        self.program._guide_click(SimpleNamespace(x=x, y=y))
        self.assertEqual((self.program.teaching.get(), wizard.selected), ("O4", "O4"))
        self.program._guide_click(SimpleNamespace(x=2, y=40))
        self.assertEqual(wizard.selected, "O4")

    def test_while_touching_the_corners_only_a_corner_can_be_chosen_to_touch_again(self):
        from dobot_studio.matcalib import outer_points
        wizard = self.program.wizard
        wizard.step = 3                       # Touch the four corners
        self.settle()
        x, y, _ = self.circle("B2")
        self.program._guide_click(SimpleNamespace(x=x, y=y))
        self.assertIsNone(wizard.redo)
        corner = outer_points(A3_MAT)[2]
        x, y, _ = self.circle(corner)
        self.program._guide_click(SimpleNamespace(x=x, y=y))
        self.assertEqual((wizard.redo, wizard.target()), (corner, corner))

    def test_the_dobots_side_turns_the_map_and_the_wording(self):
        self.program.teaching.set("A1")
        self.settle()
        x, y, _ = self.circle("A1")
        centre = (self.program.guide.winfo_width() / 2, self.program.guide.winfo_height() / 2)
        self.assertIn("top row, left cell", self.program.guide_text.get())
        self.program.dobot_side.set(True)
        self.program._draw_guide(force=True)
        turned_x, turned_y, _ = self.circle("A1")
        self.assertAlmostEqual(turned_x - centre[0], centre[0] - x, delta=1.5)
        self.assertGreater(turned_y, y)
        self.assertIn("bottom row, right cell", self.program.guide_text.get())
        self.assertEqual(self.studio.tictactoe_dobot_side, True)

    def test_every_control_and_the_stop_button_fit_a_720p_screen(self):
        """A 1280 x 720 screen gives the window about 666 px. Nothing may be pushed out of view."""
        program, window = self.program, self.program.window
        window.geometry("1050x666+0+0")
        self.settle()
        self.assertLessEqual(window.winfo_height(), 666)

        def inside(widget):
            bottom = widget.winfo_rooty() + widget.winfo_height()
            return widget.winfo_ismapped() and widget.winfo_rooty() >= window.winfo_rooty() \
                and bottom <= window.winfo_rooty() + window.winfo_height()

        wizard = program.wizard
        program.side_tabs.select(program.side_tabs.tabs()[0])
        for step in range(len(wizard.frames)):
            wizard.step = step
            wizard._show_step()
            self.settle()
            for name in ("heading", "status_label", "back_button", "next_button", "controls", "guide"):
                widget = getattr(wizard, name, None) or getattr(program, name)
                self.assertTrue(inside(widget), f"{name} is outside the window at step {step + 1}")
            for child in wizard.frames[step].winfo_children():
                if not child.winfo_manager():      # a button that only appears when it is needed
                    continue
                self.assertTrue(inside(child), f"a control is outside the window at step {step + 1}")
            self.assertTrue(inside(program.stop_button), f"the stop button is outside the window at step {step + 1}")
        program.side_tabs.select(str(program.match_tab))
        self.settle()
        for name in ("symbol_picker", "level_picker", "new_button", "reset_button", "release_button", "stop_button"):
            self.assertTrue(inside(getattr(program, name)), f"{name} is outside the window")

    def test_the_stop_button_stays_visible_even_if_the_side_panel_grows_too_tall(self):
        program, window = self.program, self.program.window
        window.geometry("1050x666+0+0")
        program.guide.configure(height=1400)      # far more than any screen could hold
        self.settle()
        bottom = program.stop_button.winfo_rooty() + program.stop_button.winfo_height()
        self.assertTrue(program.stop_button.winfo_ismapped())
        self.assertLessEqual(bottom, window.winfo_rooty() + window.winfo_height())

    def test_a_new_game_or_reset_switches_to_the_match_tab(self):
        program = self.program
        self.assertEqual(program.side_tabs.index(program.side_tabs.select()), 0)
        program._show_match()
        self.assertEqual(program.side_tabs.select(), str(program.match_tab))

    def test_every_position_can_be_chosen_on_every_mat(self):
        self.program.wizard.step = 4
        for layout in (PAPER_MAT, A3_MAT, COMPACT_MAT, STANDARD_MAT):
            self.program.reference = SimpleNamespace(layout=layout)
            self.program.teaching.set("A1")
            self.settle()
            for label in (*layout.positions, "Park"):
                x, y, _ = self.circle(label)
                self.program._guide_click(SimpleNamespace(x=x, y=y))
                self.assertEqual(self.program.wizard.selected, label, f"{layout.label} {label}")


@unittest.skipUnless(__import__("os").environ.get("DISPLAY") or __import__("sys").platform == "win32",
                     "needs a display")
class DemoResetTests(unittest.TestCase):
    def test_demo_clears_the_board_piece_by_piece_after_the_game(self):
        from dobot_studio.tictactoe_program import TicTacToeProgram

        root = make_root(self)
        program = TicTacToeProgram(make_studio(self, root))
        program.new_game()
        program.board = FINISHED[:]
        program.turn, program.human = X, X
        program.ready = True
        program._announce()
        self.assertTrue(program.tidying)
        end = monotonic() + 8
        while monotonic() < end and (program.tidying or program.busy):
            root.update()
            sleep(0.01)
        self.assertEqual(program.board, EMPTY)
        self.assertFalse(program.busy)
        self.assertIn("Board reset", program.status.get())
        program.close()


@unittest.skipUnless(__import__("os").environ.get("DISPLAY") or __import__("sys").platform == "win32",
                     "needs a display")
class DifficultyTests(unittest.TestCase):
    def test_the_chosen_level_reaches_the_dobots_move_and_is_remembered(self):
        from unittest import mock
        from dobot_studio import tictactoe_program
        from dobot_studio.tictactoe import EASY, HARD, LEVELS, MEDIUM

        root = make_root(self)
        studio = make_studio(self, root)
        program = tictactoe_program.TicTacToeProgram(studio)
        self.assertEqual(program.level.get(), HARD)
        self.assertEqual(tuple(program.level_picker.cget("values")), LEVELS)
        self.assertEqual(str(program.level_picker.cget("state")), "readonly")
        seen = []
        real = tictactoe_program.robot_move
        with mock.patch.object(tictactoe_program, "robot_move",
                               lambda board, mark, level: seen.append(level) or real(board, mark, level)):
            for level in (EASY, MEDIUM, HARD):
                program.level.set(level)
                program.new_game()
                program.board = (X, "", "", "", "", "", "", "", "")
                program._plan_reply("Test.")
                program.stop()
        self.assertEqual(seen, [EASY, MEDIUM, HARD])
        program.level.set(MEDIUM)
        program.close()
        reopened = tictactoe_program.TicTacToeProgram(studio)
        self.assertEqual(reopened.level.get(), MEDIUM)
        reopened.close()

    def test_a_demo_game_is_playable_at_every_level(self):
        from dobot_studio import tictactoe_program
        from dobot_studio.tictactoe import LEVELS

        root = make_root(self)
        studio = make_studio(self, root)
        for level in LEVELS:
            program = tictactoe_program.TicTacToeProgram(studio)
            program.level.set(level)
            program.new_game()
            end = monotonic() + 20
            while monotonic() < end and (program.ready or program.busy):
                if program.turn == program.human and not program.busy and program.ready:
                    cell = next(i for i in range(9) if not program.board[i])
                    program.board = with_move(program.board, cell, program.human)
                    program._after_player(cell)
                root.update()
                sleep(0.01)
            self.assertTrue(program.board == EMPTY and not program.busy, level)
            program.close()


if __name__ == "__main__":
    unittest.main()
