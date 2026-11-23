"""Known-geometry block fixtures and a checked, single-step construction planner."""
from dataclasses import dataclass
from math import hypot

from .robot import Pose

EDGE = 20
MARKER = 12
COLOURS = ("Red", "Blue")
PYRAMID, BOX, REBUILD = "Stepped pyramid", "Block box", "Rebuild by colour"
CHALLENGES = (PYRAMID, BOX, REBUILD)
ANCHORS = {40: (-62, -69), 41: (62, -69), 42: (62, 40), 43: (-62, 40)}
DATUMS = ((-60, -59), (60, -59))


@dataclass(frozen=True, order=True)
class Slot:
    x: int
    y: int
    level: int = 0

    def overlaps(self, other):
        return abs(self.x - other.x) < EDGE and abs(self.y - other.y) < EDGE

    def label(self):
        return f"({self.x}, {self.y}) · layer {self.level + 1}"


BUFFER = tuple(Slot(x, y) for y in (-55, -29) for x in (-48, -24, 0, 24, 48))
LEFT_BASE = tuple(Slot(x, y) for y in (-1, 23) for x in (-37, -13))
RIGHT_BASE = tuple(Slot(x, y) for y in (-1, 23) for x in (13, 37))
ROOFS = (Slot(-25, 11, 1), Slot(25, 11, 1))
UPPER = {cell: Slot(cell.x, cell.y, 1) for cell in (*LEFT_BASE, *RIGHT_BASE)}
SLOTS = (*BUFFER, *LEFT_BASE, *RIGHT_BASE, *UPPER.values(), *ROOFS)


def block_colour(marker):
    return COLOURS[marker // 4 % len(COLOURS)]


def demo_scene(challenge):
    if challenge == REBUILD:
        left, right = LEFT_BASE[:2], RIGHT_BASE[:2]
        return {left[0]: 0, left[1]: 4, UPPER[left[0]]: 5, UPPER[left[1]]: 1,
                right[0]: 6, right[1]: 2, UPPER[right[0]]: 3, UPPER[right[1]]: 7}
    return dict(zip(BUFFER, range(5 if challenge == PYRAMID else 8)))


def exposed(board, slot):
    return not any(other.level > slot.level and slot.overlaps(other) for other in board)


def goals(challenge):
    if challenge == PYRAMID:
        return {slot: None for slot in (*LEFT_BASE, ROOFS[0])}
    if challenge == BOX:
        return {slot: None for slot in (*LEFT_BASE, *(UPPER[cell] for cell in LEFT_BASE))}
    return {slot: colour
            for cells, colour in ((LEFT_BASE[:2], "Red"), (RIGHT_BASE[:2], "Blue"))
            for base in cells for slot in (base, UPPER[base])}


@dataclass(frozen=True)
class Transfer:
    source: Slot
    target: Slot
    marker: int


class BlockPlan:
    def __init__(self, challenge):
        self.challenge = challenge
        self.target = goals(challenge)
        self.building = challenge != REBUILD
        self.placed = {}

    def register(self, board):
        """Retain placements covered by a later block, and verify visible ones."""
        known = dict(board)
        for slot, marker in self.placed.items():
            if slot not in board and not exposed(board, slot):
                known[slot] = marker
            elif board.get(slot) != marker:
                raise ValueError("A previously placed block moved or is hidden by the camera angle.")
        if len(known) != len(set(known.values())):
            raise ValueError("Duplicate marker IDs in the scene.")
        return known

    def next_transfer(self, observed):
        board = self.register(observed)
        if not self.building:
            storage = {slot: marker for slot, marker in board.items() if slot in BUFFER}
            if len(storage) > 8 or any(marker not in range(8) for marker in storage.values()):
                raise ValueError("Use block IDs 0–7 for the colour rebuild.")
            if len(storage) == 8:
                if len(board) != 8:
                    raise ValueError("Remove objects outside the eight staged blocks.")
                self.building = True
            else:
                source = next((slot for slot in sorted(board, key=lambda p: (-p.level, p.x, p.y))
                               if slot not in BUFFER and exposed(board, slot)), None)
                target = next((slot for slot in BUFFER if slot not in storage), None)
                if source is None:
                    raise ValueError("Waiting to see the remaining blocks on the two structures.")
                if board[source] not in range(8):
                    raise ValueError("Use block IDs 0–7 for the colour rebuild.")
                return Transfer(source, target, board[source])
        for target, colour in self.target.items():
            if target in self.placed:
                continue
            if any(slot.level >= target.level and target.overlaps(slot) for slot in board):
                raise ValueError("Clear the target location before placing the next block.")
            if target.level:
                supports = [slot for slot in self.target if slot.level == 0 and target.overlaps(slot)]
                if any(slot not in self.placed for slot in supports):
                    raise ValueError("Complete and confirm the supporting layer first.")
            source = next((slot for slot in BUFFER if slot in board
                           and (colour is None or block_colour(board[slot]) == colour)), None)
            if source is None:
                raise ValueError(f"Put a {'matching ' + colour.lower() if colour else 'tagged'} block in the staging rack.")
            return Transfer(source, target, board[source])
        return None

    def confirm(self, transfer, observed):
        if observed.get(transfer.target) != transfer.marker or transfer.source in observed:
            raise ValueError("The camera has not confirmed the transferred block at its destination.")
        if self.building:
            self.placed[transfer.target] = transfer.marker


class RobotBoard:
    """Transform board positions using two taught suction or jaw-contact datums."""

    def __init__(self, first, second, park):
        distance = hypot(second.x - first.x, second.y - first.y)
        if abs(distance - 120) > 3:
            raise ValueError("The taught datums must be 120 mm apart.")
        if abs(second.z - first.z) > 2 or any(abs(p.r - park.r) > 4 for p in (first, second)):
            raise ValueError("Teach level datums with the same tool rotation as Park.")
        self.first, self.park = first, park
        self.ux, self.uy = (second.x - first.x) / distance, (second.y - first.y) / distance
        self.contact_z = (first.z + second.z) / 2
        if not 32 <= park.z - self.contact_z <= 75:
            raise ValueError("Park must clear both 20 mm layers by at least 12 mm.")

    def pose(self, slot):
        x, y = slot.x - DATUMS[0][0], slot.y - DATUMS[0][1]
        return Pose(self.first.x + x*self.ux - y*self.uy,
                    self.first.y + x*self.uy + y*self.ux,
                    self.contact_z + slot.level*EDGE, self.park.r)
