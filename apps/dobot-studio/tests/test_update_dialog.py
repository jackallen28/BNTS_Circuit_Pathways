"""The Check for updates window and the restart."""
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from threading import Event
from time import monotonic, sleep
from unittest import mock
import os
import sys
import tkinter as tk
import unittest

from dobot_studio.updater import UpdateResult, UpdateStatus

needs_display = unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "needs a display")


class FakeUpdater:
    def __init__(self, status, result=None, hold=None):
        self.status, self.result, self.hold = status, result, hold
        self.checks = self.updates = 0

    def version(self):
        return "abc1234  ·  2026-11-24"

    def check(self):
        self.checks += 1
        if self.hold:
            self.hold.wait(5)
        return self.status

    def update(self):
        self.updates += 1
        if self.hold:
            self.hold.wait(5)
        return self.result


CURRENT = UpdateStatus("current", "You have the latest version.", "abc1234  ·  2026-11-24", "main")
AVAILABLE = UpdateStatus("available", "A newer version is available (2 updates).", "abc1234  ·  2026-11-24", "main", 2,
                         ("Fix the camera lock", "Add the connect screen"))
DONE = UpdateResult(True, "Updated. Restart Dobot Studio to use the new version.", True)


@needs_display
class UpdateDialogTests(unittest.TestCase):
    def setUp(self):
        from dobot_studio.app import Studio

        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.addCleanup(lambda: self.root.eval("foreach id [after info] {after cancel $id}"))
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        self.studio = Studio(self.root, Path("/nonexistent"), Path(folder))

    def pump(self, seconds=1.0, until=None):
        end = monotonic() + seconds
        while monotonic() < end:
            self.root.update()
            sleep(0.01)
            if until and until():
                return True
        return until() if until else None

    def open(self, updater):
        from dobot_studio.update_dialog import UpdateDialog

        dialog = UpdateDialog(self.studio, updater)
        self.studio.update_dialog = dialog
        self.addCleanup(lambda: dialog.window.winfo_exists() and dialog.window.destroy())
        return dialog

    def enabled(self, button):
        return "disabled" not in button.state()

    def test_it_checks_when_opened_and_a_current_copy_says_so(self):
        updater = FakeUpdater(CURRENT)
        dialog = self.open(updater)
        self.assertEqual(dialog.message.get(), "Checking GitHub…")
        self.assertFalse(self.enabled(dialog.close_button), "no closing while a check is running")
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.assertEqual(updater.checks, 1)
        self.assertEqual(dialog.message.get(), "You have the latest version.")
        self.assertIn("abc1234", dialog.version.get())
        self.assertFalse(self.enabled(dialog.update_button))
        self.assertTrue(self.enabled(dialog.check_button) and self.enabled(dialog.close_button))
        self.assertFalse(self.enabled(dialog.restart_button))

    def test_a_newer_version_lists_whats_new_and_updates_then_offers_a_restart(self):
        updater = FakeUpdater(AVAILABLE, DONE)
        dialog = self.open(updater)
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.assertIn("2 updates", dialog.message.get())
        self.assertEqual(dialog.news.get(0, "end"), ("•  Fix the camera lock", "•  Add the connect screen"))
        self.assertTrue(self.enabled(dialog.update_button))
        dialog.update()
        self.assertEqual(dialog.message.get(), "Updating…")
        self.assertFalse(self.enabled(dialog.update_button) or self.enabled(dialog.close_button))
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.assertEqual(updater.updates, 1)
        self.assertEqual(dialog.message.get(), DONE.message)
        self.assertTrue(self.enabled(dialog.restart_button))
        self.assertFalse(self.enabled(dialog.update_button), "the update is done, so it cannot be repeated")

    def test_new_packages_say_it_may_take_a_while_and_a_problem_with_them_is_shown(self):
        needs = UpdateStatus("available", "A newer version is available (1 update).", "abc", "main", 1, ("x",),
                             requirements_changed=True)
        warned = UpdateResult(True, DONE.message, True, ("The new version needs Python packages that could not be installed: oops.",))
        dialog = self.open(FakeUpdater(needs, warned))
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        dialog.update()
        self.assertIn("few minutes", dialog.message.get())
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.assertIn("could not be installed", dialog.notes.cget("text"))
        self.assertTrue(self.enabled(dialog.restart_button))

    def test_a_blocked_or_failed_check_explains_and_cannot_update(self):
        for state, text in (("blocked", "you have changed tictactoe.py"), ("error", "Cannot reach GitHub."),
                            ("unsupported", "not installed with git")):
            with self.subTest(state):
                dialog = self.open(FakeUpdater(UpdateStatus(state, text)))
                self.assertTrue(self.pump(3, lambda: dialog.working is None))
                self.assertEqual(dialog.message.get(), text)
                self.assertFalse(self.enabled(dialog.update_button))
                self.assertTrue(self.enabled(dialog.check_button))
                dialog.window.destroy()

    def test_it_will_not_update_while_the_arm_is_busy_or_armed(self):
        updater = FakeUpdater(AVAILABLE, DONE)
        dialog = self.open(updater)
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.studio.busy = "move"
        dialog._refresh()
        self.assertFalse(self.enabled(dialog.update_button))
        self.assertIn("Stop what the arm is doing", dialog.message.get())
        dialog.update()
        self.assertEqual(updater.updates, 0)
        self.studio.busy = None
        self.studio.armed = True
        dialog._refresh()
        self.assertFalse(self.enabled(dialog.update_button))
        self.studio.armed = False
        dialog._refresh()
        self.assertTrue(self.enabled(dialog.update_button))

    def test_the_window_stays_alive_while_a_slow_github_answers(self):
        hold = Event()
        dialog = self.open(FakeUpdater(CURRENT, hold=hold))
        self.pump(0.5)
        self.assertEqual(dialog.working, "check")
        dialog.close()
        self.assertTrue(dialog.window.winfo_exists(), "it cannot be closed in the middle of a job")
        hold.set()
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        dialog.close()
        self.assertFalse(dialog.window.winfo_exists())
        self.assertIsNone(self.studio.update_dialog)

    def test_check_again_asks_github_again(self):
        updater = FakeUpdater(CURRENT)
        dialog = self.open(updater)
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        dialog.check()
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        self.assertEqual(updater.checks, 2)

    def test_restart_closes_the_window_and_restarts_the_studio(self):
        dialog = self.open(FakeUpdater(AVAILABLE, DONE))
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        dialog.update()
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        with mock.patch.object(self.studio, "restart") as restart:
            dialog.restart()
        restart.assert_called_once()
        self.assertFalse(dialog.window.winfo_exists())

    def test_restart_does_nothing_before_an_update_or_while_the_arm_is_busy(self):
        dialog = self.open(FakeUpdater(AVAILABLE, DONE))
        self.assertTrue(self.pump(3, lambda: dialog.working is None))
        with mock.patch.object(self.studio, "restart") as restart:
            dialog.restart()
            dialog.update()
            self.assertTrue(self.pump(3, lambda: dialog.working is None))
            self.studio.busy = "move"
            dialog.restart()
        restart.assert_not_called()

    def test_the_studio_opens_one_window_and_the_buttons_are_on_both_first_screens(self):
        studio = self.studio
        with mock.patch("dobot_studio.app.UpdateDialog") as dialog_class:
            window = dialog_class.return_value.window
            window.winfo_exists.return_value = True
            studio.show_updates()
            studio.show_updates()
        dialog_class.assert_called_once()
        window.lift.assert_called_once()

        def labels(widget):
            found = []
            for child in widget.winfo_children():
                try:
                    found.append(str(child.cget("text")))
                except tk.TclError:
                    pass
                found += labels(child)
            return found

        studio.show_connect()
        self.assertIn("Check for updates…", labels(studio.program_menu))
        studio.leave_connect()
        self.assertIn("Check for updates…", labels(studio.program_menu))


