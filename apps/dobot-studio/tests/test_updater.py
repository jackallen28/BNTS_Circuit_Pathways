"""Updating Dobot Studio from GitHub, against real git repositories."""
from pathlib import Path
from shutil import rmtree
from subprocess import TimeoutExpired, run
from tempfile import mkdtemp
import os
import unittest

from dobot_studio.updater import Updater, explain, signin

IDENTITY = {"GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(folder, *args):
    return run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True,
               env={**os.environ, **IDENTITY}).stdout.strip()


class Setup(unittest.TestCase):
    """A bare 'GitHub', a clone that publishes new versions, and a 'Pi' clone that updates."""

    def setUp(self):
        self.base = Path(mkdtemp())
        self.addCleanup(rmtree, self.base, True)
        run(["git", "init", "--bare", "-b", "main", str(self.base / "github.git")], check=True, capture_output=True)
        self.maker = self.base / "maker"
        run(["git", "clone", "-q", str(self.base / "github.git"), str(self.maker)], check=True, capture_output=True,
            env={**os.environ, **IDENTITY})
        app = self.maker / "apps" / "dobot-studio"
        (app / "dobot_studio").mkdir(parents=True)
        (app / "requirements.txt").write_text("pyserial==3.5\n")
        (app / "dobot_studio" / "tictactoe.py").write_text("VERSION = 1\n")
        (app / "dobot_studio" / "notes.txt").write_text("notes\n")
        git(self.maker, "add", "-A")
        git(self.maker, "commit", "-qm", "First version")
        git(self.maker, "push", "-q", "origin", "HEAD:main")
        run(["git", "clone", "-q", str(self.base / "github.git"), str(self.base / "pi")], check=True, capture_output=True,
            env={**os.environ, **IDENTITY})
        self.pi = self.base / "pi"
        self.app = self.pi / "apps" / "dobot-studio"
        self.installed = []
        self.updater = Updater(self.app, install=self.record_install)

    def record_install(self, requirements):
        self.installed.append(Path(requirements))
        return self.install_problem if hasattr(self, "install_problem") else ""

    def publish(self, subject, files):
        for name, text in files.items():
            path = self.maker / "apps" / "dobot-studio" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.maker, "add", "-A")
        git(self.maker, "commit", "-qm", subject)
        git(self.maker, "push", "-q", "origin", "HEAD:main")


class CheckTests(Setup):
    def test_a_copy_that_is_up_to_date_says_so_and_shows_its_version(self):
        status = self.updater.check()
        self.assertEqual((status.state, status.behind), ("current", 0))
        self.assertIn("latest", status.message)
        self.assertEqual(status.branch, "main")
        self.assertRegex(status.version, r"^[0-9a-f]{7,}  ·  \d{4}-\d\d-\d\d$")
        self.assertEqual(self.updater.version(), status.version)

    def test_newer_versions_are_found_and_listed_newest_first(self):
        self.publish("Add the connect screen", {"dobot_studio/connect.py": "print()\n"})
        self.publish("Fix the camera lock", {"dobot_studio/tictactoe.py": "VERSION = 2\n"})
        status = self.updater.check()
        self.assertEqual((status.state, status.behind), ("available", 2))
        self.assertEqual(status.incoming, ("Fix the camera lock", "Add the connect screen"))
        self.assertFalse(status.requirements_changed)
        self.assertIn("2 updates", status.message)

    def test_checking_changes_nothing_on_the_copy(self):
        self.publish("A new version", {"dobot_studio/tictactoe.py": "VERSION = 2\n"})
        before = git(self.pi, "rev-parse", "HEAD")
        self.updater.check()
        self.assertEqual(git(self.pi, "rev-parse", "HEAD"), before)
        self.assertEqual((self.app / "dobot_studio" / "tictactoe.py").read_text(), "VERSION = 1\n")

    def test_a_change_to_the_packages_is_noticed(self):
        self.publish("New package", {"requirements.txt": "pyserial==3.5\nnumpy\n"})
        self.assertTrue(self.updater.check().requirements_changed)


