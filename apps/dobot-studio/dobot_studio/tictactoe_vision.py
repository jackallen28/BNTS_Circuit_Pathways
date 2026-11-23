"""Identify the flush playing pieces in the registered overhead tray view."""
from dataclasses import dataclass
from functools import lru_cache
from math import radians

from .block_vision import detect
from .tictactoe import (
    ANCHORS, BANK, CELLS, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH,
    MAT_HEIGHT, MAT_POSITIONS, MAT_WIDTH, NOUGHT_INNER, NOUGHT_OUTER, O, UNKNOWN, X,
)

DENSITY = 4
RADIUS = 13 * DENSITY


@dataclass(frozen=True)
class Position:
    board: tuple
    reserve: tuple


@dataclass(frozen=True)
class Reference:
    grey: object
    corners: object
    shape: tuple


def rectify(rgb):
    import cv2
    import numpy as np

    markers = detect(rgb)
    if not all(marker in markers for marker in ANCHORS):
        raise ValueError("Show all four mat markers, numbered 44–47.")
    corners = np.array([markers[marker].mean(axis=0) for marker in ANCHORS], dtype=np.float32)
    if not cv2.isContourConvex(corners) or abs(cv2.contourArea(corners)) < 12000:
        raise ValueError("Move the camera closer and keep the full mat in view.")
    target = np.asarray(tuple(ANCHORS.values()), dtype=np.float32) * DENSITY
    matrix = cv2.getPerspectiveTransform(corners, target)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    warped = cv2.warpPerspective(grey, matrix, (MAT_WIDTH*DENSITY, MAT_HEIGHT*DENSITY))
    return corners, warped, matrix


def _patch(image, centre):
    x, y = (round(value * DENSITY) for value in centre)
    return image[y - RADIUS:y + RADIUS + 1, x - RADIUS:x + RADIUS + 1]


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


def read_position(grey, baseline):
    symbols = {name: piece(_patch(grey, centre), _patch(baseline, centre))
               for name, centre in MAT_POSITIONS.items()}
    return Position(tuple(symbols[name] for name in CELLS), tuple(symbols[name] for name in BANK))
