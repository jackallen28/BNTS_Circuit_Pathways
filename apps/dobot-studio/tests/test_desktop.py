"""The Dobot Studio icon on the desktop, and the window icon."""
from pathlib import Path
from shutil import rmtree, which
from subprocess import run
from tempfile import mkdtemp
from types import SimpleNamespace
import os
import shlex
import stat
import unittest

from PIL import Image

from dobot_studio import desktop

APP = Path(__file__).resolve().parents[1]


def quiet(calls=None):
    def runner(command, **kwargs):
        if calls is not None:
            calls.append(command)
        return SimpleNamespace(stdout="", returncode=0)
    return runner


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(mkdtemp())
        self.addCleanup(rmtree, self.home, True)
        (self.home / "Desktop").mkdir()
        self.environ = {}

    def test_the_launcher_names_the_app_runs_launch_sh_and_points_at_the_icon(self):
        lines = dict(line.split("=", 1) for line in desktop.entry(APP).splitlines() if "=" in line)
        self.assertEqual(lines["Type"], "Application")
        self.assertEqual(lines["Name"], "Dobot Studio")
        self.assertEqual(lines["Terminal"], "false")
        self.assertEqual(shlex.split(lines["Exec"]), ["sh", str(APP / "launch.sh")])
        self.assertEqual(Path(lines["Path"]), APP)
        self.assertTrue(Path(lines["Icon"]).is_file())
        self.assertTrue((APP / "launch.sh").is_file())

    def test_a_folder_with_spaces_and_awkward_characters_still_runs_the_right_file(self):
        folder = self.home / 'My "Pi" $HOME 100% `x`'
        folder.mkdir()
        text = desktop.entry(folder)
        exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
        # The specification's escapes: \" \` \$ \\ inside quotes, and %% for a literal percent.
        self.assertIn('\\"Pi\\"', exec_line)
        self.assertIn("\\$HOME", exec_line)
        self.assertIn("100%%", exec_line)
        self.assertIn("\\`x\\`", exec_line)
        self.assertEqual(len([line for line in text.splitlines() if line.startswith("Exec=")]), 1)

    def test_a_line_break_in_the_folder_name_is_refused_so_nothing_can_be_injected(self):
        with self.assertRaises(ValueError):
            desktop.entry(self.home / "bad\nExec=rm -rf")

    def test_install_writes_the_menu_entry_and_the_desktop_icon_and_makes_them_runnable(self):
        written = desktop.install(APP, self.home, quiet(), self.environ)
        self.assertEqual({path.name for path in written}, {"dobot-studio.desktop", "Dobot Studio.desktop"})
        for path in written:
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR, f"{path} cannot be run")
            self.assertEqual(path.read_text(), desktop.entry(APP))
        self.assertTrue((self.home / ".local" / "share" / "applications" / "dobot-studio.desktop").is_file())
        self.assertTrue((self.home / "Desktop" / "Dobot Studio.desktop").is_file())

    def test_it_tells_the_file_manager_to_trust_the_launcher_and_carries_on_if_it_cannot(self):
        calls = []
        desktop.install(APP, self.home, quiet(calls), self.environ)
        self.assertTrue(any(command[:3] == ["gio", "set", str(self.home / "Desktop" / "Dobot Studio.desktop")]
                            for command in calls))

        def broken(command, **kwargs):
            raise FileNotFoundError(command[0])

        self.assertEqual(len(desktop.install(APP, self.home, broken, self.environ)), 2)

    def test_installing_twice_changes_nothing_and_removing_takes_it_away(self):
        first = desktop.install(APP, self.home, quiet(), self.environ)
        before = [path.read_text() for path in first]
        self.assertEqual(desktop.install(APP, self.home, quiet(), self.environ), first)
        self.assertEqual([path.read_text() for path in first], before)
        gone = desktop.remove(self.home, quiet(), self.environ)
        self.assertEqual(set(gone), set(first))
        self.assertFalse(any(path.exists() for path in first))
        self.assertEqual(desktop.remove(self.home, quiet(), self.environ), [])

    def test_with_no_desktop_folder_only_the_menu_entry_is_added(self):
        (self.home / "Desktop").rmdir()
        written = desktop.install(APP, self.home, quiet(), self.environ)
        self.assertEqual([path.name for path in written], ["dobot-studio.desktop"])

    def test_the_desktop_folder_the_system_names_is_used(self):
        elsewhere = self.home / "Escritorio"
        elsewhere.mkdir()

        def runner(command, **kwargs):
            return SimpleNamespace(stdout=str(elsewhere) + "\n" if command[0] == "xdg-user-dir" else "", returncode=0)

        written = desktop.install(APP, self.home, runner, self.environ)
        self.assertIn(elsewhere / "Dobot Studio.desktop", written)

    def test_the_first_run_adds_the_icon_once_and_does_not_put_back_one_that_was_deleted(self):
        first = desktop.ensure(APP, self.home, quiet(), self.environ)
        self.assertEqual(len(first), 2)
        for path in first:
            path.unlink()
        self.assertEqual(desktop.ensure(APP, self.home, quiet(), self.environ), [])
        self.assertFalse((self.home / "Desktop" / "Dobot Studio.desktop").exists())

    def test_the_script_a_person_runs_adds_and_removes_the_icon(self):
        environment = {**os.environ, "HOME": str(self.home)}
        for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            environment.pop(name, None)
        added = run(["sh", str(APP / "install-desktop.sh")], capture_output=True, text=True, env=environment)
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertTrue((self.home / "Desktop" / "Dobot Studio.desktop").is_file())
        removed = run(["sh", str(APP / "install-desktop.sh"), "--remove"], capture_output=True, text=True, env=environment)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse((self.home / "Desktop" / "Dobot Studio.desktop").exists())

    @unittest.skipUnless(which("desktop-file-validate"), "needs desktop-file-validate")
    def test_the_launcher_passes_the_desktop_file_validator(self):
        path = self.home / "check.desktop"
        path.write_text(desktop.entry(APP))
        result = run(["desktop-file-validate", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_setup_script_adds_the_icon_and_the_scripts_are_runnable(self):
        self.assertIn("install-desktop.sh", (APP / "setup-pi.sh").read_text())
        for name in ("install-desktop.sh", "setup-pi.sh", "launch.sh"):
            self.assertTrue((APP / name).stat().st_mode & stat.S_IXUSR, name)
            self.assertEqual(run(["sh", "-n", str(APP / name)]).returncode, 0, name)


class IconTests(unittest.TestCase):
    def test_the_icon_is_a_square_png_with_see_through_corners(self):
        image = Image.open(APP / "assets" / "dobot-studio.png")
        self.assertEqual((image.size, image.mode), ((256, 256), "RGBA"))
        self.assertEqual(image.getpixel((0, 0))[3], 0)          # the rounded corner is transparent
        self.assertEqual(image.getpixel((128, 128))[3], 255)    # the middle is solid

    def test_the_window_icon_loads(self):
        import tkinter as tk
        if not (os.environ.get("DISPLAY")):
            self.skipTest("needs a display")
        from dobot_studio.app import ICON, set_window_icon
        root = tk.Tk()
        self.addCleanup(root.destroy)
        self.assertTrue(ICON.is_file())
        set_window_icon(root)
        self.assertEqual((root._icon.width(), root._icon.height()), (256, 256))

    def test_a_missing_icon_file_does_not_stop_the_app(self):
        import tkinter as tk
        from unittest import mock
        if not os.environ.get("DISPLAY"):
            self.skipTest("needs a display")
        from dobot_studio import app
        root = tk.Tk()
        self.addCleanup(root.destroy)
        with mock.patch.object(app, "ICON", Path("/nonexistent/icon.png")):
            app.set_window_icon(root)


if __name__ == "__main__":
    unittest.main()
