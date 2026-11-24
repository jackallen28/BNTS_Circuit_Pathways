"""Read playing pieces and check for obstructions in the registered mat view."""
from dataclasses import dataclass
from functools import lru_cache
from math import radians

from .block_vision import detect
from .tictactoe import (
    CELLS, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, MAT_LAYOUTS, MatLayout, NOUGHT_INNER,
    NOUGHT_OUTER, O, PIECE_RADIUS, STANDARD_MAT, UNKNOWN, X,
)

DENSITY = 4
RADIUS = 13 * DENSITY
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


def rectify(rgb):
    import cv2
    import numpy as np

    markers = detect(rgb)
    suitable = [layout for layout in MAT_LAYOUTS if all(marker in markers for marker in layout.anchors)]
    if len(suitable) != 1:
        raise ValueError("Show the four camera markers from one mat.")
    layout = suitable[0]
    corners = np.array([markers[marker].mean(axis=0) for marker in layout.anchors], dtype=np.float32)
    if not cv2.isContourConvex(corners) or abs(cv2.contourArea(corners)) < 12000:
        raise ValueError("Move the camera closer and keep the full mat in view.")
    target = np.asarray(tuple(layout.anchors.values()), dtype=np.float32) * DENSITY
    matrix = cv2.getPerspectiveTransform(corners, target)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    warped = cv2.warpPerspective(grey, matrix, (layout.width*DENSITY, layout.height*DENSITY))
    clear_matrix = matrix.copy()
    clear_matrix[:2] *= CLEAR_DENSITY / DENSITY
    colour = cv2.warpPerspective(rgb, clear_matrix, (layout.width*CLEAR_DENSITY, layout.height*CLEAR_DENSITY))
    return MatView(warped, colour, corners, grey.shape, matrix, layout)


def _patch(image, centre, scale):
    import cv2

    x, y = (round(value * DENSITY) for value in centre)
    radius = round(RADIUS * scale)
    tile = image[y - radius:y + radius + 1, x - radius:x + radius + 1]
    if radius == RADIUS:
        return tile
    return cv2.resize(tile, (2*RADIUS + 1, 2*RADIUS + 1), interpolation=cv2.INTER_AREA)


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
    return body, centre, {key: np.stack(value) for key, value in templates.items()}


def piece(tile, baseline):
    import numpy as np

    body, centre, templates = _templates()
    delta = np.abs(tile.astype(np.int16) - baseline.astype(np.int16))
    changed = np.mean(delta[body] >= 29)
    if changed < 0.17:
        return ""
    if changed < 0.55:
        return UNKNOWN
    tint = float(np.median(tile[body]))
    difference = np.abs(tile.astype(np.float32) - tint)
    ink = (difference > 32) & centre
    size = ink.sum()
    if size < 95:
        return UNKNOWN
    scores = {}
    for mark, shapes in templates.items():
        intersection = np.count_nonzero(shapes & ink, axis=(1, 2))
        union = np.count_nonzero(shapes, axis=(1, 2)) + size - intersection
        scores[mark] = float((intersection / union).max())
    best, alternate = sorted(scores, key=scores.__getitem__, reverse=True)
    return best if scores[best] >= 0.60 and scores[best] - scores[alternate] >= 0.12 else UNKNOWN


def read_position(grey, baseline, layout=STANDARD_MAT):
    scale = layout.piece_scale
    symbols = {name: piece(_patch(grey, centre, scale), _patch(baseline, centre, scale))
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
