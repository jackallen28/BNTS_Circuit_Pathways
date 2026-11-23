"""Bounded USB transport for the Dobot Magician serial protocol."""
from dataclasses import dataclass
from math import dist, isfinite
import struct
from time import monotonic

HEADER = b"\xaa\xaa"
GET_POSE, GET_ALARMS, GET_HOME, HOME = 10, 20, 30, 31
SUCTION, COORDINATE_SPEED, COMMON_SPEED, MOVE = 62, 81, 83, 84
QUEUE_START, QUEUE_STOP, QUEUE_FORCE_STOP, QUEUE_CLEAR, QUEUE_INDEX = 240, 241, 242, 245, 246
READ, WRITE, QUEUED_WRITE, LINEAR = 0, 1, 3, 2
POSITION_LIMIT_MM, ROTATION_LIMIT_DEG = 100, 25


class RobotError(Exception):
    pass


class MotionStopped(RobotError):
    pass


class StopUnconfirmed(RobotError):
    pass


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float
    r: float

    def xyz(self):
        return self.x, self.y, self.z

    def wire(self):
        return self.x, self.y, self.z, self.r

    def near(self, other, mm=2, degrees=3):
        return dist(self.xyz(), other.xyz()) <= mm and abs(self.r - other.r) <= degrees

    def label(self):
        return f"{self.x:.1f}, {self.y:.1f}, {self.z:.1f} mm  ·  {self.r:.1f}°"


def serial_ports():
    from serial.tools.list_ports import comports
    return sorted(port.device for port in comports() if port.vid is not None)


def frame(command, control, params=b""):
    payload = bytes((command, control)) + params
    return HEADER + bytes((len(payload),)) + payload + bytes((-sum(payload) & 0xff,))


