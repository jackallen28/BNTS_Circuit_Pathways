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
HOVER = 30            # mm above the height where the cup meets the top of a piece, for visiting a point
CLEARANCE = 40        # mm above that height, for Park and for travelling between points
# Hand-guiding the cup onto a circle is good to a few millimetres, and the circles are large, so a small
# miss is only a warning. Only a gross one, such as touching the wrong circle, stops the setup.
WARN_RESIDUAL = 4.0   # mm a taught point may sit from where the other points say it should, before a warning
BLOCK_RESIDUAL = 10.0   # mm from where the other points say, before the setup stops
WARN_SCALE_ERROR, BLOCK_SCALE_ERROR = 0.05, 0.15
WARN_TILT, BLOCK_TILT = 3.0, 8.0   # degrees of slope the playing surface may have
THICKNESS_RANGE = (1.0, 12.0)   # mm a piece may be, when it is adjusted by hand


def outer_points(layout):
    """The four circles farthest out towards the corners of the layout, in a fixed order."""
    names = list(layout.positions)

    def farthest(sign_x, sign_y):
        return max(names, key=lambda name: sign_x * layout.positions[name][0] + sign_y * layout.positions[name][1])

    return [farthest(-1, -1), farthest(1, -1), farthest(1, 1), farthest(-1, 1)]    # top left, top right, ...


def fit_similarity(mat, robot):
    """Fit robot = scale * A @ mat + offset, where A is a rotation that may include a mirror.

    The mat is drawn with y running down and the arm's y runs the other way when seen from above,
    so a mirror is usual. Returns (scale, A, offset). At least three points that are not in a line.
    """
    mat, robot = np.asarray(mat, float), np.asarray(robot, float)
    if len(mat) < 3:
        raise ValueError("At least three points are needed.")
    centre_m, centre_r = mat.mean(axis=0), robot.mean(axis=0)
    m, r = mat - centre_m, robot - centre_r
    spread = (m ** 2).sum()
    if np.linalg.matrix_rank(m, tol=1e-6 * max(spread, 1)) < 2:
        raise ValueError("The points are in a line. Teach points that are spread over the mat.")
    best = None
    for mirror in (False, True):
        flip = np.diag([1.0, -1.0]) if mirror else np.eye(2)
        u, s, vt = np.linalg.svd((r.T @ (m @ flip)) / len(m))
        sign = np.sign(np.linalg.det(u @ vt)) or 1.0
        rotation = u @ np.diag([1.0, sign]) @ vt
        scale = (s * [1.0, sign]).sum() * len(m) / spread
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

    def __init__(self, layout, touched, adjustments=None, piece_height=None):
        """``touched`` maps a circle name, or "Park", to the pose where the cup touched the mat there.

        The arm is touched onto the surface of the mat, so the surface is height zero. Everything
        the arm does with a piece is that plus the thickness of a piece: the cup meets the top of a
        piece lying on the mat there, and a piece held by its top has its underside on the surface
        when the cup is at the same height.
        """
        self.layout = layout
        self.touched = dict(touched)
        self.adjustments = dict(adjustments or {})
        self.piece_height = PIECE_HEIGHT * layout.piece_scale if piece_height is None else float(piece_height)
        names = [name for name in self.touched if name == PARK or name in layout.positions]
        if len(names) < 3:
            raise ValueError("Touch at least three points on the mat.")
        self.names = names
        self.scale, self.linear, self.offset = fit_similarity(
            [self._mat(name) for name in names], [(self.touched[name].x, self.touched[name].y) for name in names])
        self.plane = fit_plane([self.touched[name].xyz() for name in names])
        self.rotation = float(np.median([self.touched[name].r for name in names]))
        # How far each touched point is from where the others put it: a bad touch shows up here.
        self.residuals = {name: float(hypot(*(self.xy(name, adjusted=False) - (self.touched[name].x, self.touched[name].y))))
                          for name in names}

    def _mat(self, name):
        return self.layout.park if name == PARK else self.layout.positions[name]

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

    def poses(self):
        """The pick pose of every circle, and Park at a clear height."""
        result = {name: self.pick(name) for name in self.layout.positions}
        result[PARK] = self.park()
        return result

    def adjust(self, name, dx=0.0, dy=0.0, dz=0.0):
        """Nudge one point by a small amount, in millimetres, on top of earlier nudges."""
        if name != PARK and name not in self.layout.positions:
            raise KeyError(name)
        before = self.adjustments.get(name, (0.0, 0.0, 0.0))
        self.adjustments[name] = (before[0] + dx, before[1] + dy, before[2] + dz)
        return self.adjustments[name]
