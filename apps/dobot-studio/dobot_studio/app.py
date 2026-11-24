"""Dobot Studio desktop app. Tk owns the UI; USB and camera I/O run off-thread."""
import argparse
import os
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from time import monotonic
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .learning import (
    CUSTOM_HAND, SYMBOL, TRAINABLE, Recognizer, default_training_folder, empty_classes, load_classes,
)
from .block_program import BlockProgram
from .connect import ConnectScreen
from . import desktop
from .programs import build_program_picker
from .teach_program import TeachProgram
from .tictactoe_program import TicTacToeProgram
from .robot import Magician, MotionStopped, Pose, POSITION_LIMIT_MM, ROTATION_LIMIT_DEG, StopUnconfirmed, serial_ports
from .theme import BORDER, DARK, DARKER, GREEN, INK, MUTED, PANEL, PURPLE, WHITE
from .theme import Theme, gradient, icon
from .trainer import TrainingWindow
from .update_dialog import UpdateDialog
from .updater import Updater
from .vision import Camera, Detection, GestureGate, HAND, POSE
from .workcell import Workcell

DEMO_A, DEMO_B = Pose(220, -28, 80, 0), Pose(220, 28, 80, 0)
SOURCE = {HAND: ("Thumb up", "Victory sign", "Closed fist"),
          POSE: ("Left wrist up", "Right wrist up", "Both wrists up"),
          CUSTOM_HAND: ("Trained hand sign", "Trained hand sign", "A trained stop sign"),
          SYMBOL: ("Trained symbol", "Trained symbol", "A trained stop symbol")}
TRACK_TIMEOUT = 0.75
APP_FOLDER = Path(__file__).resolve().parents[1]
ICON = APP_FOLDER / "assets" / "dobot-studio.png"


