"""The guided setup for the physical Tic-tac-toe mat.

1. Show the mat to the camera and see "Good to go".
2. Capture the empty mat, with the arm out of the camera's way.
3. Touch the arm onto the centre mark.
4. Touch the arm onto the four outer circles. That is all the arm needs: it works out the rest.
5. Watch the arm visit every point, and nudge any that are a little off.
6. Check that the camera reads some pieces.

The camera only reads pieces. Where the arm goes comes from the points it was touched on.
"""
from time import monotonic
import tkinter as tk
from tkinter import ttk

from .matcalib import MatCalibration, PARK, outer_points
from .robot import QUICK, SLOW, StopUnconfirmed
from .theme import DARK, GREEN, MUTED, PANEL, PURPLE, RED
from .tictactoe import O, UNKNOWN, X, describe_slot
from .tictactoe_vision import lock_view

STEPS = ("Show the mat", "Capture the empty mat", "Touch the centre mark", "Touch the four corners",
         "Check every point", "Check the pieces", "Ready to play")
PIECES, READY = 5, 6
NUDGES = ("0.5 mm", "1 mm", "2 mm")
THICKNESS_STEP = 0.2
# Directions as the arm sees them: x runs away from its base and y to its left.
PAD = {"forward": ("▲  Forward", (1, 0, 0)), "back": ("▼  Back", (-1, 0, 0)), "left": ("◀  Left", (0, 1, 0)),
       "right": ("Right  ▶", (0, -1, 0)), "up": ("⬆  Up", (0, 0, 1)), "down": ("⬇  Down", (0, 0, -1))}
FRESH = 0.55
AMBER = "#8a5a00"


