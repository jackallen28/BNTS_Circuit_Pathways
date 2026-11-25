"""Camera adjustments for the mat setup.

Two separate things, so the live view can stay as the camera makes it while the Pi reads a version
tuned to show the X and O marks clearly:

* ``Tune`` is software only. It changes the picture the Pi reads (brightness, contrast, gamma and
  sharpening) and never the picture people see.
* ``controls`` talks to the camera itself with ``v4l2-ctl`` (exposure, focus, white balance, gain...).
  That changes what the camera sends, so it changes the live view too. It is how automatic exposure
  and focus hunting is stopped.

Neither is saved. They are set up again each time the mat is calibrated.
"""
from dataclasses import dataclass, replace
import re
import subprocess


@dataclass(frozen=True)
class Tune:
    brightness: float = 0.0     # -100 to 100, added to every grey level (a fraction of 255)
    contrast: float = 1.0       # 0.5 to 3, around the middle grey
    gamma: float = 1.0          # 0.4 to 2.5. Above 1 lifts the shadows, below 1 deepens them
    sharpen: float = 0.0        # 0 to 3, the strength of an unsharp mask

    def is_neutral(self):
        return self == Tune()

    def with_(self, **changes):
        return replace(self, **changes)

    def clamped(self):
        return Tune(min(100.0, max(-100.0, float(self.brightness))), min(3.0, max(0.5, float(self.contrast))),
                    min(2.5, max(0.4, float(self.gamma))), min(3.0, max(0.0, float(self.sharpen))))


def apply(rgb, tune):
    """The picture the Pi reads: ``rgb`` (uint8, height x width x 3) with the adjustments. The input is not changed."""
    if tune is None or tune.is_neutral():
        return rgb
    import cv2
    import numpy as np

    tune = tune.clamped()
    levels = np.arange(256, dtype=np.float32) / 255.0
    levels = np.power(levels, 1.0 / tune.gamma)
    levels = (levels - 0.5) * tune.contrast + 0.5 + tune.brightness / 100.0 * 0.5
    table = np.clip(levels * 255.0 + 0.5, 0, 255).astype(np.uint8)
    out = cv2.LUT(np.ascontiguousarray(rgb), table)
    if tune.sharpen > 0:
        blurred = cv2.GaussianBlur(out, (0, 0), 2.0)
        out = cv2.addWeighted(out, 1.0 + tune.sharpen, blurred, -tune.sharpen, 0)
    return out


# ---- the camera's own controls, through v4l2-ctl

LINE = re.compile(r"^\s*(?P<name>\w+)\s+0x[0-9a-fA-F]+\s+\((?P<kind>\w+)\)\s*:\s*(?P<rest>.*)$")
PAIR = re.compile(r"(\w+)=(-?\d+)")
AUTO_EXPOSURE_NAMES = ("auto_exposure", "exposure_auto")
EXPOSURE_NAMES = ("exposure_time_absolute", "exposure_absolute")
FOCUS_AUTO_NAMES = ("focus_automatic_continuous", "focus_auto")
WHITE_AUTO_NAMES = ("white_balance_automatic", "white_balance_temperature_auto")
MANUAL, AUTOMATIC = 1, 3          # the values of an exposure menu


@dataclass(frozen=True)
class Control:
    name: str
    kind: str                 # "int", "bool" or "menu"
    minimum: int = 0
    maximum: int = 1
    step: int = 1
    default: int = 0
    value: int = 0
    inactive: bool = False

    @property
    def label(self):
        return {"auto_exposure": "Automatic exposure", "exposure_auto": "Automatic exposure",
                "exposure_time_absolute": "Exposure", "exposure_absolute": "Exposure",
                "focus_automatic_continuous": "Automatic focus", "focus_auto": "Automatic focus",
                "focus_absolute": "Focus", "white_balance_automatic": "Automatic white balance",
                "white_balance_temperature_auto": "Automatic white balance",
                "white_balance_temperature": "White balance"}.get(self.name, self.name.replace("_", " ").capitalize())


def parse_controls(text):
    """The controls ``v4l2-ctl --list-ctrls`` lists, in order."""
    found = []
    for line in text.splitlines():
        match = LINE.match(line)
        if not match or match["kind"] not in ("int", "bool", "menu"):
            continue
        numbers = dict(PAIR.findall(match["rest"]))
        found.append(Control(match["name"], match["kind"], int(numbers.get("min", 0)),
                             int(numbers.get("max", 1)), int(numbers.get("step", 1)), int(numbers.get("default", 0)),
                             int(numbers.get("value", numbers.get("default", 0))), "inactive" in match["rest"]))
    return found


def device_path(device):
    text = str(device).strip()
    return f"/dev/video{text}" if text.isdecimal() else text


class CameraControls:
    """List and change a camera's own controls. ``run`` can be replaced in tests."""

    def __init__(self, device, run=subprocess.run):
        self.path, self.run = device_path(device), run
        self.problem = ""

    def _v4l2(self, *args):
        try:
            result = self.run(["v4l2-ctl", "-d", self.path, *args], capture_output=True, text=True, timeout=8)
        except FileNotFoundError:
            self.problem = "The camera controls need  v4l2-ctl.  Run:  sudo apt install v4l-utils"
            return None
        except (OSError, subprocess.SubprocessError) as error:
            self.problem = f"The camera did not answer: {error}"
            return None
        if result.returncode:
            self.problem = (result.stderr or result.stdout).strip().splitlines()[-1:] and \
                (result.stderr or result.stdout).strip().splitlines()[-1] or "The camera refused that."
            return None
        self.problem = ""
        return result.stdout

    def list(self):
        text = self._v4l2("--list-ctrls")
        return [] if text is None else parse_controls(text)

    def set(self, name, value):
        """Set one control. Returns True if the camera took it."""
        return self._v4l2("--set-ctrl", f"{name}={int(value)}") is not None

    def set_auto_exposure(self, automatic, controls):
        name = next((c.name for c in controls if c.name in AUTO_EXPOSURE_NAMES), None)
        return bool(name) and self.set(name, AUTOMATIC if automatic else MANUAL)


def interesting(controls):
    """The controls worth showing, in a sensible order: exposure, focus, white balance, then the picture controls."""
    order = (*AUTO_EXPOSURE_NAMES, *EXPOSURE_NAMES, "gain", "brightness", "contrast", "saturation", "gamma",
             "sharpness", *WHITE_AUTO_NAMES, "white_balance_temperature", *FOCUS_AUTO_NAMES, "focus_absolute",
             "backlight_compensation")
    chosen = [c for name in order for c in controls if c.name == name]
    return chosen