@needs_display
class RestartTests(unittest.TestCase):
    def test_restarting_closes_the_studio_cleanly_and_asks_to_start_again(self):
        from dobot_studio.app import Studio

        root = tk.Tk()
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        studio = Studio(root, Path("/nonexistent"), Path(folder))
        studio.restart()
        self.assertTrue(studio.restart_requested)
        self.assertTrue(studio.closing)
        end = monotonic() + 3
        while monotonic() < end:
            try:
                root.update()
            except tk.TclError:
                break                    # the window went away, as it should
            sleep(0.01)
        with self.assertRaises(tk.TclError):
            root.winfo_exists()

    def test_the_new_process_starts_in_the_studios_folder_with_the_same_options(self):
        from dobot_studio import app

        with mock.patch.object(app.os, "execv") as execv, mock.patch.object(app.os, "chdir") as chdir, \
                mock.patch.object(app.sys, "argv", ["dobot_studio", "--models", "/m"]):
            app.relaunch()
        chdir.assert_called_once_with(app.APP_FOLDER)
        execv.assert_called_once_with(sys.executable, [sys.executable, "-m", "dobot_studio", "--models", "/m"])


@needs_display
class RealUpdateTests(unittest.TestCase):
    """The window and the real updater together, on real git repositories."""

    def test_checking_and_updating_a_real_copy_from_the_window(self):
        from dobot_studio.app import Studio
        from dobot_studio.update_dialog import UpdateDialog
        from dobot_studio.updater import Updater
        from tests.test_updater import Setup

        world = Setup()
        world.setUp()
        self.addCleanup(world.tearDown)
        installed = []
        root = tk.Tk()
        self.addCleanup(root.destroy)
        folder = mkdtemp()
        self.addCleanup(rmtree, folder, True)
        studio = Studio(root, Path("/nonexistent"), Path(folder))
        world.publish("Fix the camera lock", {"dobot_studio/tictactoe.py": "VERSION = 2\n", "requirements.txt": "pyserial==3.5\nnumpy\n"})
        dialog = UpdateDialog(studio, Updater(world.app, install=lambda path: installed.append(path) or ""))
        self.addCleanup(lambda: dialog.window.winfo_exists() and dialog.window.destroy())

        def pump(until):
            end = monotonic() + 8
            while monotonic() < end:
                root.update()
                sleep(0.01)
                if until():
                    return True
            return False

        self.assertTrue(pump(lambda: dialog.working is None))
        self.assertIn("1 update", dialog.message.get())
        self.assertEqual(dialog.news.get(0, "end"), ("•  Fix the camera lock",))
        dialog.update()
        self.assertTrue(pump(lambda: dialog.working is None))
        self.assertIn("Updated", dialog.message.get())
        self.assertEqual((world.app / "dobot_studio" / "tictactoe.py").read_text(), "VERSION = 2\n")
        self.assertEqual(installed, [world.app / "requirements.txt"])
        self.assertNotIn("disabled", dialog.restart_button.state())
        dialog.check()
        self.assertTrue(pump(lambda: dialog.working is None))
        self.assertEqual(dialog.message.get(), "You have the latest version.")


if __name__ == "__main__":
    unittest.main()