class Magician:
    def __init__(self, port):
        import serial
        self.port = serial.Serial(
            port, baudrate=115200, timeout=0.025, write_timeout=0.15, exclusive=True
        )
        self.buffer = bytearray()

    def _request(self, command, control=READ, params=b"", size=0):
        packet = frame(command, control, params)
        if self.port.write(packet) != len(packet):
            raise RobotError("Incomplete USB write.")
        deadline = monotonic() + 0.4
        while monotonic() < deadline:
            self.buffer.extend(self.port.read(min(256, self.port.in_waiting or 1)))
            while len(self.buffer) >= 3:
                start = self.buffer.find(HEADER)
                if start < 0:
                    self.buffer[:] = self.buffer[-1:] if self.buffer[-1] == 0xaa else b""
                    break
                del self.buffer[:start]
                if len(self.buffer) < 3:
                    break
                length = self.buffer[2]
                if length < 2 or length > 64:
                    del self.buffer[0]
                    continue
                if len(self.buffer) < length + 4:
                    break
                candidate = self.buffer[3:length + 4]
                if sum(candidate) & 0xff:
                    del self.buffer[0]
                    continue
                del self.buffer[:length + 4]
                if candidate[:2] != bytes((command, control)):
                    continue
                if length != size + 2:
                    raise RobotError(f"Unexpected response length for USB command {command}.")
                return bytes(candidate[2:-1])
        self.buffer.clear()
        raise RobotError(f"Dobot did not answer USB command {command}.")

    def _pose(self, params, fmt):
        values = struct.unpack(fmt, params)
        if not all(isfinite(value) for value in values):
            raise RobotError("The Dobot returned invalid position data.")
        return Pose(*values[:4])

    def pose(self):
        return self._pose(self._request(GET_POSE, size=32), "<8f")

    def check_alarms(self):
        alarms = self._request(GET_ALARMS, size=16)
        if any(alarms):
            codes = [f"{i * 8 + bit:02X}" for i, byte in enumerate(alarms)
                     for bit in range(8) if byte & (1 << bit)]
            raise RobotError("Dobot alarms: " + ", ".join(codes))

    def stop(self):
        try:
            self._request(QUEUE_FORCE_STOP, WRITE)
            self._request(QUEUE_CLEAR, WRITE)
        except Exception as error:
            raise StopUnconfirmed("Stop could not be confirmed. Use the hardware stop.") from error

    def close(self):
        self.port.close()

    def _run(self, command, params, target, stop, timeout):
        try:
            if stop.is_set():
                raise MotionStopped("Motion stopped.")
            # Pause and empty the controller queue before submitting this single move.
            self._request(QUEUE_FORCE_STOP if command == HOME else QUEUE_STOP, WRITE)
            self._request(QUEUE_CLEAR, WRITE)
            if command == MOVE:
                self._request(COORDINATE_SPEED, WRITE, struct.pack("<4f", 25, 15, 40, 30))
                self._request(COMMON_SPEED, WRITE, struct.pack("<2f", 60, 60))
            index, = struct.unpack("<Q", self._request(command, QUEUED_WRITE, params, 8))
            if stop.is_set():
                raise MotionStopped("Motion stopped.")
            self._request(QUEUE_START, WRITE)
            deadline = monotonic() + timeout
            settled = 0
            while monotonic() < deadline:
                if stop.wait(0.085):
                    raise MotionStopped("Motion stopped.")
                current, = struct.unpack("<Q", self._request(QUEUE_INDEX, size=8))
                if stop.is_set():
                    raise MotionStopped("Motion stopped.")
                self.check_alarms()
                if stop.is_set():
                    raise MotionStopped("Motion stopped.")
                position = self.pose()
                if stop.is_set():
                    raise MotionStopped("Motion stopped.")
                if current == index and position.near(target):
                    settled += 1
                    if settled >= 3:
                        self._request(QUEUE_STOP, WRITE)
                        return position
                else:
                    settled = 0
            raise RobotError("The Dobot did not reach the requested position in time.")
        except Exception as error:
            try:
                self.stop()
            except StopUnconfirmed as stop_error:
                raise StopUnconfirmed(f"{error} {stop_error}") from stop_error
            raise

    def home(self, stop):
        target = self._pose(self._request(GET_HOME, size=16), "<4f")
        return self._run(HOME, struct.pack("<I", 0), target, stop, timeout=35)

    def move(self, target, permitted_origins, stop):
        self.check_alarms()
        position = self.pose()
        if not any(position.near(origin, mm=4, degrees=5) for origin in permitted_origins):
            raise RobotError("The arm is away from both taught positions. Re-teach after homing.")
        if not position.near(target, mm=POSITION_LIMIT_MM, degrees=ROTATION_LIMIT_DEG):
            raise RobotError("The requested move exceeds the demo's travel limit.")
        return self._run(MOVE, struct.pack("<B4f", LINEAR, *target.wire()), target, stop, timeout=15)


    def set_suction(self, enabled):
        self._request(SUCTION, WRITE, bytes((1, int(enabled))))

    def sort_chip(self, pick, drop, park, stop):
        """Execute one taught tabletop transfer and finish at the park pose."""
        self.check_alarms()
        if not self.pose().near(park, mm=4, degrees=5):
            raise RobotError("Place the suction tool at its taught park position first.")
        if any(not 12 <= park.z - pose.z <= 75 or abs(park.r - pose.r) > 5
               for pose in (pick, drop)):
            raise RobotError("Park must be 12 to 75 mm above pickup and drop-off, with the same rotation.")
        near_pick = Pose(pick.x, pick.y, park.z, park.r)
        near_drop = Pose(drop.x, drop.y, park.z, park.r)
        path = (near_pick, pick, near_pick, near_drop, drop, near_drop, park)
        if any(dist(a.xyz(), b.xyz()) > 150 for a, b in zip((park, *path), path)):
            raise RobotError("A transfer segment exceeds 150 mm. Move the tray or bins closer.")
        holding = False
        try:
            for index, target in enumerate(path):
                self._run(MOVE, struct.pack("<B4f", LINEAR, *target.wire()), target, stop, timeout=15)
                if stop.is_set():
                    self.stop()
                    raise MotionStopped("Sorting stopped.")
                if index == 1:
                    holding = True
                    self.set_suction(True)
                    stop.wait(0.35)
                elif index == 4:
                    self.set_suction(False)
                    holding = False
                    stop.wait(0.2)
            if stop.is_set():
                self.stop()
                raise MotionStopped("Sorting stopped.")
        except Exception as error:
            if holding:
                raise RobotError(f"{error} Suction may still be on. Check the tool before release.") from error
            raise
        return self.pose()
