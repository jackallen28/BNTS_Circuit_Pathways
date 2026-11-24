"""A camera-verified physical game and a screen-only demo."""
from math import dist
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from .theme import DARK, MUTED, PANEL, PURPLE, WHITE
from .tictactoe import (
    CELLS, EMPTY, HARD, LEVELS, O, STANDARD_MAT, TEACH_ORDER, UNKNOWN, X,
    human_change, outcome, robot_move, tidy_plan, winning_line, with_move,
)
from .tictactoe_vision import DENSITY, Position, mat_clear, read_position, rectify
from .vision import Camera, TABLETOP

TURN_DELAY = 1.5
VIEW_TIMEOUT = 0.55


class TurnDelay:
    """Time an unchanged position using consecutive clear camera observations."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.position = None
        self.since = self.last = 0.0

    def remaining(self, position, timestamp):
        if position != self.position or timestamp - self.last > VIEW_TIMEOUT:
            self.position = position
            self.since = timestamp
        self.last = timestamp
        return TURN_DELAY - (timestamp - self.since)


class TicTacToeProgram:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root, bg="#e9eff8", padx=10, pady=10)
        self.window.title("Tic-tac-toe")
        self.window.transient(studio.root)
        self.window.geometry(f"{min(1050, studio.root.winfo_screenwidth()-32)}x"
                             f"{min(680, studio.root.winfo_screenheight()-54)}")
        self.window.minsize(810, 525)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.stop())

        self.device = tk.StringVar(value=studio.camera_device.get())
        self.teaching = tk.StringVar(value=TEACH_ORDER[0])
        self.status = tk.StringVar()
        self.detail = tk.StringVar()
        self.camera_status = tk.StringVar(value="Camera offline")
        self.board = EMPTY
        self.turn = X
        self.human = X
        self.player_choice = tk.StringVar(value=X)
        self.roles = tk.StringVar()
        self.ready = studio.demo
        self.auto_reset = tk.BooleanVar(value=True)
        # The chosen difficulty is kept for the session, so reopening the program remembers it.
        self.level = tk.StringVar(value=getattr(studio, "tictactoe_level", HARD))
        self.level.trace_add("write", lambda *_: setattr(studio, "tictactoe_level", self.level.get()))
        # Resetting: waiting for a still, clear mat (pending), then returning pieces one at a time.
        self.tidy_pending = self.tidying = False
        self.tidy, self.tidy_left = [], 0
        self.poses = {}
        self.reference = self.rectified = self.feed = self.photo = None
        self.latest = self.chosen = self.checking = None
        self.view_clear = False
        self.turn_delay = TurnDelay()
        self.seen = 0
        self.timestamp = self.analysed = self.deadline = 0
        self.camera = self.busy = self.demo_timer = None
        self.camera_epoch = 0
        self.events = SimpleQueue()
        self.abort = Event()

        self._build()
        self.status.set("Your turn. Pick an empty cell." if studio.demo else
                        "Start the camera, capture the empty mat and teach the tool positions.")
        self._render()
        self.window.after(65, self._tick)

    def _build(self):
        ui = self.studio
        header = tk.Frame(self.window, bg="#dce9f6", padx=11, pady=6)
        header.pack(fill="x", pady=(0, 7))
        ui._label(header, "Tic-tac-toe", size=16, fg=PURPLE, weight="bold",
                  bg="#dce9f6").pack(side="left")
        ui._label(header, "DEMO" if ui.demo else "USB SUCTION", size=9,
                  fg=MUTED, bg="#dce9f6").pack(side="left", padx=8)
        ui._button(header, "Done", self.close).pack(side="right")
        if ui.demo:
            ui._button(header, "Set up USB arm", self.setup_usb).pack(side="right", padx=5)

        main = tk.Frame(self.window, bg="#e9eff8")
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        self.views = ttk.Notebook(main)
        self.views.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        game = tk.Frame(self.views, bg=DARK)
        self.game = tk.Canvas(game, width=405, height=330, bg=DARK, highlightthickness=0)
        self.game.pack(fill="both", expand=True)
        self.game.bind("<Configure>", lambda _event: self._draw_game())
        self.game.bind("<Button-1>", self._click_game)
        self.views.add(game, text="Game board")

        if not ui.demo:
            overhead = tk.Frame(self.views, bg=DARK)
            self.preview = tk.Canvas(overhead, bg=DARK, highlightthickness=0)
            self.preview.pack(fill="both", expand=True)
            self.preview.bind("<Configure>", lambda _event: self._draw_camera())
            self.views.add(overhead, text="Overhead camera")
            self.views.select(overhead)

        panels = tk.Frame(main, bg="#e9eff8")
        panels.grid(row=0, column=1, sticky="nsew")
        if not ui.demo:
            pane, body = ui._pane(panels, "Mat and suction setup")
            pane.pack(fill="x", pady=(0, 7))
            line = tk.Frame(body, bg=PANEL)
            line.pack(fill="x", pady=(2, 4))
            ui._label(line, "Camera", size=9, fg=MUTED).pack(side="left")
            ttk.Entry(line, textvariable=self.device, width=6).pack(side="left", padx=5)
            self.camera_button = ui._button(line, "Start camera", self.toggle_camera)
            self.camera_button.pack(side="right")
            self.empty_button = ui._button(body, "Capture empty mat", self.capture_empty, "Purple")
            self.empty_button.pack(fill="x", pady=(0, 5))
            select = tk.Frame(body, bg=PANEL)
            select.pack(fill="x", pady=(0, 4))
            self.slot_picker = ttk.Combobox(select, textvariable=self.teaching, values=TEACH_ORDER,
                                            state="readonly", width=11)
            self.slot_picker.pack(side="left")
            self.slot_picker.bind("<<ComboboxSelected>>", lambda _event: self._draw_camera())
            self.teach_button = ui._button(select, "Teach tool position", self.teach)
            self.teach_button.pack(side="right", padx=(4, 0))
            ui._label(body, textvariable=self.camera_status, size=9, fg=MUTED, wraplength=245,
                      justify="left").pack(fill="x", pady=(4, 0))

        pane, body = ui._pane(panels, "Match")
        pane.pack(fill="x", pady=(0, 7))
        choose = tk.Frame(body, bg=PANEL)
        choose.pack(fill="x", pady=(0, 5))
        ui._label(choose, "Play as", size=9, fg=MUTED).pack(side="left")
        self.symbol_picker = ttk.Combobox(choose, textvariable=self.player_choice, values=(X, O),
                                          state="readonly", width=4)
        self.symbol_picker.pack(side="right")
        self.symbol_picker.bind("<<ComboboxSelected>>", self._pick_symbol)
        level = tk.Frame(body, bg=PANEL)
        level.pack(fill="x", pady=(0, 5))
        ui._label(level, "Dobot difficulty", size=9, fg=MUTED).pack(side="left")
        self.level_picker = ttk.Combobox(level, textvariable=self.level, values=LEVELS,
                                         state="readonly", width=7)
        self.level_picker.pack(side="right")
        ui._label(body, textvariable=self.roles, size=10, weight="bold",
                  fg=PURPLE).pack(fill="x")
        ui._label(body, textvariable=self.detail, size=9, fg=MUTED, wraplength=245,
                  justify="left").pack(fill="x", pady=(5, 6))
        self.new_button = ui._button(body, "New game", self.new_game)
        self.new_button.pack(fill="x")
        self.reset_button = ui._button(body, "Reset board", self.reset_board)
        self.reset_button.pack(fill="x", pady=(5, 0))
        tk.Checkbutton(body, text="Reset the board after each game", variable=self.auto_reset,
                       bg=PANEL, activebackground=PANEL, fg=DARK, font=ui.theme.font(9),
                       anchor="w", borderwidth=0, highlightthickness=0).pack(fill="x", pady=(6, 0))
        if not ui.demo:
            self.release_button = ui._button(body, "Release suction", self.release)
            self.release_button.pack(fill="x", pady=(5, 0))

        footer = tk.Frame(self.window, bg="#dce9f6", padx=8, pady=4)
        footer.pack(fill="x", pady=(6, 0))
        ui._label(footer, textvariable=self.status, size=9, bg="#dce9f6", wraplength=680,
                  justify="left").pack(side="left", fill="x", expand=True)
        self.stop_button = ui._button(footer, "Stop  ·  Esc", self.stop, "Stop")
        self.stop_button.pack(side="right")

    @property
    def dobot(self):
        return O if self.human == X else X

    @property
    def layout(self):
        view = self.reference or self.rectified
        return view.layout if view is not None else STANDARD_MAT

    @property
    def teach_order(self):
        return (*self.layout.positions, "Park")

    def _pick_symbol(self, _event=None):
        if self.studio.demo and self.board == EMPTY:
            self.new_game()
        self._render()

    def setup_usb(self):
        self.close()
        if self.studio.workcell is None:
            self.studio.set_mode(False)
            self.studio.status_text.set("Connect and home the arm, then reopen Tic-tac-toe.")

    def _job(self, name, action):
        if self.busy:
            return
        self.busy = name
        self.abort.clear()

        def run():
            try:
                self.events.put((name, action(), None))
            except Exception as error:
                self.events.put((name, None, error))

        Thread(target=run, name=f"tictactoe-{name}", daemon=True).start()
        self._render()

    def toggle_camera(self):
        if self.busy or self.checking:
            return
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
            self.camera_epoch += 1
            self.camera = self.feed = self.rectified = self.latest = None
            self.ready = False
            self.view_clear = False
            self.turn_delay.reset()
            self.camera_status.set("Camera stopped. Resume with a new game.")
        elif self.device.get().strip() and not self.studio.camera_closing:
            self.camera_epoch += 1
            epoch = self.camera_epoch
            self.camera = Camera(self.device.get().strip(), TABLETOP, self.studio.models,
                                 lambda error: self.events.put(("camera", epoch, error)))
            self.timestamp = self.analysed = 0
            self.camera_status.set("Opening the overhead camera…")
        self._render()
        self._draw_camera()

    def capture_empty(self):
        if self.busy or self.checking or self.ready:
            return
        if self.rectified is None or monotonic() - self.analysed > VIEW_TIMEOUT:
            self.status.set("Wait until all four markers are visible.")
            return
        if not messagebox.askokcancel("Capture the empty mat", "Remove all pieces and take your hands off the mat. "
                                      "For play, capture the mat with the tool at Park.", parent=self.window):
            return
        if self.rectified is None or monotonic() - self.analysed > VIEW_TIMEOUT:
            self.status.set("Show all four mat markers again.")
            return
        if self.reference is None or self._shifted(self.rectified):
            self.poses.clear()
        self.reference = self.rectified
        self.latest = None
        self.view_clear = False
        self.seen = 0
        if all(place in self.poses for place in self.teach_order):
            self.status.set("Empty mat captured. Load the reserves and start a new game.")
        else:
            self.status.set("Empty mat captured. Teach each centre with a sample playing piece.")
        self._render()

    def _shifted(self, view):
        import numpy as np

        return (view.layout is not self.reference.layout or view.shape != self.reference.shape
                or np.linalg.norm(view.corners - self.reference.corners, axis=1).max() > 2.0)

    def teach(self):
        if self.busy or self.checking or self.ready or not self.studio.robot or not self.studio.homed:
            return
        if (self.reference is None or self.rectified is None or monotonic()-self.analysed > VIEW_TIMEOUT
                or self._shifted(self.rectified)):
            self.status.set("Capture the empty mat with the camera and mat fixed in place.")
            return
        name, reference = self.teaching.get(), self.reference
        self._job("teach", lambda: (reference, name, self.studio.robot.pose()))

    def _check_setup(self):
        if not self.studio.robot or not self.studio.homed:
            raise ValueError("Connect and home the Dobot first.")
        if self.reference is None or not all(place in self.poses for place in self.teach_order):
            raise ValueError("Capture the empty mat and teach every cell, reserve slot and Park.")
        layout = self.reference.layout
        positions = layout.positions
        park = self.poses["Park"]
        points = list(positions)
        for i, first in enumerate(points):
            pose = self.poses[first]
            for second in points[i+1:]:
                other = self.poses[second]
                actual = dist((pose.x, pose.y), (other.x, other.y))
                expected = dist(positions[first], positions[second])
                if abs(actual - expected) > 7 or abs(pose.z - other.z) > 3:
                    raise ValueError(f"Check the taught centres and piece height at {first} and {second}.")
            if not 12 <= park.z - pose.z <= 75 or abs(park.r - pose.r) > 5:
                raise ValueError("Teach Park above the playing surface with the same tool rotation.")
            if dist((pose.x, pose.y), (park.x, park.y)) > layout.park_limit:
                raise ValueError("Teach Park above the small ring so the tool can reach the cells and reserves.")

    def _steady(self, robot_mark=None, *, min_frames=2):
        if self.latest is None or self.seen < min_frames or monotonic() - self.analysed > VIEW_TIMEOUT:
            raise ValueError("Wait for a steady view of the entire mat.")
        if not self.view_clear:
            raise ValueError("Move hands and loose items off the mat. Keep the tool at Park.")
        if UNKNOWN in self.latest.board:
            raise ValueError("Centre each piece on its circle and check the camera contrast.")
        reserve = dict(zip(self.layout.reserve, self.latest.reserve))
        for mark in self.layout.reserve_marks(robot_mark or self.dobot):
            if any(reserve[name] not in ("", mark) for name in self.layout.bank(mark)):
                raise ValueError(f"Keep only {mark} pieces in the matching reserve slots.")
        return self.latest

    def new_game(self):
        if (self.busy or self.checking or self.tidy_pending or self.tidying
                or (self.ready and not self.studio.demo)):
            return
        human = self.player_choice.get()
        robot = O if human == X else X
        if not self.studio.demo:
            try:
                self._check_setup()
                position = self._steady(robot)
                if position.board != EMPTY:
                    raise ValueError("Clear the board before starting a new game.")
                reserve = dict(zip(self.layout.reserve, position.reserve))
                for mark in self.layout.reserve_marks(robot):
                    count = 5 if mark == X else 4
                    if sum(reserve[name] == mark for name in self.layout.bank(mark)) < count:
                        raise ValueError(f"Load at least {count} {mark} pieces in their reserve slots.")
            except ValueError as error:
                self.status.set(str(error))
                return
        self.human = human
        self.turn_delay.reset()
        self.board, self.turn, self.chosen, self.ready = EMPTY, X, None, True
        if self.turn == self.dobot:
            self._plan_reply("Dobot opens.")
        else:
            self.status.set("Your turn. Place one cross in an empty cell.")
        self._render()

    def _automatic_turn(self):
        try:
            position = self._steady(min_frames=1)
            player_turn = self.turn == self.human
            if player_turn and position.board == self.board:
                self.turn_delay.reset()
                self.status.set(f"Your turn. Place one {self.human} piece in an empty cell.")
                return
            if player_turn:
                player_cell = human_change(self.board, position.board, self.human)
            elif position.board != self.board:
                raise ValueError("Keep the board still while the Dobot is taking its turn.")
            remaining = self.turn_delay.remaining(position, self.analysed)
            if remaining > 0:
                self.status.set(f"Mat clear. Confirming the position in {remaining:.1f} s. Keep hands clear.")
                return
            self.turn_delay.reset()
            if player_turn:
                self.board = position.board
                self._after_player(player_cell)
            if self.ready:
                self._place_piece(position)
        except ValueError as error:
            self.turn_delay.reset()
            self.status.set(str(error))

    def _place_piece(self, position):
        self._check_setup()
        reserve = dict(zip(self.layout.reserve, position.reserve))
        source = next((name for name in self.layout.bank(self.dobot) if reserve[name] == self.dobot), None)
        if source is None:
            raise ValueError(f"Load a {self.dobot} piece into its reserve slots.")
        target = self.chosen
        index = self.layout.reserve.index(source)
        expected = Position(with_move(position.board, target, self.dobot),
                            (*position.reserve[:index], "", *position.reserve[index + 1:]))
        pick, drop, park = (self.poses[place] for place in (source, CELLS[target], "Park"))
        self.status.set(f"Moving {self.dobot} to {CELLS[target]}… Keep hands clear.")
        self._job("place", lambda: (expected, self.studio.robot.sort_chip(
            pick, drop, park, self.abort, via_park=True)))

    def _after_player(self, index):
        if outcome(self.board):
            self._announce()
        else:
            self._plan_reply(f"{self.human} at {CELLS[index]}.")
        self._render()

    def _plan_reply(self, message):
        self.turn = self.dobot
        self.chosen = robot_move(self.board, self.dobot, self.level.get())
        self.status.set(f"{message} Dobot chose {CELLS[self.chosen]}.")
        if self.studio.demo:
            self.busy = "demo"
            self.demo_timer = self.window.after(420, self._demo_move)

    def _click_game(self, event):
        if (not self.studio.demo or self.busy or not self.ready or self.turn != self.human
                or outcome(self.board)):
            return
        left, top, size = self._grid()
        x, y = event.x-left, event.y-top
        if not (0 <= x < size and 0 <= y < size):
            return
        index = int(y/(size/3))*3 + int(x/(size/3))
        if self.board[index]:
            return
        self.board = with_move(self.board, index, self.human)
        self._after_player(index)

    def _demo_move(self):
        self.demo_timer = None
        if self.busy == "demo":
            self.busy = None
            self.board = with_move(self.board, self.chosen, self.dobot)
            self._after_dobot()

    def _after_dobot(self):
        target, self.chosen = self.chosen, None
        self.turn = self.human
        if outcome(self.board):
            self._announce()
        else:
            self.status.set(f"Dobot placed {self.dobot} at {CELLS[target]}. Your turn.")
        self._render()

    def _announce(self):
        result = outcome(self.board)
        if result is not None:
            self.ready = False
            message = {self.human: "You won.", self.dobot: "Dobot won.", "Draw": "Draw."}[result]
            self.status.set(message + " Play again with a clear board.")
            if self.auto_reset.get():
                self._start_reset(message)

    def reset_board(self):
        if not self.ready and not self.busy and not self.checking:
            self._start_reset()

    def _start_reset(self, prefix=""):
        """Have the Dobot return every piece it can to the reserve slots."""
        if self.ready or self.busy or self.checking or self.tidy_pending or self.tidying:
            return
        lead = prefix + " " if prefix else ""
        if self.studio.demo:
            if any(self.board):
                self.tidying = True
                self.busy = "demo"
                self.status.set(lead + "Dobot is clearing the board…")
                self.demo_timer = self.window.after(1500, self._demo_clear)
            else:
                self.status.set("The board is already clear.")
            return
        self.tidy_pending = True
        self.turn_delay.reset()
        self.status.set(lead + "Resetting the board once the mat is clear. Keep hands clear.")

    def _demo_clear(self):
        self.demo_timer = None
        if self.busy != "demo" or not self.tidying:
            return
        index = next((cell for cell, piece in enumerate(self.board) if piece), None)
        if index is not None:
            self.board = with_move(self.board, index, "")
        if any(self.board):
            self.demo_timer = self.window.after(380, self._demo_clear)
        else:
            self.busy, self.tidying, self.chosen = None, False, None
            self.status.set("Board reset. Choose New game to play again.")
        self._render()

    def _cancel_tidy(self):
        self.tidy_pending = self.tidying = False
        self.tidy = []

    def _automatic_tidy(self):
        try:
            position = self._steady(min_frames=1)
            remaining = self.turn_delay.remaining(position, self.analysed)
            if remaining > 0:
                self.status.set(f"Mat clear. Resetting the board in {remaining:.1f} s. Keep hands clear.")
                return
        except ValueError as error:
            self.turn_delay.reset()
            self.status.set(str(error))
            return
        self.turn_delay.reset()
        try:
            self._check_setup()
            moves, left = tidy_plan(self.layout, position.board, position.reserve, self.dobot)
        except ValueError as error:
            self._cancel_tidy()
            self.status.set(str(error))
            return
        self.tidy_pending = False
        self.tidy, self.tidy_left = moves, left
        self.board = position.board
        self.tidying = True
        self._tidy_next()

    def _tidy_next(self):
        position = self.latest
        if self.tidy:
            try:
                self._check_setup()
                self._tidy_step(position)
            except ValueError as error:
                self._cancel_tidy()
                self.status.set(str(error))
            return
        self.tidying = False
        note = ""
        if self.tidy_left:
            plural = "s" if self.tidy_left != 1 else ""
            note = f" Take your {self.tidy_left} piece{plural} off the mat."
        self.status.set("Board reset." + note + " Check the reserves, then choose New game.")

    def _tidy_step(self, position):
        cell, mark, slot = self.tidy.pop(0)
        index = self.layout.reserve.index(slot)
        expected = Position(with_move(position.board, cell, ""),
                            (*position.reserve[:index], mark, *position.reserve[index + 1:]))
        pick, drop, park = (self.poses[place] for place in (CELLS[cell], slot, "Park"))
        self.status.set(f"Returning {mark} from {CELLS[cell]} to {slot}… Keep hands clear.")
        self._job("place", lambda: (expected, self.studio.robot.sort_chip(
            pick, drop, park, self.abort, via_park=True)))

    def release(self):
        if self.ready or self.busy or self.checking or not self.studio.robot:
            return
        if messagebox.askokcancel("Release suction", "Support any piece on the cup before releasing it.",
                                  parent=self.window):
            self._job("release", lambda: self.studio.robot.set_suction(False))

    def stop(self):
        self.ready = False
        self.checking = None
        self._cancel_tidy()
        self.turn_delay.reset()
        if self.busy == "demo":
            self.window.after_cancel(self.demo_timer)
            self.demo_timer = self.busy = None
        elif self.busy == "place":
            self.abort.set()
            self.studio.homed = False
            self.studio.points.clear()
        self.status.set("Game stopped. Check the mat before starting a new game.")
        self._render()

    def _read_frame(self, sample, image):
        import numpy as np

        self.feed = image
        self.timestamp = sample.timestamp
        if sample.timestamp - self.analysed < 0.15:
            return False
        self.analysed = sample.timestamp
        try:
            self.rectified = rectify(np.asarray(image))
            view = self.rectified
            if self.reference is None:
                self.camera_status.set(f"{view.layout.label} mat found. Capture it while empty.")
            elif self._shifted(view):
                raise ValueError("The mat or camera moved. Re-register the empty mat.")
            else:
                position = read_position(view.grey, self.reference.grey, view.layout)
                clear = self.busy != "place" and mat_clear(view, self.reference, position)
                self.seen = self.seen+1 if position == self.latest and clear and self.view_clear else 1
                self.view_clear = clear
                self.latest = position
                self.camera_status.set(f"{view.layout.label} mat · {sum(bool(piece) for piece in position.reserve)} in reserve")
        except (ImportError, ValueError) as error:
            if self.rectified is not None and self.reference is not None and self._shifted(self.rectified):
                self.stop()
                self.reference = self.rectified = None
                self.poses.clear()
                self.status.set("The registered mat moved. Capture it again and re-teach the tool.")
            else:
                self.rectified = None
            self.latest = None
            self.seen = 0
            self.view_clear = False
            self.camera_status.set(str(error))
        self._draw_camera()
        return True

    def _tick(self):
        while True:
            try:
                name, value, error = self.events.get_nowait()
            except Empty:
                break
            if name == "camera":
                if value == self.camera_epoch:
                    self.stop()
                    self.camera_status.set(str(error))
                    if self.camera:
                        self.studio.camera_closing = self.camera
                    self.camera = self.feed = self.latest = self.rectified = None
                    self.view_clear = False
                    self._draw_camera()
                continue
            self.busy = None
            if error:
                if name == "place":
                    self.ready = self.studio.homed = False
                    self.studio.points.clear()
                    self._cancel_tidy()
                self.status.set(str(error))
            elif name == "teach":
                reference, place, pose = value
                if reference is self.reference:
                    self.poses[place] = pose
                    order = self.teach_order
                    following = order[(order.index(place)+1) % len(order)]
                    self.teaching.set(following)
                    self.status.set(f"{place} taught. Next: {following}.")
            elif name == "place" and (self.ready or self.tidying):
                self.checking, self.studio.position = value
                self.deadline = monotonic() + 3.5
                self.seen = 0
                self.status.set(f"Checking where {self.dobot} landed…")
            elif name == "release":
                self.status.set("Suction release acknowledged.")

        updated = False
        if self.camera:
            sample = self.camera.read()
            if sample and sample[0].timestamp > self.timestamp:
                updated = self._read_frame(*sample)
        now = monotonic()
        stale = now - self.analysed > VIEW_TIMEOUT
        if self.busy == "place" and not self.abort.is_set() and now - self.timestamp > 0.85:
            self.stop()
            self.status.set("Camera stalled. Stopping the transfer.")
        if self.checking:
            if now > self.deadline:
                self.checking = None
                self.ready = False
                resetting, self.tidying = self.tidying, False
                self._cancel_tidy()
                self.status.set("The piece move was not confirmed. Check the mat, then choose Reset board."
                                if resetting else
                                "Placement was not confirmed. Check the piece and clear the mat for a new game.")
            elif not stale and self.view_clear and self.seen >= 2 and self.latest == self.checking:
                self.board = self.checking.board
                self.checking = None
                if self.tidying:
                    self._tidy_next()
                else:
                    self._after_dobot()
        elif self.ready and not self.busy and not self.studio.demo:
            if stale:
                self.turn_delay.reset()
                self.status.set("Waiting for a fresh overhead camera view.")
            elif updated:
                self._automatic_turn()
        elif self.tidy_pending and not self.busy and not self.studio.demo:
            if stale:
                self.turn_delay.reset()
                self.status.set("Waiting for a fresh overhead camera view.")
            elif updated:
                self._automatic_tidy()
        self._render()
        self.window.after(65, self._tick)

    def _render(self):
        ui = self.studio
        idle = not self.busy and self.checking is None
        player = self.human if self.ready else self.player_choice.get()
        self.roles.set(f"You play {player}. Dobot plays {O if player == X else X}.")
        can_choose = not self.ready or (ui.demo and self.board == EMPTY)
        resetting = self.tidy_pending or self.tidying
        self.symbol_picker.configure(state="readonly" if idle and can_choose and not resetting else "disabled")
        self.level_picker.configure(state="readonly" if idle and not resetting else "disabled")
        if ui.demo:
            self.detail.set("Select an empty cell on the blue board. Dobot replies automatically.")
        else:
            order = self.teach_order
            self.detail.set("Place one piece and take your hand away. Dobot replies after 1.5 clear seconds."
                            if self.ready else f"{len(self.poses)}/{len(order)} tool positions taught. "
                            "Capture the mat empty before loading the reserves.")
            self.camera_button.configure(text="Stop camera" if self.camera else "Start camera")
            self.slot_picker.configure(values=order, state="readonly" if idle and not self.ready else "disabled")
            if self.teaching.get() not in order:
                self.teaching.set(order[0])
            ui._set_button(self.camera_button, idle)
            ui._set_button(self.empty_button, idle and not self.ready and self.rectified is not None)
            ui._set_button(self.teach_button, idle and not self.ready and ui.homed and self.reference is not None)
            ui._set_button(self.release_button, idle and not self.ready and ui.robot is not None)
        ui._set_button(self.new_button, idle and (ui.demo or not self.ready) and not resetting)
        can_reset = any(self.board) if ui.demo else ui.homed and self.reference is not None
        ui._set_button(self.reset_button, idle and not self.ready and not resetting and can_reset)
        ui._set_button(self.stop_button, self.ready or not idle or self.tidy_pending)
        self._draw_game()

    def _grid(self):
        w, h = self.game.winfo_width(), self.game.winfo_height()
        size = max(1, min(w - 56, h - 96))
        return (w-size)/2, (h-size)/2, size

    def _draw_game(self):
        canvas = self.game
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if min(w, h) < 10:
            return
        canvas.delete("all")
        left, top, size = self._grid()
        step = size/3
        tl, br = (left, top), (left+size, top+size)
        canvas.create_rectangle(*tl, *br, fill="#192c48", outline="#5891a4", width=2)
        line = winning_line(self.board)
        for index, value in enumerate(self.board):
            row, col = divmod(index, 3)
            x, y = left+col*step, top+row*step
            highlight = index in line or index == self.chosen and self.ready
            canvas.create_rectangle(x+3, y+3, x+step-3, y+step-3, width=1,
                                    outline="#7fccc9" if highlight else "#425d7a",
                                    fill="#245665" if highlight else "#203855")
            canvas.create_text(x+10, y+8, text=CELLS[index], fill="#a2bcd3", anchor="nw",
                               font=self.studio.theme.font(9))
            if value or highlight:
                shown = value or self.dobot
                canvas.create_text(x+step/2, y+step/2, text=shown,
                                   fill=("#ffd997" if shown == X else "#8decdf") if value else "#6ca1ad",
                                   font=self.studio.theme.font(max(14, round(step*0.41)), "bold"))
        status = "Your turn" if self.turn == self.human else "Dobot’s turn"
        if self.tidy_pending or self.tidying:
            status = "Dobot is clearing the board"
        elif not self.ready:
            status = {self.human: "You won", self.dobot: "Dobot won", "Draw": "Draw"}.get(
                outcome(self.board), "Start a new game")
        canvas.create_text(w/2, top/2, text=status,
                           fill=WHITE, font=self.studio.theme.font(14, "bold"))
        canvas.create_text(w/2, min(h-14, top+size+23), text=f"{self.human} · player     {self.dobot} · Dobot",
                           fill="#acc9dd", font=self.studio.theme.font(10))

    def _draw_camera(self):
        if self.studio.demo:
            return
        canvas = self.preview
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if min(w, h) < 10:
            return
        canvas.delete("all")
        if self.feed is None:
            canvas.create_text(w/2, h/2, text="Start the overhead camera", fill=WHITE)
            return
        from PIL import Image, ImageTk

        image = self.feed.copy()
        image.thumbnail((w, h), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        left, top = (w-image.width)/2, (h-image.height)/2
        canvas.create_image(left, top, image=self.photo, anchor="nw")
        if self.rectified is not None:
            import cv2
            import numpy as np

            view = self.rectified
            inverse = np.linalg.inv(view.matrix)
            positions = view.layout.positions
            xy = np.array(tuple(positions.values()), dtype=np.float32)[None] * DENSITY
            frame_points = cv2.perspectiveTransform(xy, inverse)[0]
            readings = (*self.latest.board, *self.latest.reserve) if self.latest else ("",)*len(positions)
            for label, (x, y), value in zip(positions, frame_points, readings):
                sx, sy = left+x*image.width/self.feed.width, top+y*image.height/self.feed.height
                tint = "#ffd997" if label == self.teaching.get() and not self.ready else "#9cebe3"
                canvas.create_oval(sx-4, sy-4, sx+4, sy+4, outline=tint, width=2)
                name = label.replace("Reserve ", "R")
                canvas.create_text(sx+7, sy-9, text=f"{name} {value}", fill=tint,
                                   anchor="sw", font=self.studio.theme.font(8, "bold"))

    def close(self):
        if self.busy or self.checking:
            self.stop()
            return
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
        self.window.destroy()
        self.studio.end_workcell()
