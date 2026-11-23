"""Tic-tac-toe rules and the physical mat dimensions, in millimetres."""
from functools import lru_cache


MAT_WIDTH = 300
MAT_HEIGHT = 300
MAT_FLOOR = 2.0
MAT_TOP = 2.8
NEST_RADIUS = 13.6
PIECE_RADIUS = 12.5
PIECE_HEIGHT = 3.2
MARK_DEPTH = 0.6
NOUGHT_OUTER = 8.6
NOUGHT_INNER = 5.2
CROSS_HALF_LENGTH = 9.25
CROSS_HALF_WIDTH = 1.65

CELLS = tuple(f"{row}{col}" for row in "ABC" for col in "123")
BANK = tuple(f"Reserve {index}" for index in range(1, 6))
MAT_POSITIONS = dict(zip((*CELLS, *BANK), (
    *((x, y) for y in (80, 135, 190) for x in (80, 134, 188)),
    *((234, y) for y in (86, 116, 174, 204, 234)),
)))
ANCHORS = {44: (17, 17), 45: (283, 17), 46: (283, 283), 47: (17, 283)}
ANCHOR_SIZE = 16
SUGGESTED_PARK = (155, 207)
TEACH_ORDER = (*MAT_POSITIONS, "Park")

EMPTY = ("",) * 9
X, O, UNKNOWN = "X", "O", "?"
ORDER = (4, 0, 2, 6, 8, 1, 3, 5, 7)
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6))


def winning_line(board):
    return next((line for line in LINES if board[line[0]] in (X, O)
                 and all(board[index] == board[line[0]] for index in line)), ())


def outcome(board):
    line = winning_line(board)
    if line:
        return board[line[0]]
    return "Draw" if all(board) else None


def with_move(board, index, mark):
    return (*board[:index], mark, *board[index + 1:])


@lru_cache(maxsize=10000)
def score(board, turn):
    result = outcome(board)
    if result == "Draw":
        return 0
    if result is not None:
        margin = 1 + board.count("")
        return margin if result == O else -margin
    values = (score(with_move(board, index, turn), X if turn == O else O)
              for index in ORDER if not board[index])
    return max(values) if turn == O else min(values)


def robot_move(board):
    if outcome(board):
        return None
    return max((index for index in ORDER if not board[index]),
               key=lambda index: score(with_move(board, index, O), X))


def human_change(previous, current):
    changes = [index for index in range(9) if previous[index] != current[index]]
    if len(changes) != 1 or previous[changes[0]] or current[changes[0]] != X:
        raise ValueError("Place one cross in an empty cell and leave the other pieces in place.")
    return changes[0]
