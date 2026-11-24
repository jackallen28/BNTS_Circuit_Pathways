"""The Dobot Studio icon on the desktop and in the applications menu.

Run  sh install-desktop.sh  to add it (setup-pi.sh does), or  sh install-desktop.sh --remove  to take it away.
Dobot Studio also adds it once, the first time it runs, if there is none.
"""
import os
from pathlib import Path
import subprocess
import sys

FOLDER = Path(__file__).resolve().parents[1]
FILE = "dobot-studio.desktop"
DESKTOP_NAME = "Dobot Studio.desktop"
MARKER = "launcher-added"


def quote(value):
    """A path as one quoted word in a launcher's Exec line, per the desktop entry specification."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + escaped.replace("%", "%%") + '"'


def entry(folder=FOLDER):
    folder = Path(folder).resolve()
    for part in map(str, folder.parts):
        if "\n" in part or "\r" in part:
            raise ValueError("The folder name has a line break in it.")
    return "\n".join((
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Dobot Studio",
        "GenericName=Dobot Magician controls",
        "Comment=Control the Dobot Magician with a camera",
        f"Exec=sh {quote(str(folder / 'launch.sh'))}",
        f"Path={folder}",
        f"Icon={folder / 'assets' / 'dobot-studio.png'}",
        "Terminal=false",
        "StartupNotify=true",
        "Categories=Education;Electronics;",
        "",
    ))


def data_folder(environ=os.environ, home=None):
    return Path(environ.get("XDG_DATA_HOME") or (Path(home or Path.home()) / ".local" / "share"))


def config_folder(environ=os.environ, home=None):
    return Path(environ.get("XDG_CONFIG_HOME") or (Path(home or Path.home()) / ".config")) / "dobot-studio"


def desktop_folder(home=None, run=subprocess.run, environ=os.environ):
    """The user's Desktop folder, if there is one."""
    home = Path(home or Path.home())
    try:
        found = run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5,
                    env={**environ, "HOME": str(home)}).stdout.strip()
        if found and Path(found) != home and Path(found).is_dir():
            return Path(found)
    except (OSError, subprocess.SubprocessError):
        pass
    fallback = home / "Desktop"
    return fallback if fallback.is_dir() else None


def install(folder=FOLDER, home=None, run=subprocess.run, environ=os.environ):
    """Write the launcher into the applications menu and onto the desktop. Returns the files written."""
    text = entry(folder)
    targets = [data_folder(environ, home) / "applications" / FILE]
    desktop = desktop_folder(home, run, environ)
    if desktop:
        targets.append(desktop / DESKTOP_NAME)
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        target.chmod(0o755)                           # a launcher on the desktop must be executable
        try:                                          # file managers that ask "trust this launcher?" are told yes
            run(["gio", "set", str(target), "metadata::trusted", "true"], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        run(["update-desktop-database", str(targets[0].parent)], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass
    return targets


def remove(home=None, run=subprocess.run, environ=os.environ):
    gone = []
    desktop = desktop_folder(home, run, environ)
    for target in (data_folder(environ, home) / "applications" / FILE, *([desktop / DESKTOP_NAME] if desktop else [])):
        if target.exists():
            target.unlink()
            gone.append(target)
    return gone


def ensure(folder=FOLDER, home=None, run=subprocess.run, environ=os.environ):
    """Add the launcher the first time Dobot Studio runs. It is not put back if it is deleted later."""
    marker = config_folder(environ, home) / MARKER
    if marker.exists():
        return []
    try:
        written = install(folder, home, run, environ)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("A Dobot Studio icon was added.\n", encoding="utf-8")
        return written
    except OSError:
        return []


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] in ("--remove", "remove"):
        gone = remove()
        print("Removed:" if gone else "There was no Dobot Studio icon to remove.", *map(str, gone), sep="\n  ")
        return 0
    if arguments and arguments[0] in ("--print", "print"):
        print(entry(), end="")
        return 0
    written = install()
    print("Added the Dobot Studio icon:", *map(str, written), sep="\n  ")
    if len(written) == 1:
        print("There is no Desktop folder here, so it is only in the applications menu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
