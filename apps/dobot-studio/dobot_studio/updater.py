"""Check for a newer Dobot Studio on GitHub and bring this copy up to date.

The Pi runs a copy cloned with git, so updating is a fast-forward of that clone. It is careful:

* it only ever fast-forwards, so nothing is merged, rewritten or thrown away;
* it will not touch a file that has been changed here and is also changed upstream;
* it never waits for a password, because there may be nobody at the keyboard;
* if the new version needs new Python packages it installs them, so the app still starts.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys

FETCH_TIMEOUT, MERGE_TIMEOUT, INSTALL_TIMEOUT = 45, 30, 900
SUBJECTS = 12


@dataclass(frozen=True)
class UpdateStatus:
    # "current", "available", "blocked", "unsupported" or "error"
    state: str
    message: str
    version: str = ""
    branch: str = ""
    behind: int = 0
    incoming: tuple = ()
    blockers: tuple = ()
    requirements_changed: bool = False


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    message: str
    restart: bool = False
    notes: tuple = field(default=())


class Updater:
    def __init__(self, folder, run=subprocess.run, install=None):
        """``folder`` is the Dobot Studio folder. ``run`` and ``install`` can be replaced in tests."""
        self.folder = Path(folder).resolve()
        self.run = run
        self.install = install or self._pip_install
        self.root = None

    # ---- talking to git
    def _git(self, *args, timeout=FETCH_TIMEOUT):
        environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
                       "GIT_SSH_COMMAND": "ssh -o BatchMode=yes", "LC_ALL": "C"}
        command = ["git", "-C", str(self.root or self.folder), *args]
        return self.run(command, capture_output=True, text=True, timeout=timeout, env=environment)

    def _output(self, *args, timeout=FETCH_TIMEOUT):
        result = self._git(*args, timeout=timeout)
        if result.returncode:
            raise GitFailed(result.stderr.strip() or result.stdout.strip() or f"git {args[0]} failed")
        return result.stdout.strip()

    # ---- what is installed
    def version(self):
        """The short id and date of the commit this copy is on, or an empty string."""
        try:
            self._locate()
            return self._output("log", "-1", "--format=%h  ·  %cs", timeout=10)
        except (GitFailed, OSError, subprocess.SubprocessError, Unsupported):
            return ""

    def _locate(self):
        try:
            self.root = Path(self._output("rev-parse", "--show-toplevel", timeout=10)).resolve()
        except GitFailed as error:
            raise Unsupported("This copy of Dobot Studio was not installed with git, so it cannot update itself. "
                              "See the README to install it again.") from error

    # ---- is there something newer?
    def check(self):
        try:
            return self._check()
        except Unsupported as reason:
            return UpdateStatus("unsupported", str(reason))
        except FileNotFoundError:
            return UpdateStatus("error", "Git is not installed. Run:  sudo apt install git")
        except subprocess.TimeoutExpired:
            return UpdateStatus("error", "GitHub did not answer in time. Check the internet connection and try again.")
        except GitFailed as error:
            return UpdateStatus("error", explain(str(error)), version=self.version())

    def _check(self):
        self._locate()
        branch = self._output("rev-parse", "--abbrev-ref", "HEAD", timeout=10)
        if branch == "HEAD":
            raise Unsupported("This copy is not on a branch, so it cannot tell what is newer. Ask for help.")
        try:
            upstream = self._output("rev-parse", "--abbrev-ref", "@{u}", timeout=10)
        except GitFailed as error:
            raise Unsupported(f"The branch {branch} is not linked to GitHub, so it cannot update itself.") from error
        remote, _, remote_branch = upstream.partition("/")
        self._output("fetch", "--quiet", remote, remote_branch)
        ahead, behind = (int(value) for value in self._output("rev-list", "--left-right", "--count",
                                                              "HEAD...@{u}", timeout=10).split())
        version = self._output("log", "-1", "--format=%h  ·  %cs", timeout=10)
        if behind == 0:
            note = " This copy also has changes of its own that are not on GitHub." if ahead else ""
            return UpdateStatus("current", "You have the latest version." + note, version, branch)
        incoming = tuple(self._output("log", f"-{SUBJECTS}", "--format=%s", "HEAD..@{u}", timeout=10).splitlines())
        if ahead:
            return UpdateStatus("blocked", f"A newer version exists, but this copy has {ahead} change"
                                f"{'s' if ahead != 1 else ''} of its own, so it cannot be updated safely. "
                                "Ask for help.", version, branch, behind, incoming)
        changed = set(self._output("diff", "--name-only", "HEAD", "@{u}", timeout=10).splitlines())
        edited = set(self._output("diff", "--name-only", "HEAD", timeout=10).splitlines())   # changed here, tracked
        blockers = tuple(sorted(changed & edited))
        requirements = self.folder.joinpath("requirements.txt").relative_to(self.root).as_posix()
        needs = requirements in changed
        if blockers:
            return UpdateStatus("blocked", "A newer version exists, but you have changed "
                                + ", ".join(blockers[:3]) + (" and others" if len(blockers) > 3 else "")
                                + " on this copy, and the update would overwrite that. Ask for help.",
                                version, branch, behind, incoming, blockers, needs)
        return UpdateStatus("available", f"A newer version is available ({behind} update{'s' if behind != 1 else ''}).",
                            version, branch, behind, incoming, (), needs)

    # ---- bring it up to date
    def update(self):
        """Fast-forward to the newer version, install any new packages, and say whether to restart."""
        status = self.check()
        if status.state != "available":
            return UpdateResult(False, status.message)
        try:
            self._output("merge", "--ff-only", "--quiet", "@{u}", timeout=MERGE_TIMEOUT)
        except (GitFailed, subprocess.SubprocessError) as error:
            return UpdateResult(False, "The update could not be applied, and nothing was changed. " + explain(str(error)))
        notes = []
        if status.requirements_changed:
            problem = self.install(self.folder / "requirements.txt")
            if problem:
                notes.append("The new version needs Python packages that could not be installed: "
                             f"{problem} Connect to the internet and run  sh setup-pi.sh  in the Dobot Studio folder.")
        return UpdateResult(True, "Updated. Restart Dobot Studio to use the new version.", True, tuple(notes))

    def _pip_install(self, requirements):
        """Install the packages the new version needs. Returns a problem as text, or an empty string."""
        try:
            result = self.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(requirements)],
                              capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as error:
            return str(error)
        return "" if result.returncode == 0 else (result.stderr.strip().splitlines() or ["pip failed."])[-1]


class GitFailed(Exception):
    pass


class Unsupported(Exception):
    pass


def explain(message):
    """Git's own wording, in words a person can act on."""
    text = message.lower()
    if any(part in text for part in ("authentication failed", "could not read username", "terminal prompts disabled",
                                     "permission denied", "error: 403", "error: 401", "invalid username or password")) \
            or ("repository" in text and "not found" in text):     # GitHub says this for a private repository
        return signin()
    if any(part in text for part in ("could not resolve host", "unable to access", "network is unreachable",
                                     "connection timed out", "failed to connect", "could not read from remote",
                                     "does not appear to be a git repository", "connection refused")):
        return "Cannot reach GitHub. Check the Pi's internet connection and try again."
    if "not possible to fast-forward" in text or "diverging" in text:
        return "This copy has changes of its own, so it cannot fast-forward. Ask for help."
    first = message.strip().splitlines()[0] if message.strip() else "Something went wrong."
    return first


def signin():
    return ("GitHub wants a sign-in for this copy. In a terminal, run  git pull  in the Dobot Studio folder once "
            "and enter your login. Saving it with  git config --global credential.helper store  stops it asking again.")
