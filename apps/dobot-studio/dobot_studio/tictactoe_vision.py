"""Read playing pieces and check for obstructions in the registered mat view."""
from dataclasses import dataclass
from functools import lru_cache
from math import radians

from .block_vision import detect
from .tictactoe import (
    CELLS, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, MAT_LAYOUTS, MatLayout, NOUGHT_INNER,
    NOUGHT_OUTER, O, PIECE_RADIUS, STANDARD_MAT, UNKNOWN, X,
)

# Half the width of the patch of mat looked at for each circle, in mm. A piece may sit a few mm off the middle of its
# circle, so the patch reaches well past the circle and the piece (Ø25 mm).
PATCH = 17
DENSITY = 4
RADIUS = PATCH * DENSITY
CLEAR_DENSITY = 2


@dataclass(frozen=True)
class Position:
    board: tuple
    reserve: tuple


@dataclass(frozen=True)
class MatView:
    grey: object
    colour: object
    corners: object
    shape: tuple
    matrix: object
    layout: MatLayout
    source: object = None          # the picture as the camera gave it, before any adjustment, so a view can be redone


def _view(rgb, matrix, corners, layout, source=None):
    import cv2

    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    warped = cv2.warpPerspective(grey, matrix, (layout.width*DENSITY, layout.height*DENSITY))
    clear_matrix = matrix.copy()
    clear_matrix[:2] *= CLEAR_DENSITY / DENSITY
    colour = cv2.warpPerspective(rgb, clear_matrix, (layout.width*CLEAR_DENSITY, layout.height*CLEAR_DENSITY))
    return MatView(warped, colour, corners, grey.shape, matrix, layout, rgb if source is None else source)


def _tuned(rgb, tune):
    from .camera_tune import apply

    return apply(rgb, tune)


def retuned(view, tune):
    """The same view, looked at again through different camera adjustments (from the picture it was made from)."""
    if view is None or view.source is None:
        return view
    return _view(_tuned(view.source, tune), view.matrix, view.corners, view.layout, view.source)


def rectify(rgb, tune=None):
    """Find the mat from its four corner markers. This is only a rough reference.

    ``tune`` is the adjustment the Pi reads the picture through. The markers are found in the adjusted picture.

    It is used until the empty mat is captured. After that the registration is locked, so a
    marker hidden by the arm, or read a little out, cannot change where the mat is taken to be.
    """
    import cv2
    import numpy as np

    source, rgb = rgb, _tuned(rgb, tune)
    markers = detect(rgb)
    suitable = [layout for layout in MAT_LAYOUTS if all(marker in markers for marker in layout.anchors)]
    if len(suitable) != 1:
        raise ValueError("Show the four camera markers from one mat.")
    layout = suitable[0]
    corners = np.array([markers[marker].mean(axis=0) for marker in layout.anchors], dtype=np.float32)
    if not cv2.isContourConvex(corners) or abs(cv2.contourArea(corners)) < 12000:
        raise ValueError("Move the camera closer and keep the full mat in view.")
    target = np.asarray(tuple(layout.anchors.values()), dtype=np.float32) * DENSITY
    return _view(rgb, cv2.getPerspectiveTransform(corners, target), corners, layout, source)


def lock_view(rgb, reference, tune=None):
    """Read a frame through the registration that was made when the empty mat was captured.

    No markers are looked for, so nothing in front of them matters.
    """
    if rgb.shape[:2] != reference.shape:
        raise ValueError("The camera picture changed size. Capture the empty mat again.")
    return _view(_tuned(rgb, tune), reference.matrix, reference.corners, reference.layout, rgb)