class UpdateTests(Setup):
    def test_the_update_brings_in_the_new_files_and_asks_for_a_restart(self):
        self.publish("A new version", {"dobot_studio/tictactoe.py": "VERSION = 2\n", "dobot_studio/added": "new\n"})
        result = self.updater.update()
        self.assertTrue(result.ok and result.restart, result.message)
        self.assertEqual((self.app / "dobot_studio" / "tictactoe.py").read_text(), "VERSION = 2\n")
        self.assertEqual((self.app / "dobot_studio" / "added").read_text(), "new\n")
        self.assertEqual(git(self.pi, "rev-parse", "HEAD"), git(self.pi, "rev-parse", "@{u}"))
        self.assertEqual(self.updater.check().state, "current")
        self.assertEqual(self.installed, [], "no new packages were needed")

    def test_new_packages_are_installed_before_the_restart(self):
        self.publish("New package", {"requirements.txt": "pyserial==3.5\nnumpy\n"})
        result = self.updater.update()
        self.assertTrue(result.ok)
        self.assertEqual(self.installed, [self.app / "requirements.txt"])
        self.assertEqual(result.notes, ())

    def test_if_the_packages_cannot_be_installed_the_update_still_lands_with_a_clear_note(self):
        self.install_problem = "No matching distribution found for numpy"
        self.publish("New package", {"requirements.txt": "pyserial==3.5\nnumpy\n"})
        result = self.updater.update()
        self.assertTrue(result.ok and result.restart)
        self.assertTrue(result.notes and "numpy" in result.notes[0] and "setup-pi.sh" in result.notes[0])

    def test_nothing_to_update_does_nothing(self):
        before = git(self.pi, "rev-parse", "HEAD")
        result = self.updater.update()
        self.assertFalse(result.ok)
        self.assertEqual(git(self.pi, "rev-parse", "HEAD"), before)

    def test_a_file_changed_here_that_the_update_also_changes_blocks_it_and_keeps_the_edit(self):
        (self.app / "dobot_studio" / "tictactoe.py").write_text("VERSION = 1\nMY_EDIT = True\n")
        self.publish("A new version", {"dobot_studio/tictactoe.py": "VERSION = 2\n"})
        before = git(self.pi, "rev-parse", "HEAD")
        status = self.updater.check()
        self.assertEqual(status.state, "blocked")
        self.assertEqual(status.blockers, ("apps/dobot-studio/dobot_studio/tictactoe.py",))
        self.assertIn("tictactoe.py", status.message)
        result = self.updater.update()
        self.assertFalse(result.ok)
        self.assertEqual(git(self.pi, "rev-parse", "HEAD"), before)
        self.assertEqual((self.app / "dobot_studio" / "tictactoe.py").read_text(), "VERSION = 1\nMY_EDIT = True\n")

    def test_edits_to_other_files_are_kept_and_do_not_block_the_update(self):
        (self.app / "dobot_studio" / "notes.txt").write_text("my own notes\n")
        (self.app / "models").mkdir()
        (self.app / "models" / "gesture_recognizer.task").write_text("model")        # not tracked
        self.publish("A new version", {"dobot_studio/tictactoe.py": "VERSION = 2\n"})
        result = self.updater.update()
        self.assertTrue(result.ok, result.message)
        self.assertEqual((self.app / "dobot_studio" / "notes.txt").read_text(), "my own notes\n")
        self.assertTrue((self.app / "models" / "gesture_recognizer.task").exists())
        self.assertEqual((self.app / "dobot_studio" / "tictactoe.py").read_text(), "VERSION = 2\n")

    def test_a_copy_with_commits_of_its_own_is_never_merged_or_rewritten(self):
        (self.app / "dobot_studio" / "mine.py").write_text("mine\n")
        git(self.pi, "add", "-A")
        git(self.pi, "commit", "-qm", "My change")
        self.publish("A new version", {"dobot_studio/tictactoe.py": "VERSION = 2\n"})
        before = git(self.pi, "rev-parse", "HEAD")
        status = self.updater.check()
        self.assertEqual(status.state, "blocked")
        self.assertIn("1 change of its own", status.message)
        self.assertFalse(self.updater.update().ok)
        self.assertEqual(git(self.pi, "rev-parse", "HEAD"), before)

    def test_commits_of_its_own_with_nothing_newer_is_just_current(self):
        (self.app / "dobot_studio" / "mine.py").write_text("mine\n")
        git(self.pi, "add", "-A")
        git(self.pi, "commit", "-qm", "My change")
        status = self.updater.check()
        self.assertEqual(status.state, "current")
        self.assertIn("changes of its own", status.message)


