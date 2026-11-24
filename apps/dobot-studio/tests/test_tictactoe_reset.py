"""The Dobot returns pieces to the reserve at the end of a game."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from time import monotonic, sleep
from types import SimpleNamespace
import tkinter as tk
import unittest

from dobot_studio.robot import Pose
from dobot_studio.tictactoe import (
    A3_MAT, CELLS, EMPTY, O, PAPER_MAT, STANDARD_MAT, X, outcome, tidy_plan, with_move,
)
from dobot_studio.tictactoe_vision import Position

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

    def position(self):
        return Position(tuple(self.board), tuple(self.reserve))


class FakeRobot:
    def __init__(self, world, poses):
        self.world, self.names = world, {pose: name for name, pose in poses.items()}
        self.on_move = None

    def sort_chip(self, pick, drop, park, stop, attachment=None, *, via_park=False):
        source, target = self.names[pick], self.names[drop]
        self.world.moves.append((source, target))
        if not self.world.refuse:
            cell = CELLS.index(source)
            slot = self.world.layout.reserve.index(target)
            self.world.reserve[slot] = self.world.board[cell]
            self.world.board = with_move(tuple(self.world.board), cell, "")
        if self.on_move:
            self.on_move()
        return park

    def set_suction(self, enabled):
        pass


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
        poses = {name: Pose(150 + x, -150 + y, 30, 0) for name, (x, y) in layout.positions.items()}
        poses["Park"] = Pose(150 + layout.width/2, -150 + layout.height/2, 60, 0)
        self.world = World(layout, board)
        studio.robot = FakeRobot(self.world, poses)
        program = self.program_class(studio)
        self.addCleanup(lambda: program.window.winfo_exists() and program.window.destroy())
        program.poses = poses
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

    def test_single_bank_mat_leaves_the_players_pieces_for_the_player(self):
        program = self.program(STANDARD_MAT, FINISHED, human=X)
        program.ready = True
        program._announce()
        self.assertTrue(self.pump(program, 15, lambda: not program.tidy_pending and not program.tidying and not program.busy))
        self.assertEqual(self.world.board, (X, "", "", X, "", "", X, "", ""))
        self.assertEqual(self.world.reserve[:2], [O, O])
        self.assertIn("Take your 3 pieces", program.status.get())

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


if __name__ == "__main__":
    unittest.main()
