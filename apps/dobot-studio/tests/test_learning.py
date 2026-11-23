from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from dobot_studio.learning import (
    CUSTOM_HAND, SYMBOL, Examples, hand_features, load_classes, new_symbol_descriptor,
    save_classes, symbol_features, symbol_region, train,
)


class RecognitionTests(unittest.TestCase):
    def test_symbol_profile_matches_known_cards_and_rejects_a_novel_symbol(self):
        hog = new_symbol_descriptor()
        region = symbol_region(640, 480)

        def card(symbol, angle):
            frame = np.full((480, 640, 3), 237, dtype=np.uint8)
            if symbol == "Ring":
                cv2.circle(frame, (320, 240), 58, (20, 20, 20), 14)
            elif symbol == "Cross":
                cv2.line(frame, (270, 190), (370, 290), (20, 20, 20), 14)
                cv2.line(frame, (370, 190), (270, 290), (20, 20, 20), 14)
            elif symbol == "Line":
                cv2.line(frame, (255, 240), (385, 240), (20, 20, 20), 14)
            rotation = cv2.getRotationMatrix2D((320, 240), angle, 1)
            moved = cv2.warpAffine(frame, rotation, (640, 480), borderValue=(237, 237, 237))
            features, _ = symbol_features(moved, region, hog)
            return features

        classes = {
            name: Examples(action, [card(name, angle).tolist() for angle in range(-4, 4)])
            for name, action in (("Neutral", "No action"), ("Ring", "Position A"), ("Cross", "Position B"))
        }
        learner, correct, total = train(SYMBOL, classes)
        self.assertEqual(correct, total)
        self.assertEqual(learner.predict(card("Ring", 5)), ("Ring", "A"))
        self.assertEqual(learner.predict(card("Cross", 5)), ("Cross", "B"))
        self.assertEqual(learner.predict(card("Neutral", 0)), ("Neutral", None))
        self.assertIsNone(learner.predict(card("Line", 0)))
        self.assertIsNone(symbol_features(np.zeros((480, 640, 3), np.uint8), region, hog)[0])
        with TemporaryDirectory() as path:
            folder = Path(path)
            save_classes(folder, SYMBOL, classes)
            self.assertEqual(load_classes(folder, SYMBOL), classes)
            (folder / "symbols.json").write_text('{"version":1,"classes":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_classes(folder, SYMBOL)

    def test_hand_features_ignore_translation_and_scale_and_reject_ambiguous_matches(self):
        def features(shift, scale, direction):
            points = [SimpleNamespace(x=shift + direction * scale * i / 20,
                                      y=0.35 + scale * i / 20, z=0)
                      for i in range(21)]
            return hand_features(points, 640, 480)

        hand = features(0.45, 0.2, 1)
        similar = features(0.34, 0.25, 1)
        other = features(0.55, 0.23, -1)
        np.testing.assert_allclose(hand, similar, atol=1e-6)
        examples = {
            "Neutral": Examples("No action", [other.tolist()] * 8),
            "Point": Examples("Stop", [hand.tolist()] * 8),
        }
        learner, correct, total = train(CUSTOM_HAND, examples)
        self.assertEqual(correct, total)
        self.assertEqual(learner.predict(similar), ("Point", "Stop"))
        examples["Similar"] = Examples("Position A", [hand.tolist()] * 8)
        learner, _, _ = train(CUSTOM_HAND, examples)
        self.assertIsNone(learner.predict(similar))
        self.assertIsNone(hand_features([], 640, 480))


if __name__ == "__main__":
    unittest.main()
