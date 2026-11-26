"""The guided setup for the physical Tic-tac-toe mat.

1. Show the mat to the camera and see "Good to go".
2. Capture the empty mat, with the arm out of the camera's way.
3. Touch the arm onto the centre mark.
4. Touch the arm onto the four outer circles. That is all the arm needs: it works out the rest.
5. Watch the arm visit every point, and nudge any that are a little off.
6. Check that the camera reads some pieces.

The camera only reads pieces. Where the arm goes comes from the points it was touched on.
"""
from dataclasses import replace
from math import hypot
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np

from .matcalib import MatCalibration, PARK, REST, outer_points
from .robot import ATTACHMENTS, HEIGHT_MM, Magician, Pose, RobotError, StopUnconfirmed
from .theme import DARK, GREEN, MUTED, PANEL, PURPLE, RED
from .tictactoe import CELLS, O, SMALL_MAT, SMALL_SUGGESTED_DISTANCE, UNKNOWN, X, describe_slot
from .tictactoe_vision import explain, lock_view, pixels_per_mm

STEPS = ("Show the mat", "Capture the empty mat", "Touch the centre mark", "Touch the corners",
         "Check every point", "Check the pieces", "Ready to play")
PIECES, READY = 5, 6
NUDGES = ("0.5 mm", "1 mm", "2 mm")
THICKNESS_STEP = 0.2
PAPER_THICKNESS = 0.4           # mm: a token cut from card
# Directions as the arm sees them: x runs away from its base and y to its left.
PAD = {"forward": ("▲  Forward", (1, 0, 0)), "back": ("▼  Back", (-1, 0, 0)), "left": ("◀  Left", (0, 1, 0)),
       "right": ("Right  ▶", (0, -1, 0)), "up": ("⬆  Up", (0, 0, 1)), "down": ("⬇  Down", (0, 0, -1))}
FRESH = 0.55
MOVE_STEPS = ("1 mm", "2 mm", "5 mm", "10 mm", "20 mm")
PICK_STEP, PICK_RANGE = 0.5, (-5.0, 12.0)   # mm the cup goes past the top of a piece to pick it up, to be changed by hand
PRINT_LINE_MM = 100.0   # the line printed at the foot of a paper mat
PRINT_RANGE = (90.0, 110.0)    # a measurement outside this is a mistake, not a scaled print
NEAR_CLEARANCE = 12     # mm above the mat while the arm is moved with the buttons
# Which way each arrow moves the cup on the map and the camera view, as a step across the mat's picture.
SCREEN = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
AMBER = "#8a5a00"
# How the arm is taught the mat. Both end the same way: the arm visits every circle and can be nudged.
FULL, QUICK_MODE = "full", "quick"
MODES = {FULL: "Accurate: the centre and the four corners (5 touches)",
         QUICK_MODE: "Quick: the centre and one corner (2 touches)"}


