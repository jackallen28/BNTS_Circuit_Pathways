"""Tic-tac-toe rules and the physical mat dimensions, in millimetres."""
from dataclasses import dataclass
from functools import lru_cache
import random


MAT_WIDTH = 300
MAT_HEIGHT = 300
MAT_MARK_DEPTH = 0.6
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
EASY, MEDIUM, HARD = "Easy", "Medium", "Hard"
LEVELS = (EASY, MEDIUM, HARD)
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
    park: tuple = SUGGESTED_PARK

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
                      PAPER_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS, park=PAPER_PARK)

A3_WIDTH, A3_HEIGHT = 420, 297
A3_POSITIONS = dict(zip((*CELLS, *PAPER_CROSSES, *PAPER_NOUGHTS), (
    *((x, y) for y in (68.5, 150.5, 232.5) for x in (123.6, 210, 296.4)),
    *((x, y) for x in (55, 365) for y in (32.5, 80.5, 128.5, 176.5, 224.5)),
)))
A3_ANCHORS = {32: (18.5, 18.5), 33: (401.5, 18.5), 34: (401.5, 278.5), 35: (18.5, 278.5)}
A3_PARK = (210, 191.5)
A3_MAT = MatLayout("A3", A3_ANCHORS, A3_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS,
                   width=A3_WIDTH, height=A3_HEIGHT, piece_scale=1.6, anchor_size=20, park_limit=235,
                   park=A3_PARK)

# The compact mat: Ø25 mm pieces, 16 mm camera markers and everything centred on an A4 landscape sheet
# (297 x 210 mm). The 3D mat is cut from the middle of the same sheet, so paper and 3D share one layout.
COMPACT_WIDTH, COMPACT_HEIGHT = 297, 210
COMPACT_CENTRE = (COMPACT_WIDTH / 2, COMPACT_HEIGHT / 2)
COMPACT_BANK_X = 100                      # a reserve bank sits this far from the centre line
COMPACT_POSITIONS = dict(zip((*CELLS, *PAPER_CROSSES, *PAPER_NOUGHTS), (
    *((COMPACT_CENTRE[0] + dx, COMPACT_CENTRE[1] + dy) for dy in (-55, 0, 55) for dx in (-54, 0, 54)),
    *((COMPACT_CENTRE[0] - COMPACT_BANK_X, COMPACT_CENTRE[1] + dy) for dy in (-60, -30, 0, 30, 60)),
    *((COMPACT_CENTRE[0] + COMPACT_BANK_X, COMPACT_CENTRE[1] + dy) for dy in (-60, -30, 0, 30, 60)),
)))
# Marker IDs 28 to 31 are free: 0 to 9 and 40 to 43 belong to the Block Lab, and the other mats use 32 to 39 and 44 to 47.
COMPACT_ANCHORS = {28: (36.5, 20), 29: (260.5, 20), 30: (260.5, 190), 31: (36.5, 190)}
COMPACT_PARK = (COMPACT_CENTRE[0], COMPACT_CENTRE[1] + 27.5)   # the middle of the lower grid divider
COMPACT_MAT = MatLayout("Compact", COMPACT_ANCHORS, COMPACT_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS,
                        width=COMPACT_WIDTH, height=COMPACT_HEIGHT, park=COMPACT_PARK)
# The cut for the 3D mat: left, top, right, bottom on the sheet.
COMPACT_3D_BOUNDS = (21.5, 5, 275.5, 205)

# The small mat: the same Ø25 mm pieces and 16 mm camera markers on an A4 sheet, but packed so that every
# circle fits in a ring about 90 mm from the middle. The Dobot Magician reaches 130 to 310 mm from its base,
# and a mat the size of the compact one is too wide to fit that ring in most positions. See SMALL_PLACEMENT.
SMALL_PITCH = 36                          # between the centres of neighbouring cells, across and down
SMALL_BANK_X, SMALL_BANK_PITCH = 68, 30   # a bank's distance from the centre line, and between its circles
SMALL_POSITIONS = dict(zip((*CELLS, *PAPER_CROSSES, *PAPER_NOUGHTS), (
    *((COMPACT_CENTRE[0] + dx * SMALL_PITCH, COMPACT_CENTRE[1] + dy * SMALL_PITCH) for dy in (-1, 0, 1) for dx in (-1, 0, 1)),
    *((COMPACT_CENTRE[0] - SMALL_BANK_X, COMPACT_CENTRE[1] + k * SMALL_BANK_PITCH) for k in (-2, -1, 0, 1, 2)),
    *((COMPACT_CENTRE[0] + SMALL_BANK_X, COMPACT_CENTRE[1] + k * SMALL_BANK_PITCH) for k in (-2, -1, 0, 1, 2)),
)))
# Marker IDs 24 to 27 are free.
SMALL_ANCHORS = {24: (COMPACT_CENTRE[0] - 100, COMPACT_CENTRE[1] - 78), 25: (COMPACT_CENTRE[0] + 100, COMPACT_CENTRE[1] - 78),
                 26: (COMPACT_CENTRE[0] + 100, COMPACT_CENTRE[1] + 78), 27: (COMPACT_CENTRE[0] - 100, COMPACT_CENTRE[1] + 78)}
