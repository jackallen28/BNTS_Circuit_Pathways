"""Read the teaching firmware's bounded USB serial frames."""
from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic

from .robot import Pose


@dataclass(frozen=True)
class Tilt:
    x: int
    y: int
    z: int
    clutch: bool
    button: str
    timestamp: float


def parse_frame(line):
    try:
        prefix, x, y, z, clutch, button = line.decode("ascii").strip().split(",")
        values = tuple(map(int, (x, y, z)))
    except (UnicodeError, ValueError):
        return None
    if (prefix != "DT1" or clutch not in ("0", "1") or button not in ("-", "A", "B")
            or any(abs(axis) > 4096 for axis in values)):
        return None
    return Tilt(*values, clutch == "1", button, monotonic())


def inside(origin, pose):
    return (abs(pose.x-origin.x) <= 32 and abs(pose.y-origin.y) <= 32
            and abs(pose.z-origin.z) <= 20 and abs(pose.r-origin.r) < 0.2)


def jog(pose, origin, axes, height=False):
    x, y = (0 if abs(value) < 145 else 3 if value > 0 else -3 for value in axes)
    result = Pose(pose.x + (0 if height else x), pose.y + (0 if height else y),
                  pose.z + (y if height else 0), pose.r)
    return result if result != pose and inside(origin, result) else None


class TiltLink:
    def __init__(self, port, report):
        self.port, self.report = port, report
        self.latest = None
        self.buttons = []
        self.lock = Lock()
        self.stop = Event()
        self.thread = Thread(target=self._run, daemon=True, name="microbit-usb")
        self.thread.start()

    def read(self):
        with self.lock:
            buttons, self.buttons = self.buttons, []
            return self.latest, buttons

    def close(self):
        self.stop.set()

    def _run(self):
        try:
            from serial import Serial

            with Serial(self.port, 115200, timeout=0.1, exclusive=True) as connection:
                while not self.stop.is_set():
                    line = connection.read_until(size=96)
                    if not line.endswith(b"\n"):
                        continue
                    sample = parse_frame(line)
                    if sample:
                        with self.lock:
                            self.latest = sample
                            if sample.button != "-" and len(self.buttons) < 8:
                                self.buttons.append(sample)
        except Exception as error:
            if not self.stop.is_set():
                self.report(str(error))
