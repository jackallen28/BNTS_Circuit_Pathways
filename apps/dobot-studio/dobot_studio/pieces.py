"""Teach the camera what the X and O pieces look like.

The built-in reading matches each piece's mark against an ideal X and an ideal O. Printed pieces are never
quite ideal, and a soft or dim picture changes them further. So the person can show the camera their own
pieces in two ways, and the camera keeps the shape of every mark it sees:

* a **close-up**, with the camera right over one piece, gives the true shape of the mark;
* **from a distance**, with the camera in its working place and only X pieces (or only O pieces) on the mat,
  gives the mark as the camera will see it in a game, and the **colour** of those pieces.

If the X pieces and the O pieces are clearly different colours, the colour is a second, stronger way to tell them
apart. It decides when a mark cannot be made out (a reflection, or a soft picture), and it stops a piece being
read as a mark its colour says it is not.

These shapes are only asked when the built-in reading is not sure, so teaching can only help a reading, never
break one that already works. What was taught is saved with the rest of the setup.
"""
import numpy as np

from .tictactoe import O, PIECE_RADIUS, X
from .tictactoe_vision import (
    DENSITY, RADIUS, _patch, _patch_colour, best_match, body_colour, circle_positions, half_density, mark_of, present,
)

CAP = {"close": 3, "distance": 5}      # shapes kept of each mark and kind. Older ones are dropped first
PER_PICTURE = 3                        # a picture of a whole mat of pieces teaches this many of them: the most different
WANTED = 3                             # pictures of each kind, for each mark, that the person is asked for
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


def mat_marks(view, reference, layout, *, learned=None, centres=None):
    """The marks of every piece on the mat, from the camera's own view of it: a list of masks."""
    found = []
    for centre in circle_positions(layout, centres).values():
        mask = mark_of(_patch(view.grey, centre, layout.piece_scale), _patch(reference.grey, centre, layout.piece_scale))
        if mask is not None:
            found.append(mask)
    return found


def mat_pieces(view, reference, layout, centres=None):
    """Every piece on the mat: a list of (the mark's mask or None if it does not show, the body's colour as Lab)."""
    found = []
    for centre in circle_positions(layout, centres).values():
        tile = _patch(view.grey, centre, layout.piece_scale)
        base = _patch(reference.grey, centre, layout.piece_scale)
        if not present(tile, base):
            continue
        lab, _ = body_colour(_patch_colour(view.colour, centre, layout.piece_scale))
        found.append((mark_of(tile, base), lab))
    return found