class ProblemTests(Setup):
    def test_a_copy_that_is_not_a_git_clone_explains_itself(self):
        folder = self.base / "unzipped"
        folder.mkdir()
        (folder / "requirements.txt").write_text("")
        status = Updater(folder).check()
        self.assertEqual(status.state, "unsupported")
        self.assertIn("not installed with git", status.message)
        self.assertEqual(Updater(folder).version(), "")

    def test_a_branch_with_no_link_to_github_cannot_update(self):
        git(self.pi, "checkout", "-q", "-b", "local-only")
        status = self.updater.check()
        self.assertEqual(status.state, "unsupported")
        self.assertIn("local-only", status.message)

    def test_a_detached_copy_cannot_update(self):
        git(self.pi, "checkout", "-q", "--detach")
        self.assertEqual(self.updater.check().state, "unsupported")

    def test_an_unreachable_github_is_reported_in_plain_english(self):
        git(self.pi, "remote", "set-url", "origin", str(self.base / "does-not-exist.git"))
        status = self.updater.check()
        self.assertEqual(status.state, "error")
        self.assertIn("Cannot reach GitHub", status.message)

    def test_a_missing_git_says_how_to_install_it(self):
        def missing(*args, **kwargs):
            raise FileNotFoundError("git")

        status = Updater(self.app, run=missing).check()
        self.assertEqual(status.state, "error")
        self.assertIn("sudo apt install git", status.message)

    def test_a_slow_github_times_out_with_a_message(self):
        def slow(*args, **kwargs):
            raise TimeoutExpired("git", 45)

        status = Updater(self.app, run=slow).check()
        self.assertEqual(status.state, "error")
        self.assertIn("did not answer", status.message)

    def test_git_is_never_allowed_to_wait_for_a_password(self):
        seen = []

        def spy(command, **kwargs):
            seen.append(kwargs["env"])
            return run(command, **kwargs)

        Updater(self.app, run=spy).check()
        self.assertTrue(seen)
        for environment in seen:
            self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
            self.assertIn("BatchMode=yes", environment["GIT_SSH_COMMAND"])

    def test_gits_own_errors_become_words_a_person_can_act_on(self):
        for text in ("fatal: could not read Username for 'https://github.com': terminal prompts disabled",
                     "remote: Invalid username or password.\nfatal: Authentication failed for 'https://github.com/x'",
                     "fatal: unable to access 'https://github.com/x': The requested URL returned error: 403",
                     "fatal: repository 'https://github.com/x' not found"):
            self.assertEqual(explain(text), signin(), text)
        for text in ("fatal: unable to access 'https://github.com/x/': Could not resolve host: github.com",
                     "ssh: connect to host github.com port 22: Connection timed out",
                     "fatal: Could not read from remote repository."):
            self.assertIn("Cannot reach GitHub", explain(text), text)
        self.assertIn("fast-forward", explain("fatal: Not possible to fast-forward, aborting."))
        self.assertEqual(explain("fatal: something odd\nmore"), "fatal: something odd")


if __name__ == "__main__":
    unittest.main()
