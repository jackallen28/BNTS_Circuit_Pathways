"""Where the mat is, from the arm's point of view, worked out from a few touched points.

The mat's circles sit at known positions in millimetres. The arm is taught only the outer ones and
the centre mark. A fit of the mat's position, rotation, size and tilt then gives the pose of every
other circle, so setup needs no camera and no per-circle teaching.

A mat printed a little small, or placed a little askew, is absorbed by the fit. Only the arm's own
measurements are used, so the camera cannot throw the arm off.
"""
from math import atan, degrees, hypot

import numpy as np

from .robot import Pose
from .tictactoe import PIECE_HEIGHT

PARK = "Park"
REST = "Rest"
HOVER = 30            # mm above the height where the cup meets the top of a piece, for visiting a point
CLEARANCE = 40        # mm above that height, for Park and for travelling between points
# Hand-guiding the cup onto a circle is good to a few millimetres, and the circles are large, so a small
# miss is only a warning. Only a gross one, such as touching the wrong circle, stops the setup.
WARN_RESIDUAL = 4.0   # mm a taught point may sit from where the other points say it should, before a warning
BLOCK_RESIDUAL = 10.0   # mm from where the other points say, before the setup stops
WARN_SCALE_ERROR, BLOCK_SCALE_ERROR = 0.05, 0.15
WARN_TILT, BLOCK_TILT = 3.0, 8.0   # degrees of slope the playing surface may have
REST_CLEARANCE = 25   # mm between the edge of the nearest circle and the tool, while the arm waits off the mat
REST_MIN_RADIUS = 138  # mm from the arm's base: it cannot reach nearer than 130
REST_TIGHT = 15       # mm. A resting place closer than this to a circle is not really off the mat
THICKNESS_RANGE = (1.0, 12.0)   # mm a piece may be, when it is adjusted by hand


def outer_points(layout):
    """The four circles farthest out towards the corners of the layout, in a fixed order."""
    names = list(layout.positions)

    def farthest(sign_x, sign_y):
        return max(names, key=lambda name: sign_x * layout.positions[name][0] + sign_y * layout.positions[name][1])

    return [farthest(-1, -1), farthest(1, -1), farthest(1, 1), farthest(-1, 1)]    # top left, top right, ...


def in_a_line(points):
    """True when the points do not spread over a plane: two points, or three or more on one line."""
    points = np.asarray(points, float)
    if len(points) < 3:
        return True
    centred = points - points.mean(axis=0)
    return bool(np.linalg.matrix_rank(centred, tol=1e-6 * max((centred ** 2).sum(), 1)) < 2)


def fit_similarity(mat, robot, mirror=None, fixed_scale=None):
    """Fit robot = scale * A @ mat + offset, where A is a rotation that may include a mirror.

    The mat is drawn with y running down and the arm's y runs the other way when seen from above,
    so a mirror is usual. Returns (scale, A, offset). With ``mirror`` left out, at least three points
    that are not in a line are needed and the mirror is found. A camera looking down at the mat always
    sees that mirror, so ``mirror=True`` may be given, and then two points are enough. If the size is
    already known, ``fixed_scale`` keeps it, and only the position and the turn are fitted.
    """
    mat, robot = np.asarray(mat, float), np.asarray(robot, float)
    if len(mat) < (2 if mirror is not None else 3):
        raise ValueError("At least three points are needed." if mirror is None else "At least two points are needed.")
    centre_m, centre_r = mat.mean(axis=0), robot.mean(axis=0)
    m, r = mat - centre_m, robot - centre_r
    spread = (m ** 2).sum()
    if spread < 1e-9:
        raise ValueError("The points are all in one place. Teach points that are spread over the mat.")
    if mirror is None and in_a_line(mat):
        raise ValueError("The points are in a line. Teach points that are spread over the mat.")
    best = None
    for mirror in ((False, True) if mirror is None else (bool(mirror),)):
        flip = np.diag([1.0, -1.0]) if mirror else np.eye(2)
        u, s, vt = np.linalg.svd((r.T @ (m @ flip)) / len(m))
        sign = np.sign(np.linalg.det(u @ vt)) or 1.0
        rotation = u @ np.diag([1.0, sign]) @ vt
        scale = (s * [1.0, sign]).sum() * len(m) / spread
        if fixed_scale:
            scale = float(fixed_scale)
        linear = scale * rotation @ flip
        error = float(((r - m @ linear.T) ** 2).sum())
        if best is None or error < best[0]:
            best = (error, linear)
    linear = best[1]
    return float(np.sqrt(abs(np.linalg.det(linear)))), linear, centre_r - linear @ centre_m


