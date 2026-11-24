"""Tic-tac-toe rules and the physical mat dimensions, in millimetres."""
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MatLayout:
    label: str
    anchors: dict
    positions: dict
    cross_bank: tuple
    nought_bank: tuple
    width: int = MAT_WIDTH
    height: int = MAT_HEIGHT
    piece_scale: float = 1.0
    anchor_size: float = ANCHOR_SIZE
    park_limit: float = 150

    @property
    def reserve(self):
        return tuple(name for name in self.positions if name not in CELLS)

    def bank(self, mark):
        return self.cross_bank if mark == X else self.nought_bank

    def reserve_marks(self, robot_mark):
        return (robot_mark,) if self.cross_bank == self.nought_bank else (X, O)


PAPER_CROSSES = tuple(f"X{index}" for index in range(1, 6))
PAPER_NOUGHTS = tuple(f"O{index}" for index in range(1, 6))
PAPER_POSITIONS = {cell: MAT_POSITIONS[cell] for cell in CELLS}
PAPER_POSITIONS.update(zip(PAPER_CROSSES, ((34, y) for y in (86, 116, 146, 176, 206))))
PAPER_POSITIONS.update(zip(PAPER_NOUGHTS, ((234, y) for y in (86, 116, 146, 176, 206))))
PAPER_PARK = (153, 154)
STANDARD_MAT = MatLayout("Standard", ANCHORS, MAT_POSITIONS, BANK, BANK)
PAPER_MAT = MatLayout("Paper", dict(zip(range(36, 40), ANCHORS.values())),
                      PAPER_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS)

A3_WIDTH, A3_HEIGHT = 420, 297
A3_POSITIONS = dict(zip((*CELLS, *PAPER_CROSSES, *PAPER_NOUGHTS), (
    *((x, y) for y in (68.5, 150.5, 232.5) for x in (123.6, 210, 296.4)),
    *((x, y) for x in (55, 365) for y in (32.5, 80.5, 128.5, 176.5, 224.5)),
)))
A3_ANCHORS = {32: (18.5, 18.5), 33: (401.5, 18.5), 34: (401.5, 278.5), 35: (18.5, 278.5)}
A3_PARK = (210, 191.5)
A3_MAT = MatLayout("A3", A3_ANCHORS, A3_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS,
                   width=A3_WIDTH, height=A3_HEIGHT, piece_scale=1.6, anchor_size=20, park_limit=235)
MAT_LAYOUTS = (STANDARD_MAT, PAPER_MAT, A3_MAT)


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


def robot_move(board, mark=O):
    if outcome(board):
        return None
    prefer = max if mark == O else min
    next_mark = X if mark == O else O
    return prefer((index for index in ORDER if not board[index]),
                  key=lambda index: score(with_move(board, index, mark), next_mark))


def human_change(previous, current, mark=X):
    changes = [index for index in range(9) if previous[index] != current[index]]
    if len(changes) != 1 or previous[changes[0]] or current[changes[0]] != mark:
        piece = "cross" if mark == X else "nought"
        raise ValueError(f"Place one {piece} in an empty cell and leave the other pieces in place.")
    return changes[0]