class SetupWizard:
    def __init__(self, program, parent):
        self.p = program
        self.studio = program.studio
        self.step = 0
        self.corner = 0
        self.touched = {}
        self.calibration = None
        self.notice = ""               # why the arm last refused or failed to move
        self.rest_shift = (0.0, 0.0)   # how far the person has nudged the arm's resting place from where it was worked out
        self.furthest = 0              # the last step reached, so any step up to it can be gone back to
        self.accepted = False          # the person chose to go on although a point looks far out
        self.pending = None            # the point a touch is being saved for
        self.selected = None           # the point being checked and nudged
        self.at, self.low = None, False
        self.order = []
        self.redo = None               # a corner being touched again
        self.checked = self.parked = self.pieces_ok = False
        self.unreadable, self.summary, self.problem = [], (0, 0, 0, 0), ""
        self.bank_report = {}          # each bank circle: (what was found, the mark it should hold, why if unreadable)
        self.grid_note, self.mark_notes = "", []
        self.reference_waiting = None
        self.title, self.text, self.status = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.mode = tk.StringVar(value=FULL)
        self.print_mm = tk.StringVar()          # what the printed 100 mm line measures, if it was measured
        self.print_note = tk.StringVar()
        self.lock_height = tk.BooleanVar(value=True)     # corners use the height of the centre mark
        self.move_step = tk.StringVar(value=MOVE_STEPS[2])
        self.nudge_step = tk.StringVar(value=NUDGES[1])
        self.adjust_text = tk.StringVar()
        self.thickness_text = tk.StringVar()
        self._build(parent)

    # ---- the layout of the panel
    def _build(self, parent):
        ui = self.studio
        # Any step already reached can be gone back to, a finished setup can go straight back to the game, and the whole
        # setup can be reset.
        self.shortcuts = tk.Frame(parent, bg=PANEL)
        self.shortcuts.pack(fill="x")
        self.jump_choice = tk.StringVar()
        self.jump_box = ttk.Combobox(self.shortcuts, textvariable=self.jump_choice, state="readonly", width=20,
                                     values=[f"{number + 1}. {name}" for number, name in enumerate(STEPS)])
        self.jump_box.pack(side="left")
        self.jump_box.bind("<<ComboboxSelected>>", lambda _event: self.jump(self.jump_box.current()))
        self.return_button = ui._button(self.shortcuts, "Back to the game", self.return_to_game, "Purple")
        self.reset_setup_button = ui._button(self.shortcuts, "Reset…", self.reset_setup)
        self.reset_setup_button.pack(side="right")
        self.heading = ui._label(parent, textvariable=self.title, size=11, weight="bold", fg=PURPLE, wraplength=320,
                                 justify="left")
        self.heading.pack(fill="x", pady=(2, 2))
        ui._label(parent, textvariable=self.text, size=9, fg=DARK, wraplength=320, justify="left").pack(fill="x")
        self.status_label = ui._label(parent, textvariable=self.status, size=9, weight="bold", wraplength=320,
                                      justify="left")
        self.status_label.pack(fill="x", pady=(4, 3))
        self.navigation = tk.Frame(parent, bg=PANEL)
        self.navigation.pack(side="bottom", fill="x", pady=(5, 0))
        self.back_button = ui._button(self.navigation, "◀  Back", self.back)
        self.back_button.pack(side="left")
        # The camera and piece adjustments are only here, while setting up. Play uses what they set.
        self.tune_button = ui._button(self.navigation, "Camera & pieces…", self.p.open_tune)
        self.tune_button.pack(side="left", padx=6)
        self.next_button = ui._button(self.navigation, "Next  ▶", self.next, "Purple")
        self.next_button.pack(side="right", ipadx=8)
        self.controls = tk.Frame(parent, bg=PANEL)
        self.controls.pack(side="bottom", fill="x", pady=(5, 0))
        self.program_map = self.p._build_guide(parent)
        self.frames = [tk.Frame(self.controls, bg=PANEL) for _ in STEPS]
        self._build_camera(self.frames[0])
        self._build_capture(self.frames[1])
        self._build_centre(self.frames[2])
        self._build_corners(self.frames[3])
        self._build_check(self.frames[4])
        self._build_pieces(self.frames[PIECES])
        self._show_step()

    def _build_camera(self, frame):
        ui = self.studio
        self.saved_banner = tk.Frame(frame, bg="#fff6dd", highlightbackground="#e0c068", highlightthickness=1, padx=6, pady=4)
        self.saved_text = tk.StringVar()
        ui._label(self.saved_banner, textvariable=self.saved_text, size=9, bg="#fff6dd", wraplength=290, justify="left").pack(fill="x")
        row = tk.Frame(self.saved_banner, bg="#fff6dd")
        row.pack(fill="x", pady=(3, 0))
        self.use_saved_button = ui._button(row, "Use the saved setup", lambda: self.use_saved("latest"), "Purple")
        self.use_saved_button.pack(side="left")
        self.start_fresh_button = ui._button(row, "Start fresh", self.start_fresh)
        self.start_fresh_button.pack(side="left", padx=4)
        self.use_backup_button = ui._button(row, "Before the last reset", lambda: self.use_saved("backup"))
        self.camera_row = tk.Frame(frame, bg=PANEL)
        self.camera_row.pack(fill="x")
        ui._label(self.camera_row, "Camera", size=9, fg=MUTED).pack(side="left")
        ttk.Entry(self.camera_row, textvariable=self.p.device, width=5).pack(side="left", padx=5)
        self.camera_button = ui._button(self.camera_row, "Start camera", self.p.toggle_camera)
        self.camera_button.pack(side="right")

    def _build_capture(self, frame):
        self.capture_button = self.studio._button(frame, "Capture empty mat", self.capture, "Purple")
        self.capture_button.pack(fill="x")

    def _build_centre(self, frame):
        self.connection_button = self.studio._button(frame, "Dobot connection…", self.p.setup_usb)
        ui = self.studio
        line = tk.Frame(frame, bg=PANEL)
        line.pack(fill="x", pady=(0, 4))
        ui._label(line, "Printed line measures", size=9, fg=MUTED).pack(side="left")
        entry = ttk.Entry(line, textvariable=self.print_mm, width=7)
        entry.pack(side="left", padx=4)
        ui._label(line, "mm", size=9, fg=MUTED).pack(side="left")
        self.print_mm.trace_add("write", lambda *_: self.print_changed())
        ui._label(frame, textvariable=self.print_note, size=9, fg=MUTED, wraplength=320, justify="left").pack(
            fill="x", pady=(0, 4))
        self.print_changed()
        self.centre_button = self.studio._button(frame, "Save the centre mark", self.save_centre, "Purple")
        self.centre_button.pack(fill="x")

    def _build_corners(self, frame):
        ui = self.studio
        self.mode_buttons = []
        for value, label in MODES.items():
            button = tk.Radiobutton(frame, text=label, value=value, variable=self.mode, command=self.set_mode,
                                    bg=PANEL, activebackground=PANEL, anchor="w", justify="left",
                                    font=ui.theme.font(9), highlightthickness=0)
            button.pack(fill="x")
            self.mode_buttons.append(button)
        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x", pady=(3, 0))
        self.near_button = ui._button(row, "Go near", self.go_near)
        self.near_button.pack(side="left")
        self.lower_mat_button = ui._button(row, "Lower to the mat", self.lower_to_mat)
        self.lower_mat_button.pack(side="left", padx=(4, 0))
        self.corner_button = ui._button(row, "Save this corner", self.save_corner, "Purple")
        self.corner_button.pack(side="right")
        arrows = tk.Frame(frame, bg=PANEL)
        arrows.pack(fill="x", pady=(3, 0))
        self.move_buttons = {}
        for key, label in (("left", "◀"), ("up", "▲"), ("down", "▼"), ("right", "▶")):
            button = ui._button(arrows, label, lambda key=key: self.move_cup(key))
            button.pack(side="left", padx=(0, 3), ipadx=4)
            self.move_buttons[key] = button
        for key, label in (("raise", "⬆"), ("sink", "⬇")):
            button = ui._button(arrows, label, lambda key=key: self.move_cup(key))
            button.pack(side="left", padx=(0, 3), ipadx=4)
            self.move_buttons[key] = button
        ttk.Combobox(arrows, textvariable=self.move_step, values=MOVE_STEPS, state="readonly", width=6).pack(
            side="right")
        tk.Checkbutton(frame, text="Use the centre mark's height for the corners", variable=self.lock_height,
                       bg=PANEL, activebackground=PANEL, anchor="w", font=ui.theme.font(9),
                       highlightthickness=0).pack(fill="x", pady=(3, 0))
        self.anyway_button = self.studio._button(frame, "Use these points anyway", self.use_anyway)

    def _build_check(self, frame):
        ui = self.studio
        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x")
        self.tour_button = ui._button(row, "Check all points", self.run_check, "Purple")
        self.tour_button.pack(side="left", fill="x", expand=True)
        self.go_button = ui._button(row, "Go to selected", lambda: self.visit(False))
        self.go_button.pack(side="left", padx=(4, 0))
        self.lower_button = ui._button(row, "Lower", lambda: self.visit(True))
        self.lower_button.pack(side="left", padx=(4, 0))
        pad = tk.Frame(frame, bg=PANEL)
        pad.pack(pady=(5, 0))
        self.pad_buttons = {}
        for key, (row_index, column) in {"forward": (0, 1), "left": (1, 0), "back": (1, 1), "right": (1, 2),
                                         "up": (0, 3), "down": (1, 3)}.items():
            label, delta = PAD[key]
            button = ui._button(pad, label, lambda delta=delta: self.nudge(delta))
            button.grid(row=row_index, column=column, padx=2, pady=1, sticky="ew")
            self.pad_buttons[key] = button
        pad.columnconfigure(2, minsize=3)
        line = tk.Frame(frame, bg=PANEL)
        line.pack(fill="x", pady=(4, 0))
        ui._label(line, "Nudge by", size=9, fg=MUTED).pack(side="left")
        ttk.Combobox(line, textvariable=self.nudge_step, values=NUDGES, state="readonly", width=7).pack(side="left", padx=5)
        self.reset_button = ui._button(line, "Undo nudges", self.reset_adjustment)
        self.reset_button.pack(side="right")
        ui._label(frame, textvariable=self.adjust_text, size=9, fg=MUTED, wraplength=320, justify="left").pack(
            fill="x", pady=(3, 0))
        pick = tk.Frame(frame, bg=PANEL)
        pick.pack(fill="x", pady=(3, 0))
        self.pick_text = tk.StringVar()
        ui._label(pick, textvariable=self.pick_text, size=9, fg=DARK, wraplength=190, justify="left").pack(side="left")
        self.test_pick_button = ui._button(pick, "Test pick", self.test_pick)
        self.test_pick_button.pack(side="right")
        self.shallower_button = ui._button(pick, "−", lambda: self.change_pick(-PICK_STEP))
        self.shallower_button.pack(side="right", padx=(0, 4))
        self.deeper_button = ui._button(pick, "+", lambda: self.change_pick(PICK_STEP))
        self.deeper_button.pack(side="right", padx=(0, 4))
        thickness = tk.Frame(frame, bg=PANEL)
        thickness.pack(fill="x", pady=(3, 0))
        ui._label(thickness, textvariable=self.thickness_text, size=9, fg=DARK, wraplength=250,
                  justify="left").pack(side="left")
        self.thicker_button = ui._button(thickness, "+", lambda: self.change_thickness(THICKNESS_STEP))
        self.thicker_button.pack(side="right")
        self.thinner_button = ui._button(thickness, "−", lambda: self.change_thickness(-THICKNESS_STEP))
        self.thinner_button.pack(side="right", padx=(0, 4))
        self.paper_button = ui._button(thickness, "Paper", self.paper_tokens)
        self.paper_button.pack(side="right", padx=(0, 4))

    def _build_pieces(self, frame):
        ui = self.studio
        self.pieces_button = ui._button(frame, "Capture pieces", self.capture_pieces, "Purple")
        self.pieces_button.pack(fill="x")
        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x", pady=(4, 0))
        ui._label(row, "Resting place", size=9, fg=MUTED).pack(side="left", padx=(0, 6))
        self.rest_buttons = {}
        for key, label in (("left", "◀"), ("up", "▲"), ("down", "▼"), ("right", "▶")):
            button = ui._button(row, label, lambda key=key: self.nudge_rest(key))
            button.pack(side="left", padx=(0, 3), ipadx=4)
            self.rest_buttons[key] = button

    # ---- the state the panel is in
    @property
    def robot_ready(self):
        return self.studio.robot is not None and self.studio.homed

    @property
    def idle(self):
        return not self.p.busy and self.p.checking is None

    @property
    def view_fresh(self):
        return self.p.found is not None and monotonic() - self.p.analysed < FRESH

    @property
    def done(self):
        return self.p.setup_done

    def corners(self):
        return outer_points(self.p.layout)

    def required(self):
        """The corners that must be touched. Quick mode needs only the first; the others can still be added."""
        corners = self.corners()
        return corners[:1] if self.mode.get() == QUICK_MODE else corners

    def next_corner(self):
        """The corner to touch now: the first one still to do, or the last one if all are done."""
        required = self.required()
        return required[min(self.corner, len(required) - 1)]

    def set_mode(self):
        """The person chose Quick or Accurate. Keep what has been touched, and see what is still needed."""
        if self.step != 3 or not self.idle:
            return
        self.corner = next((i for i, corner in enumerate(self.required()) if corner not in self.touched),
                           len(self.required()))
        self.accepted = False
        self._calibrate()
        self.p.teaching.set(self.target() or "")
        self.p._draw_camera()

    def target(self):
        """The point the map and the camera view should be pointing at."""
        if self.step == 2:
            return PARK
        if self.step == 3:
            return self.redo or self.next_corner()
        if self.step == PIECES:
            bad = self.bad_slots()
            return bad[0] if bad else None
        return self.selected if self.step == 4 else None

    # ---- moving between steps
    def next(self):
        if self.step == READY:
            self.p.side_tabs.select(self.p.match_tab)
        elif self.step == PIECES:
            self.finish()
        elif self._ready_to_leave():
            self.step += 1
            self._entered()

    def back(self):
        if self.step and self.idle:
            self.step -= 1
            self._entered()

    def _ready_to_leave(self):
        return {0: self.p.found is not None and self.view_fresh, 1: self.p.reference is not None,
                2: PARK in self.touched, 3: self.usable(),
                4: self.checked}.get(self.step, False) and self.idle

    def print_scale(self):
        """How big the printed mat is as a fraction of its design, from the measured line, or None if not given."""
        text = self.print_mm.get().strip().replace(",", ".").removesuffix("mm").strip()
        try:
            value = float(text)
        except ValueError:
            return None
        return value / PRINT_LINE_MM if PRINT_RANGE[0] <= value <= PRINT_RANGE[1] else None

    def print_changed(self):
        text = self.print_mm.get().strip()
        scale = self.print_scale()
        if not text:
            self.print_note.set("Optional. Measure the 100 mm line at the foot of the printed mat with a ruler and type "
                                "what it measures. The arm then allows for a print that is not exactly full size.")
        elif scale is None:
            self.print_note.set(f"That is not a length near 100 mm. Type a number from {PRINT_RANGE[0]:g} to {PRINT_RANGE[1]:g}, "
                                "or leave it empty.")
        else:
            self.print_note.set(f"The print is {scale * 100:.1f}% of full size, and the arm allows for it.")
        if getattr(self, "frames", None) and self.touched and self.step <= 4 and self.calibration is not None:
            self._calibrate()           # the points change with the print size
            self.p._draw_camera()

    def usable(self):
        """Corners are saved and nothing is clearly wrong, or the person has chosen to go on anyway."""
        return self.calibration is not None and not self.unreachable() and (not self.calibration.errors() or self.accepted)

    def floor(self):
        """The lowest height the arm may be sent to: just under the mat it was touched on.

        The mat sits wherever the table is, which can be lower than the arm's usual working floor,
        so the floor follows the touches instead. Nothing is ever sent below the mat itself.
        """
        heights = [pose.z for pose in self.touched.values()]
        return min(HEIGHT_MM[0], min(heights) - 5) if heights else HEIGHT_MM[0]

    def unreachable(self):
        """Points the arm cannot reach from where the mat sits, as (name, reason). The arm would refuse them."""
        if self.calibration is None:
            return []
        found = []
        for name in (*self.p.layout.positions, PARK, REST):
            try:
                floor = self.floor()
                special = {PARK: self.calibration.park, REST: self.calibration.rest}
                Magician.check_reach(special[name]() if name in special else self.calibration.hover(name), floor)
                Magician.check_reach(special[name]() if name in special else self.calibration.pick(name), floor)
            except RobotError as error:
                found.append((name, str(error)))
        return found

    def use_anyway(self):
        if self.calibration is not None and self.calibration.errors():
            self.accepted = True

    def _entered(self):
        self.furthest = max(self.furthest, self.step)
        if self.step == 4:
            self.p.poses = self.calibration.poses()
            self.selected = None
        if self.step == PIECES and not self.parked:
            self._go_to_park()
        self.p.teaching.set(self.target() or "")
        self._show_step()
        self.p._draw_camera()

    def _show_step(self):
        for index, frame in enumerate(self.frames):
            frame.pack_forget()
            if index == self.step:
                frame.pack(fill="x")

    # ---- step 2: the empty mat
    def capture(self):
        self.p.capture_empty()
        self.parked = False
        self.p.setup_done = False

    # ---- steps 3 and 4: touching the arm onto the mat
    def _touch(self, name):
        if self.robot_ready and self.idle:
            self.pending = name
            self.p._job("touch", self.studio.robot.pose)

    def save_centre(self):
        self._touch(PARK)

    def save_corner(self):
        self._touch(self.redo or self.next_corner())

    # ---- moving the arm with the buttons instead of by hand
    def height(self):
        """The height of the mat's surface, from the centre mark."""
        return self.touched[PARK].z if PARK in self.touched else None

    def _map(self):
        """The mat's picture to the arm's millimetres, as (2 x 2 matrix, offset), from what is known so far.

        With two touches this is the quick fit. With only the centre, it is a rough guess: the Dobot
        at the top edge of the mat on the map, so the mat's "down" is away from the arm's base.
        """
        layout = self.p.layout
        if len(self.touched) >= 2:
            fit = MatCalibration(layout, self.touched, print_scale=self.print_scale())
            return fit.linear * (fit.print_scale or 1.0), fit.offset
        centre = self.touched[PARK]
        length = hypot(centre.x, centre.y) or 1.0
        ux, uy = centre.x / length, centre.y / length
        linear = np.array([[-uy, ux], [ux, uy]]) * (self.print_scale() or 1.0)
        return linear, np.array((centre.x, centre.y)) - linear @ np.asarray(layout.park, float)

    def near_pose(self, name):
        """Where the cup should be to be near a circle, a little above the mat."""
        linear, offset = self._map()
        x, y = linear @ np.asarray(self.p.layout.positions[name], float) + offset
        return Pose(round(float(x), 2), round(float(y), 2), self.height() + NEAR_CLEARANCE, self.touched[PARK].r)

    def _can_move_by_buttons(self):
        return PARK in self.touched and self.robot_ready and self.idle and self.step == 3

    def go_near(self):
        """Lift the cup and carry it to where this circle should be, as far as is known. The arrows do the rest."""
        name = self.redo or self.target()
        if not (name and self._can_move_by_buttons()):
            return
        goal, robot, floor = self.near_pose(name), self.studio.robot, self.floor()
        slow, quick = self.p.speeds()
        self.notice = ""

        def run():
            here = robot.pose()
            lifted = Pose(here.x, here.y, max(here.z, goal.z), goal.r)
            return robot.travel([lifted, goal], self.p.abort, speed=quick, floor=floor)

        self.p._job("move", run)

    def lower_to_mat(self):
        if not self._can_move_by_buttons():
            return
        robot, floor, height = self.studio.robot, self.floor(), self.height()
        slow, quick = self.p.speeds()
        self.notice = ""

        def run():
            here = robot.pose()
            return robot.travel([Pose(here.x, here.y, height, here.r)], self.p.abort, speed=slow, floor=floor)

        self.p._job("move", run)

    def move_cup(self, key):
        """An arrow: one step across the mat as it looks on the map and the camera, or up and down."""
        if not self._can_move_by_buttons():
            return
        amount = float(self.move_step.get().split()[0])
        if key in ("raise", "sink"):
            delta = (0.0, 0.0, amount if key == "raise" else -amount)
        else:
            linear, _ = self._map()
            across = np.asarray(SCREEN[key], float) * (-1 if self.p.dobot_side.get() else 1)
            moved = linear @ across
            moved = moved / (hypot(*moved) or 1.0) * amount
            delta = (float(moved[0]), float(moved[1]), 0.0)
        robot, floor = self.studio.robot, self.floor()
        self.notice = ""
        self.p._job("move", lambda: robot.jog(delta, self.p.abort, floor=floor))

    def picked(self, name):
        """A circle was clicked on the map."""
        if not self.idle:
            return
        if self.step == 3 and name in self.corners():
            self.redo = name
            self.p.teaching.set(name)
        elif self.step == 4 and name != PARK:
            self.selected = name
            self.p.teaching.set(name)
        elif self.step == 4:
            self.selected = PARK
            self.p.teaching.set(PARK)
        self.p._draw_camera()

    def _calibrate(self):
        old = self.calibration.adjustments if self.calibration else {}
        thickness = self.calibration.piece_height if self.calibration else None
        if PARK in self.touched and all(name in self.touched for name in self.required()):
            self.calibration = MatCalibration(self.p.layout, self.touched, old, thickness, self.print_scale(),
                                              self.rest_shift)
            self.p.poses = self.calibration.poses()
        else:
            self.calibration = None

    # ---- step 5: watching the arm visit every point
    def run_check(self):
        if not (self.calibration and self.robot_ready and self.idle):
            return
        self.notice = ""
        self.order = list(self.p.layout.positions)
        path = []
        if self.low and self.at:
            path.append(self.calibration.hover(self.at))
        path += [self.calibration.hover(name) for name in self.order] + [self.calibration.rest()]
        offset = len(path) - len(self.order) - 1
        labels = [None] * offset + self.order + [REST]
        events, robot = self.p.events, self.studio.robot

        def tour():
            return robot.travel(path, self.p.abort, speed=self.p.speeds()[1], floor=self.floor(),
                                arrived=lambda index, _pose: events.put(("arrived", labels[index], None)))

        self.low = False
        self.p._job("tour", tour)

    def visit(self, lower):
        if not (self.calibration and self.selected and self.robot_ready and self.idle):
            return
        self.notice = ""
        name, calibration = self.selected, self.calibration
        path = []
        if self.at and self.at != name and self.low:
            path.append(calibration.hover(self.at))
        path.append(calibration.park() if name == PARK else (calibration.pick(name) if lower else calibration.hover(name)))
        self.pending = (name, lower)
        robot, floor = self.studio.robot, self.floor()
        self.p._job("visit", lambda: robot.travel(path, self.p.abort, speed=self.p.speeds()[0 if lower else 1],
                                                           floor=floor))

    def nudge(self, delta):
        if not (self.calibration and self.selected):
            return
        amount = float(self.nudge_step.get().split()[0])
        self.calibration.adjust(self.selected, *(value * amount for value in delta))
        self.p.poses = self.calibration.poses()
        self.visit(self.low)

    def change_thickness(self, delta):
        """The pieces are thicker or thinner than expected: every pick and place height follows."""
        if not self.calibration:
            return
        try:
            self.calibration.set_piece_height(self.calibration.piece_height + delta)
        except ValueError as error:
            self.p.status.set(str(error))
            return
        self.p.poses = self.calibration.poses()          # only the arm's heights change: the game can carry on from here
        self.visit(self.low) if self.selected else None

    # ---- how far down the cup goes to pick a piece up
    def change_pick(self, delta):
        """The cup did not take hold of a piece (or pressed too hard): go a little deeper or higher to pick one up."""
        value = min(max(self.p.pick_press + delta, PICK_RANGE[0]), PICK_RANGE[1])
        self.p.pick_press = round(value, 2)

    def test_pick(self):
        """Pick up the first piece of the Dobot's bank, hold it a moment, and put it back. Then it is plain to see if it took hold."""
        if not (self.calibration and self.robot_ready and self.idle):
            return
        slot = self.p.layout.bank(self.p.dobot)[0]
        calibration, robot, floor, abort = self.calibration, self.studio.robot, self.floor(), self.p.abort
        slow, quick = self.p.speeds()
        rest, hover = calibration.rest(), calibration.hover(slot)
        down = replace(calibration.pick(slot), z=calibration.pick(slot).z - self.p.pick_press)
        self.notice = ""

        def run():
            robot.to_rest(rest, abort, speed=quick, floor=floor)
            robot.travel([hover], abort, speed=quick, floor=floor)
            robot.travel([down], abort, speed=slow, floor=floor)
            robot.set_attachment(ATTACHMENTS[0], True)
            abort.wait(0.6)
            robot.travel([hover], abort, speed=slow, floor=floor)          # lifted: is the piece up on the cup?
            abort.wait(1.2)
            robot.travel([down], abort, speed=slow, floor=floor)
            robot.set_attachment(ATTACHMENTS[0], False)
            abort.wait(0.3)
            robot.travel([hover], abort, speed=slow, floor=floor)
            return robot.to_rest(rest, abort, speed=quick, floor=floor)

        self.p.status.set(f"Picking up the piece on {slot}, holding it, and putting it back. Watch the cup. Put a piece there first.")
        self.p._job("pick_test", run)

    def paper_tokens(self):
        """Tokens cut from paper or thin card, rather than the 3D pieces: about 0.4 mm thick."""
        if self.calibration:
            self.change_thickness(PAPER_THICKNESS - self.calibration.piece_height)

    def reset_adjustment(self):
        if self.calibration and self.selected and self.selected in self.calibration.adjustments:
            del self.calibration.adjustments[self.selected]
            self.p.poses = self.calibration.poses()
            self.visit(self.low)

    # ---- step 6: resting position and the pieces
    def _go_to_park(self):
        """Take the arm to its resting place, off the mat, where it waits during a game."""
        if not (self.calibration and self.robot_ready and self.idle):
            return
        robot, rest, floor = self.studio.robot, self.calibration.rest(), self.floor()
        quick = self.p.speeds()[1]
        self.p._job("park", lambda: robot.to_rest(rest, self.p.abort, speed=quick, floor=floor))

    def nudge_rest(self, key):
        """Move the resting place a step across the mat's picture, as the arrows on the map show, and go there."""
        if not (self.calibration and self.robot_ready and self.idle and self.step == PIECES):
            return
        linear, _ = self._map()
        across = np.asarray(SCREEN[key], float) * (-1 if self.p.dobot_side.get() else 1)
        moved = linear @ across
        moved = moved / (hypot(*moved) or 1.0) * float(self.move_step.get().split()[0])
        self.rest_shift = (self.rest_shift[0] + float(moved[0]), self.rest_shift[1] + float(moved[1]))
        self.calibration.rest_shift = self.rest_shift
        self.p.poses = self.calibration.poses()
        self.parked = False                  # the camera looks again, with the arm in its new place
        self._go_to_park()

    def capture_pieces(self):
        """Check the two banks: a piece on every circle of both.

        That is all the camera needs to know during a game: whether a circle's black is covered or clear. What each piece
        is, X or O, is known from the bank it is in. If the camera can also make out a mark, and it is plainly the other
        mark, that is mentioned (a piece in the wrong bank), but it does not stop the setup.
        The nine grid circles are not part of this check. They hold no pieces yet.
        """
        p = self.p
        self.pieces_ok = False
        self.problem, self.bank_report, self.unreadable, self.grid_note, self.mark_notes = "", {}, [], "", []
        if p.camera_moved:
            self.problem = "The camera has moved. Go back and capture the empty mat again."
            return
        latest = p.latest
        if latest is None or not self.view_fresh_any() or p.rectified is None or p.reference is None:
            self.problem = "Wait for a steady view of the whole mat."
            return
        covered = dict(zip(p.layout.reserve, latest.reserve))
        reading = dict(zip(p.layout.reserve, p.reading.reserve)) if p.reading is not None else {}
        for mark in p.layout.reserve_marks(p.dobot):
            for slot in p.layout.bank(mark):
                if covered[slot] == "":
                    self.bank_report[slot] = ("empty", mark, "")
                else:
                    self.bank_report[slot] = ("ok", mark, "")
                    seen = reading.get(slot, "")
                    if seen in (X, O) and seen != mark:
                        self.mark_notes.append(f"{slot} looks like an {seen}, but it is in the {mark} bank")
        self.pieces_ok = all(state == "ok" for state, _, _ in self.bank_report.values())
        busy = [name for name, mark in zip(CELLS, latest.board) if mark != ""]
        self.grid_note = f"The grid should be clear, but {', '.join(busy)} look covered." if busy else ""
        self.summary = (sum(m == X for m in latest.board), sum(m == O for m in latest.board),
                        sum(m == X for m in latest.reserve), sum(m == O for m in latest.reserve))
        bad = self.bad_slots()
        if bad:
            p.teaching.set(bad[0])
        p._draw_camera()

    def bad_slots(self):
        """The bank circles that are not right, in the order they were checked."""
        return [slot for slot, (state, _, _) in self.bank_report.items() if state != "ok"]

    def finish(self):
        if self.pieces_ok and self.idle and self.calibration:
            self.p.finish_setup()
            self.step = self.furthest = READY
            self._show_step()

    # ---- going back into the setup, and back to the game
    def jump(self, step):
        """Go to a step that has been reached before, to change a small thing, then return to the game."""
        if not self.idle or step == self.step or step > self.furthest:
            return
        if (step >= 2 and self.p.reference is None) or (step >= 4 and self.calibration is None):
            return
        self.step = step
        self._entered()

    def return_to_game(self):
        """The setup is finished and nothing that matters was moved: back to the Match tab."""
        if self.p.setup_done and self.idle:
            self.step = READY
            self._show_step()
            self.p.side_tabs.select(self.p.match_tab)

    def reset_setup(self):
        """Begin the whole setup again, keeping the saved copy for a way back or throwing it away."""
        if not self.idle:
            return
        answer = messagebox.askyesnocancel(
            "Reset the setup", "Begin the setup again?\n\nYes: reset, and keep the saved setup so it can be used again.\n"
            "No: reset, and do not keep the saved setup.\nCancel: carry on as you are.", parent=self.p.window)
        if answer is not None:
            self.p.reset_setup(keep=bool(answer))

    def use_saved(self, which="latest"):
        if not self.idle:
            return
        try:
            message = self.p.restore(which)
        except (ValueError, KeyError, OSError, TypeError) as error:
            self.p.status.set(f"The saved setup could not be used: {error}")
            return
        self.p.status.set(message)

    def start_fresh(self):
        self.p.begin_new_setup()
        self.p.status.set("Starting a new setup. The saved one is kept aside.")

    def load(self, data, layout):
        """Take a saved setup back, as far as the pictures of it allow. The arm is not moved."""
        from .matcalib import MatCalibration

        self.calibration, self.touched = None, {}
        self.mode.set(data.get("mode", FULL))
        self.lock_height.set(bool(data.get("lock_height", True)))
        self.print_mm.set(data.get("print_mm", ""))
        self.rest_shift = tuple(float(v) for v in data.get("rest_shift", (0.0, 0.0)))
        self.touched = {name: Pose(*values) for name, values in data["touched"].items()}
        self.accepted = bool(data.get("accepted"))
        self.corner = next((i for i, corner in enumerate(self.required()) if corner not in self.touched), len(self.required()))
        if PARK in self.touched and all(name in self.touched for name in self.required()):
            self.calibration = MatCalibration(
                layout, self.touched, {name: tuple(shift) for name, shift in data.get("adjustments", {}).items()},
                data.get("piece_height"), self.print_scale(), self.rest_shift)
        done = bool(data.get("setup_done")) and self.calibration is not None
        step = int(data.get("step", 0))
        step = READY if done else (min(step, PIECES) if self.calibration else min(step, 3))
        self.checked = done or int(data.get("furthest", 0)) >= 5
        self.parked = self.pieces_ok = done
        self.selected, self.at, self.low, self.redo = None, None, False, None
        self.step, self.furthest = step, max(int(data.get("furthest", 0)), step)
        self.p.poses = self.calibration.poses() if self.calibration else {}
        if step == PIECES:
            self._entered()                       # the arm goes to its resting place and the camera looks again
        else:
            self.p.teaching.set(self.target() or "")
            self._show_step()

    # ---- results of the jobs the arm ran
    def finished(self, name, value, error):
        if error:
            self.p.status.set(str(error))
            self.notice = str(error)
            if isinstance(error, StopUnconfirmed):
                self.studio.homed = False      # the arm may not have stopped: home it again before trusting it
            self.p._draw_camera()
            return
        self.notice = ""
        if name == "move":
            pass
        elif name == "pick_test":
            self.p.status.set("Test pick done. If the piece did not lift with the cup, go a little deeper with + and try again.")
        elif name == "touch":
            if self.pending != PARK and PARK in self.touched and self.lock_height.get():
                value = replace(value, z=self.touched[PARK].z)       # the mat is the height of the centre mark
            self.touched[self.pending] = value
            self.redo = None
            self.corner = next((i for i, corner in enumerate(self.required()) if corner not in self.touched),
                               len(self.required()))
            self.accepted = False
            self.pieces_ok = False
            self.p.setup_done = False
            self._calibrate()
            if self.target():
                self.p.teaching.set(self.target())
        elif name == "tour":
            self.checked, self.at, self.low = True, None, False
            self.p.status.set("Every point has been visited. Click a circle on the map to look at it more closely.")
        elif name == "visit":
            self.at, self.low = self.pending[0], self.pending[1]
        elif name == "park":
            self.parked, self.at, self.low = True, None, False
            self.reference_waiting = monotonic() + 0.8      # let the arm settle before the camera looks
        self.p._draw_camera()

    def arrived(self, name):
        if name:
            self.p.teaching.set(name)
            self.selected = name if name not in (PARK, REST) else self.selected
            self.at = name if name != REST else None
            self.p.status.set(f"Visiting {name}" if name != REST else "Back at the resting place.")
            self.p._draw_camera()

    def tick(self):
        """Take the camera's second reference once the arm has settled at Park."""
        if self.reference_waiting and monotonic() >= self.reference_waiting and self.view_fresh_any():
            self.reference_waiting = None
            import numpy as np
            self.p.reference = lock_view(np.asarray(self.p.feed), self.p.reference, self.p.tune)
            self.p.latest, self.p.seen, self.p.view_clear = None, 0, False

    def view_fresh_any(self):
        return self.p.feed is not None and monotonic() - self.p.analysed < FRESH

    # ---- the words and the buttons
    def refresh(self):
        ui, p = self.studio, self.p
        self.tick()
        self._refresh_extras()
        self.title.set(f"Step {self.step + 1} of {len(STEPS)} · {STEPS[self.step]}")
        text, status, ok = getattr(self, f"_words{self.step}")()
        self.text.set(text)
        self.status.set(status)
        self.status_label.configure(fg=AMBER if ok == "warn" else GREEN if ok else RED if ok is False else MUTED)
        idle = self.idle
        ui._set_button(self.back_button, idle and self.step > 0)
        ui._set_button(self.tune_button, idle and p.feed is not None and not self.p.studio.demo)
        if self.step == READY:
            self.tune_button.pack_forget()
        elif not self.tune_button.winfo_ismapped():
            self.tune_button.pack(side="left", padx=6, after=self.back_button)
        self.next_button.configure(text={PIECES: "Finish setup  ▶", READY: "Go to Match  ▶"}.get(self.step, "Next  ▶"))
        ui._set_button(self.next_button, {PIECES: self.pieces_ok and idle, READY: True}.get(self.step, self._ready_to_leave()))
        ui._set_button(self.camera_button, idle)
        self.camera_button.configure(text="Stop camera" if p.camera else "Start camera")
        ui._set_button(self.capture_button, idle and self.view_fresh and not p.ready)
        arm = self.robot_ready and idle
        ui._set_button(self.centre_button, arm)
        ui._set_button(self.corner_button, arm)
        moving = arm and PARK in self.touched and self.step == 3
        for button in (self.near_button, self.lower_mat_button, *self.move_buttons.values()):
            ui._set_button(button, moving)
        for button in self.mode_buttons:
            button.configure(state="normal" if idle else "disabled")
        asking = self.step == 3 and self.calibration is not None and bool(self.calibration.errors()) and not self.accepted
        if asking and not self.anyway_button.winfo_ismapped():
            self.anyway_button.pack(fill="x", pady=(4, 0))
        elif not asking:
            self.anyway_button.pack_forget()
        ui._set_button(self.anyway_button, idle)
        if self.robot_ready:
            self.connection_button.pack_forget()
        elif not self.connection_button.winfo_ismapped():
            self.connection_button.pack(fill="x", pady=(0, 4), before=self.centre_button)
        chosen = bool(self.selected and self.calibration)
        for button in (self.go_button, self.lower_button, *self.pad_buttons.values(), self.reset_button):
            ui._set_button(button, arm and chosen)
        ui._set_button(self.tour_button, arm and self.calibration is not None)
        for button in (self.thicker_button, self.thinner_button, self.paper_button):
            ui._set_button(button, idle and self.calibration is not None)
        if self.calibration:
            self.thickness_text.set(f"Piece thickness {self.calibration.piece_height:.1f} mm. Picking and placing "
                                    "are the mat plus this.")
        self.reset_button.configure(state="normal" if arm and chosen and self.selected in
                                    (self.calibration.adjustments if self.calibration else {}) else "disabled")
        ui._set_button(self.pieces_button, idle and self.parked and self.p.reference is not None)
        for button in self.rest_buttons.values():
            ui._set_button(button, arm and self.calibration is not None)
        if self.calibration and self.selected:
            shift = self.calibration.adjustments.get(self.selected)
            self.adjust_text.set(f"{self.selected}: moved by {shift[0]:+.1f}, {shift[1]:+.1f}, {shift[2]:+.1f} mm."
                                 if shift else f"{self.selected}: as worked out. Nudge it if it is off.")
        else:
            self.adjust_text.set("Click a circle on the map to look at it, then nudge it if it is off centre.")

    def _refresh_extras(self):
        ui, p = self.studio, self.p
        reached = p.reference is not None
        self.jump_choice.set(f"{self.step + 1}. {STEPS[self.step]}")
        self.jump_box.configure(state="readonly" if reached and self.idle else "disabled")
        if p.setup_done and not self.return_button.winfo_ismapped():
            self.return_button.pack(side="left", padx=6)
        elif not p.setup_done:
            self.return_button.pack_forget()
        ui._set_button(self.return_button, self.idle)
        ui._set_button(self.reset_setup_button, self.idle)
        undecided = self.step == 0 and p.store.has() and not p.autosave_enabled
        if undecided and not self.saved_banner.winfo_ismapped():
            self.saved_text.set(f"A setup saved {p.store.when()} is here. Use it only if the mat, the camera and the arm's base "
                                "have not been moved.")
            self.saved_banner.pack(fill="x", pady=(0, 4), before=self.camera_row)
            if p.store.has("backup"):
                self.use_backup_button.pack(side="left")
        elif not undecided:
            self.saved_banner.pack_forget()
        self.pick_text.set(f"Pick depth {p.pick_press:+.1f} mm past the top of a piece")
        arm = self.robot_ready and self.idle
        for button in (self.deeper_button, self.shallower_button):
            ui._set_button(button, self.idle)
        ui._set_button(self.test_pick_button, arm and self.calibration is not None)

    def _words0(self):
        p = self.p
        if not p.camera:
            return ("Put the mat where the arm can reach it and the camera can see the whole of it, with all four "
                    "corner markers.", "Start the camera.", None)
        if self.view_fresh:
            where = ""
            ppmm = pixels_per_mm(p.found)
            size = f" The mat is {ppmm:.1f} pixels for every millimetre in the picture."
            if ppmm < 2.5:
                size += " That is small. Move the camera closer so the mat fills more of the picture: the X and O marks read much better at 3 or more."
            if p.found.layout is SMALL_MAT:
                where = (f" Place the Dobot facing the middle of a long edge of the sheet, with the middle of the mat about "
                         f"{SMALL_SUGGESTED_DISTANCE} mm from the arm's base, so every circle is in reach.")
            return ("The corner markers are only used to find the mat once. After the next step the camera "
                    "does not need them." + size + where, f"✔  Good to go. The {p.found.layout.label} mat is in view.",
                    "warn" if ppmm < 2.0 else True)
        return ("Move the mat and the camera until all four corner markers are in view.",
                "Looking for the four markers…", False)

    def _words1(self):
        if self.p.reference is not None:
            return ("The empty mat is captured. Go on, or capture it again if something was in the way.",
                    "✔  Empty mat captured.", True)
        return ("Clear everything off the mat, and move the Dobot's arm out of the camera's view. "
                "Then capture the empty mat.",
                "Ready to capture." if self.view_fresh else "Waiting for all four markers…", None if self.view_fresh else False)

    def _words2(self):
        if not self.robot_ready:
            return ("The arm must be connected and homed first.", "✖  The Dobot is not connected and homed.", False)
        if PARK in self.touched:
            pose = self.touched[PARK]
            return ("The centre mark is saved. Go on, or touch it again if the cup slipped.",
                    f"✔  Saved at {pose.x:.0f}, {pose.y:.0f}, {pose.z:.0f} mm.", True)
        return ("Hold the arm's button and guide the suction cup down until it just touches the mat on the small ring "
                "in the middle. Do not press. This is the height of the mat, and the arm adds the thickness of a "
                "piece itself. Keep the tool pointing straight down, then save.",
                "Touch the cup to the centre mark.", None)

    def _words3(self):
        required = self.required()
        saved = [name for name in required if name in self.touched]
        if not self.robot_ready:
            return ("The arm must be connected and homed first.", "✖  The Dobot is not connected and homed.", False)
        if self.notice:
            return ("Fix that, or move the arm by hand.", "✖  " + self.notice, False)
        if self.redo:
            return (f"Guide the cup onto the middle of the orange circle and save it. "
                    f"{describe_slot(self.p.layout, self.redo, self.p.dobot_side.get())}",
                    f"Touching {self.redo} again.", None)
        if self.calibration:
            out = self.unreachable()
            if out:
                name, reason = out[0]
                return ("Move the mat closer to the arm, or turn it, so every circle is within reach. Then touch the "
                        "centre and corner again.", f"✖  The arm cannot reach {name}. {reason}", False)
            errors, warnings = self.calibration.errors(), self.calibration.warnings()
            if errors and not self.accepted:
                return ("That looks like a slip. Click the circle on the map that you want to touch again, then save. "
                        "If the points are right, use them anyway.", "✖  " + errors[0], False)
            if errors or warnings:
                return ("That is good enough to go on with. In the next step the arm visits every circle, and you can "
                        "nudge any that are a little off.", "⚠  " + (errors + warnings)[0], "warn")
            if self.calibration.quick:
                return ("The arm has worked out where every circle is from two touches, and takes the mat as flat. "
                        "Nothing checks those two touches, so watch the next step closely. Click another corner on the "
                        "map and save it to make the fit more accurate.",
                        "✔  Quick setup done. Check every point in the next step.", True)
            return ("The arm now knows where every circle is. You can click a corner to touch it again.",
                    f"✔  All corners saved. The mat is placed to within {self.calibration.worst[1]:.1f} mm.", True)
        name = self.next_corner()
        return (f"Guide the cup onto the middle of the orange circle and save it, or press Go near and use the arrows. "
                f"The arrows move the cup as you see it on the map. {describe_slot(self.p.layout, name, self.p.dobot_side.get())}",
                f"Corner {min(self.corner, len(required) - 1) + 1} of {len(required)} ({len(saved)} saved).", None)

    def _words4(self):
        if not self.robot_ready:
            return ("The arm must be connected and homed first.", "✖  The Dobot is not connected and homed.", False)
        words = ("Press Check all points to watch the arm visit every circle. Then click a circle on the map to look "
                 "at it, lower the cup onto it, and nudge it if it is off centre.")
        if self.notice:
            return (words, "✖  " + self.notice, False)
        if self.checked:
            return (words, "✔  Every point has been visited.", True)
        return (words, "Not checked yet.", None)

    def _words5(self):
        if not self.parked:
            return ("The arm is moving to its resting place, off the mat. It waits there during a game, so keep that "
                    "area clear. The camera then notes where it is.", "Moving the arm to its resting place…", None)
        if self.reference_waiting:
            return ("The arm is at its resting place. The camera is noting it.", "Looking…", None)
        marks = [f"{len(self.p.layout.bank(mark))} {mark}" for mark in self.p.layout.reserve_marks(self.p.dobot)]
        wanted = " and ".join(marks)
        if self.pieces_ok:
            note = " " + self.grid_note if self.grid_note else ""
            if self.mark_notes:
                note += " Check: " + "; ".join(self.mark_notes[:3]) + "."
            return ("Is that what is in the banks? The camera's reading is written next to each circle. If it is right, "
                    "finish. Otherwise fix the pieces and capture again." + note + self._rest_words(),
                    f"✔  All {wanted} pieces are in place.", True)
        if self.problem:
            return ("Fix that, then capture again.", "✖  " + self.problem, False)
        if self.bank_report:
            lines = []
            for slot in self.bad_slots():
                state, mark, extra = self.bank_report[slot]
                lines.append({"empty": f"{slot} has no piece in it",
                              "wrong": f"{slot} holds {extra}, not {mark}",
                              "unreadable": f"{slot} cannot be read"}[state])
            first = self.bank_report[self.bad_slots()[0]]
            advice = {"empty": "Put a piece on every circle of both banks.",
                      "wrong": "Each bank holds only its own mark: X pieces in the X bank, O pieces in the O bank.",
                      "unreadable": "Centre the piece on its circle and keep the lighting even. "
                                    + (f"The camera says {first[2]}." if first[2] else "")}[first[0]]
            return (advice + " The grid is not checked here. Then capture again.",
                    "✖  " + "; ".join(lines[:3]) + (f"; and {len(lines) - 3} more" if len(lines) > 3 else "") + ".", False)
        return (f"Put {wanted} pieces in their banks, one on each circle, then capture. The grid is not checked here."
                + self._rest_words(), "Fill both banks, then capture.", None)

    def _rest_words(self):
        """Where the arm waits, in words: it is the area to keep clear."""
        if not self.calibration:
            return ""
        gap, near = self.calibration.rest_gap()
        tight = " That is close to the mat. Move the arm's resting place with the arrows." if gap < 15 else ""
        return (f" The arm waits {max(gap, 0):.0f} mm from {near}. Keep that area clear.{tight}")

    def _words6(self):
        return ("Everything is set up. Open the Match tab and choose New game. If the mat or the arm is ever "
                "moved, go back and run the setup again.", "✔  Ready to play.", True)