class Studio:
    def __init__(self, root, models, training_folder=None):
        self.root, self.models = root, models
        self.training_folder = training_folder if training_folder is not None else default_training_folder()
        self.training_window = self.classifier = None
        self.workcell = self.program_menu = self.connect_screen = None
        self.app_folder = APP_FOLDER
        self.update_dialog = None
        self.restart_requested = False
        self._version = None
        self.theme = Theme(root)
        self.demo = True
        self.armed = self.homed = self.closing = False
        self.robot = self.camera = self.camera_closing = self.busy = self.position = None
        self.worker_events = SimpleQueue()
        self.stop_signal = Event()
        self.gate = GestureGate()
        self.tracked_at = self.last_frame = 0.0
        self.preview = self.preview_photo = None
        self.synthetic = None
        self.synthetic_until = 0.0
        self.camera_token = 0
        self.input_mode = tk.StringVar(value=HAND)
        self.camera_device = tk.StringVar(value="0")
        self.port = tk.StringVar()
        self.vision_text = tk.StringVar(value="Neutral hand")
        self.status_text = tk.StringVar(value="Demo ready. Enable controls to try the sample inputs.")
        self.points = {"A": DEMO_A, "B": DEMO_B}
        self.position = DEMO_A
        self._build()
        self._render()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind("<Escape>", lambda _event: self.stop("Stopped from the keyboard."))
        self.root.after(35, self._tick)

    def _label(self, parent, text="", *, size=10, weight="normal", fg=INK, bg=PANEL, **kw):
        return tk.Label(parent, text=text, font=self.theme.font(size, weight), fg=fg,
                        bg=bg, anchor="w", borderwidth=0, **kw)

    def _button(self, parent, text, command, kind="Glass"):
        return ttk.Button(parent, text=text, command=command, style=kind + ".TButton", width=0)

    def _pane(self, parent, title, subtitle=None):
        pane = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        top = tk.Frame(pane, bg="#e7eff9", padx=10, pady=2, highlightbackground="#d2ddea",
                       highlightthickness=1)
        top.pack(fill="x")
        self._label(top, title, size=10, weight="bold", fg=PURPLE, bg="#e7eff9").pack(side="left")
        if subtitle:
            self._label(top, subtitle, size=9, fg=MUTED, bg="#e7eff9").pack(side="right")
        body = tk.Frame(pane, bg=PANEL, padx=10, pady=5)
        body.pack(fill="both", expand=True)
        return pane, body

    def _build(self):
        root = self.root
        root.title("Dobot Studio")
        root.geometry(f"{min(1130, root.winfo_screenwidth()-32)}x{min(735, root.winfo_screenheight()-65)}")
        root.minsize(860, 550)
        outer = tk.Canvas(root, bg="#254d71", borderwidth=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        self.desktop = outer
        shell = tk.Frame(outer, bg="#e9eff8", highlightbackground="#a8bbd4", highlightthickness=1)
        shell_id = outer.create_window(18, 15, anchor="nw", window=shell)

        def paint_outer(event):
            w, h = event.width, event.height
            outer.delete("paint")
            gradient(outer, w, h, "#10566b", "#40345e")
            outer.create_polygon(0, h*.7, w*.83, 0, w, 0, w*.1, h, 0, h,
                                 fill="#276b85", outline="", tags="paint")
            outer.create_polygon(0, h, w, h * .18, w, h, fill="#424573", outline="", tags="paint")
            outer.tag_lower("paint")
            outer.coords(shell_id, 18, 15)
            outer.itemconfigure(shell_id, width=w-36, height=h-30)

        outer.bind("<Configure>", paint_outer)
        masthead = tk.Canvas(shell, height=72, borderwidth=0, highlightthickness=0, bg="#d7eaf5")
        masthead.pack(fill="x")

        def paint_header(event):
            w, h = event.width, event.height
            masthead.delete("all")
            gradient(masthead, w, h, "#fafeff", "#bfd8ee")
            masthead.create_polygon(w*.54, h, w*.83, 0, w, 0, w, h, fill="#d8d4ed", outline="", tags="paint")
            masthead.create_line(w*.72, h, w*.94, 0, fill="#edf2ff", width=3)
            masthead.create_line(0, h-1, w, h-1, fill="#a2b7d1")
            masthead.create_rectangle(17, 15, 66, 62, fill="#eefbff", outline="#98c1d9")
            masthead.create_rectangle(19, 17, 64, 60, fill="#d3edf1", outline="#ffffff")
            icon(masthead, "arm", 41, 38, 1.6)
            masthead.create_text(83, 17, text="Dobot Studio", anchor="nw",
                                 fill=PURPLE, font=self.theme.font(22, "bold"))
            masthead.create_text(85, 50, text="Dobot Magician  ·  Camera control",
                                 anchor="nw", fill="#405671", font=self.theme.font(10))

        masthead.bind("<Configure>", paint_header)

        toolbar = tk.Frame(shell, bg="#edf3fa", padx=12, pady=4)
        toolbar.pack(fill="x")
        self.program_button = self._button(toolbar, "Programs", self.show_programs)
        self.program_button.pack(side="left", padx=(0, 11))
        self.demo_button = self._button(toolbar, "Demo", lambda: self.set_mode(True), "Purple")
        self.demo_button.pack(side="left")
        self.live_button = self._button(toolbar, "USB hardware", lambda: self.set_mode(False))
        self.live_button.pack(side="left", padx=(5, 0))
        self.training_button = self._button(toolbar, "Train recognition…", self.open_training)
        self.training_button.pack(side="left", padx=(11, 0))
        self.system_badge = self._label(toolbar, size=9, weight="bold", bg="#e4edf6")
        self.system_badge.pack(side="right", ipadx=9, ipady=4)

        workspace = tk.Frame(shell, bg="#e9eff8", padx=12, pady=5)
        workspace.pack(fill="both", expand=True)
        workspace.grid_columnconfigure(0, weight=1, minsize=360)
        workspace.grid_columnconfigure(1, minsize=300)
        workspace.grid_rowconfigure(0, weight=1)

        left = tk.Frame(workspace, bg="#e9eff8")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 11))
        self.camera_panel, stage = self._pane(left, "Camera & tracking", "640 × 480 target")
        self.camera_panel.pack(fill="both", expand=True)
        self.screen = tk.Canvas(stage, bg=DARK, bd=0, highlightthickness=1, highlightbackground="#344964")
        self.screen.pack(fill="both", expand=True)
        self.screen.bind("<Configure>", lambda _event: self._draw_preview())
        signal = tk.Frame(stage, bg="#e8f0fa", padx=8, pady=4)
        signal.pack(fill="x", pady=(6, 0))
        self._label(signal, "Detected", fg=MUTED, bg="#e8f0fa", size=9).pack(side="left")
        self._label(signal, textvariable=self.vision_text, weight="bold", bg="#e8f0fa").pack(side="left", padx=8)
        self.signal_badge = self._label(signal, bg="#e8f0fa", fg=GREEN, size=9, weight="bold")
        self.signal_badge.pack(side="right")

        self.sim_panel, sim = self._pane(left, "Try a recognition input")
        self.sim_panel.pack(fill="x", side="bottom", before=self.camera_panel, pady=(6, 0))
        self.sim_buttons = []
        for index, command in enumerate(("A", "B", "Stop", None)):
            button = self._button(sim, "Neutral", lambda action=command: self.simulate(action))
            sim.columnconfigure(index, weight=1)
            button.grid(row=0, column=index, sticky="ew", padx=(0, 4) if index < 3 else 0)
            self.sim_buttons.append(button)

        right = tk.Frame(workspace, bg="#e9eff8")
        right.grid(row=0, column=1, sticky="nsew")
        pane, connection = self._pane(right, "Dobot connection")
        pane.pack(fill="x")
        connection.columnconfigure(0, weight=1)
        self.port_box = ttk.Combobox(connection, textvariable=self.port, width=13)
        self.port_box.grid(row=0, column=0, sticky="ew")
        self.refresh_button = self._button(connection, "Scan", self.scan_ports)
        self.refresh_button.grid(row=0, column=1, padx=(4, 0))
        self.connect_button = self._button(connection, "Connect", self.connect)
        self.connect_button.grid(row=0, column=2, padx=(4, 0))
        self.home_button = self._button(connection, "Home", self.home)
        self.home_button.grid(row=0, column=3, padx=(4, 0), sticky="ew")
        self.connection_text = self._label(connection, fg=MUTED, size=9)
        self.connection_text.grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        pane, capture = self._pane(right, "Tracking input")
        pane.pack(fill="x", pady=(7, 0))
        capture.columnconfigure(0, weight=1)
        self.input_box = ttk.Combobox(capture, state="readonly", textvariable=self.input_mode,
                                      values=(HAND, POSE, *TRAINABLE), width=21)
        self.input_box.grid(row=0, column=0, sticky="ew")
        self.input_box.bind("<<ComboboxSelected>>", self.change_input)
        self._label(capture, "Camera", fg=MUTED, size=9).grid(row=0, column=1, padx=(7, 4))
        self.device_box = ttk.Entry(capture, textvariable=self.camera_device, width=4)
        self.device_box.grid(row=0, column=2)
        self.preview_button = self._button(capture, "Start camera", self.toggle_camera)
        self.preview_button.grid(row=0, column=3, padx=(6, 0), sticky="ew")

        pane, presets = self._pane(right, "Taught positions", "X, Y, Z  /  R")
        pane.pack(fill="x", pady=(7, 0))
        presets.columnconfigure(1, weight=1)
        self.point_labels = {}
        self.source_labels = []
        self.teach_buttons = {}
        for i, name in enumerate(("A", "B")):
            token = self._label(presets, name, size=10, weight="bold", fg=PURPLE, bg="#ebe4f5")
            token.grid(row=i*2, column=0, ipadx=6, ipady=3, sticky="w", padx=(0, 6))
            value = self._label(presets, size=9, weight="bold")
            value.grid(row=i*2, column=1, sticky="w")
            self.point_labels[name] = value
            hint = self._label(presets, size=9, fg=MUTED)
            hint.grid(row=i*2+1, column=1, sticky="w", pady=(1, 5 if i == 0 else 0))
            self.source_labels.append(hint)
            teach = self._button(presets, "Teach", lambda key=name: self.teach(key))
            teach.grid(row=i*2, rowspan=2, column=2, padx=(6, 0), sticky="e")
            self.teach_buttons[name] = teach

        status = tk.Frame(shell, bg="#dfe8f3", padx=13, pady=4)
        status.pack(fill="x", side="bottom", before=workspace)
        self._label(status, textvariable=self.status_text, fg=INK, bg="#dfe8f3", size=9,
                    justify="left", wraplength=615).pack(side="left", fill="x", expand=True)
        self.pose_text = self._label(status, fg=MUTED, bg="#dfe8f3", size=9)
        self.pose_text.pack(side="right", padx=(8, 0))

        motion = tk.Frame(shell, bg="#f6faff", padx=12, pady=6, highlightbackground=BORDER,
                          highlightthickness=1)
        motion.pack(fill="x", side="bottom", before=workspace, padx=12, pady=(0, 5))
        control = tk.Frame(motion, bg="#f6faff")
        control.pack(side="left")
        self.control_text = self._label(control, weight="bold", fg=PURPLE, bg="#f6faff")
        self.control_text.pack(fill="x")
        self.stop_hint = self._label(control, size=9, fg=MUTED, bg="#f6faff")
        self.stop_hint.pack(fill="x", pady=(1, 0))
        self.stop_button = self._button(motion, "Stop  ·  Esc", lambda: self.stop("Stopped."), "Stop")
        self.stop_button.pack(side="right", ipadx=16)
        self.arm_button = self._button(motion, "Enable controls", self.enable, "Teal")
        self.arm_button.pack(side="right", padx=(0, 6), ipadx=12)

    def _set_button(self, button, enabled):
        button.state(["!disabled"] if enabled else ["disabled"])

    def _render(self):
        connected = self.robot is not None
        idle = self.busy is None and not self.closing and self.training_window is None and self.workcell is None
        live = not self.demo
        mode = self.input_mode.get()
        trainable = mode in TRAINABLE
        camera_idle = self.camera is None and self.camera_closing is None
        can_change = idle and not connected and camera_idle
        self.demo_button.configure(style="Purple.TButton" if self.demo else "Glass.TButton")
        self.live_button.configure(style="Purple.TButton" if live else "Glass.TButton")
        self._set_button(self.demo_button, can_change or self.demo)
        self._set_button(self.live_button, can_change or live)
        self.system_badge.configure(text="DEMO MODE" if self.demo else "LOCAL USB",
                                    fg=PURPLE if self.demo else GREEN)
        self.port_box.configure(state="normal" if live and idle and not connected else "disabled")
        self._set_button(self.refresh_button, live and idle and not connected)
        self._set_button(self.connect_button, live and idle)
        self.connect_button.configure(text="Disconnect" if connected else "Connect")
        self._set_button(self.home_button, live and connected and idle and not self.armed)
        self.connection_text.configure(text="Simulated Dobot Magician" if self.demo else
                                      "Homed" if connected and self.homed else
                                      "Connected · Home required" if connected else "Connect via USB")
        self.input_box.configure(state="readonly" if not self.armed and idle and camera_idle else "disabled")
        self.device_box.configure(state="normal" if camera_idle and idle and not self.armed else "disabled")
        camera_action = "Stop camera" if self.camera else "Start camera"
        self.preview_button.configure(text="Closing…" if self.camera_closing else camera_action)
        self._set_button(self.preview_button, not self.closing and self.training_window is None
                         and self.camera_closing is None and self.workcell is None and (not self.armed or self.camera is not None))
        self._set_button(self.training_button, idle and not self.armed and self.camera_closing is None)
        self._set_button(self.program_button, idle and not self.armed and camera_idle)
        simulate = self._simulated_input()
        if simulate and not self.sim_panel.winfo_manager():
            self.sim_panel.pack(fill="x", side="bottom", before=self.camera_panel, pady=(6, 0))
        elif not simulate and self.sim_panel.winfo_manager():
            self.sim_panel.pack_forget()
        self.signal_badge.configure(text="SIMULATION" if simulate else "TRACKING" if self._tracking_ready()
                                    else "NO TRACKING")
        self.stop_hint.configure(text="Esc or a mapped stop input" if trainable else f"{SOURCE[mode][2]} or Esc to stop")
        for name, hint, source in zip(("A", "B"), self.source_labels, SOURCE[mode]):
            pose = self.points.get(name)
            self.point_labels[name].configure(text=pose.label() if pose else "Position " + name + " not taught")
            hint.configure(text=source)
            self._set_button(self.teach_buttons[name], connected and self.homed and idle and not self.armed)
        actions = SOURCE[HAND] if mode == HAND else ("Left wrist", "Right wrist", "Both wrists")
        for button, title in zip(self.sim_buttons, (*actions, "Neutral")):
            button.configure(text=title)
        self.arm_button.configure(text="Disarm" if self.armed else "Enable controls")
        camera_ready = self._tracking_ready() and (not trainable or self.classifier is not None)
        arm_ready = (simulate or camera_ready) and (self.demo or connected and self.homed and len(self.points) == 2)
        self._set_button(self.arm_button, self.armed or idle and arm_ready)
        self._set_button(self.stop_button, not self.closing and (self.demo or connected))
        if self.busy == "stop":
            text = "Stopping…"
        elif self.busy == "home":
            text = "Homing in progress"
        elif self.busy == "move":
            text = "Moving to taught position"
        elif self.armed:
            text = "Controls enabled"
        else:
            text = "Controls disarmed"
        self.control_text.configure(text=text, fg=GREEN if self.armed else PURPLE)
        self.pose_text.configure(text=self.position.label() if self.position else "Position unavailable")
        if self.connect_screen:
            self.connect_screen.refresh()

    def _simulated_input(self):
        return self.demo and self.camera is None and self.input_mode.get() not in TRAINABLE

    def _tracking_ready(self):
        return self.camera is not None and self.tracked_at > 0 and monotonic() - self.tracked_at < TRACK_TIMEOUT

    def _draw_preview(self):
        canvas = self.screen
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 10 or h < 10:
            return
        canvas.delete("all")
        if self.preview is not None:
            from PIL import Image, ImageTk
            image = self.preview.copy()
            image.thumbnail((w-2, h-2), Image.Resampling.BILINEAR)
            self.preview_photo = ImageTk.PhotoImage(image)
            canvas.create_image(w/2, h/2, image=self.preview_photo)
            return
        gradient(canvas, w, h, DARKER, "#243b60")
        cx, cy = w*.5, h*.49
        if self._simulated_input():
            for i in range(-7, 8):
                canvas.create_line(w*.5+i*24, h*.45, w*.5+i*91, h, fill="#304a70")
            for fraction in (.49, .54, .60, .68, .78, .90):
                canvas.create_line(0, h*fraction, w, h*fraction, fill="#304a70")
            cy = h*.43
            scale = min(w/560, (h-55)/276, 1.35)
            base_y = cy + 66*scale
            endpoint = ((self.position.y if self.position else 0) / 28) * 32*scale
            points = (cx-68*scale, base_y-8*scale, cx-101*scale, cy-26*scale,
                      cx-48*scale, cy-77*scale, cx+42*scale+endpoint, cy-35*scale)
            canvas.create_oval(cx-132*scale, base_y-13*scale, cx-4*scale, base_y+17*scale,
                               fill="#293c68", outline="#7d93bb", width=2)
            for offset, line_color in ((18, "#5d77a4"), (11, "#9fb8d9"), (2, "#dcefff")):
                canvas.create_line(*points, fill=line_color, width=max(1, offset*scale),
                                   joinstyle="round", capstyle="round")
            for x, y in zip(points[::2], points[1::2]):
                canvas.create_oval(x-7*scale, y-7*scale, x+7*scale, y+7*scale,
                                   fill="#162741", outline="#8ae6e8", width=2)
            x, y = points[-2:]
            canvas.create_line(x, y, x, y+26*scale, fill="#aabfe7", width=5*scale)
            canvas.create_line(x-8*scale, y+26*scale, x+8*scale, y+26*scale,
                               fill="#aabfe7", width=3*scale)
            for preset, shift in (("A", -1), ("B", 1)):
                x = cx+shift*58*scale+66*scale
                y = base_y+15*scale
                selected = self.position == self.points.get(preset)
                canvas.create_oval(x-14*scale, y-9*scale, x+14*scale, y+9*scale,
                                   fill="#197881" if selected else "#263c61",
                                   outline="#7ee0e5" if selected else "#687ca5")
                canvas.create_text(x, y, text=preset, fill=WHITE, font=self.theme.font(8, "bold"))
            label = "Simulated feed"
            detail = "Try an input below to send a demo command."
            title_y = min(base_y + max(42*scale, 30), h-42)
        else:
            icon(canvas, "camera", cx, cy-28, 1.5, foreground="#add7ea")
            label = "Opening USB camera…" if self.camera else "Camera offline"
            detail = "Start the camera to see tracking here."
            title_y = cy+5
        canvas.create_text(cx, title_y, text=label, fill=WHITE, font=self.theme.font(13, "bold"))
        canvas.create_text(cx, title_y+21, text=detail, fill="#c2d7ef", font=self.theme.font(9))
        for x, dx in ((16, 15), (w-16, -15)):
            for y, dy in ((16, 15), (h-16, -15)):
                canvas.create_line(x+dx, y, x, y, x, y+dy, fill="#67abbc", width=1)

    def set_mode(self, demo):
        if self.demo == demo or self.busy or self.robot or self.camera or self.camera_closing:
            return
        self.demo = demo
        self.armed = self.homed = False
        self.tracked_at = self.last_frame = 0
        self.gate.reset()
        self.position = DEMO_A if demo else None
        self.points = {"A": DEMO_A, "B": DEMO_B} if demo else {}
        self.synthetic = None
        self.synthetic_until = 0
        if demo:
            self.status_text.set("Demo ready. Enable controls to try the sample inputs.")
        else:
            self.scan_ports()
            self.status_text.set("Connect the Dobot and start the USB camera.")
        self.vision_text.set("Neutral hand" if demo else "Waiting for camera")
        self._draw_preview()
        self._render()

    def scan_ports(self):
        try:
            ports = serial_ports()
            self.port_box.configure(values=ports)
            if len(ports) == 1 and not self.port.get():
                self.port.set(ports[0])
            self.status_text.set("Choose the Dobot USB port." if ports else "No USB serial devices found.")
        except ImportError:
            self.status_text.set("Install the hardware dependencies from the setup guide.")

    def _launch(self, job, action):
        if self.busy or self.closing:
            return
        self.busy = job
        self.stop_signal.clear()

        def run():
            try:
                self.worker_events.put((job, action(), None))
            except Exception as error:
                self.worker_events.put((job, None, error))

        Thread(target=run, daemon=True, name=f"robot-{job}").start()
        self._render()

    def connect(self):
        if self.demo or self.busy:
            return
        if self.robot:
            if self.armed:
                self.stop("Disarmed. Click Disconnect again to close USB.")
                return
            self._launch("disconnect", self.robot.close)
            return
        port = self.port.get().strip()
        if not port:
            self.status_text.set("Select or enter the Dobot USB serial port.")
            return

        def open_robot():
            robot = Magician(port)
            try:
                return robot, robot.pose()
            except Exception:
                robot.close()
                raise

        self.status_text.set(f"Connecting to {port}…")
        self._launch("connect", open_robot)

    def home(self):
        if not self.robot or self.armed or self.busy:
            return
        if not messagebox.askokcancel("Home the Dobot", "The arm will move to find its reference. "
                                      "Clear the entire workspace and keep the physical stop within reach.",
                                      icon="warning", parent=self.root):
            return
        self.homed = False
        self.points.clear()
        self.status_text.set("Homing. Keep the arm's workspace clear.")
        self._launch("home", lambda: self.robot.home(self.stop_signal))

    def teach(self, name):
        if self.homed and self.robot and not self.armed and not self.busy:
            self._launch("teach " + name, self.robot.pose)

    def change_input(self, _event=None):
        self.gate.reset()
        self.tracked_at = self.synthetic_until = 0
        self.classifier = None
        mode = self.input_mode.get()
        if mode in TRAINABLE:
            self.vision_text.set("Start camera or open training")
        elif self.demo:
            self.vision_text.set("Neutral hand" if mode == HAND else "Neutral pose")
        self._draw_preview()
        self._render()

    def show_programs(self):
        if (self.armed or self.busy or self.camera or self.camera_closing
                or self.training_window or self.workcell or self.program_menu):
            return
        self._build_picker()
        self.desktop.pack_forget()
        self.program_menu.pack(fill="both", expand=True)

    def _build_picker(self):
        self.picker_notice = tk.StringVar()
        self.program_menu = build_program_picker(self, self.picker_notice)

    def show_connect(self):
        """The first screen, and the way back to it: connect and home the arm, then try it."""
        if (self.armed or self.busy or self.camera or self.camera_closing
                or self.training_window or self.workcell):
            return
        if self.program_menu:
            self.program_menu.destroy()
            self.program_menu = self.connect_screen = None
        else:
            self.desktop.pack_forget()
        if self.demo and not self.robot:
            self.set_mode(False)
        self.connect_screen = ConnectScreen(self)
        self.program_menu = self.connect_screen.canvas
        self.program_menu.pack(fill="both", expand=True)
        if not self.demo and not self.robot:
            self.scan_ports()
        self._render()

    def leave_connect(self):
        if self.program_menu:
            self.program_menu.destroy()
            self.program_menu = self.connect_screen = None
        self.show_programs()

    def version(self):
        """The commit this copy is on, for the footer. Empty if it is not a git copy."""
        if self._version is None:
            self._version = Updater(self.app_folder).version()
        return self._version

    def show_updates(self):
        """Open the Check for updates window."""
        if self.update_dialog and self.update_dialog.window.winfo_exists():
            self.update_dialog.window.lift()
            return
        self.update_dialog = UpdateDialog(self)
        self.update_dialog.window.wait_visibility()
        self.update_dialog.window.grab_set()

    def restart(self):
        """Close Dobot Studio as usual, then start it again. Used after an update."""
        self.restart_requested = True
        self._version = None
        self.quit()

    def jog(self, delta):
        """Move the tool a small step from where it is."""
        if self.robot and self.homed and not self.busy and not self.armed and not self.closing:
            self.status_text.set("Moving…")
            self._launch("jog", lambda: self.robot.jog(delta, self.stop_signal))

    def hold(self, tool, holding):
        """Turn the suction on or off, or close or open the gripper, to try it."""
        if self.robot and not self.busy and not self.armed and not self.closing:
            def apply():
                self.robot.set_attachment(tool, holding)
                return tool, holding
            self._launch("tool", apply)

    def _notice(self, text):
        """A short message on the programs page."""
        if self.program_menu is not None and not self.connect_screen and getattr(self, "picker_notice", None):
            self.picker_notice.set(text)

    def open_program(self, name, tries=0):
        if name in ("control", "train"):
            if self.program_menu:
                self.program_menu.destroy()
                self.program_menu = None
                self.desktop.pack(fill="both", expand=True)
            if name == "train":
                self.open_training()
        elif name in ("sort", "inspect", "math", "blocks", "teach", "tictactoe"):
            # The programs page stays where it is until the program's own window is up, so a program
            # that cannot open yet never leaves a different screen behind.
            if self.workcell or self.armed or self.busy or self.closing:
                self._notice("Wait for the arm to finish what it is doing, then choose again.")
                return
            if self.camera or self.camera_closing:
                if tries < 40:
                    self._notice("The camera is closing. The program will open in a moment…")
                    self.root.after(250, lambda: self.open_program(name, tries + 1) if self.program_menu else None)
                else:
                    self._notice("The camera did not close. Unplug it and plug it in again, then choose again.")
                return
            self._notice("")
            if name == "blocks":
                self.workcell = BlockProgram(self)
            elif name == "teach":
                self.workcell = TeachProgram(self)
            elif name == "tictactoe":
                self.workcell = TicTacToeProgram(self)
            else:
                self.workcell = Workcell(self, name)
            self.workcell.window.wait_visibility()
            self.workcell.window.grab_set()
            self._render()

    def end_workcell(self):
        """A program's window closed: back to the programs page, with the arm's state brought up to date."""
        self.workcell = None
        if self.program_menu is not None and not self.connect_screen:
            self.program_menu.destroy()
            self._build_picker()
            self.program_menu.pack(fill="both", expand=True)
        self._render()

    def open_training(self):
        if self.armed or self.busy or self.closing or self.training_window or self.workcell or self.camera_closing:
            return
        mode = self.input_mode.get()
        if mode not in TRAINABLE:
            mode = choose_training_mode(self)
            if mode is None:
                return
            self.input_mode.set(mode)
            self.change_input()
        error = None
        try:
            classes = load_classes(self.training_folder, mode)
        except (OSError, ValueError) as failure:
            error = str(failure)
            classes = empty_classes()
        training = TrainingWindow(self, mode, classes)
        self.training_window = training
        self.gate.reset()
        self.tracked_at = 0
        training.window.wait_visibility()
        training.window.grab_set()
        if self.camera is None:
            self._start_camera()
        if error:
            training.status.set(error)
        self._render()

    def update_training(self, mode, classifier):
        if self.input_mode.get() == mode:
            self.classifier = classifier
            self.tracked_at = 0
            self.gate.reset()
            if self.camera:
                self.camera.set_classifier(classifier)

    def end_training(self):
        self.training_window = None
        self.tracked_at = 0
        self.gate.reset()
        self._draw_preview()
        self._render()

    def toggle_camera(self):
        if self.camera_closing or self.training_window:
            return
        if self.camera:
            if self.armed:
                self.stop("Camera stopped. Controls disarmed.")
            self._close_camera()
            self.status_text.set("Camera stopped.")
        elif not self.armed:
            self._start_camera()
        self._render()

    def _start_camera(self):
        device = self.camera_device.get().strip()
        if not device:
            message = "Enter a camera index such as 0, or a path such as /dev/video0."
            self.status_text.set(message)
            if self.training_window:
                self.training_window.camera_lost(message)
            return
        self.camera_token += 1
        token = self.camera_token
        mode = self.input_mode.get()
        self.classifier = None
        self.tracked_at = self.last_frame = 0
        self.gate.reset()
        message = "Opening the USB camera…"
        args = ()
        if mode in TRAINABLE:
            try:
                classes = load_classes(self.training_folder, mode)
                if len(classes) >= 2:
                    self.classifier = Recognizer(mode, classes)
            except (ImportError, OSError, ValueError) as error:
                message = str(error)
            args = (self.classifier,)
        self.camera = Camera(device, mode, self.models,
                             lambda error: self.worker_events.put(("camera", token, error)), *args)
        self.status_text.set(message)
        self.vision_text.set("Waiting for camera")
        self._draw_preview()

    def _close_camera(self):
        self.camera_token += 1
        if self.camera:
            self.camera.close()
            self.camera_closing = self.camera
        self.camera = self.preview = self.preview_photo = None
        self.tracked_at = self.last_frame = 0
        self.gate.reset()
        self.vision_text.set("Waiting for camera")
        self._draw_preview()

    def enable(self):
        if self.armed:
            self.stop("Controls disarmed.")
            return
        if self.busy or self.closing or self.training_window or self.workcell:
            return
        if not self._simulated_input() and (not self._tracking_ready()
                or self.input_mode.get() in TRAINABLE and self.classifier is None):
            return
        if not self.demo:
            if not self.robot or not self.homed or len(self.points) != 2:
                return
            if not self.points["A"].near(self.points["B"], mm=POSITION_LIMIT_MM, degrees=ROTATION_LIMIT_DEG):
                self.status_text.set(f"Teach positions within {POSITION_LIMIT_MM} mm and {ROTATION_LIMIT_DEG}°.")
                return
            if not messagebox.askokcancel("Enable gesture control", "Confirm the straight path between "
                                          "A and B is clear. Start with the arm at A or B and show a neutral "
                                          "gesture before requesting a move.", parent=self.root):
                return
            if self.closing or self.training_window or not self._tracking_ready():
                return
        self.armed = True
        self.gate.reset()
        self.status_text.set("Controls enabled. Show neutral, then hold a command input.")
        self._render()

    def stop(self, reason):
        was_armed = self.armed
        self.armed = False
        self.gate.reset()
        self.status_text.set(reason)
        if self.busy in ("home", "move", "jog"):
            self.stop_signal.set()
            if not self.demo:
                self.homed = False
                self.points.clear()
        elif self.robot and not self.busy and (was_armed or reason.startswith("Stopped")):
            self._launch("stop", self.robot.stop)
        self._render()

    def simulate(self, action):
        if self._simulated_input():
            self.synthetic = action
            self.synthetic_until = monotonic() + 0.75 if action else 0

    def _observe(self, detection):
        self.vision_text.set(detection.label)
        if detection.tracked:
            self.tracked_at = detection.timestamp
        elif self.armed:
            self.gate.reset()
            return
        if not self.armed or self.training_window or self.workcell:
            return
        action = self.gate.observe(detection)
        if action == "Stop":
            self.stop("Stopped by the tracking input.")
        elif action and not self.busy and action in self.points:
            target = self.points[action]
            self.status_text.set(f"Position {action} requested.")
            if self.demo:
                self.busy = "move"
                self.stop_signal.clear()

                def simulate_move():
                    if self.stop_signal.is_set():
                        self._finish("move", None, MotionStopped("Demo move stopped."))
                    else:
                        self._finish("move", target, None)

                self.root.after(425, simulate_move)
            else:
                origins = tuple(self.points.values())
                self._launch("move", lambda: self.robot.move(target, origins, self.stop_signal))

    def _finish(self, job, result, error):
        if job == "camera":
            if result != self.camera_token:
                return
            if self.armed:
                self.stop("Camera lost. Controls disarmed.")
            self._close_camera()
            self.status_text.set(str(error))
            if self.training_window:
                self.training_window.camera_lost(str(error))
            return
        self.busy = None
        if error:
            self.armed = False
            if job == "jog" and isinstance(error, StopUnconfirmed):
                self.homed = False
            if job in ("move", "home", "stop") and not self.demo:
                self.homed = False
                self.position = None
                self.points.clear()
            self.status_text.set(str(error))
            if self.closing and (isinstance(error, StopUnconfirmed) or job == "stop"):
                self.closing = False
            if job == "disconnect":
                self.robot = self.position = None
                self.homed = False
                self.points.clear()
        elif job == "connect":
            self.robot, self.position = result
            self.status_text.set("Dobot connected. Clear the workspace and home the arm.")
        elif job == "disconnect":
            self.robot = self.position = None
            self.homed = False
            self.points.clear()
            self.status_text.set("Dobot disconnected.")
        elif job == "home":
            if not self.stop_signal.is_set():
                self.homed, self.position = True, result
                self.status_text.set("Homed. Position the tool and use Teach for each preset.")
        elif job.startswith("teach "):
            name = job[-1]
            self.points[name] = self.position = result
            self.status_text.set(f"Captured position {name}.")
        elif job == "move":
            self.position = result
            if not self.stop_signal.is_set():
                self.status_text.set("Position reached.")
            if self.demo:
                self._draw_preview()
        elif job == "stop":
            self.status_text.set("Dobot force-stop acknowledged. Controls disarmed.")
        elif job == "jog":
            self.position = result
            self.status_text.set("Moved. Tool at " + result.label())
        elif job == "tool":
            tool, holding = result
            action = {(True, True): "Suction on.", (False, True): "Gripper closed.",
                      (True, False): "Suction off.", (False, False): "Gripper open."}
            self.status_text.set(action[(tool == "Suction cup", holding)])
        self._render()

    def _tick(self):
        if self.camera_closing and not self.camera_closing.thread.is_alive():
            self.camera_closing = None
        while True:
            try:
                job, result, error = self.worker_events.get_nowait()
            except Empty:
                break
            self._finish(job, result, error)
        if self.closing:
            if not self.busy:
                if self.robot:
                    try:
                        self.robot.close()
                    except OSError:
                        pass
                self.root.destroy()
                return
            self.root.after(35, self._tick)
            return
        now = monotonic()
        if self._simulated_input():
            action = self.synthetic if now < self.synthetic_until else None
            names = dict(zip(("A", "B", "Stop"), SOURCE[self.input_mode.get()]))
            neutral = "Neutral hand" if self.input_mode.get() == HAND else "Neutral pose"
            self._observe(Detection(action, names.get(action, neutral), True, now))
        elif self.camera:
            latest = self.camera.read()
            if latest and latest[0].timestamp > self.last_frame:
                first = self.last_frame == 0
                detection, self.preview = latest
                self.last_frame = detection.timestamp
                if now - detection.timestamp < TRACK_TIMEOUT:
                    self._observe(detection)
                if self.training_window:
                    self.training_window.show(detection, self.preview)
                else:
                    self._draw_preview()
                if first and not self.training_window:
                    self.status_text.set("Camera active. Check the detected input in the preview.")
            if self.armed and now - self.tracked_at >= TRACK_TIMEOUT:
                self.stop("Tracking lost. Controls disarmed.")
        self._render()
        self.root.after(35, self._tick)

    def quit(self):
        if self.closing:
            return
        if self.workcell:
            self.workcell.close()
            if self.workcell:
                return
        if self.training_window:
            self.training_window.close()
            if self.training_window:
                return
        if self.busy in ("move", "home") or self.armed:
            self.stop("Stopping before exit…")
        self.closing = True
        self._close_camera()
        self._render()


