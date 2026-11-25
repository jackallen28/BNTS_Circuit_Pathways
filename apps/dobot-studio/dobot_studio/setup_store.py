"""The Tic-tac-toe setup, kept on disk so a crash or a restart does not lose it.

It is saved by itself as it changes (what the arm was touched on, the nudges, the piece thickness, the pick depth, the
speed, the camera adjustments and what the camera was taught, and the picture of the empty mat the camera reads against),
and the latest copy is kept for a quick return. It is only a good copy while nothing has been moved: the mat, the camera
and the arm's base must be where they were. The setup says so when it loads one, and the camera warns if it has moved.

Two copies are kept in the folder:

* ``latest`` is the autosave. It is rewritten each time the setup changes.
* ``before-reset`` is the autosave that was there when the setup was reset (or a new one was begun), so it is not lost.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

VERSION = 1
FILE, IMAGE = "setup.json", "empty-mat.png"
COPIES = {"latest": "latest", "backup": "before-reset"}


class SetupStore:
    def __init__(self, folder):
        self.folder = Path(folder)

    def _folder(self, which):
        return self.folder / COPIES[which]

    # ---- writing
    def save(self, snapshot, image=None, which="latest"):
        """Write the setup. ``image`` is the empty-mat picture (a PIL image), only needed when it has changed."""
        folder = self._folder(which)
        folder.mkdir(parents=True, exist_ok=True)
        if image is not None:
            with NamedTemporaryFile(dir=folder, suffix=".png", delete=False) as stream:
                temporary = Path(stream.name)
            image.save(temporary, format="PNG")
            os.replace(temporary, folder / IMAGE)
        with NamedTemporaryFile("w", encoding="utf-8", dir=folder, suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": VERSION, **snapshot}, stream)
        os.replace(temporary, folder / FILE)

    def keep_backup(self):
        """Put the latest copy aside as the one from before a reset, and clear the latest."""
        latest, backup = self._folder("latest"), self._folder("backup")
        if not (latest / FILE).is_file():
            return False
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(latest), str(backup))
        return True

    def discard(self, which="latest"):
        shutil.rmtree(self._folder(which), ignore_errors=True)

    # ---- reading
    def has(self, which="latest"):
        return (self._folder(which) / FILE).is_file()

    def load(self, which="latest"):
        """(snapshot, image path or None), or None if there is no copy or it cannot be read."""
        folder = self._folder(which)
        try:
            snapshot = json.loads((folder / FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(snapshot, dict) or snapshot.get("version") != VERSION:
            return None
        image = folder / IMAGE
        return snapshot, image if image.is_file() else None

    def when(self, which="latest"):
        """When the copy was last saved, in words, or an empty string."""
        loaded = self.load(which)
        if not loaded:
            return ""
        seconds = max(0, datetime.now().timestamp() - float(loaded[0].get("saved_at", 0)))
        if seconds < 90:
            return "a moment ago"
        if seconds < 3600:
            return f"{round(seconds / 60)} minutes ago"
        if seconds < 86400:
            return f"{round(seconds / 3600)} hours ago"
        return datetime.fromtimestamp(float(loaded[0]["saved_at"])).strftime("%d %b at %H:%M")
