"""Teach the camera what the X and O pieces look like.

The built-in reading matches each piece's mark against an ideal X and an ideal O. Printed pieces are never
quite ideal, and a soft or dim picture changes them further. So the person can show the camera their own
pieces in two ways, and the camera keeps the shape of every mark it sees:

* a **close-up**, with the camera right over one piece, gives the true shape of the mark;
* **from a distance**, with the camera in its working place and only X pieces (or only O pieces) on the mat,
  gives the mark as the camera will see it in a game.

These shapes are only asked when the built-in reading is not sure, so teaching can only help a reading, never
break one that already works. Nothing is saved: the pieces are taught each time the mat is set up.
"""
import numpy as np

from .tictactoe import O, PIECE_RADIUS, X
from .tictactoe_vision import DENSITY, RADIUS, _patch, mark_of

CAP = {"close": 3, "distance": 5}      # shapes kept of each mark and kind. Older ones are dropped first
PER_PICTURE = 3                        # a picture of a whole mat of pieces teaches this many of them: the most different
WANTED = 3                             # pictures of each kind, for each mark, that the person is asked for
SHIFTS = (-5, 0, 5)            # pixels, a quarter of the circle's 1.25 mm slack either way
ROTATIONS = tuple(range(0, 90, 10))
KINDS = ("close", "distance")


def _disc(rgb):
    """The piece in a close-up picture: its centre and radius in pixels, or None. A light piece on a darker background."""
    import cv2

    grey = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    grey = cv2.GaussianBlur(grey, (0, 0), 2.0)
    _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if mask[0, 0] and mask[-1, -1] and mask[0, -1] and mask[-1, 0]:
        mask = cv2.bitwise_not(mask)              # the light was the background: the piece is the dark part
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    height, width = grey.shape
    for contour in contours:
        area = cv2.contourArea(contour)
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius < min(height, width) / 10 or area < 0.7 * np.pi * radius ** 2:
            continue                                  # too small, or not round
        if best is None or radius > best[2]:
            best = (x, y, radius)
    return best


def closeup_mark(rgb):
    """The mark of the piece in a close-up picture, as a mask the size of a circle's patch, or None if no piece is found."""
    import cv2

    found = _disc(rgb)
    if found is None:
        return None
    x, y, radius = found
    scale = PIECE_RADIUS * DENSITY / radius            # the piece's real size in the mat picture's pixels
    matrix = np.array([[scale, 0, RADIUS - scale * x], [0, scale, RADIUS - scale * y]], dtype=np.float32)
    grey = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    tile = cv2.warpAffine(cv2.GaussianBlur(grey, (0, 0), 1.0 / scale), matrix, (2 * RADIUS + 1, 2 * RADIUS + 1),
                          flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    from .tictactoe_vision import ink_of

    tile = cv2.GaussianBlur(tile, (0, 0), 1.0)         # as soft as the picture of the mat is
    ink = ink_of(tile)
    return ink if ink.sum() >= 95 else None


def mat_marks(view, reference, layout, *, learned=None):
    """The marks of every piece on the mat, from the camera's own view of it: a list of masks."""
    found = []
    for centre in layout.positions.values():
        mask = mark_of(_patch(view.grey, centre, layout.piece_scale), _patch(reference.grey, centre, layout.piece_scale))
        if mask is not None:
            found.append(mask)
    return found


def _variants(mask, rotate):
    import cv2

    height, width = mask.shape
    centre = (width // 2, height // 2)
    out = []
    for degrees in ROTATIONS if rotate else (0,):
        turn = cv2.getRotationMatrix2D(centre, degrees, 1.0)
        for dx in SHIFTS:
            for dy in SHIFTS:
                matrix = turn.copy()
                matrix[0, 2] += dx
                matrix[1, 2] += dy
                out.append(cv2.warpAffine(mask.astype(np.uint8), matrix, (width, height), flags=cv2.INTER_NEAREST) > 0)
    return np.stack(out)


def diverse(masks, count=PER_PICTURE):
    """Up to ``count`` of the masks, spread across their sizes, so a picture of a row of alike pieces teaches the odd ones too."""
    if len(masks) <= count:
        return list(masks)
    ordered = sorted(masks, key=lambda mask: int(mask.sum()))
    return [ordered[round(i * (len(ordered) - 1) / (count - 1))] for i in range(count)]


class Learned:
    """The marks the camera has been shown. ``templates(mark)`` are the shapes the reading tries."""

    def __init__(self):
        self.shapes = {X: [], O: []}                 # (mask, kind)
        self.pictures = {X: {kind: 0 for kind in KINDS}, O: {kind: 0 for kind in KINDS}}
        self._cache = {}

    def add(self, mark, masks, kind):
        """One picture of a mark: the masks found in it (one for a close-up, up to a few for a view of the mat)."""
        if mark not in self.shapes or kind not in KINDS:
            raise ValueError("Teach an X or an O, from close up or from a distance.")
        masks = [np.asarray(mask, bool) for mask in (masks if isinstance(masks, (list, tuple)) else [masks])]
        masks = diverse(masks) if kind == "distance" else masks[:1]
        self.shapes[mark].extend((mask, kind) for mask in masks)
        mine = [index for index, (_, k) in enumerate(self.shapes[mark]) if k == kind]
        for index in reversed(mine[:-CAP[kind]]):
            del self.shapes[mark][index]
        self.pictures[mark][kind] += 1
        self._cache.pop(mark, None)

    def clear(self, mark=None):
        for key in (mark,) if mark else self.shapes:
            self.shapes[key].clear()
            self.pictures[key] = {kind: 0 for kind in KINDS}
            self._cache.pop(key, None)

    def count(self, mark, kind=None):
        """How many pictures of this mark were taken, of one kind or of both."""
        return sum(self.pictures[mark].values()) if kind is None else self.pictures[mark][kind]

    def has(self, mark):
        return bool(self.shapes[mark])

    def ready(self):
        return any(self.shapes.values())

    def templates(self, mark):
        if mark not in self._cache:
            self._cache[mark] = np.concatenate([_variants(mask, rotate=(mark == X)) for mask, _ in self.shapes[mark]])
        return self._cache[mark]

    def warnings(self):
        """Things about what was taught that look wrong, in plain English."""
        found = []
        if self.has(X) and self.has(O):
            for mask, _ in self.shapes[X]:
                size = int(mask.sum())
                crossed = self.templates(O)
                overlap = np.count_nonzero(crossed & mask, axis=(1, 2))
                union = np.count_nonzero(crossed, axis=(1, 2)) + size - overlap
                if float((overlap / union).max()) >= 0.55:
                    found.append("An X and an O that were taught look alike. Check that each set holds only its own mark.")
                    break
        return found

    def summary(self):
        return {mark: dict(self.pictures[mark]) for mark in (X, O)}