def fit_plane(points):
    """Fit z = a x + b y + c through (x, y, z) points. Returns (a, b, c)."""
    points = np.asarray(points, float)
    design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
    return tuple(float(value) for value in np.linalg.lstsq(design, points[:, 2], rcond=None)[0])


class MatCalibration:
    """The arm's map of the mat, with a small hand adjustment for each point."""

    def __init__(self, layout, touched, adjustments=None, piece_height=None, print_scale=None, rest_shift=(0.0, 0.0)):
        """``touched`` maps a circle name, or "Park", to the pose where the cup touched the mat there.

        The arm is touched onto the surface of the mat, so the surface is height zero. Everything
        the arm does with a piece is that plus the thickness of a piece: the cup meets the top of a
        piece lying on the mat there, and a piece held by its top has its underside on the surface
        when the cup is at the same height.
        """
        self.layout = layout
        # How big the printed mat really is, as a fraction of its design (the measured scale line over 100 mm), if it
        # was measured. The mat's points are then taken at their real size, and the fit only finds where and how turned.
        self.print_scale = None if print_scale is None else float(print_scale)
        self.rest_shift = tuple(float(value) for value in rest_shift)       # a nudge of the resting place, in the arm's mm
        self.touched = dict(touched)
        self.adjustments = dict(adjustments or {})
        self.piece_height = PIECE_HEIGHT * layout.piece_scale if piece_height is None else float(piece_height)
        names = [name for name in self.touched if name == PARK or name in layout.positions]
        if len(names) < 2:
            raise ValueError("Touch at least two points on the mat.")
        self.names = names
        mat_points = [self._mat(name) for name in names]
        # With the centre and one corner (or points in a line) there is too little to find the mirror or the
        # slope, so the camera's top-down view supplies the mirror and the mat is taken as flat.
        self.quick = in_a_line(mat_points)
        self.scale, self.linear, self.offset = fit_similarity(
            mat_points, [(self.touched[name].x, self.touched[name].y) for name in names],
            mirror=True if self.quick else None, fixed_scale=1.0 if self.quick and self.print_scale else None)
        heights = [self.touched[name].z for name in names]
        self.plane = (0.0, 0.0, float(np.mean(heights))) if self.quick else fit_plane([self.touched[name].xyz() for name in names])
        self.rotation = float(np.median([self.touched[name].r for name in names]))
        # How far each touched point is from where the others put it: a bad touch shows up here.
        self.residuals = {name: float(hypot(*(self.xy(name, adjusted=False) - (self.touched[name].x, self.touched[name].y))))
                          for name in names}

    def _mat(self, name):
        point = self.layout.park if name == PARK else self.layout.positions[name]
        return point if self.print_scale is None else (point[0] * self.print_scale, point[1] * self.print_scale)

    def xy(self, name, adjusted=True):
        x, y = self.linear @ np.asarray(self._mat(name), float) + self.offset
        dx, dy, _ = self.adjustments.get(name, (0, 0, 0)) if adjusted else (0, 0, 0)
        return np.array((x + dx, y + dy))

    def surface_z(self, x, y):
        a, b, c = self.plane
        return a * x + b * y + c

    @property
    def tilt(self):
        """The slope of the playing surface, in degrees."""
        return degrees(atan(hypot(self.plane[0], self.plane[1])))

    @property
    def worst(self):
        name = max(self.residuals, key=self.residuals.get)
        return name, self.residuals[name]

    def errors(self):
        """Reasons the calibration cannot be used: something is clearly wrong."""
        found = []
        name, error = self.worst
        if error >= BLOCK_RESIDUAL:
            found.append(f"{name} is {error:.0f} mm from where the other points put it. Touch it again, "
                         "or check you touched the right circle.")
        if abs(self.scale - 1) > BLOCK_SCALE_ERROR:
            found.append(f"The mat measures {self.scale * 100:.0f}% of its printed size. Check the print scale.")
        if self.tilt > BLOCK_TILT:
            found.append(f"The mat slopes by {self.tilt:.0f} degrees. Is it lying flat?")
        return found

    def warnings(self):
        """Things that are a little off but good enough to go on with. They can be nudged in the next step."""
        found = []
        name, error = self.worst
        if WARN_RESIDUAL < error < BLOCK_RESIDUAL:
            found.append(f"{name} is {error:.1f} mm from where the other points put it.")
        if WARN_SCALE_ERROR < abs(self.scale - 1) <= BLOCK_SCALE_ERROR:
            found.append(f"The mat measures {self.scale * 100:.1f}% of its printed size.")
        if WARN_TILT < self.tilt <= BLOCK_TILT:
            found.append(f"The mat slopes by {self.tilt:.1f} degrees.")
        gap, near = self.rest_gap()
        if gap < REST_TIGHT:
            found.append(f"The arm's resting place is only {max(gap, 0):.0f} mm from {near}, so it is not clear of the mat. "
                         "Move the mat a little further from the arm.")
        return found

    def problems(self):
        """Everything worth mentioning: the errors first, then the warnings."""
        return self.errors() + self.warnings()

    def _pose(self, name, above):
        x, y = self.xy(name)
        z = self.surface_z(x, y) + self.piece_height + above + self.adjustments.get(name, (0, 0, 0))[2]
        return Pose(round(float(x), 2), round(float(y), 2), round(float(z), 2), round(self.rotation, 2))

    def set_piece_height(self, millimetres):
        """The thickness of a piece, if the printed ones are not the size the layout expects."""
        if not THICKNESS_RANGE[0] <= millimetres <= THICKNESS_RANGE[1]:
            raise ValueError(f"A piece is between {THICKNESS_RANGE[0]:g} and {THICKNESS_RANGE[1]:g} mm thick.")
        self.piece_height = round(float(millimetres), 3)
        return self.piece_height

    def pick(self, name):
        """Where the cup meets the top of a piece lying on this circle: the surface plus a piece.

        The same height places a piece, since its underside is then on the surface.
        """
        return self._pose(name, 0)

    def hover(self, name):
        """A little above that, for visiting the point without touching."""
        return self._pose(name, HOVER)

    def park(self):
        return self._pose(PARK, CLEARANCE)

    def rest_xy(self):
        """Where the arm waits during a game: off the mat, between the arm's base and the mat.

        Along the line from the base through the middle of the mat, as near the base as keeps the tool
        clear of the nearest circle (and no nearer than the arm can reach), then nudged by ``rest_shift``.
        """
        circles = np.array([self.xy(name) for name in self.layout.positions])
        centre = circles.mean(axis=0)
        length = hypot(*centre) or 1.0
        bearing = centre / length
        radius = max(REST_MIN_RADIUS, float((circles @ bearing).min()) - 12.5 * self.layout.piece_scale - REST_CLEARANCE)
        return bearing * radius + np.asarray(self.rest_shift)

    def rest_gap(self):
        """How far the resting place is from the edge of the nearest circle, and that circle's name."""
        spot = self.rest_xy()
        name = min(self.layout.positions, key=lambda circle: hypot(*(self.xy(circle) - spot)))
        return hypot(*(self.xy(name) - spot)) - 12.5 * self.layout.piece_scale, name

    def rest(self):
        """The resting pose: the height of Park, at the resting place."""
        x, y = self.rest_xy()
        return Pose(round(float(x), 2), round(float(y), 2), self.park().z, round(self.rotation, 2))

    def poses(self):
        """The pick pose of every circle, and Park at a clear height."""
        result = {name: self.pick(name) for name in self.layout.positions}
        result[PARK] = self.park()
        result[REST] = self.rest()
        return result

    def adjust(self, name, dx=0.0, dy=0.0, dz=0.0):
        """Nudge one point by a small amount, in millimetres, on top of earlier nudges."""
        if name != PARK and name not in self.layout.positions:
            raise KeyError(name)
        before = self.adjustments.get(name, (0.0, 0.0, 0.0))
        self.adjustments[name] = (before[0] + dx, before[1] + dy, before[2] + dz)
        return self.adjustments[name]
