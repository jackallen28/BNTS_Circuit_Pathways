"""Calibrated tabletop vision for flat chips and staged assembly checks."""
from dataclasses import dataclass
import math

from .learning import symbol_features
from .robot import Pose


COLOURS = ("Red", "Orange", "Yellow", "Green", "Cyan", "Blue", "Purple")
ZONE_NAMES = tuple(f"{row}{column}" for row in "ABC" for column in "123")


class Calibration:
    """Map three camera landmarks to taught robot positions on a plane."""

    def __init__(self, marks, poses):
        if len(marks) != 3 or len(poses) != 3:
            raise ValueError("Teach three calibration marks.")
        self.marks = tuple(marks)
        self.poses = tuple(poses)
        self.pixel_area = self._denominator(self.marks)
        self.robot_marks = tuple((p.x, p.y) for p in poses)
        robot_area = self._denominator(self.robot_marks)
        if abs(self.pixel_area) < 1000 or abs(robot_area) < 200:
            raise ValueError("Space the three marks apart in a triangle.")
        if max(math.dist(a, b) for a in self.robot_marks for b in self.robot_marks) > 150:
            raise ValueError("Keep calibration marks within 150 mm of each other.")
        if max(p.z for p in poses) - min(p.z for p in poses) > 3:
            raise ValueError("Teach all marks at the same chip pickup height.")
        self.mm_per_pixel_area = abs(robot_area / self.pixel_area)

    @staticmethod
    def _denominator(points):
        (ax, ay), (bx, by), (cx, cy) = points
        return (by-cy)*(ax-cx) + (cx-bx)*(ay-cy)

    @classmethod
    def _weights(cls, anchors, point):
        (ax, ay), (bx, by), (cx, cy) = anchors
        x, y = point
        area = cls._denominator(anchors)
        first = ((by-cy)*(x-cx) + (cx-bx)*(y-cy)) / area
        second = ((cy-ay)*(x-cx) + (ax-cx)*(y-cy)) / area
        return first, second, 1 - first - second

    def contains(self, point, inset=0.0):
        return min(self._weights(self.marks, point)) >= inset

    def contains_robot(self, pose):
        return min(self._weights(self.robot_marks, (pose.x, pose.y))) >= 0

    def pick(self, point, rotation):
        weights = self._weights(self.marks, point)
        if min(weights) < 0:
            raise ValueError("Chip lies outside the calibrated area.")
        x, y, z = (sum(weight * getattr(pose, axis) for weight, pose in zip(weights, self.poses))
                   for axis in ("x", "y", "z"))
        return Pose(x, y, z, rotation)


@dataclass(frozen=True)
class Chip:
    centre: tuple
    bounds: tuple
    label: str
    bin_name: str | None
    area_mm2: float


def _change_mask(frame, baseline):
    import cv2
    import numpy as np

    delta = cv2.absdiff(cv2.cvtColor(frame, cv2.COLOR_RGB2LAB),
                        cv2.cvtColor(baseline, cv2.COLOR_RGB2LAB))
    return np.max(delta, axis=2) >= 24


def _colour(rgb):
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    strong = hsv[(hsv[:, 1] > 75) & (hsv[:, 2] > 58), 0]
    if len(strong) < 0.63 * len(hsv):
        return "Unknown"
    bands = np.digitize(strong, (9, 20, 35, 83, 103, 136, 170)) % 7
    count = np.bincount(bands, minlength=len(COLOURS))
    best = int(count.argmax())
    return COLOURS[best] if count[best] >= 0.78 * len(strong) else "Unknown"


def _text(frame, bounds, classifier, descriptor):
    import cv2

    x, y, width, height = bounds
    margin = max(2, round(min(width, height) * 0.08))
    inner = frame[y + margin:y + height - margin, x + margin:x + width - margin]
    h, w = inner.shape[:2]
    size = max(h, w, 32) + 4
    left, top = (size - w) // 2, (size - h) // 2
    padded = cv2.copyMakeBorder(inner, top, size-h-top, left, size-w-left,
                               cv2.BORDER_CONSTANT, value=(237, 237, 237))
    vector, _ = symbol_features(padded, (0, 0, size), descriptor)
    if vector is not None and classifier is not None:
        match = classifier.predict(vector)
        if match:
            label, action = match
            return label, action if action in ("A", "B") else None
    return "Unknown", None


def find_chips(frame, empty, calibration, colour_bins, classifier=None, descriptor=None):
    import cv2
    import numpy as np

    if frame.shape != empty.shape:
        raise ValueError("Camera view size changed. Capture the empty tray again.")
    mask = _change_mask(frame, empty).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(mask)
    chips = []
    for index in range(1, count):
        x, y, width, height, area = map(int, stats[index])
        if (min(width, height) < 18 or max(width, height) > 3 * min(width, height)
                or area < 240 or area > abs(calibration.pixel_area) * 0.14
                or area < 0.40 * width * height):
            continue
        centre = tuple(centres[index])
        corners = ((x, y), (x + width, y), (x, y + height), (x + width, y + height))
        if not calibration.contains(centre, 0.04) or not all(calibration.contains(p) for p in corners):
            continue
        bounds = (x, y, width, height)
        if colour_bins is not None:
            patch = frame[y:y + height, x:x + width]
            label = _colour(patch[labels[y:y + height, x:x + width] == index])
            target = colour_bins.get(label)
        else:
            label, target = _text(frame, bounds, classifier, descriptor)
        chips.append(Chip(centre, bounds, label, target, area * calibration.mm_per_pixel_area))
    return sorted(chips, key=lambda chip: (chip.centre[1], chip.centre[0]))


def same_chip(before, after, require_bin=True):
    return ((not require_bin or before.bin_name and before.bin_name == after.bin_name)
            and before.label == after.label
            and math.dist(before.centre, after.centre) <= 10
            and 0.8 <= after.area_mm2 / before.area_mm2 <= 1.2)


def inspection_view(frame):
    """Use the central square of the fixed overhead view for inspection."""
    import cv2

    h, w = frame.shape[:2]
    extent = min(h, w) * 3 // 4
    left, top = (w - extent) // 2, (h - extent) // 2
    return cv2.resize(frame[top:top+extent, left:left+extent], (180, 180), interpolation=cv2.INTER_AREA)


def inspect_assembly(current, expected, empty=None):
    import numpy as np

    changed = _change_mask(current, expected)
    present = _change_mask(current, empty) if empty is not None else None
    wanted = _change_mask(expected, empty) if empty is not None else None
    findings = []
    for index, zone in enumerate(ZONE_NAMES):
        row, col = divmod(index, 3)
        section = np.s_[row*60:(row+1)*60, col*60:(col+1)*60]
        if np.mean(changed[section]) < 0.085:
            continue
        cause = "Changed"
        if empty is not None:
            missing = np.mean(wanted[section] & ~present[section])
            extra = np.mean(present[section] & ~wanted[section])
            if missing > 0.075 and missing > 2 * extra:
                cause = "Possible missing material"
            elif extra > 0.075 and extra > 2 * missing:
                cause = "Possible extra material"
        findings.append((zone, cause))
    return findings