def loupe(rgb, matrix, centre, size=220, window=44, turned=False):
    """A close-up, looking straight down, of the mat around one point.

    ``centre`` is where the point should be on the mat in millimetres, ``window`` how many
    millimetres across the close-up shows, and ``turned`` rotates it half a turn to match a map
    drawn from the Dobot's side. The point is always in the middle of the picture.
    """
    import cv2
    import numpy as np

    pixels = size / window
    cx, cy = centre
    to_close_up = np.array([[pixels, 0, size / 2 - pixels * cx],
                            [0, pixels, size / 2 - pixels * cy],
                            [0, 0, 1]], dtype=np.float64)
    from_layout_pixels = np.diag([1 / DENSITY, 1 / DENSITY, 1.0])
    result = cv2.warpPerspective(rgb, to_close_up @ from_layout_pixels @ matrix, (size, size),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return cv2.rotate(result, cv2.ROTATE_180) if turned else result


def _patch(image, centre, scale):
    import cv2

    x, y = (round(value * DENSITY) for value in centre)
    radius = round(RADIUS * scale)
    tile = image[y - radius:y + radius + 1, x - radius:x + radius + 1]
    if radius == RADIUS:
        return tile
    return cv2.resize(tile, (2*RADIUS + 1, 2*RADIUS + 1), interpolation=cv2.INTER_AREA)


COLOUR_RADIUS = PATCH * CLEAR_DENSITY      # the colour picture's patch half-size, in its pixels


def _patch_colour(image, centre, scale):
    """The same patch as ``_patch``, from the colour picture (which is at a lower density)."""
    import cv2

    x, y = (round(value * CLEAR_DENSITY) for value in centre)
    radius = round(COLOUR_RADIUS * scale)
    tile = image[y - radius:y + radius + 1, x - radius:x + radius + 1]
    if radius == COLOUR_RADIUS:
        return tile
    return cv2.resize(tile, (2 * COLOUR_RADIUS + 1, 2 * COLOUR_RADIUS + 1), interpolation=cv2.INTER_AREA)


@lru_cache(maxsize=1)
def _colour_masks():
    import numpy as np

    axis = np.arange(-COLOUR_RADIUS, COLOUR_RADIUS + 1, dtype=np.float32) / CLEAR_DENSITY
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    # The body shows between the mark (which reaches 9.25 mm) and the piece's edge (12.5 mm). The paper is in the corners.
    return (radius >= 9.9) & (radius <= 11.7), radius > 13.2


def body_colour(tile):
    """The colour of a piece's body, as Lab, and the colour it would be on white paper (RGB) to draw as a swatch.

    The body is judged against the paper around the circle, so a camera that tints or dims the whole picture
    (its automatic white balance and exposure) does not change the answer. Returns (lab, rgb).
    """
    import cv2
    import numpy as np

    body, paper = _colour_masks()
    body_rgb = np.median(tile[body].astype(np.float32), axis=0)
    paper_rgb = np.maximum(np.median(tile[paper].astype(np.float32), axis=0), 1.0)
    balanced = np.clip(body_rgb / paper_rgb * 235.0, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(balanced.reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)
    return np.array((lab[0] * 100 / 255, lab[1] - 128, lab[2] - 128), np.float32), tuple(int(v) for v in balanced)


@lru_cache(maxsize=1)
def _templates():
    import numpy as np

    axis = np.arange(-RADIUS, RADIUS + 1, dtype=np.float32) / DENSITY
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    body = (radius >= 10.1) & (radius <= 11.7)
    centre = radius <= 10.3
    templates = {O: [], X: []}
    for tx in (-1.25, 0, 1.25):
        for ty in (-1.25, 0, 1.25):
            cx, cy = x-tx, y-ty
            relative = np.hypot(cx, cy)
            templates[O].append((relative < NOUGHT_OUTER) & (relative > NOUGHT_INNER))
            for angle in range(0, 90, 10):
                theta = radians(angle)
                u = np.cos(theta) * cx + np.sin(theta) * cy
                v = -np.sin(theta) * cx + np.cos(theta) * cy
                templates[X].append(((abs(u) < CROSS_HALF_LENGTH) & (abs(v) < CROSS_HALF_WIDTH)) |
                                    ((abs(v) < CROSS_HALF_LENGTH) & (abs(u) < CROSS_HALF_WIDTH)))
    # The paper around the circle, in the corners of the patch: it shows how much the camera's exposure moved.
    outside = radius > 13.2
    return body, centre, {key: np.stack(value) for key, value in templates.items()}, outside


# ---- finding the mark wherever the piece sits on its circle
#
# A piece is never exactly on the middle of its circle: it is put down by hand, and a piece 3 mm thick leans away from
# the middle of the picture. So the mark is looked for over a range of positions, not only in the middle, and the
# part of the picture that is not the piece (the black circle showing round its edge) is left out once the piece
# has been found. Matching is done at half the picture's density, which is plenty and much quicker.
HALF = 2
HALF_RADIUS = PATCH * HALF
SEARCH = 10                 # pixels at HALF density: the piece may be up to 5 mm off the middle of its circle
WIDE = 12.8                 # mm from the middle of the patch where a mark may be looked for
EDGE = 11.3                 # mm from the piece's own middle: inside its 12.5 mm edge


@lru_cache(maxsize=1)
def _wide_masks():
    import numpy as np

    axis = np.arange(-RADIUS, RADIUS + 1, dtype=np.float32) / DENSITY
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    return radius <= WIDE, radius <= 11.0, x, y


@lru_cache(maxsize=1)
def _match_templates():
    """The ideal X (every 10 degrees; it is the same turned a quarter) and O, at half density, for matching."""
    import numpy as np

    axis = np.arange(-HALF_RADIUS, HALF_RADIUS + 1, dtype=np.float32) / HALF
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    nought = ((radius < NOUGHT_OUTER) & (radius > NOUGHT_INNER)).astype(np.float32)[None]
    crosses = []
    for angle in range(0, 90, 10):
        theta = radians(angle)
        u = np.cos(theta) * x + np.sin(theta) * y
        v = -np.sin(theta) * x + np.cos(theta) * y
        crosses.append((((abs(u) < CROSS_HALF_LENGTH) & (abs(v) < CROSS_HALF_WIDTH)) |
                        ((abs(v) < CROSS_HALF_LENGTH) & (abs(u) < CROSS_HALF_WIDTH))).astype(np.float32))
    return {O: nought, X: np.stack(crosses)}


def black_circle(tile, baseline):
    """How the empty circle is lit now: (x, y, light) for each pixel of the black circle, or None if it is not one.

    A piece on a black circle makes it light. Only the black circle is looked at, because a white piece cannot be told
    from the white paper round it. Looking at the pixels that were dark when the mat was empty also means a picture
    that has slipped a little, or an edge that is softer or tinted, does not look like a piece.
    """
    import numpy as np

    axis = np.arange(-HALF_RADIUS, HALF_RADIUS + 1, dtype=np.float32) / HALF
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    small, ground = tile[::2, ::2].astype(np.float32), baseline[::2, ::2].astype(np.float32)
    paper = float(np.median(ground[radius > 13.2]))
    circle = (ground < 0.5 * paper) & (radius <= 12.5)         # the dark part of the empty mat
    if circle.sum() < 200:
        return None
    dark = float(np.median(ground[circle]))
    light = small[circle] > dark + 0.4 * (paper - dark)
    return x[circle], y[circle], light


def piece_centre(state):
    """Where the middle of the piece is, in mm from the middle of its circle: (dx, dy).

    On the black circle the piece's body is light and whatever it does not cover is still black, so the piece's edge
    shows as a light/dark boundary inside the circle. The middle that best explains which parts of the circle are light
    is the piece's middle. A piece covering the whole circle gives no boundary, and then the answer is the middle of
    the circle. Without a black circle there is nothing to see the edge against, and it is the middle of the circle.
    """
    import numpy as np

    if state is None:
        return 0.0, 0.0
    gx, gy, light = state

    def agreement(dx, dy):
        inside = (gx - dx) ** 2 + (gy - dy) ** 2 <= PIECE_RADIUS ** 2
        return int(np.count_nonzero(inside == light)) - 0.002 * (dx * dx + dy * dy)    # nearer the middle wins a tie

    best = max(((agreement(dx, dy), dx, dy) for dx in range(-5, 6) for dy in range(-5, 6)))
    _, bx, by = best
    best = max(((agreement(bx + fx / 4, by + fy / 4), bx + fx / 4, by + fy / 4) for fx in range(-3, 4) for fy in range(-3, 4)))
    return float(best[1]), float(best[2])


def presence(tile, baseline):
    """How much a piece covers the circle, and the two limits: below the first it is empty, above the second there is a piece.

    On a black circle it is the share of the circle that is light. Otherwise it is the share of the circle's rim that
    has changed since the mat was empty. Returns (amount, empty_below, piece_from, the black circle or None).
    """
    import numpy as np

    state = black_circle(tile, baseline)
    if state is not None:
        return float(state[2].mean()), 0.12, 0.35, state
    body = _templates()[0]
    delta = np.abs(tile.astype(np.int16) - baseline.astype(np.int16))
    return float(np.mean(delta[body] >= 29)), 0.17, 0.55, None


def ink_in_piece(tile, centre):
    """The marks on the piece: what differs most from its body colour, inside the piece's own edge.

    ``centre`` is the piece's middle (dx, dy in mm), so the black circle showing round its edge is left out.
    """
    import cv2
    import numpy as np

    _, _, x, y = _wide_masks()
    inside = np.hypot(x - centre[0], y - centre[1]) <= EDGE
    tint = float(np.percentile(tile[np.hypot(x - centre[0], y - centre[1]) <= 9.0], 80))
    difference = np.abs(tile.astype(np.float32) - tint)
    ink = ((difference > max(32.0, 0.5 * float(np.percentile(difference[inside], 98)))) & inside).astype(np.uint8)
    # A mark is at least 3 mm wide. The thin line round a piece's edge, and specks, are not marks.
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0


def half_density(mask):
    import cv2
    import numpy as np

    size = 2 * HALF_RADIUS + 1
    return (cv2.resize(np.asarray(mask, np.float32), (size, size), interpolation=cv2.INTER_AREA) > 0.5).astype(np.float32)


def best_match(ink, shapes):
    """How well the ink (at half density) matches the best of the shapes, wherever it sits: (IoU, (dx, dy) in pixels)."""
    import cv2
    import numpy as np

    padded = cv2.copyMakeBorder(ink, SEARCH, SEARCH, SEARCH, SEARCH, cv2.BORDER_CONSTANT, value=0)
    area = float(ink.sum())
    best = (0.0, (0, 0))
    for shape in shapes:
        inter = cv2.matchTemplate(padded, shape, cv2.TM_CCORR)
        iou = inter / np.maximum(float(shape.sum()) + area - inter, 1.0)
        row, column = np.unravel_index(int(np.argmax(iou)), iou.shape)
        if iou[row, column] > best[0]:
            best = (float(iou[row, column]), (column - SEARCH, row - SEARCH))
    return best


def ink_of(tile):
    """The mark on a piece: where the picture differs most from the piece's own body colour, in the middle of the circle."""
    import numpy as np

    body, centre, _, _ = _templates()
    tint = float(np.median(tile[body]))
    difference = np.abs(tile.astype(np.float32) - tint)
    # Half way between the piece and its mark, so a soft or out-of-focus edge does not fatten or thin the mark.
    return (difference > max(32.0, 0.5 * float(np.percentile(difference[centre], 98)))) & centre


def _corrected(tile, baseline):
    """The tile with the camera's overall gain taken off, so it can be compared with the empty mat."""
    import numpy as np

    outside = _templates()[3]
    gain = float(np.median(tile[outside])) / max(float(np.median(baseline[outside])), 1.0)
    if 0.4 <= gain <= 2.0 and abs(gain - 1) > 0.02:
        return np.clip(tile.astype(np.float32) / gain, 0, 255).astype(np.uint8)
    return tile


def mark_of(tile, baseline):
    """If a piece is on this circle, its mark as a mask centred on the piece, otherwise None. Used to teach the camera."""
    import cv2
    import numpy as np

    tile = _corrected(tile, baseline)
    amount, _, piece_from, state = presence(tile, baseline)
    if amount < piece_from:
        return None
    dx, dy = piece_centre(state)
    ink = ink_in_piece(tile, (dx, dy))
    if ink.sum() < 95:
        return None
    shift = np.float32([[1, 0, -dx * DENSITY], [0, 1, -dy * DENSITY]])             # back to the middle of the patch
    return cv2.warpAffine(ink.astype(np.uint8), shift, ink.shape[::-1], flags=cv2.INTER_NEAREST) > 0


def present(tile, baseline):
    """Whether something like a piece covers this circle."""
    tile = _corrected(tile, baseline)
    amount, _, piece_from, _ = presence(tile, baseline)
    return bool(amount >= piece_from)


def inspect(tile, baseline, learned=None, report=None, rgb=None):
    """What is on one circle, and if the answer is "?", why.

    Returns (mark, detail). ``mark`` is "" for an empty circle, X, O or UNKNOWN. ``detail`` is a short
    plain-English reason that goes with an UNKNOWN, and is empty otherwise. ``learned`` is what the
    person has taught the camera about their own pieces: the shapes of the marks, which are only asked when
    the built-in shapes are not sure, and the colours of the pieces. ``rgb`` is the circle in colour, which
    the colours need. If ``report`` is a dict, it is filled with what the reading worked from.
    """
    import numpy as np

    centre = _templates()[1]
    tile = _corrected(tile, baseline)
    delta = np.abs(tile.astype(np.int16) - baseline.astype(np.int16))
    changed, empty_below, piece_from, state = presence(tile, baseline)
    if report is not None:
        report.update(tile=tile, changed=float(changed), ink=None, size=0, scores={}, colour=None, colour_vote=None)
    if changed < empty_below:
        return "", ""
    if changed < piece_from:
        # The rim of the circle differs, but is the middle as it was? A piece changes the middle a lot. A circle
        # whose picture has shifted a little, or is shaded or lit differently at the edge, does not.
        if np.mean(delta[centre] >= 29) < 0.05:
            return "", ""
        return UNKNOWN, "something is partly on this circle, or in its way"
    middle = piece_centre(state)                        # where the piece really sits on its circle
    ink = ink_in_piece(tile, middle)
    by_shape, scores = None, {}
    size = int(ink.sum())
    if report is not None:
        report.update(ink=ink, size=size, middle=middle)

    def verdict(found):
        best, alternate = sorted(found, key=found.__getitem__, reverse=True)
        return best if found[best] >= 0.60 and found[best] - found[alternate] >= 0.12 else None

    if size >= 95:
        half = half_density(ink)
        scores = {mark: best_match(half, shapes)[0] for mark, shapes in _match_templates().items()}
        by_shape = verdict(scores)
        if by_shape is None and learned is not None and learned.ready():
            taught = {mark: max(scores[mark], best_match(half, learned.templates(mark))[0] if learned.has(mark) else 0.0)
                      for mark in scores}
            by_shape = verdict(taught)
            scores = taught
    by_colour = None
    if rgb is not None and learned is not None and learned.colours_ready():
        lab, swatch = body_colour(rgb)
        by_colour = learned.colour_vote(lab)
        if report is not None:
            report.update(colour=swatch, colour_vote=by_colour)
    if report is not None:
        report["scores"] = dict(scores)
    if by_shape and by_colour and by_shape != by_colour:
        return UNKNOWN, f"the mark looks like an {by_shape} but the piece's colour is that of an {by_colour}"
    if by_shape:
        return by_shape, ""
    if by_colour:
        return by_colour, ""              # the colour decides when the mark does not show or is not clear
    if size < 95:
        return UNKNOWN, "a piece is here but its X or O mark does not show up. Check the lighting"
    return UNKNOWN, (f"the mark is not clearly an X or an O (it matches an X {scores[X]:.0%} and an O {scores[O]:.0%}). "
                     "Is the piece centred and the right way up?")


def piece(tile, baseline, learned=None, rgb=None):
    return inspect(tile, baseline, learned, rgb=rgb)[0]


def look(grey, baseline, layout, name, learned=None, colour=None):
    """What the Pi sees on one circle: (mark, reason, report). The report has the tile and the mark's mask for drawing."""
    centre = layout.positions[name]
    scale = layout.piece_scale
    report = {}
    rgb = None if colour is None else _patch_colour(colour, centre, scale)
    mark, why = inspect(_patch(grey, centre, scale), _patch(baseline, centre, scale), learned, report, rgb)
    return mark, why, report


def pixels_per_mm(view):
    """How big the mat is in the camera's picture: pixels for each millimetre, from the corner markers."""
    import numpy as np

    corners = np.asarray(view.corners, float)
    anchors = np.asarray(tuple(view.layout.anchors.values()), float)
    ratios = [np.hypot(*(corners[i] - corners[(i + 1) % 4])) / np.hypot(*(anchors[i] - anchors[(i + 1) % 4]))
              for i in range(4)]
    return float(np.mean(ratios))


def explain(grey, baseline, layout, name, learned=None, colour=None):
    """Why one circle reads "?": the reason, in plain English."""
    return look(grey, baseline, layout, name, learned, colour)[1]


def side_by_side(view, reference, centre, size=150, window=44, turned=False):
    """The same patch of mat, now and when empty, as two pictures. Both are looked at through the same registration."""
    import cv2

    def crop(image):
        density = CLEAR_DENSITY
        x, y = round(centre[0] * density), round(centre[1] * density)
        half = round(window / 2 * density)
        padded = cv2.copyMakeBorder(image, half, half, half, half, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        patch = padded[y:y + 2 * half, x:x + 2 * half]
        patch = cv2.resize(patch, (size, size), interpolation=cv2.INTER_CUBIC)
        return cv2.rotate(patch, cv2.ROTATE_180) if turned else patch

    return crop(view.colour), crop(reference.colour)


def read_position(grey, baseline, layout=STANDARD_MAT, learned=None, colour=None):
    """What is on every circle. ``colour`` is the mat's colour picture, used once the pieces' colours have been taught."""
    scale = layout.piece_scale
    symbols = {name: piece(_patch(grey, centre, scale), _patch(baseline, centre, scale), learned,
                           None if colour is None else _patch_colour(colour, centre, scale))
               for name, centre in layout.positions.items()}
    return Position(tuple(symbols[name] for name in CELLS), tuple(symbols[name] for name in layout.reserve))


def mat_clear(view, reference, position):
    """Check for foreground objects between the markers, including between the slots."""
    import cv2

    delta = cv2.absdiff(view.colour, reference.colour)
    foreground = cv2.bitwise_not(cv2.inRange(delta, (0, 0, 0), (34, 34, 34)))
    radius = round((PIECE_RADIUS + 2) * view.layout.piece_scale * CLEAR_DENSITY)
    for (x, y), mark in zip(view.layout.positions.values(), (*position.board, *position.reserve)):
        if mark in (X, O):
            cv2.circle(foreground, (round(x * CLEAR_DENSITY), round(y * CLEAR_DENSITY)), radius, 0, -1)

    xs, ys = zip(*view.layout.anchors.values())
    left, right = (round(x * CLEAR_DENSITY) for x in (min(xs), max(xs)))
    top, bottom = (round(y * CLEAR_DENSITY) for y in (min(ys), max(ys)))
    region = foreground[top:bottom, left:right]
    # Remove thin edges from minor registration differences before measuring the obstruction.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    region = cv2.morphologyEx(region, cv2.MORPH_OPEN, kernel)
    return cv2.countNonZero(region) <= 40 * CLEAR_DENSITY**2
