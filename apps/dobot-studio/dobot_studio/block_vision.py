"""Read top-face fiducials with two camera-calibrated height planes."""
from functools import lru_cache

from .blocks import ANCHORS, MARKER, SLOTS


def square(x, y):
    r = MARKER / 2
    return ((x-r, y+r), (x+r, y+r), (x+r, y-r), (x-r, y-r))


def detect(rgb):
    import cv2

    detector = _detector()
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    if ids is None:
        return {}
    found = {}
    for marker, quad in zip(ids.ravel(), corners):
        marker = int(marker)
        if marker in found:
            raise ValueError(f"Marker {marker} is duplicated in the camera view.")
        found[marker] = quad.reshape(4, 2)
    return found


@lru_cache(maxsize=1)
def _detector():
    import cv2

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(dictionary, parameters)



def calibrate(markers):
    import cv2
    import numpy as np

    if not all(marker in markers for marker in ANCHORS):
        raise ValueError("Show all four calibration markers 40–43.")
    source = np.concatenate([markers[marker] for marker in ANCHORS]).astype(np.float32)
    target = np.array([point for x, y in ANCHORS.values() for point in square(x, y)], dtype=np.float32)
    matrix, _ = cv2.findHomography(source, target)
    if matrix is None:
        raise ValueError("Calibration markers do not form a usable plane.")
    projected = cv2.perspectiveTransform(source[None], matrix)[0]
    if not np.isfinite(projected).all() or np.linalg.norm(projected - target, axis=1).max() > 1.6:
        raise ValueError("Calibration error is too high. Check marker orientation, height and print scale.")
    return matrix


def locate(markers, planes):
    import cv2
    import numpy as np

    slots = {}
    errors = []
    if set(planes) != {0, 1}:
        return slots, errors
    project = {}
    for slot in SLOTS:
        matrix = np.linalg.inv(planes[slot.level])
        quad = np.array(square(slot.x, slot.y), dtype=np.float32)[None]
        project[slot] = cv2.perspectiveTransform(quad, matrix)[0]
    for marker, actual in markers.items():
        if marker in ANCHORS:
            continue
        if not 0 <= marker <= 9:
            errors.append(f"Unsupported marker {marker}")
            continue
        scores = []
        for slot, expected in project.items():
            # The square may rotate by a quarter turn on the block.
            edge = np.linalg.norm(expected - np.roll(expected, 1, axis=0), axis=1).mean()
            if edge < 5:
                continue
            error = min(np.sqrt(np.mean(np.sum((expected - np.roll(actual, turn, axis=0))**2, axis=1)))
                        for turn in range(4))
            scores.append((float(error * MARKER / edge), slot))
        scores.sort()
        if len(scores) < 2 or scores[0][0] > 2.2 or scores[1][0] - scores[0][0] < 0.85:
            errors.append(f"Marker {marker} is off-grid or ambiguous")
            continue
        slot = scores[0][1]
        if slot in slots:
            errors.append("Two blocks match the same location")
        else:
            slots[slot] = marker
    return slots, errors


def anchors_stable(markers, plane):
    import cv2
    import numpy as np

    if not all(marker in markers for marker in ANCHORS):
        return False
    corners = np.concatenate([markers[marker] for marker in ANCHORS]).astype(np.float32)
    expected = np.array([point for x, y in ANCHORS.values() for point in square(x, y)], dtype=np.float32)
    actual = cv2.perspectiveTransform(corners[None], plane)[0]
    return bool(np.isfinite(actual).all() and np.linalg.norm(actual - expected, axis=1).max() <= 2.3)