def _variants(mask, rotate):
    """A mark, centred, as the shapes to match: at half density, and turned every 10 degrees if it is an X.

    Where on its circle a piece sits is searched for when matching, so no shifted copies are needed.
    """
    import cv2

    shape = half_density(mask)
    height, width = shape.shape
    centre = (width // 2, height // 2)
    out = []
    for degrees in ROTATIONS if rotate else (0,):
        out.append(cv2.warpAffine(shape, cv2.getRotationMatrix2D(centre, degrees, 1.0), (width, height),
                                  flags=cv2.INTER_NEAREST))
    return np.stack(out).astype(np.float32)


MIN_SEPARATION = 25.0          # Lab distance between the X colour and the O colour for the colour to be of any use
MAX_COLOURS = 12
LIGHTNESS = 0.35               # how much the lightness counts against the colour itself: exposure moves it most


def lab_to_rgb(lab):
    """A Lab colour (as ``body_colour`` gives it) as an (R, G, B) to draw."""
    import cv2

    pixel = np.array([[[lab[0] * 255 / 100, lab[1] + 128, lab[2] + 128]]], np.float32).clip(0, 255).astype(np.uint8)
    return tuple(int(v) for v in cv2.cvtColor(pixel, cv2.COLOR_LAB2RGB)[0, 0])


def colour_distance(a, b):
    return float(np.sqrt(LIGHTNESS * (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))


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
        self.colours = {X: [], O: []}                # the body colour of each piece taught from a distance, as Lab
        self._cache = {}

    def add(self, mark, masks, kind, colours=()):
        """One picture of a mark: the masks found in it (one for a close-up, up to a few for a view of the mat).

        ``colours`` are the body colours (Lab) of the pieces in a picture from a distance.
        """
        if mark not in self.shapes or kind not in KINDS:
            raise ValueError("Teach an X or an O, from close up or from a distance.")
        if kind == "distance":
            self.colours[mark].extend(np.asarray(lab, np.float32) for lab in colours)
            del self.colours[mark][:-MAX_COLOURS]
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
            self.colours[key].clear()
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

    # ---- colour
    def colour_of(self, mark):
        """The usual body colour of a mark's pieces, and how far the taught ones stray from it."""
        samples = np.array(self.colours[mark])
        centre = np.median(samples, axis=0)
        spread = max(colour_distance(sample, centre) for sample in samples)
        return centre, spread

    def separation(self):
        """How different the X colour and the O colour are, or None until both have been taught."""
        if not (self.colours[X] and self.colours[O]):
            return None
        return colour_distance(self.colour_of(X)[0], self.colour_of(O)[0])

    def colours_ready(self):
        """True when X pieces and O pieces were taught, and are different enough in colour to tell apart."""
        separation = self.separation()
        return separation is not None and separation >= MIN_SEPARATION

    def colour_vote(self, lab):
        """X or O if a piece of this colour is clearly one of them, or None."""
        if not self.colours_ready():
            return None
        distances, limits = {}, {}
        separation = self.separation()
        for mark in (X, O):
            centre, spread = self.colour_of(mark)
            distances[mark] = colour_distance(lab, centre)
            limits[mark] = min(max(1.5 * spread + 6.0, 10.0), 0.45 * separation)
        best, other = sorted(distances, key=distances.get)
        if distances[best] <= limits[best] and distances[best] <= 0.7 * distances[other]:
            return best
        return None

    def warnings(self):
        """Things about what was taught that look wrong, in plain English."""
        found = []
        separation = self.separation()
        if separation is not None and separation < MIN_SEPARATION:
            found.append("The X and O pieces are too alike in colour for the colour to help. Use clearly different colours.")
        for mark in (X, O):
            if len(self.colours[mark]) > 1:
                centre, spread = self.colour_of(mark)
                if spread > 28:
                    found.append(f"The {mark} pieces taught are not all one colour.")
        if self.has(X) and self.has(O):
            for mask, _ in self.shapes[X]:
                if best_match(half_density(mask), self.templates(O))[0] >= 0.55:
                    found.append("An X and an O that were taught look alike. Check that each set holds only its own mark.")
                    break
        return found

    def to_data(self):
        """What has been taught, as plain data (for the saved setup)."""
        import base64

        def pack(mask):
            return {"shape": list(mask.shape), "bits": base64.b64encode(np.packbits(mask.ravel()).tobytes()).decode("ascii")}

        return {"shapes": {mark: [{**pack(mask), "kind": kind} for mask, kind in self.shapes[mark]] for mark in (X, O)},
                "pictures": {mark: dict(self.pictures[mark]) for mark in (X, O)},
                "colours": {mark: [[float(v) for v in lab] for lab in self.colours[mark]] for mark in (X, O)}}

    @classmethod
    def from_data(cls, data):
        import base64

        learned = cls()
        for mark in (X, O):
            for item in data.get("shapes", {}).get(mark, []):
                height, width = item["shape"]
                bits = np.unpackbits(np.frombuffer(base64.b64decode(item["bits"]), np.uint8))[:height * width]
                learned.shapes[mark].append((bits.reshape(height, width).astype(bool), item["kind"]))
            for kind in KINDS:
                learned.pictures[mark][kind] = int(data.get("pictures", {}).get(mark, {}).get(kind, 0))
            learned.colours[mark] = [np.array(lab, np.float32) for lab in data.get("colours", {}).get(mark, [])]
        return learned

    def summary(self):
        return {mark: dict(self.pictures[mark]) for mark in (X, O)}
