"""Local, supervised recognition from labelled camera features."""
from dataclasses import dataclass, field
import json
from math import isfinite
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


CUSTOM_HAND = "Custom hand signs"
SYMBOL = "Printed/drawn symbols"
TRAINABLE = (CUSTOM_HAND, SYMBOL)
NEUTRAL = "Neutral"
ACTIONS = {"Position A": "A", "Position B": "B", "Stop": "Stop", "No action": None}
NO_ACTION = "No action"
MIN_EXAMPLES = 8
MAX_EXAMPLES = 80
MAX_CLASSES = 12
FEATURE_SIZE = {CUSTOM_HAND: 63, SYMBOL: 388}
PROFILE_FILES = {CUSTOM_HAND: "hand-signs.json", SYMBOL: "symbols.json"}


@dataclass
class Examples:
    action: str
    vectors: list = field(default_factory=list)


def empty_classes():
    return {NEUTRAL: Examples(NO_ACTION)}


def default_training_folder():
    home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return home / "dobot-studio" / "training"


def save_classes(folder, mode, classes):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / PROFILE_FILES[mode]
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as stream:
        provisional = Path(stream.name)
        try:
            json.dump({"version": 1, "classes": [
                {"name": name, "action": group.action, "samples": group.vectors}
                for name, group in classes.items()
            ]}, stream, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            provisional.unlink(missing_ok=True)
            raise
    try:
        provisional.replace(target)
    finally:
        provisional.unlink(missing_ok=True)


def load_classes(folder, mode):
    try:
        with (folder / PROFILE_FILES[mode]).open(encoding="utf-8") as stream:
            profile = json.load(stream)
    except FileNotFoundError:
        return empty_classes()
    try:
        if profile["version"] != 1 or not 2 <= len(profile["classes"]) <= MAX_CLASSES:
            raise ValueError("Unsupported profile")
        classes = {}
        names = set()
        for entry in profile["classes"]:
            name, action, vectors = entry["name"], entry["action"], entry["samples"]
            if (not valid_name(name) or name.casefold() in names or action not in ACTIONS
                    or not isinstance(vectors, list) or len(vectors) > MAX_EXAMPLES):
                raise ValueError("Invalid class")
            for vector in vectors:
                if (not isinstance(vector, list) or len(vector) != FEATURE_SIZE[mode]
                        or not all(type(value) in (int, float) and isfinite(value)
                                   and abs(value) <= 4 for value in vector)):
                    raise ValueError("Invalid sample")
            classes[name] = Examples(action, vectors)
            names.add(name.casefold())
        check_classes(classes)
        return classes
    except (KeyError, OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid saved training profile: {PROFILE_FILES[mode]}") from error


def valid_name(name):
    return isinstance(name, str) and 1 <= len(name) <= 24 and name.isprintable() and name == name.strip()


def check_classes(classes):
    if NEUTRAL not in classes or classes[NEUTRAL].action != NO_ACTION:
        raise ValueError("Keep Neutral as a no-action example class.")
    if len(classes) < 2:
        raise ValueError("Add at least one named example class.")
    short = [name for name, group in classes.items() if len(group.vectors) < MIN_EXAMPLES]
    if short:
        raise ValueError(f"Capture {MIN_EXAMPLES} examples for each class. Still needed: " + ", ".join(short))


def hand_features(points, width, height):
    """Describe hand shape and orientation relative to the wrist."""
    import numpy as np

    if len(points) != 21 or any(not 0.02 < p.x < 0.98 or not 0.02 < p.y < 0.98 for p in points):
        return None
    hand = np.array([(p.x * width, p.y * height, p.z * width) for p in points], dtype=np.float32)
    hand -= hand[0].copy()
    extent = np.linalg.norm(hand, axis=1).max()
    if not np.isfinite(extent) or extent < min(width, height) * 0.08:
        return None
    return (hand / extent).ravel()


def symbol_region(width, height):
    span = round(min(width, height) * 0.56)
    return (width - span) // 2, (height - span) // 2, span


def symbol_features(rgb, region, hog):
    """Normalise dark ink on light card to a centred shape descriptor."""
    import cv2
    import numpy as np

    x, y, span = region
    if span < 32:
        return None, "Camera image is too small"
    gray = cv2.cvtColor(rgb[y:y + span, x:x + span], cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    paper = float(np.median(gray))
    if paper < 125 or np.mean(gray > 115) < 0.65:
        return None, "Fill the guide with light paper"
    ink = (gray < min(172, paper - 35)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    kept = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= max(8, span * span * 0.0004)]
    if not kept:
        return np.zeros(FEATURE_SIZE[SYMBOL], dtype=np.float32), "Blank card"
    accepted = np.zeros(count, dtype=np.uint8)
    accepted[kept] = 255
    mask = accepted[labels]
    bx, by, width, height = cv2.boundingRect(mask)
    if min(bx, by, span - bx - width, span - by - height) < 3:
        return None, "Keep the whole symbol inside the guide"
    if max(width, height) < 0.16 * span or np.count_nonzero(mask) > 0.35 * span * span:
        return None, "Show one clear, dark symbol"
    scale = 26 / max(width, height)
    thumb = cv2.resize(mask[by:by + height, bx:bx + width],
                       (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA)
    canvas = np.zeros((32, 32), dtype=np.uint8)
    th, tw = thumb.shape
    top, left = (32 - th) // 2, (32 - tw) // 2
    canvas[top:top + th, left:left + tw] = thumb
    density = cv2.resize(canvas, (8, 8), interpolation=cv2.INTER_AREA).ravel() / 255
    return np.concatenate((hog.compute(canvas).ravel(), density)).astype(np.float32), "Symbol in guide"


def new_symbol_descriptor():
    import cv2

    return cv2.HOGDescriptor((32, 32), (16, 16), (8, 8), (8, 8), 9)


class Recognizer:
    """Nearest-example learner with class-specific rejection distances."""

    def __init__(self, mode, classes):
        import numpy as np

        floor, cap = (0.027, 0.115) if mode == CUSTOM_HAND else (0.039, 0.135)
        self.names = tuple(classes)
        self.actions = tuple(ACTIONS[group.action] for group in classes.values())
        groups = [np.asarray(group.vectors, dtype=np.float32) for group in classes.values()]
        self.vectors = np.concatenate(groups)
        self.starts = np.cumsum([0, *(len(group) for group in groups[:-1])])
        self.radii = []
        for group in groups:
            gaps = group[:, None, :] - group[None, :, :]
            distances = np.sqrt(np.mean(np.square(gaps), axis=2))
            np.fill_diagonal(distances, np.inf)
            radius = np.percentile(distances.min(axis=1), 90) * 1.65
            self.radii.append(float(np.clip(radius, floor, cap)))

    def predict(self, vector):
        import numpy as np

        distance = np.sqrt(np.mean(np.square(self.vectors - vector), axis=1))
        nearest = np.minimum.reduceat(distance, self.starts)
        first, second = np.argsort(nearest)[:2]
        # Require a sufficiently close match and separation from competing labels.
        if nearest[first] > self.radii[first] or nearest[first] >= nearest[second] * 0.78:
            return None
        return self.names[first], self.actions[first]


def train(mode, classes):
    """Measure held-out recognition, then fit the saved recognizer on every example."""
    check_classes(classes)
    train_set, held_out = {}, []
    for name, group in classes.items():
        train_set[name] = Examples(group.action, [v for i, v in enumerate(group.vectors) if i % 4 != 3])
        held_out.extend((name, v) for i, v in enumerate(group.vectors) if i % 4 == 3)
    learner = Recognizer(mode, train_set)
    correct = 0
    for name, vector in held_out:
        guess = learner.predict(vector)
        correct += guess is not None and guess[0] == name
    return Recognizer(mode, classes), correct, len(held_out)
