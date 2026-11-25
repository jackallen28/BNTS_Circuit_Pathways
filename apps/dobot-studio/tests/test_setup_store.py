"""The saved setup: written by itself, kept as the latest copy, and put aside rather than lost."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from time import time
import json
import unittest

import numpy as np
from PIL import Image

from dobot_studio.pieces import Learned
from dobot_studio.setup_store import FILE, IMAGE, SetupStore
from dobot_studio.tictactoe import O, X


class SetupStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(mkdtemp())
        self.addCleanup(rmtree, self.folder, True)
        self.store = SetupStore(self.folder / "setup")
        self.picture = Image.fromarray(np.full((8, 12, 3), 77, np.uint8))

    def test_nothing_is_saved_to_begin_with(self):
        self.assertFalse(self.store.has())
        self.assertIsNone(self.store.load())
        self.assertEqual(self.store.when(), "")

    def test_a_setup_is_saved_and_read_back_with_its_picture(self):
        self.store.save({"saved_at": time(), "layout": "Small", "pick_press": 1.5}, self.picture)
        self.assertTrue(self.store.has())
        data, image = self.store.load()
        self.assertEqual((data["layout"], data["pick_press"], data["version"]), ("Small", 1.5, 1))
        self.assertEqual(np.asarray(Image.open(image)).shape, (8, 12, 3))
        self.assertEqual(self.store.when(), "a moment ago")

    def test_the_picture_is_only_written_when_it_is_given_so_a_small_change_costs_little(self):
        self.store.save({"saved_at": time()}, self.picture)
        picture = self.folder / "setup" / "latest" / IMAGE
        before = picture.stat().st_mtime_ns
        self.store.save({"saved_at": time(), "pick_press": 2.0})
        self.assertEqual(picture.stat().st_mtime_ns, before)
        self.assertEqual(self.store.load()[0]["pick_press"], 2.0)

    def test_saving_leaves_no_half_written_files_behind(self):
        for number in range(3):
            self.store.save({"saved_at": time(), "n": number}, self.picture)
        self.assertEqual(sorted(path.name for path in (self.folder / "setup" / "latest").iterdir()), sorted([FILE, IMAGE]))

    def test_a_reset_puts_the_latest_aside_and_it_can_still_be_used(self):
        self.store.save({"saved_at": time(), "layout": "Small"}, self.picture)
        self.assertTrue(self.store.keep_backup())
        self.assertFalse(self.store.has("latest"))
        self.assertTrue(self.store.has("backup"))
        self.assertEqual(self.store.load("backup")[0]["layout"], "Small")
        self.store.save({"saved_at": time(), "layout": "Compact"}, self.picture)       # a new setup begins
        self.store.keep_backup()                                                      # the older backup is replaced
        self.assertEqual(self.store.load("backup")[0]["layout"], "Compact")
        self.assertFalse(self.store.keep_backup(), "nothing to put aside")

    def test_discarding_removes_it(self):
        self.store.save({"saved_at": time()}, self.picture)
        self.store.discard()
        self.assertFalse(self.store.has())

    def test_a_damaged_or_unknown_copy_is_ignored_not_trusted(self):
        self.store.save({"saved_at": time()}, self.picture)
        path = self.folder / "setup" / "latest" / FILE
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.store.load())
        path.write_text(json.dumps({"version": 99}), encoding="utf-8")
        self.assertIsNone(self.store.load())
        path.write_text(json.dumps([1, 2]), encoding="utf-8")
        self.assertIsNone(self.store.load())

    def test_how_long_ago_is_said_in_words(self):
        for seconds, words in ((10, "a moment ago"), (600, "10 minutes ago"), (7200, "2 hours ago")):
            self.store.save({"saved_at": time() - seconds}, self.picture)
            self.assertEqual(self.store.when(), words)


class LearnedDataTests(unittest.TestCase):
    def test_what_the_camera_was_taught_survives_being_saved(self):
        learned = Learned()
        mask = np.zeros((137, 137), bool)
        mask[40:90, 60:75] = True
        learned.add(X, [mask], "close")
        learned.add(O, [mask], "distance", [np.array((70.0, 40.0, 10.0), np.float32)])
        again = Learned.from_data(json.loads(json.dumps(learned.to_data())))
        self.assertTrue(np.array_equal(again.shapes[X][0][0], mask))
        self.assertEqual(again.shapes[X][0][1], "close")
        self.assertEqual(again.summary(), learned.summary())
        self.assertEqual([list(map(float, lab)) for lab in again.colours[O]], [[70.0, 40.0, 10.0]])

    def test_nothing_taught_is_nothing_saved(self):
        again = Learned.from_data(Learned().to_data())
        self.assertFalse(again.ready())


if __name__ == "__main__":
    unittest.main()
