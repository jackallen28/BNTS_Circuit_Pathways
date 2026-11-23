"""A camera-verified physical game and a screen-only demo."""
from math import dist
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from .theme import DARK, MUTED, PANEL, PURPLE, WHITE
from .tictactoe import (
    BANK, CELLS, EMPTY, MAT_POSITIONS, O, TEACH_ORDER, UNKNOWN, X,
    human_change, outcome, robot_move, winning_line, with_move,
)
from .tictactoe_vision import DENSITY, Position, Reference, read_position, rectify
from .vision import Camera, TABLETOP


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
        self.ready = studio.demo
        self.poses = {}
        self.reference = self.rectified = self.feed = self.photo = None
        self.latest = self.chosen = self.checking = None
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
        ui._label(body, "You play X. Dobot plays O.", size=10, weight="bold",
                  fg=PURPLE).pack(fill="x")
        ui._label(body, textvariable=self.detail, size=9, fg=MUTED, wraplength=245,
                  justify="left").pack(fill="x", pady=(5, 6))
        if not ui.demo:
            self.turn_button = ui._button(body, "Read my cross", self.advance, "Teal")
            self.turn_button.pack(fill="x", pady=(0, 5))
        self.new_button = ui._button(body, "New game", self.new_game)
        self.new_button.pack(fill="x")
        if not ui.demo:
            self.release_button = ui._button(body, "Release suction", self.release)
            self.release_button.pack(fill="x", pady=(5, 0))

        footer = tk.Frame(self.window, bg="#dce9f6", padx=8, pady=4)
        footer.pack(fill="x", pady=(6, 0))
        ui._label(footer, textvariable=self.status, size=9, bg="#dce9f6", wraplength=680,
                  justify="left").pack(side="left", fill="x", expand=True)
        self.stop_button = ui._button(footer, "Stop  ·  Esc", self.stop, "Stop")
        self.stop_button.pack(side="right")

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
        if self.rectified is None or monotonic() - self.analysed > 0.55:
            self.status.set("Wait until all four markers are visible.")
            return
        if not messagebox.askokcancel("Capture the empty mat", "Remove every piece from the board and reserve slots.",
                                      parent=self.window):
            return
        if self.rectified is None or monotonic() - self.analysed > 0.55:
            self.status.set("Show all four mat markers again.")
            return
        corners, grey, _ = self.rectified
        if self.reference is None or self._shifted(corners):
            self.poses.clear()
        self.reference = Reference(grey.copy(), corners.copy(), self.feed.size)
        self.latest = None
        self.seen = 0
        self.status.set("Empty mat captured. Teach each centre with a sample playing piece in the recess.")
        self._render()

    def _shifted(self, corners):
        import numpy as np

        return (self.feed.size != self.reference.shape
                or np.linalg.norm(corners - self.reference.corners, axis=1).max() > 2.0)

    def teach(self):
        if self.busy or self.checking or self.ready or not self.studio.robot or not self.studio.homed:
            return
        if (self.reference is None or self.rectified is None or monotonic()-self.analysed > 0.55
                or self._shifted(self.rectified[0])):
            self.status.set("Capture the empty mat with the camera and mat fixed in place.")
            return
        name = self.teaching.get()
        self._job("teach", lambda: (name, self.studio.robot.pose()))

    def _check_setup(self):
        if not self.studio.robot or not self.studio.homed:
            raise ValueError("Connect and home the Dobot first.")
        if not all(place in self.poses for place in TEACH_ORDER):
            raise ValueError("Teach all nine cells, five reserve slots and Park.")
        points = list(MAT_POSITIONS)
        for i, first in enumerate(points):
            pose = self.poses[first]
            for second in points[i+1:]:
                other = self.poses[second]
                actual = dist((pose.x, pose.y), (other.x, other.y))
                expected = dist(MAT_POSITIONS[first], MAT_POSITIONS[second])
                if abs(actual - expected) > 7 or abs(pose.z - other.z) > 3:
                    raise ValueError(f"Check the taught centres and piece height at {first} and {second}.")
            park = self.poses["Park"]
            if not 12 <= park.z - pose.z <= 75 or abs(park.r - pose.r) > 5:
                raise ValueError("Teach Park above the playing surface with the same tool rotation.")
            if dist((pose.x, pose.y), (park.x, park.y)) > 150:
                raise ValueError("Teach Park near the marked clearance point so each cell is within 150 mm.")

    def _steady(self):
        if self.latest is None or self.seen < 2 or monotonic() - self.analysed > 0.55:
            raise ValueError("Wait for a steady view of the entire mat.")
        if UNKNOWN in self.latest.board or any(value not in (O, "") for value in self.latest.reserve):
            raise ValueError("Seat the pieces in their recesses and check the camera contrast.")
        return self.latest

    def new_game(self):
        if self.busy or self.checking:
            return
        if not self.studio.demo:
            try:
                self._check_setup()
                position = self._steady()
                if position.board != EMPTY or position.reserve.count(O) < 4:
                    raise ValueError("Clear the board and place at least four noughts in the reserve slots.")
            except ValueError as error:
                self.status.set(str(error))
                return
        self.board, self.turn, self.chosen, self.ready = EMPTY, X, None, True
        self.status.set("Your turn. Place one cross in an empty cell.")
        self._render()

    def advance(self):
        if not self.ready or self.busy or self.checking or outcome(self.board):
            return
        try:
            position = self._steady()
            if self.turn == X:
                index = human_change(self.board, position.board)
                self.board = position.board
                self._after_cross(index)
                return
            self._check_setup()
            if position.board != self.board or O not in position.reserve:
                raise ValueError("Keep the board still and load a nought in a reserve slot.")
            index = position.reserve.index(O)
            target = self.chosen
            text = f"Move a nought from {BANK[index]} to {CELLS[target]}. Keep hands off the mat."
            if not messagebox.askokcancel("Place Dobot nought", text, parent=self.window):
                return
            if self._steady() != position:
                raise ValueError("The board changed during confirmation. Check the mat and try again.")
            expected = Position(with_move(position.board, target, O),
                                (*position.reserve[:index], "", *position.reserve[index + 1:]))
            pick, drop, park = (self.poses[place] for place in (BANK[index], CELLS[target], "Park"))
            self.status.set(f"Moving a nought to {CELLS[target]}…")
            self._job("place", lambda: (expected, self.studio.robot.sort_chip(
                pick, drop, park, self.abort, via_park=True)))
        except ValueError as error:
            self.status.set(str(error))
        self._render()

    def _after_cross(self, index):
        if outcome(self.board):
            self._announce()
        else:
            self.turn = O
            self.chosen = robot_move(self.board)
            self.status.set(f"Cross at {CELLS[index]}. Dobot chose {CELLS[self.chosen]}.")
        self._render()

    def _click_game(self, event):
        if not self.studio.demo or self.busy or not self.ready or outcome(self.board):
            return
        left, top, size = self._grid()
        x, y = event.x-left, event.y-top
        if not (0 <= x < size and 0 <= y < size):
            return
        index = int(y/(size/3))*3 + int(x/(size/3))
        if self.board[index]:
            return
        self.board = with_move(self.board, index, X)
        self._after_cross(index)
        if self.chosen is not None:
            self.busy = "demo"
            self.demo_timer = self.window.after(420, self._demo_move)
            self._render()

    def _demo_move(self):
        self.demo_timer = None
        if self.busy == "demo":
            self.busy = None
            self.board = with_move(self.board, self.chosen, O)
            self._after_nought()

    def _after_nought(self):
        target, self.chosen = self.chosen, None
        self.turn = X
        if outcome(self.board):
            self._announce()
        else:
            self.status.set(f"Dobot placed a nought at {CELLS[target]}. Your turn.")
        self._render()

    def _announce(self):
        result = outcome(self.board)
        if result is not None:
            self.ready = False
            self.status.set({X: "You won.", O: "Dobot won.", "Draw": "Draw. Play again with a clear board."}[result])

    def release(self):
        if self.busy or self.checking or not self.studio.robot:
            return
        if messagebox.askokcancel("Release suction", "Support any piece on the cup before releasing it.",
                                  parent=self.window):
            self._job("release", lambda: self.studio.robot.set_suction(False))

    def stop(self):
        self.ready = False
        self.checking = None
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
            return
        self.analysed = sample.timestamp
        try:
            self.rectified = rectify(np.asarray(image))
            corners, grey, _ = self.rectified
            if self.reference is None:
                self.camera_status.set("Mat found. Capture it while empty.")
            elif self._shifted(corners):
                raise ValueError("The mat or camera moved. Re-register the empty mat.")
            else:
                position = read_position(grey, self.reference.grey)
                self.seen = self.seen+1 if position == self.latest else 1
                self.latest = position
                self.camera_status.set(f"Registered mat · {position.reserve.count(O)} noughts in reserve")
        except (ImportError, ValueError) as error:
            if self.rectified is not None and self.reference is not None and self._shifted(self.rectified[0]):
                self.stop()
                self.reference = self.rectified = None
                self.poses.clear()
                self.status.set("The registered mat moved. Capture it again and re-teach the tool.")
            else:
                self.rectified = None
            self.latest = None
            self.seen = 0
            self.camera_status.set(str(error))
        self._draw_camera()

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
                    self._draw_camera()
                continue
            self.busy = None
            if error:
                if name == "place":
                    self.ready = self.studio.homed = False
                    self.studio.points.clear()
                self.status.set(str(error))
            elif name == "teach":
                place, pose = value
                self.poses[place] = pose
                following = TEACH_ORDER[(TEACH_ORDER.index(place)+1) % len(TEACH_ORDER)]
                self.teaching.set(following)
                self.status.set(f"{place} taught. Next: {following}.")
            elif name == "place" and self.ready:
                self.checking, self.studio.position = value
                self.deadline = monotonic() + 3.5
                self.seen = 0
                self.status.set("Checking where the nought landed…")
            elif name == "release":
                self.status.set("Suction release acknowledged.")

        if self.camera:
            sample = self.camera.read()
            if sample and sample[0].timestamp > self.timestamp:
                self._read_frame(*sample)
        if self.busy == "place" and not self.abort.is_set() and monotonic() - self.timestamp > 0.85:
            self.stop()
            self.status.set("Camera stalled. Stopping the transfer.")
        if self.checking and self.latest == self.checking and self.seen >= 2:
            self.board = self.checking.board
            self.checking = None
            self._after_nought()
        if self.checking and monotonic() > self.deadline:
            self.checking = None
            self.ready = False
            self.status.set("Placement was not confirmed. Check the piece and clear the mat for a new game.")
        self._render()
        self.window.after(65, self._tick)

    def _render(self):
        ui = self.studio
        idle = not self.busy and self.checking is None
        result = outcome(self.board)
        if ui.demo:
            self.detail.set("Select an empty cell on the blue board. Dobot replies automatically.")
        else:
            self.detail.set(f"{len(self.poses)}/{len(TEACH_ORDER)} tool positions taught. "
                            "Capture the mat empty before loading reserve noughts.")
            self.camera_button.configure(text="Stop camera" if self.camera else "Start camera")
            self.slot_picker.configure(state="readonly" if idle and not self.ready else "disabled")
            ui._set_button(self.camera_button, idle)
            ui._set_button(self.empty_button, idle and not self.ready and self.rectified is not None)
            ui._set_button(self.teach_button, idle and not self.ready and ui.homed and self.reference is not None)
            self.turn_button.configure(text="Read my cross" if self.turn == X else "Place Dobot nought")
            ui._set_button(self.turn_button, idle and self.ready and not result)
            ui._set_button(self.release_button, idle and ui.robot is not None)
        ui._set_button(self.new_button, idle)
        ui._set_button(self.stop_button, self.ready or not idle)
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
                shown = value or O
                canvas.create_text(x+step/2, y+step/2, text=shown,
                                   fill=("#ffd997" if shown == X else "#8decdf") if value else "#6ca1ad",
                                   font=self.studio.theme.font(max(14, round(step*0.41)), "bold"))
        status = "Your turn" if self.turn == X else "Dobot’s turn"
        if not self.ready:
            status = {"X": "You won", "O": "Dobot won", "Draw": "Draw"}.get(outcome(self.board), "Start a new game")
        canvas.create_text(w/2, top/2, text=status,
                           fill=WHITE, font=self.studio.theme.font(14, "bold"))
        canvas.create_text(w/2, min(h-14, top+size+23), text="X · player     O · Dobot",
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

            inverse = np.linalg.inv(self.rectified[2])
            xy = np.array(tuple(MAT_POSITIONS.values()), dtype=np.float32)[None] * DENSITY
            frame_points = cv2.perspectiveTransform(xy, inverse)[0]
            readings = (*self.latest.board, *self.latest.reserve) if self.latest else ("",)*14
            for label, (x, y), value in zip(MAT_POSITIONS, frame_points, readings):
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
