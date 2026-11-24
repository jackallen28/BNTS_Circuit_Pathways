"""Angled-camera construction challenges and isometric demo."""
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from .blocks import (
    BUFFER, CHALLENGES, EDGE, BlockPlan, RobotBoard, block_colour, demo_scene,
)
from .block_vision import anchors_stable, calibrate, detect, locate
from .robot import ATTACHMENTS, GRIPPER_TOOL, SUCTION_TOOL
from .theme import DARK, MUTED, PANEL, PURPLE, WHITE, colour
from .vision import Camera, TABLETOP


PALETTE = {"Red": "#ed6873", "Blue": "#61b8ee"}


class BlockProgram:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root, bg="#e9eff8", padx=11, pady=10)
        self.window.title("3D Block Lab")
        self.window.transient(studio.root)
        self.window.geometry(f"{min(1060, studio.root.winfo_screenwidth()-32)}x"
                             f"{min(690, studio.root.winfo_screenheight()-50)}")
        self.window.minsize(810, 510)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.stop())
        self.events = SimpleQueue()
        self.stop_signal = Event()
        self.camera = self.busy = self.raw = self.photo = self.pending = None
        self.last_frame = self.last_detection = self.verify_until = 0.0
        self.markers, self.planes, self.datums, self.board = {}, {}, {}, {}
        self.errors = []
        self.sightings = 0
        self.angle = self.moves = 0
        self.playing = False
        self.demo_timer = None
        self.fault = False
        self.attachment = tk.StringVar(value=SUCTION_TOOL)
        self.challenge = tk.StringVar(value=CHALLENGES[0])
        self.device = tk.StringVar(value=studio.camera_device.get())
        self.datum_name = tk.StringVar(value="Left datum")
        self.status = tk.StringVar()
        self.brief = tk.StringVar()
        self.setup_label = tk.StringVar()
        self._build()
        self.reset()
        self.window.after(70, self._tick)

    def _build(self):
        ui = self.studio
        bar = tk.Frame(self.window, bg="#dce9f6", padx=9, pady=6)
        bar.pack(fill="x", pady=(0, 7))
        ui._label(bar, "3D Block Lab", size=16, weight="bold", fg=PURPLE,
                  bg="#dce9f6").pack(side="left")
        ui._label(bar, "DEMO" if ui.demo else "LOCAL USB", size=9,
                  fg=MUTED, bg="#dce9f6").pack(side="left", padx=8)
        ui._button(bar, "Done", self.close).pack(side="right")
        if ui.demo:
            ui._button(bar, "Set up USB arm", self.setup_usb).pack(side="right", padx=5)
        content = tk.Frame(self.window, bg="#e9eff8")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        views = ttk.Notebook(content)
        views.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        virtual = tk.Frame(views, bg=DARK)
        views.add(virtual, text="3D workbench")
        self.scene = tk.Canvas(virtual, bg=DARK, highlightthickness=0, width=400, height=320)
        self.scene.pack(expand=True, fill="both")
        self.scene.bind("<Configure>", lambda _event: self._draw_scene())
        if not ui.demo:
            camera_tab = tk.Frame(views, bg=DARK)
            views.add(camera_tab, text="Angled camera")
            self.preview = tk.Canvas(camera_tab, bg=DARK, highlightthickness=0)
            self.preview.pack(expand=True, fill="both")
            self.preview.bind("<Configure>", lambda _event: self._draw_camera())

        controls, body = ui._pane(content, "Construction challenge")
        controls.grid(row=0, column=1, sticky="nsew")
        choice = ttk.Combobox(body, values=CHALLENGES, textvariable=self.challenge, state="readonly", width=24)
        choice.pack(fill="x")
        choice.bind("<<ComboboxSelected>>", lambda _event: self.reset())
        self.challenge_picker = choice
        ui._label(body, textvariable=self.brief, size=9, fg=MUTED, wraplength=287,
                  justify="left").pack(fill="x", pady=6)
        line = tk.Frame(body, bg=PANEL)
        line.pack(fill="x", pady=(0, 5))
        self.reset_button = ui._button(line, "Reset plan", self.reset)
        self.reset_button.pack(side="left")
        ui._button(line, "Rotate view", self.rotate).pack(side="left", padx=5)

        if not ui.demo:
            tool = tk.Frame(body, bg=PANEL)
            tool.pack(fill="x", pady=4)
            ui._label(tool, "Attachment", size=9).pack(side="left")
            self.tool_picker = ttk.Combobox(tool, values=ATTACHMENTS, textvariable=self.attachment,
                                            width=11, state="readonly")
            self.tool_picker.pack(side="right")
            self.tool_picker.bind("<<ComboboxSelected>>", self.change_tool)
            cam = tk.Frame(body, bg=PANEL)
            cam.pack(fill="x", pady=3)
            self.camera_button = ui._button(cam, "Start camera", self.toggle_camera)
            self.camera_button.pack(side="right")
            ttk.Entry(cam, textvariable=self.device, width=8).pack(side="right", padx=5)
            ui._label(cam, "Camera", size=9).pack(side="left")
            caps = tk.Frame(body, bg=PANEL)
            caps.pack(fill="x", pady=3)
            self.plane_buttons = [ui._button(caps, f"Calibrate layer {i+1}", lambda level=i: self.capture_plane(level))
                                  for i in range(2)]
            for button in self.plane_buttons:
                button.pack(side="left", padx=(0, 4))
            datums = tk.Frame(body, bg=PANEL)
            datums.pack(fill="x", pady=3)
            ttk.Combobox(datums, values=("Left datum", "Right datum", "Park"), textvariable=self.datum_name,
                         width=12, state="readonly").pack(side="left")
            self.teach_button = ui._button(datums, "Teach tool pose", self.teach)
            self.teach_button.pack(side="left", padx=5)
            ui._label(body, textvariable=self.setup_label, size=9, fg=MUTED,
                      wraplength=287, justify="left").pack(fill="x", pady=4)

        actions = tk.Frame(body, bg=PANEL)
        actions.pack(side="bottom", fill="x", pady=(9, 0))
        self.step_button = ui._button(actions, "Next transfer", self.step, "Teal")
        self.step_button.pack(side="left")
        if ui.demo:
            self.play_button = ui._button(actions, "Play demo", self.play)
            self.play_button.pack(side="left", padx=5)
        else:
            self.release_button = ui._button(actions, "Release tool", self.release)
            self.release_button.pack(side="left", padx=5)
        ui._label(body, textvariable=self.status, size=10, fg=PURPLE, wraplength=287,
                  justify="left").pack(fill="x", pady=(8, 0))
        footer = tk.Frame(self.window, bg="#dce9f6", padx=8, pady=4)
        footer.pack(fill="x", pady=(6, 0))
        ui._label(footer, "Camera-verified transfers" if not ui.demo else "Moves, support layers and colour routing",
                  size=9, bg="#dce9f6").pack(side="left")
        self.stop_button = ui._button(footer, "Stop  ·  Esc", self.stop, "Stop")
        self.stop_button.pack(side="right")

    def reset(self):
        if self.busy or self.pending or self.playing:
            return
        name = self.challenge.get()
        self.plan = BlockPlan(name)
        self.moves = 0
        self.fault = False
        if self.studio.demo:
            self.board = demo_scene(name)
        descriptions = (
            "Place four base cubes, then balance the cap on their inner corners.",
            "Build two layers of a 2 × 2 block box.",
            "Empty both mixed stacks into the rack, then rebuild a red stack and a blue stack.",
        )
        self.brief.set(descriptions[CHALLENGES.index(name)])
        self.status.set("Ready to plan the next transfer." if self.studio.demo else
                        "Calibrate both layers and teach the fitted tool before moving.")
        self._render()

    def rotate(self):
        self.angle = (self.angle + 1) % 4
        self._draw_scene()

    def setup_usb(self):
        self.close()
        if self.studio.workcell is None:
            self.studio.show_connect()

    def toggle_camera(self):
        if self.busy or self.pending:
            return
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
            self.camera = self.raw = None
            self.planes.clear()
            self.board.clear()
            self.markers.clear()
            self.last_detection = 0.0
            self.sightings = 0
        elif self.device.get().strip() and not self.studio.camera_closing:
            self.camera = Camera(self.device.get().strip(), TABLETOP, Path("."),
                                 lambda error: self.events.put(("camera", None, error)))
            self.last_frame = 0.0
            self.status.set("Opening the angled camera…")
        self._render()
        self._draw_camera()

    def capture_plane(self, level):
        if self.busy or self.pending:
            return
        try:
            if monotonic() - self.last_detection > 0.6:
                raise ValueError("Wait for a fresh camera frame.")
            self.planes[level] = calibrate(self.markers)
            self.sightings = 0
            self.status.set(f"Layer {level+1} calibrated. Use the 20 mm anchor height for transfers.")
        except (AttributeError, ImportError, ValueError) as error:
            self.status.set(str(error))
        self._render()

    def teach(self):
        if self.busy or self.pending:
            return
        if not self.studio.robot or not self.studio.homed:
            self.status.set("Connect and home the arm before teaching.")
            return
        name = self.datum_name.get()
        self._job("teach", lambda: (name, self.studio.robot.pose()))

    def change_tool(self, _event=None):
        self.datums.clear()
        self.status.set("Teach both datums and Park for the fitted tool.")
        self._render()

    def _job(self, name, action):
        self.busy = name
        self.stop_signal.clear()

        def run():
            try:
                self.events.put((name, action(), None))
            except Exception as error:
                self.events.put((name, None, error))

        Thread(target=run, daemon=True, name=f"blocks-{name}").start()
        self._render()

    def play(self):
        if not self.studio.demo or self.playing or self.busy:
            return
        self.playing = True
        self.step()

    def step(self):
        if self.busy or self.pending or self.fault:
            return
        try:
            if not self.studio.demo:
                self._check_hardware()
            transfer = self.plan.next_transfer(self.board)
            if transfer is None:
                self.playing = False
                self.status.set(f"Challenge complete · {self.moves} transfers.")
                self._render()
                return
            if self.studio.demo:
                self.busy = "demo"
                self.status.set(f"{block_colour(transfer.marker)} cube {transfer.marker} → {transfer.target.label()}")
                self.demo_timer = self.window.after(390, lambda: self._demo_move(transfer))
                self._render()
                return
            tool = self.attachment.get()
            text = f"Move cube {transfer.marker} to {transfer.target.label()}. Check the tool and travel path."
            if tool == GRIPPER_TOOL:
                text += " Make sure both jaws clear the neighbouring cubes."
            if not messagebox.askokcancel("Confirm one block transfer", text, parent=self.window):
                return
            self._check_hardware()
            if self.plan.next_transfer(self.board) != transfer:
                raise ValueError("The view changed during confirmation. Recheck the block locations.")
            rig = RobotBoard(self.datums["Left datum"], self.datums["Right datum"], self.datums["Park"])
            self.status.set(f"Transferring cube {transfer.marker}…")
            self._job("move", lambda: (transfer, self.studio.robot.sort_chip(
                rig.pose(transfer.source), rig.pose(transfer.target), rig.park, self.stop_signal, tool)))
        except ValueError as error:
            self.playing = False
            self.status.set(str(error))
            self._render()

    def _check_hardware(self):
        if not self.studio.robot or not self.studio.homed or len(self.datums) != 3:
            raise ValueError("Connect, home and teach both tool datums and Park.")
        if set(self.planes) != {0, 1} or monotonic() - self.last_detection > 0.6 or self.sightings < 2:
            raise ValueError("Wait for a steady camera view with two calibrated layers.")
        if self.errors:
            raise ValueError(self.errors[0])

    def _demo_move(self, transfer):
        self.demo_timer = None
        if self.busy != "demo":
            return
        board = dict(self.board)
        del board[transfer.source]
        board[transfer.target] = transfer.marker
        self.plan.confirm(transfer, board)
        self.board = board
        self.moves += 1
        self.busy = None
        self.status.set(f"Placed cube {transfer.marker} · {self.moves} transfers.")
        self._render()
        if self.playing:
            self.window.after(120, self._continue_demo)

    def _continue_demo(self):
        if self.playing:
            self.step()

    def release(self):
        if self.busy or self.pending or not self.studio.robot:
            return
        if messagebox.askokcancel("Release tool", "Support any load before releasing the tool.", parent=self.window):
            tool = self.attachment.get()
            self._job("release", lambda: self.studio.robot.set_attachment(tool, False))

    def stop(self):
        self.playing = False
        if self.busy == "demo":
            if self.demo_timer is not None:
                self.window.after_cancel(self.demo_timer)
                self.demo_timer = None
            self.busy = None
            self.status.set("Demo stopped.")
        if self.busy == "move" or self.pending:
            self.stop_signal.set()
            self.pending = None
            self.fault = True
            self.status.set("Transfer interrupted. Check the fixture before resetting the plan.")
        self._render()

    def _read_camera(self, detected, image):
        import numpy as np

        self.raw = image
        self.last_frame = detected.timestamp
        if self.last_frame - self.last_detection < 0.11:
            return
        self.last_detection = self.last_frame
        try:
            self.markers = detect(np.asarray(image))
            board, errors = locate(self.markers, self.planes)
            if 0 in self.planes and not anchors_stable(self.markers, self.planes[0]):
                errors.insert(0, "Restore the four anchors to 20 mm or recalibrate the camera.")
            self.sightings = self.sightings + 1 if board == self.board and not errors else 1
            self.board, self.errors = board, errors
        except (AttributeError, ImportError, ValueError) as error:
            self.sightings = 0
            self.errors = [str(error)]
        self._draw_camera()
        self._draw_scene()

    def _tick(self):
        while True:
            try:
                job, data, error = self.events.get_nowait()
            except Empty:
                break
            if job == "camera":
                self.status.set(str(error))
                if self.busy == "move":
                    self.stop()
                if self.camera:
                    self.studio.camera_closing = self.camera
                self.camera = self.raw = None
                self.planes.clear()
                self.sightings = 0
                self._draw_camera()
                continue
            self.busy = None
            if error:
                self.status.set(str(error))
                if job == "move":
                    self.fault = True
                    self.studio.homed = False
                    self.studio.points.clear()
            elif job == "teach":
                name, pose = data
                self.datums[name] = pose
                self.status.set(f"{name} taught.")
            elif job == "move" and not self.fault:
                self.pending, self.studio.position = data
                self.verify_until = monotonic() + 3
                self.sightings = 0
                self.status.set("Checking the cube at its new height and position…")
            elif job == "release":
                self.status.set("Release acknowledged.")
        if self.camera:
            latest = self.camera.read()
            if latest and latest[0].timestamp > self.last_frame:
                self._read_camera(*latest)
        if self.busy == "move" and not self.stop_signal.is_set() and monotonic() - self.last_frame > 0.85:
            self.stop()
            self.status.set("Camera stalled. Stopping the transfer.")
        if self.pending and self.sightings >= 2 and not self.errors:
            try:
                self.plan.confirm(self.pending, self.board)
            except ValueError:
                pass
            else:
                self.pending = None
                self.moves += 1
                self.status.set(f"Camera confirmed placement · {self.moves} transfers.")
        if self.pending and monotonic() > self.verify_until:
            self.pending = None
            self.fault = True
            self.status.set("The placement was not confirmed. Check the cube and reset the plan.")
        self._render(draw=False)
        self.window.after(70, self._tick)

    def _render(self, draw=True):
        idle = not self.busy and not self.pending and not self.playing
        self.challenge_picker.configure(state="readonly" if idle else "disabled")
        self.studio._set_button(self.reset_button, idle)
        self.studio._set_button(self.step_button, idle and not self.fault)
        self.studio._set_button(self.stop_button, not idle)
        if self.studio.demo:
            self.studio._set_button(self.play_button, idle)
        else:
            self.tool_picker.configure(state="readonly" if idle else "disabled")
            for button in self.plane_buttons:
                self.studio._set_button(button, idle and self.camera is not None)
            self.studio._set_button(self.teach_button, idle and self.studio.robot is not None)
            self.studio._set_button(self.release_button, idle and self.studio.robot is not None)
            self.studio._set_button(self.camera_button, idle)
            self.camera_button.configure(text="Stop camera" if self.camera else "Start camera")
            detail = self.errors[0] if self.errors else f"{len(self.board)} visible tagged cubes"
            self.setup_label.set(f"Layers {len(self.planes)}/2 · Tool poses {len(self.datums)}/3\n{detail}")
        if draw:
            self._draw_scene()

    def _draw_scene(self):
        canvas = self.scene
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 8 or height < 8:
            return
        canvas.delete("all")
        scale = min(width / 200, height / 180)

        def rotated(x, y):
            return ((x, y), (-y, x), (-x, -y), (y, -x))[self.angle]

        def point(x, y, z=0):
            vx, vy = rotated(x, y + 15)
            return width/2 + (vx-vy)*scale*0.83, height*0.57 + ((vx+vy)*0.44-z)*scale

        def polygon(points, fill, outline="#0b1424", line=1):
            vertices = [coordinate for vertex in points for coordinate in point(*vertex)]
            canvas.create_polygon(*vertices, fill=fill, outline=outline, width=line)

        polygon(((-63,-70), (63,-70), (63,43), (-63,43)), "#213550", "#56728a", 2)
        for slot in BUFFER:
            x, y = slot.x, slot.y
            polygon(((x-10,y-10), (x+10,y-10), (x+10,y+10), (x-10,y+10)), "#2b4564", "#527396")
        visible = self.board
        try:
            visible = self.plan.register(self.board)
        except ValueError:
            pass
        for slot in self.plan.target:
            if slot.level == 0 and slot not in visible:
                x, y = slot.x, slot.y
                polygon(((x-10,y-10), (x+10,y-10), (x+10,y+10), (x-10,y+10)), "#2c4f59", "#71c8c5")
        for slot in sorted(visible, key=lambda s: (s.level, sum(rotated(s.x, s.y+15)))):
            x, y, z = slot.x, slot.y, slot.level * EDGE
            corners = [(x-10,y-10), (x+10,y-10), (x+10,y+10), (x-10,y+10)]
            tint = PALETTE[block_colour(visible[slot])]
            for index in range(4):
                a, b = corners[index], corners[(index+1)%4]
                if sum(rotated((a[0]+b[0])/2-x, (a[1]+b[1])/2-y)) > 0:
                    polygon(((*a,z), (*b,z), (*b,z+EDGE), (*a,z+EDGE)),
                            colour(tint, "#0e2136", 0.33 if index%2 else 0.48))
            polygon(tuple((*corner,z+EDGE) for corner in corners), tint)
            px, py = point(x, y, z+EDGE)
            canvas.create_text(px, py, text=str(visible[slot]), fill="#15283b",
                               font=self.studio.theme.font(9, "bold"))
        canvas.create_text(12, 12, anchor="nw", fill="#b9d8ed",
                           text=f"{self.moves} transfers  ·  {len(visible)} visible or verified cubes",
                           font=self.studio.theme.font(9))

    def _draw_camera(self):
        if self.studio.demo:
            return
        canvas = self.preview
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if self.raw is None or min(w, h) < 8:
            canvas.create_text(w/2, h/2, text="Angled camera offline", fill=WHITE)
            return
        from PIL import Image, ImageTk

        image = self.raw.copy()
        image.thumbnail((w, h), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        canvas.create_image(w/2, h/2, image=self.photo)
        left, top = (w-image.width)/2, (h-image.height)/2
        for marker, quad in self.markers.items():
            points = [coordinate for x, y in quad for coordinate in
                      (left + x*image.width/self.raw.width, top + y*image.height/self.raw.height)]
            canvas.create_polygon(*points, fill="", outline="#51d4d9", width=2)
            canvas.create_text(points[0], points[1]-4, text=str(marker), fill=WHITE, anchor="sw")

    def close(self):
        if self.busy or self.pending:
            self.stop()
            return
        self.playing = False
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
        self.window.destroy()
        self.studio.end_workcell()