class SetupWizard:
    def __init__(self, program, parent):
        self.p = program
        self.studio = program.studio
        self.step = 0
        self.corner = 0
        self.touched = {}
        self.calibration = None
        self.accepted = False          # the person chose to go on although a point looks far out
        self.pending = None            # the point a touch is being saved for
        self.selected = None           # the point being checked and nudged
        self.at, self.low = None, False
        self.order = []
        self.redo = None               # a corner being touched again
        self.checked = self.parked = self.pieces_ok = False
        self.unreadable, self.summary, self.problem = [], (0, 0, 0, 0), ""
        self.reference_waiting = None
        self.title, self.text, self.status = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.nudge_step = tk.StringVar(value=NUDGES[1])
        self.adjust_text = tk.StringVar()
        self.thickness_text = tk.StringVar()
        self._build(parent)

    # ---- the layout of the panel
    def _build(self, parent):
        ui = self.studio
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
        ui._label(frame, "Camera", size=9, fg=MUTED).pack(side="left")
        ttk.Entry(frame, textvariable=self.p.device, width=5).pack(side="left", padx=5)
        self.camera_button = ui._button(frame, "Start camera", self.p.toggle_camera)
        self.camera_button.pack(side="right")

    def _build_capture(self, frame):
        self.capture_button = self.studio._button(frame, "Capture empty mat", self.capture, "Purple")
        self.capture_button.pack(fill="x")

    def _build_centre(self, frame):
        self.connection_button = self.studio._button(frame, "Dobot connection…", self.p.setup_usb)
        self.centre_button = self.studio._button(frame, "Save the centre mark", self.save_centre, "Purple")
        self.centre_button.pack(fill="x")

    def _build_corners(self, frame):
        self.corner_button = self.studio._button(frame, "Save this corner", self.save_corner, "Purple")
        self.corner_button.pack(fill="x")
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
        thickness = tk.Frame(frame, bg=PANEL)
        thickness.pack(fill="x", pady=(3, 0))
        ui._label(thickness, textvariable=self.thickness_text, size=9, fg=DARK, wraplength=250,
                  justify="left").pack(side="left")
        self.thicker_button = ui._button(thickness, "+", lambda: self.change_thickness(THICKNESS_STEP))
        self.thicker_button.pack(side="right")
        self.thinner_button = ui._button(thickness, "−", lambda: self.change_thickness(-THICKNESS_STEP))
        self.thinner_button.pack(side="right", padx=(0, 4))

    def _build_pieces(self, frame):
        self.pieces_button = self.studio._button(frame, "Capture pieces", self.capture_pieces, "Purple")
        self.pieces_button.pack(fill="x")

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

    def target(self):
        """The point the map and the camera view should be pointing at."""
        if self.step == 2:
            return PARK
        if self.step == 3:
            return self.redo or self.corners()[min(self.corner, 3)]
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

    def usable(self):
        """Corners are saved and nothing is clearly wrong, or the person has chosen to go on anyway."""
        return self.calibration is not None and (not self.calibration.errors() or self.accepted)

    def use_anyway(self):
        if self.calibration is not None and self.calibration.errors():
            self.accepted = True

    def _entered(self):
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
        self._touch(self.redo or self.corners()[min(self.corner, 3)])

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
        if PARK in self.touched and all(name in self.touched for name in self.corners()):
            self.calibration = MatCalibration(self.p.layout, self.touched, old, thickness)
            self.p.poses = self.calibration.poses()

    # ---- step 5: watching the arm visit every point
    def run_check(self):
        if not (self.calibration and self.robot_ready and self.idle):
            return
        self.order = list(self.p.layout.positions)
        path = []
        if self.low and self.at:
            path.append(self.calibration.hover(self.at))
        path += [self.calibration.hover(name) for name in self.order] + [self.calibration.park()]
        offset = len(path) - len(self.order) - 1
        labels = [None] * offset + self.order + [PARK]
        events, robot = self.p.events, self.studio.robot

        def tour():
            return robot.travel(path, self.p.abort, speed=QUICK,
                                arrived=lambda index, _pose: events.put(("arrived", labels[index], None)))

        self.low = False
        self.p._job("tour", tour)

    def visit(self, lower):
        if not (self.calibration and self.selected and self.robot_ready and self.idle):
            return
        name, calibration = self.selected, self.calibration
        path = []
        if self.at and self.at != name and self.low:
            path.append(calibration.hover(self.at))
        path.append(calibration.park() if name == PARK else (calibration.pick(name) if lower else calibration.hover(name)))
        self.pending = (name, lower)
        robot = self.studio.robot
        self.p._job("visit", lambda: robot.travel(path, self.p.abort, speed=SLOW if lower else QUICK))

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
        self.p.poses = self.calibration.poses()
        self.p.setup_done = False
        self.pieces_ok = False
        self.visit(self.low) if self.selected else None

    def reset_adjustment(self):
        if self.calibration and self.selected and self.selected in self.calibration.adjustments:
            del self.calibration.adjustments[self.selected]
            self.p.poses = self.calibration.poses()
            self.visit(self.low)

    # ---- step 6: resting position and the pieces
    def _go_to_park(self):
        if not (self.calibration and self.robot_ready and self.idle):
            return
        robot, park = self.studio.robot, self.calibration.park()
        self.p._job("park", lambda: robot.travel([park], self.p.abort, speed=QUICK))

    def capture_pieces(self):
        self.pieces_ok = False
        self.problem = ""
        names = (*self.p.layout.positions,)
        latest = self.p.latest
        # A piece the camera cannot read counts as something in the way, so the view never settles.
        # Name the circle straight from the reading instead of asking for a steady view.
        if latest is not None and self.view_fresh_any() and not self.p.camera_moved \
                and UNKNOWN in (*latest.board, *latest.reserve):
            self.unreadable = [name for name, mark in zip(names, (*latest.board, *latest.reserve)) if mark == UNKNOWN]
            self.p.teaching.set(self.unreadable[0])
            self.p._draw_camera()
            return
        try:
            position = self.p._steady(min_frames=2)
        except ValueError as error:
            self.unreadable, self.problem = [], str(error)
            return
        self.unreadable = []
        self.summary = (sum(m == X for m in position.board), sum(m == O for m in position.board),
                        sum(m == X for m in position.reserve), sum(m == O for m in position.reserve))
        self.pieces_ok = sum(self.summary) > 0
        self.p._draw_camera()

    def finish(self):
        if self.pieces_ok and self.idle and self.calibration:
            self.p.finish_setup()
            self.step = READY
            self._show_step()

    # ---- results of the jobs the arm ran
    def finished(self, name, value, error):
        if error:
            self.p.status.set(str(error))
            if name in ("tour", "visit", "park") or isinstance(error, StopUnconfirmed):
                self.studio.homed = False      # after an interrupted move, home again. The setup is kept.
            return
        if name == "touch":
            self.touched[self.pending] = value
            self.redo = None
            self.corner = next((i for i, corner in enumerate(self.corners()) if corner not in self.touched), 4)
            self.accepted = False
            self.pieces_ok = False
            self.p.setup_done = False
            self._calibrate()
            if self.target():
                self.p.teaching.set(self.target())
        elif name == "tour":
            self.checked, self.at, self.low = True, PARK, False
            self.p.status.set("Every point has been visited. Click a circle on the map to look at it more closely.")
        elif name == "visit":
            self.at, self.low = self.pending[0], self.pending[1]
        elif name == "park":
            self.parked, self.at, self.low = True, PARK, False
            self.reference_waiting = monotonic() + 0.8      # let the arm settle before the camera looks
        self.p._draw_camera()

    def arrived(self, name):
        if name:
            self.p.teaching.set(name)
            self.selected = name if name != PARK else self.selected
            self.at = name
            self.p.status.set(f"Visiting {name}")
            self.p._draw_camera()

    def tick(self):
        """Take the camera's second reference once the arm has settled at Park."""
        if self.reference_waiting and monotonic() >= self.reference_waiting and self.view_fresh_any():
            self.reference_waiting = None
            import numpy as np
            self.p.reference = lock_view(np.asarray(self.p.feed), self.p.reference)
            self.p.latest, self.p.seen, self.p.view_clear = None, 0, False

    def view_fresh_any(self):
        return self.p.feed is not None and monotonic() - self.p.analysed < FRESH

    # ---- the words and the buttons
    def refresh(self):
        ui, p = self.studio, self.p
        self.tick()
        self.title.set(f"Step {self.step + 1} of {len(STEPS)} · {STEPS[self.step]}")
        text, status, ok = getattr(self, f"_words{self.step}")()
        self.text.set(text)
        self.status.set(status)
        self.status_label.configure(fg=AMBER if ok == "warn" else GREEN if ok else RED if ok is False else MUTED)
        idle = self.idle
        ui._set_button(self.back_button, idle and self.step > 0)
        self.next_button.configure(text={PIECES: "Finish setup  ▶", READY: "Go to Match  ▶"}.get(self.step, "Next  ▶"))
        ui._set_button(self.next_button, {PIECES: self.pieces_ok and idle, READY: True}.get(self.step, self._ready_to_leave()))
        ui._set_button(self.camera_button, idle)
        self.camera_button.configure(text="Stop camera" if p.camera else "Start camera")
        ui._set_button(self.capture_button, idle and self.view_fresh and not p.ready)
        arm = self.robot_ready and idle
        ui._set_button(self.centre_button, arm)
        ui._set_button(self.corner_button, arm)
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
        for button in (self.thicker_button, self.thinner_button):
            ui._set_button(button, idle and self.calibration is not None)
        if self.calibration:
            self.thickness_text.set(f"Piece thickness {self.calibration.piece_height:.1f} mm. Picking and placing "
                                    "are the mat plus this.")
        self.reset_button.configure(state="normal" if arm and chosen and self.selected in
                                    (self.calibration.adjustments if self.calibration else {}) else "disabled")
        ui._set_button(self.pieces_button, idle and self.parked and self.p.reference is not None)
        if self.calibration and self.selected:
            shift = self.calibration.adjustments.get(self.selected)
            self.adjust_text.set(f"{self.selected}: moved by {shift[0]:+.1f}, {shift[1]:+.1f}, {shift[2]:+.1f} mm."
                                 if shift else f"{self.selected}: as worked out. Nudge it if it is off.")
        else:
            self.adjust_text.set("Click a circle on the map to look at it, then nudge it if it is off centre.")

    def _words0(self):
        p = self.p
        if not p.camera:
            return ("Put the mat where the arm can reach it and the camera can see the whole of it, with all four "
                    "corner markers.", "Start the camera.", None)
        if self.view_fresh:
            return ("The corner markers are only used to find the mat once. After the next step the camera "
                    "does not need them.", f"✔  Good to go. The {p.found.layout.label} mat is in view.", True)
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
        corners = self.corners()
        saved = [name for name in corners if name in self.touched]
        if not self.robot_ready:
            return ("The arm must be connected and homed first.", "✖  The Dobot is not connected and homed.", False)
        if self.redo:
            return (f"Guide the cup onto the middle of the orange circle and save it. "
                    f"{describe_slot(self.p.layout, self.redo, self.p.dobot_side.get())}",
                    f"Touching {self.redo} again.", None)
        if self.calibration:
            errors, warnings = self.calibration.errors(), self.calibration.warnings()
            if errors and not self.accepted:
                return ("That looks like a slip. Click the circle on the map that you want to touch again, then save. "
                        "If the points are right, use them anyway.", "✖  " + errors[0], False)
            if errors or warnings:
                return ("That is good enough to go on with. In the next step the arm visits every circle, and you can "
                        "nudge any that are a little off.", "⚠  " + (errors + warnings)[0], "warn")
            return ("The arm now knows where every circle is. You can click a corner to touch it again.",
                    f"✔  All four corners saved. The mat is placed to within {self.calibration.worst[1]:.1f} mm.", True)
        name = corners[self.corner]
        return (f"Guide the cup onto the middle of the orange circle and save it. {describe_slot(self.p.layout, name, self.p.dobot_side.get())}",
                f"Corner {self.corner + 1} of 4 ({len(saved)} saved).", None)

    def _words4(self):
        if not self.robot_ready:
            return ("The arm must be connected and homed first.", "✖  The Dobot is not connected and homed.", False)
        words = ("Press Check all points to watch the arm visit every circle. Then click a circle on the map to look "
                 "at it, lower the cup onto it, and nudge it if it is off centre.")
        if self.checked:
            return (words, "✔  Every point has been visited.", True)
        return (words, "Not checked yet.", None)

    def _words5(self):
        if not self.parked:
            return ("The arm is moving to its resting place (Park). The camera then notes where it is, so it is "
                    "not mistaken for something in the way.", "Moving the arm to Park…", None)
        if self.reference_waiting:
            return ("The arm is at Park. The camera is noting it.", "Looking…", None)
        if self.pieces_ok:
            x, o, rx, ro = self.summary
            return ("Is that what is on the mat? The camera's reading is written next to each circle. If it is right, "
                    "finish. Otherwise fix the pieces and capture again.",
                    f"✔  I can see {x} X and {o} O on the board, and {rx} X and {ro} O in the banks.", True)
        if self.problem:
            return ("Fix that, then capture again.", "✖  " + self.problem, False)
        if self.unreadable:
            return ("Centre each piece on its circle and keep the lighting even, then capture again.",
                    "✖  I cannot read " + ", ".join(self.unreadable[:6]) + ".", False)
        if self.summary != (0, 0, 0, 0):
            return ("There are no pieces on the mat. Put some X and O pieces in the cells and in both banks, then "
                    "capture.", "✖  I cannot see any pieces.", False)
        return ("Put some X and O pieces on the mat, in the cells and in both banks, then capture.",
                "Place a few pieces, then capture.", None)

    def _words6(self):
        return ("Everything is set up. Open the Match tab and choose New game. If the mat or the arm is ever "
                "moved, go back and run the setup again.", "✔  Ready to play.", True)
