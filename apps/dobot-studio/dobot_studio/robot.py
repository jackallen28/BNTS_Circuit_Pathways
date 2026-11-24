"""Bounded USB transport for the Dobot Magician serial protocol."""
from dataclasses import dataclass
from math import ceil, dist, hypot, isfinite
import struct
from time import monotonic

HEADER = b"\xaa\xaa"
GET_POSE, GET_ALARMS, GET_HOME, HOME = 10, 20, 30, 31
SUCTION, GRIPPER, COORDINATE_SPEED, COMMON_SPEED, MOVE = 62, 63, 81, 83, 84
QUEUE_START, QUEUE_STOP, QUEUE_FORCE_STOP, QUEUE_CLEAR, QUEUE_INDEX = 240, 241, 242, 245, 246
READ, WRITE, QUEUED_WRITE, LINEAR = 0, 1, 3, 2
POSITION_LIMIT_MM, ROTATION_LIMIT_DEG = 100, 25
TRANSFER_SEGMENT_MM = 150
# A sanity box for moves that are not between taught positions. The arm cannot fold in near its
# base or stretch past its reach, and nothing here should go through the table.
REACH_MM = (130, 310)
HEIGHT_MM = (-60, 160)
JOG_LIMIT_MM = 25
SLOW, QUICK = 25, 60      # tool speeds in mm per second
SUCTION_TOOL, GRIPPER_TOOL = "Suction cup", "Gripper"
ATTACHMENTS = (SUCTION_TOOL, GRIPPER_TOOL)


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

    def _run(self, command, params, target, stop, timeout, speed=SLOW):
        try:
            if stop.is_set():
                raise MotionStopped("Motion stopped.")
            # Pause and empty the controller queue before submitting this single move.
            self._request(QUEUE_FORCE_STOP if command == HOME else QUEUE_STOP, WRITE)
            self._request(QUEUE_CLEAR, WRITE)
            if command == MOVE:
                self._request(COORDINATE_SPEED, WRITE, struct.pack("<4f", speed, 15, 40, 30))
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


    @staticmethod
    def check_reach(target, floor=HEIGHT_MM[0]):
        """Refuse a point the arm cannot reach, or one below ``floor``, before any motion."""
        if not all(isfinite(value) for value in target.wire()):
            raise RobotError("That position is not a number.")
        radius = hypot(target.x, target.y)
        if not REACH_MM[0] <= radius <= REACH_MM[1]:
            raise RobotError(f"That point is {radius:.0f} mm from the arm's base. The arm can reach {REACH_MM[0]} to {REACH_MM[1]} mm.")
        if not floor <= target.z <= HEIGHT_MM[1]:
            raise RobotError(f"That height ({target.z:.0f} mm) is outside {floor:.0f} to {HEIGHT_MM[1]} mm.")

    def jog(self, delta, stop, floor=HEIGHT_MM[0]):
        """Nudge the tool by (dx, dy, dz) mm from where it is, a small step at a time."""
        if max(abs(value) for value in delta) > JOG_LIMIT_MM:
            raise RobotError(f"Move the arm in steps of {JOG_LIMIT_MM} mm or less.")
        self.check_alarms()
        here = self.pose()
        target = Pose(here.x + delta[0], here.y + delta[1], here.z + delta[2], here.r)
        self.check_reach(target, floor)
        return self._run(MOVE, struct.pack("<B4f", LINEAR, *target.wire()), target, stop, timeout=15)

    def travel(self, path, stop, speed=QUICK, arrived=None, floor=HEIGHT_MM[0]):
        """Visit each pose in turn in straight legs, none longer than the transfer limit.

        ``arrived(index, pose)`` is called when a pose of ``path`` is reached. A stop ends the
        journey where it is, and the arm's own force-stop clears whatever was queued.
        """
        self.check_alarms()
        for pose in path:
            self.check_reach(pose, floor)
        here = self.pose()
        for index, goal in enumerate(path):
            gap = dist(here.xyz(), goal.xyz())
            steps = max(1, ceil(gap / TRANSFER_SEGMENT_MM))
            for step in range(1, steps + 1):
                fraction = step / steps
                leg = Pose(*(a + (b - a) * fraction for a, b in zip(here.wire(), goal.wire())))
                self._run(MOVE, struct.pack("<B4f", LINEAR, *leg.wire()), leg, stop, timeout=20, speed=speed)
            here = goal
            if arrived:
                arrived(index, goal)
        return self.pose()

    def set_suction(self, enabled):
        self._request(SUCTION, WRITE, bytes((1, int(enabled))))

    def set_gripper(self, closed):
        self._request(GRIPPER, WRITE, bytes((1, int(closed))))

    def set_attachment(self, attachment, holding):
        if attachment == SUCTION_TOOL:
            self.set_suction(holding)
        elif attachment == GRIPPER_TOOL:
            self.set_gripper(holding)
        else:
            raise RobotError("Select a supported attachment.")

    def sort_chip(self, pick, drop, park, stop, attachment=SUCTION_TOOL, *, via_park=False):
        self.check_alarms()
        if attachment not in ATTACHMENTS:
            raise RobotError("Select a supported attachment.")
        if not self.pose().near(park, mm=4, degrees=5):
            raise RobotError("Place the fitted tool at its taught park position first.")
        if any(not 12 <= park.z - pose.z <= 75 or abs(park.r - pose.r) > 5
               for pose in (pick, drop)):
            raise RobotError("Park must be 12 to 75 mm above pickup and drop-off, with the same rotation.")
        near_pick = Pose(pick.x, pick.y, park.z, park.r)
        near_drop = Pose(drop.x, drop.y, park.z, park.r)
        carry = ((park, None),) if via_park and dist(near_pick.xyz(), near_drop.xyz()) > TRANSFER_SEGMENT_MM else ()
        actions = ((near_pick, None), (pick, True), (near_pick, None), *carry,
                   (near_drop, None), (drop, False), (near_drop, None), (park, None))
        if via_park:
            # A wide mat can need an intermediate waypoint along a clearance-height leg.
            route = []
            origin = park
            for target, grip in actions:
                if origin.z == target.z == park.z and dist(origin.xyz(), target.xyz()) > TRANSFER_SEGMENT_MM:
                    midpoint = Pose((origin.x + target.x)/2, (origin.y + target.y)/2, park.z, park.r)
                    route.append((midpoint, None))
                route.append((target, grip))
                origin = target
            actions = route
        path = (park, *(pose for pose, _ in actions))
        if any(dist(a.xyz(), b.xyz()) > TRANSFER_SEGMENT_MM for a, b in zip(path, path[1:])):
            raise RobotError(f"A transfer segment exceeds {TRANSFER_SEGMENT_MM} mm. Move the tray or bins closer.")
        holding = False
        try:
            if stop.is_set():
                raise MotionStopped("Transfer stopped.")
            if attachment == GRIPPER_TOOL:
                self.set_gripper(False)
            for target, grip in actions:
                self._run(MOVE, struct.pack("<B4f", LINEAR, *target.wire()), target, stop, timeout=15)
                if stop.is_set():
                    self.stop()
                    raise MotionStopped("Sorting stopped.")
                if grip is True:
                    holding = True
                    self.set_attachment(attachment, True)
                    stop.wait(0.35)
                elif grip is False:
                    self.set_attachment(attachment, False)
                    holding = False
                    stop.wait(0.2)
            if stop.is_set():
                self.stop()
                raise MotionStopped("Sorting stopped.")
        except Exception as error:
            if holding:
                raise RobotError(f"{error} The fitted tool may still hold a part. Check before release.") from error
            raise
        return self.pose()