def choose_training_mode(studio):
    if studio.camera is not None:
        studio.status_text.set("Stop the camera before switching to a training mode.")
        return None
    dialog = tk.Toplevel(studio.root, bg=PANEL, padx=18, pady=14)
    dialog.title("Choose what to train")
    dialog.transient(studio.root)
    studio._label(dialog, "Choose what to train", size=13, weight="bold", fg=PURPLE).pack(anchor="w")
    selection = []

    def choose(value):
        selection.append(value)
        dialog.destroy()

    for option in TRAINABLE:
        studio._button(dialog, option, lambda value=option: choose(value)).pack(fill="x", pady=(6, 0))
    dialog.wait_visibility()
    dialog.grab_set()
    studio.root.wait_window(dialog)
    return selection[0] if selection else None


def main():
    parser = argparse.ArgumentParser(description="Dobot Studio desktop controls")
    parser.add_argument("--models", type=Path, default=Path(__file__).resolve().parents[1] / "models",
                        help="folder containing the MediaPipe .task files")
    parser.add_argument("--training-data", type=Path, default=default_training_folder(),
                        help="folder for local training profiles")
    args = parser.parse_args()
    root = tk.Tk()
    set_window_icon(root)
    studio = Studio(root, args.models.resolve(), args.training_data.resolve())
    studio.show_connect()
    if desktop.ensure():
        studio.status_text.set("A Dobot Studio icon was added to the desktop and the applications menu.")
    root.mainloop()
    if studio.restart_requested:
        relaunch()


def set_window_icon(root):
    """The picture in the title bar and the taskbar. A missing icon is not a reason to stop."""
    try:
        root._icon = tk.PhotoImage(file=str(ICON))       # kept so it is not garbage collected
        root.iconphoto(True, root._icon)
    except tk.TclError:
        pass


def relaunch():
    """Start Dobot Studio again from its own folder with the same options."""
    os.chdir(APP_FOLDER)
    os.execv(sys.executable, [sys.executable, "-m", "dobot_studio", *sys.argv[1:]])