SMALL_PARK = (COMPACT_CENTRE[0], COMPACT_CENTRE[1] + SMALL_PITCH / 2)       # the middle of the lower grid divider
SMALL_MAT = MatLayout("Small", SMALL_ANCHORS, SMALL_POSITIONS, PAPER_CROSSES, PAPER_NOUGHTS,
                      width=COMPACT_WIDTH, height=COMPACT_HEIGHT, park=SMALL_PARK)
# Where the mat may go. Every circle must be within the arm's 130 to 310 mm reach (with 8 mm to spare), and the arm must
# have somewhere to wait off the mat, which is between its base and the mat, no nearer the base than 138 mm. That needs
# the base facing the middle of a long edge of the sheet, with the middle of the mat this far from the base (mm).
# Turned up to 15 degrees either way the range narrows to 207-222. Facing a short edge leaves no room to wait.
SMALL_PLACEMENT = {"long": (207, 234)}
SMALL_SUGGESTED_DISTANCE = 220

MAT_LAYOUTS = (STANDARD_MAT, PAPER_MAT, A3_MAT, COMPACT_MAT, SMALL_MAT)


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


def finishing_move(board, mark):
    """A free cell that wins the game for ``mark`` right now, or None."""
    return next((index for index in ORDER
                 if not board[index] and outcome(with_move(board, index, mark)) == mark), None)


def robot_move(board, mark=O, level=HARD, rng=random):
    """Choose the Dobot's cell.

    Hard plays perfectly and never loses. Medium wins or blocks when it can and
    otherwise plays any free cell. Easy plays any free cell but takes a win it sees.
    """
    if outcome(board):
        return None
    if level != HARD:
        win = finishing_move(board, mark)
        if win is not None:
            return win
        block = finishing_move(board, X if mark == O else O) if level == MEDIUM else None
        if block is not None:
            return block
        return rng.choice([index for index in range(9) if not board[index]])
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


def tidy_plan(layout, board, reserve, robot_mark):
    """Plan how the Dobot returns pieces from the cells to empty reserve slots.

    Returns ``(moves, left)``. Each move is ``(cell index, mark, reserve slot)``.
    ``left`` counts pieces the Dobot cannot return, which a person must collect.
    On a single-bank mat the reserve only holds the Dobot's mark, so the
    player's pieces are left for the player. ``reserve`` follows ``layout.reserve``.
    """
    marks = layout.reserve_marks(robot_mark)
    taken = dict(zip(layout.reserve, reserve))
    free = {mark: [name for name in layout.bank(mark) if not taken[name]] for mark in marks}
    moves, left = [], 0
    for index, piece in enumerate(board):
        if not piece:
            continue
        if piece not in marks:
            left += 1
        elif not free[piece]:
            raise ValueError(f"No free {piece} reserve slot. Clear the {piece} reserve slots and try again.")
        else:
            moves.append((index, piece, free[piece].pop(0)))
    return moves, left


ROWS, COLUMNS = ("top", "middle", "bottom"), ("left", "middle", "right")
ORDINALS = ("1st", "2nd", "3rd", "4th", "5th")


def describe_slot(layout, label, from_dobot=False):
    """Say in plain English where a position is on the mat.

    The mats carry no printed names, so setup shows this beside a map of the mat. It is
    worded for the player, who sits at the bottom edge, or for someone standing behind
    the mat with the Dobot, who sees everything turned end for end.
    """
    if label == "Park":
        return "Park: hold the tool a clear height above the small ring near the middle of the mat."
    if label in CELLS:
        row, column = divmod(CELLS.index(label), 3)
        if from_dobot:
            row, column = 2 - row, 2 - column
        return f"{label}: the {ROWS[row]} row, {COLUMNS[column]} cell."
    bank = next((names for names in (layout.cross_bank, layout.nought_bank) if label in names), None)
    if bank is None:
        raise KeyError(label)
    x, _ = layout.positions[label]
    side = "left" if x < layout.width / 2 else "right"
    order = sorted(bank, key=lambda name: layout.positions[name][1])
    place = order.index(label)
    if from_dobot:
        side, place = ("right" if side == "left" else "left"), len(order) - 1 - place
    owner = "single" if layout.cross_bank == layout.nought_bank else (X if bank is layout.cross_bank else O)
    name = "reserve" if owner == "single" else f"{owner} reserve"
    return f"{label}: the {ORDINALS[place]} {name} circle from the top, on the {side}."
