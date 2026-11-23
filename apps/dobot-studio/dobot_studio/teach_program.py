"""Micro:bit tilt teaching and local, editable path playback."""
import json
from math import dist, isfinite
from pathlib import Path
from queue import Empty, SimpleQueue
from tempfile import NamedTemporaryFile
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .microbit_link import TiltLink, inside, jog
from .robot import ATTACHMENTS, SUCTION_TOOL, Magician, MotionStopped, Pose
from .theme import DARK, MUTED, PANEL, PURPLE

HOME = Pose(220, 0, 75, 0)
MAX_STEPS = 400


class TeachProgram:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root, bg="#e9eff8", padx=10, pady=10)
        self.window.title("Micro:bit Teach")
        self.window.transient(studio.root)
        self.window.geometry(f"{min(1040, studio.root.winfo_screenwidth()-32)}x"
                             f"{min(680, studio.root.winfo_screenheight()-55)}")
        self.window.minsize(830, 535)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.stop())
        self.status = tk.StringVar(value="Home the arm to begin.")
        self.pose_label = tk.StringVar()
        self.micro_port = tk.StringVar(value="/dev/ttyACM0")
        self.arm_port = tk.StringVar(value=studio.port.get())
        self.attachment = tk.StringVar(value=SUCTION_TOOL)
        self.axis_mode = tk.StringVar(value="XY plane")
        self.use_clutch = tk.BooleanVar(value=False)
        self.origin = self.pose = self.path_origin = None
        self.neutral = self.link = self.sample = self.busy = None
        self.records = []
        self.dirty = False
        self.play_queue = []
        self.traces = []
        self.path_tool = SUCTION_TOOL
        self.homed = self.live = self.recording = self.paused = self.playing = False
        self.pause_after = False
        self.micro_epoch = 0
        self.last_jog = 0.0
        self.events = SimpleQueue()
        self.abort = Event()
        self._build()
        self._render()
        self.window.after(60, self._tick)

    def _build(self):
        ui = self.studio
        header = tk.Frame(self.window, bg="#dce9f6", padx=9, pady=6)
        header.pack(fill="x", pady=(0, 7))
        ui._label(header, "Micro:bit Teach", size=16, weight="bold", fg=PURPLE,
                  bg="#dce9f6").pack(side="left")
        ui._label(header, "DEMO" if ui.demo else "USB TEACHING", size=9, bg="#dce9f6",
                  fg=MUTED).pack(side="left", padx=8)
        ui._button(header, "Done", self.close).pack(side="right")
        if ui.demo:
            ui._button(header, "Set up USB arm", self.setup_usb).pack(side="right", padx=5)

        workspace = tk.Frame(self.window, bg="#e9eff8")
        workspace.pack(fill="both", expand=True)
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)
        picture, view = ui._pane(workspace, "Tool path", "Top view")
        picture.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.canvas = tk.Canvas(view, bg=DARK, highlightthickness=0, width=390, height=230)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        ui._label(view, textvariable=self.pose_label, size=9, fg=PURPLE).pack(fill="x", pady=(4, 0))

        panel, tools = ui._pane(workspace, "Teach sequence")
        panel.grid(row=0, column=1, sticky="nsew")
        if not ui.demo:
            connections = tk.Frame(tools, bg=PANEL)
            connections.pack(fill="x", pady=3)
            connections.columnconfigure(1, weight=1)
            for i, (label, value, callback) in enumerate((
                ("Dobot", self.arm_port, self.connect_arm), ("Micro:bit", self.micro_port, self.connect_micro),
            )):
                ui._label(connections, label, size=9).grid(row=i, column=0, sticky="w")
                ttk.Entry(connections, textvariable=value, width=15).grid(row=i, column=1, sticky="ew", padx=5)
                button = ui._button(connections, "Connect", callback)
                button.grid(row=i, column=2, sticky="ew", pady=2)
                if i == 0:
                    self.arm_button = button
                else:
                    self.micro_button = button

        setup = tk.Frame(tools, bg=PANEL)
        setup.pack(fill="x", pady=3)
        self.home_button = ui._button(setup, "Home", self.home)
        self.home_button.pack(side="left")
        self.centre_button = ui._button(setup, "Set centre", self.centre)
        self.centre_button.pack(side="left", padx=4)
        self.tool_picker = ttk.Combobox(setup, values=ATTACHMENTS, textvariable=self.attachment,
                                        width=11, state="readonly")
        self.tool_picker.pack(side="right")
        self.tool_picker.bind("<<ComboboxSelected>>", self.tool_changed)

        live = tk.Frame(tools, bg=PANEL)
        live.pack(fill="x", pady=3)
        ttk.Combobox(live, values=("XY plane", "Z height"), textvariable=self.axis_mode,
                     width=10, state="readonly").pack(side="left")
        self.start_button = ui._button(live, "Start", self.start, "Teal")
        self.start_button.pack(side="left", padx=4)
        self.record_button = ui._button(live, "Record", self.record, "Purple")
        self.record_button.pack(side="left")
        self.pause_button = ui._button(live, "Pause", self.pause)
        self.pause_button.pack(side="left", padx=4)

        if not ui.demo:
            self.clutch_box = ttk.Checkbutton(tools, text="Hold A+B to jog", variable=self.use_clutch)
            self.clutch_box.pack(anchor="w", pady=(1, 3))
        if ui.demo:
            demo = tk.Frame(tools, bg=PANEL)
            demo.pack(fill="x", pady=3)
            for label, values in (("←", (-400,0)), ("→", (400,0)), ("↑", (0,400)), ("↓", (0,-400))):
                ui._button(demo, label, lambda axes=values: self.move(axes)).pack(side="left", padx=(0, 3))
            for label, holding in (("A", True), ("B", False)):
                ui._button(demo, label, lambda state=holding: self.tool(state)).pack(side="left", padx=(0, 3))

        list_area = tk.Frame(tools, bg=PANEL)
        list_area.pack(fill="both", expand=True, pady=4)
        self.timeline = ttk.Treeview(list_area, columns=("step", "action"), show="headings",
                                     height=5, selectmode="browse")
        for col, text, width in (("step", "#", 37), ("action", "Recorded step", 264)):
            self.timeline.heading(col, text=text)
            self.timeline.column(col, width=width, stretch=col=="action")
        scroll = ttk.Scrollbar(list_area, orient="vertical", command=self.timeline.yview)
        self.timeline.configure(yscrollcommand=scroll.set)
        self.timeline.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.timeline.bind("<<TreeviewSelect>>", lambda _event: self._render())

        edits = tk.Frame(tools, bg=PANEL)
        edits.pack(fill="x", pady=3)
        self.cut_button = ui._button(edits, "Cut from selected", self.cut)
        self.cut_button.pack(side="left")
        self.save_button = ui._button(edits, "Save", self.save)
        self.save_button.pack(side="left", padx=5)
        self.open_button = ui._button(edits, "Open", self.open)
        self.open_button.pack(side="left")
        playback = tk.Frame(tools, bg=PANEL)
        playback.pack(fill="x", pady=3)
        self.play_button = ui._button(playback, "Play / replay", self.play, "Teal")
        self.play_button.pack(side="left")
        self.rewind_button = ui._button(playback, "Return to start", self.rewind)
        self.rewind_button.pack(side="left", padx=5)
        if not ui.demo:
            self.release_button = ui._button(playback, "Release tool", self.release)
            self.release_button.pack(side="left")
        footer = tk.Frame(self.window, bg="#dce9f6", padx=8, pady=4)
        footer.pack(fill="x", pady=(6, 0))
        ui._label(footer, textvariable=self.status, size=9, bg="#dce9f6",
                  wraplength=660, justify="left").pack(side="left", fill="x", expand=True)
        self.stop_button = ui._button(footer, "Stop  ·  Esc", self.stop, "Stop")
        self.stop_button.pack(side="right")

    def setup_usb(self):
        self.close()
        if self.studio.workcell is None:
            self.studio.set_mode(False)
            self.studio.show_programs()

    def _job(self, name, action):
        if self.busy:
            return
        self.busy = name
        self.abort.clear()

        def work():
            try:
                self.events.put((name, action(), None))
            except Exception as error:
                self.events.put((name, None, error))

        Thread(target=work, name=f"teach-{name}", daemon=True).start()
        self._render()

    def connect_arm(self):
        if self.live or self.playing or self.busy or self.studio.robot:
            return
        port = self.arm_port.get().strip()
        if not port or port == self.micro_port.get().strip():
            self.status.set("Specify the Dobot’s separate USB serial port.")
            return

        def connect():
            robot = Magician(port)
            try:
                return robot, robot.pose()
            except Exception:
                robot.close()
                raise

        self._job("connect", connect)

    def connect_micro(self):
        if self.live or self.playing or self.busy:
            return
        self.micro_epoch += 1
        epoch = self.micro_epoch
        self.sample = self.neutral = None
        if self.link:
            self.link.close()
            self.link = None
            self.status.set("Micro:bit disconnected.")
        else:
            port = self.micro_port.get().strip()
            if not port or port == self.arm_port.get().strip():
                self.status.set("Enter the Micro:bit USB port, usually /dev/ttyACM0.")
                return
            self.link = TiltLink(port, lambda error: self.events.put(("micro", epoch, error)))
            self.status.set("Waiting for the Micro:bit teaching firmware…")
        self._render()

    def home(self):
        if self.live or self.playing or self.busy:
            return
        if self.studio.demo:
            self.homed = True
            self.origin = self.pose = HOME
            self.status.set("Demo homed. Click Start to enable jogging.")
        elif self.studio.robot and messagebox.askokcancel(
                "Home the Dobot", "Clear the arm’s workspace. Homing moves the tool.", parent=self.window):
            self.homed = self.studio.homed = False
            self.studio.points.clear()
            self._job("home", lambda: self.studio.robot.home(self.abort))
        self._render()

    def centre(self):
        if self.live or self.playing or self.busy or not self.homed:
            return
        if self.studio.demo:
            self.origin = self.pose
        else:
            self._job("centre", self.studio.robot.pose)
        self._render()

    def tool_changed(self, _event=None):
        if not self.studio.demo:
            self.origin = None
            self.status.set("Set the centre again for the fitted attachment.")
        self._render()

    def start(self):
        if self.busy or self.live or self.playing or not self.homed or not self.origin:
            return
        if not self.studio.demo:
            sample = self.sample
            if sample is None or monotonic()-sample.timestamp > 0.6:
                self.status.set("Connect the Micro:bit and wait for a fresh tilt sample.")
                return
            if sample.clutch:
                self.status.set("Release both buttons and hold the Micro:bit at neutral.")
                return
            if not messagebox.askokcancel("Start tilt teaching", "Set down any load and check the taught area. "
                                          "Tilt commands can move the robot after Start.", parent=self.window):
                return
            sample = self.sample
            if not sample or sample.clutch or monotonic()-sample.timestamp > 0.6:
                self.status.set("Wait at neutral for a fresh Micro:bit sample.")
                return
            neutral = sample.x, sample.y

            def verify():
                actual = self.studio.robot.pose()
                if not inside(self.origin, actual):
                    raise ValueError("Guide the fitted tool back into its taught area.")
                return actual, neutral

            self._job("start", verify)
            return
        self._begin_live()

    def _begin_live(self):
        self.live = True
        self.paused = False
        method = "Hold A+B and tilt" if self.use_clutch.get() else "Tilt to jog"
        self.status.set(f"Live teaching. {method}. A grips or holds, B releases.")
        self._render()

    def move(self, axes):
        if not self.live or self.paused or self.busy or self.pose is None:
            return
        target = jog(self.pose, self.origin, axes, self.axis_mode.get() == "Z height")
        if target:
            self._motion(target)

    def _motion(self, target):
        origin = self.pose
        if self.studio.demo:
            action = lambda: target
        else:
            action = lambda: self.studio.robot.move(target, (origin,), self.abort)
        self._job("move", action)

    def release(self):
        if self.busy or self.live or self.playing or not self.studio.robot:
            return
        if messagebox.askokcancel("Release tool", "Support the load before releasing it.", parent=self.window):
            tool = self.attachment.get()
            self._job("release", lambda: self.studio.robot.set_attachment(tool, False))

    def tool(self, holding):
        if not self.live or self.paused or self.busy:
            return
        self._tool_job(holding)

    def _tool_job(self, holding):
        tool = self.attachment.get()

        def apply():
            if not self.studio.demo:
                self.studio.robot.set_attachment(tool, holding)
            return holding

        self._job("tool", apply)

    def record(self):
        if not self.live or self.busy or self.paused or self.recording:
            return
        if self.records and not messagebox.askokcancel(
                "Start a new recording", "Replace the current timeline?", parent=self.window):
            return
        self.path_origin, self.path_tool = self.pose, self.attachment.get()
        self.records = []
        self.dirty = False
        self.recording = True
        self.status.set("Recording completed moves and tool actions.")
        self._sync_timeline()

    def pause(self):
        if not (self.live or self.playing):
            return
        self.paused = not self.paused
        self.status.set("Paused after the current step." if self.paused else "Resumed.")
        self._render()

    def stop(self):
        moving = self.busy in ("move", "home")
        self.abort.set()
        self.live = self.recording = self.playing = self.paused = False
        self.play_queue = []
        if moving and not self.studio.demo:
            self.homed = self.studio.homed = False
            self.origin = None
        self.status.set("Stopping motion…" if moving else "Stopped. The recorded timeline is ready.")
        self._render()

    def cut(self):
        if self.live or self.playing or self.busy:
            return
        selected = self.timeline.selection()
        if selected:
            index = int(selected[0])
            if messagebox.askokcancel("Cut timeline", "Remove the selected step and everything after it?",
                                      parent=self.window):
                del self.records[index:]
                self.dirty = bool(self.records)
                self._sync_timeline()

    def play(self):
        self._start_playback(False)

    def rewind(self):
        self._start_playback(True)

    def _start_playback(self, reverse):
        if self.busy or self.live or self.playing or not self.homed or not self.records:
            return
        if self.path_tool != self.attachment.get():
            self.status.set("Select the attachment recorded in the timeline.")
            return
        positions = [self.path_origin, *(value for kind, value in self.records if kind == "move")]
        expected = positions[-1] if reverse else self.path_origin
        if self.studio.demo:
            self.pose = expected
        elif not messagebox.askokcancel(
                "Replay teaching path" if not reverse else "Return to start",
                "Clear the path and verify the fitted tool. Return to start replays positions only.",
                parent=self.window):
            return
        targets = ([("move", value) for value in reversed(positions[:-1])]
                   if reverse else list(self.records))
        if self.studio.demo:
            self._begin_playback(targets, reverse)
        else:
            def verify():
                actual = self.studio.robot.pose()
                if not actual.near(expected, mm=3, degrees=3):
                    where = "the last recorded pose" if reverse else "the recorded starting pose"
                    raise ValueError(f"Guide the fitted tool to {where} first.")
                return actual, targets, reverse

            self._job("verify-playback", verify)

    def _begin_playback(self, targets, reverse):
        self.play_queue = targets
        self.playing, self.paused = True, False
        self.status.set("Returning to start…" if reverse else "Playing the recording…")
        self._render()

    def _sync_timeline(self):
        self.timeline.delete(*self.timeline.get_children())
        for index, (kind, value) in enumerate(self.records):
            text = ("Move  " + value.label()) if kind == "move" else ("Grip / suction on" if value else "Release")
            self.timeline.insert("", "end", str(index), values=(index+1, text))
        if self.records:
            self.timeline.see(str(len(self.records)-1))
        self._render()

    def save(self):
        if not self.records or self.live or self.playing or self.busy:
            return
        name = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                           filetypes=[("Dobot teaching path", "*.json")])
        if not name:
            return
        target, temporary = Path(name), None
        try:
            with NamedTemporaryFile(mode="w", dir=target.parent, encoding="utf-8", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": 1, "tool": self.path_tool, "origin": self.path_origin.wire(),
                           "steps": [(kind, value.wire() if kind == "move" else value)
                                     for kind, value in self.records]}, stream, allow_nan=False)
            temporary.replace(target)
            self.dirty = False
            self.status.set(f"Saved {target.name}.")
        except (OSError, ValueError) as error:
            self.status.set(str(error))
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _discard_unsaved(self):
        return not self.dirty or messagebox.askokcancel(
            "Unsaved teaching path", "Discard the unsaved timeline?", parent=self.window)

    def open(self):
        if self.live or self.playing or self.busy or not self._discard_unsaved():
            return
        name = filedialog.askopenfilename(parent=self.window, filetypes=[("Dobot teaching path", "*.json")])
        if not name:
            return
        try:
            with Path(name).open(encoding="utf-8") as stream:
                origin, tool, steps = read_path(json.load(stream))
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
            self.status.set(str(error))
            return
        self.path_origin, self.path_tool, self.records = origin, tool, steps
        self.dirty = False
        self.status.set(f"Loaded {len(steps)} steps.")
        self._sync_timeline()

    def _tick(self):
        while True:
            try:
                job, data, error = self.events.get_nowait()
            except Empty:
                break
            if job == "micro":
                if data == self.micro_epoch:
                    self.link = self.sample = None
                    if self.live:
                        self.stop()
                    self.status.set(str(error))
                continue
            self.busy = None
            if error:
                self.live = self.recording = self.playing = self.paused = False
                if job in ("home", "move") and not self.studio.demo:
                    self.homed = self.studio.homed = False
                    self.origin = None
                self.status.set(str(error))
            elif job == "connect":
                self.studio.robot, self.pose = data
                self.studio.port.set(self.arm_port.get())
                self.status.set("Dobot connected. Home the arm.")
            elif job in ("home", "centre"):
                self.origin = self.pose = data
                self.studio.position = data
                self.homed = self.studio.homed = True
                self.status.set("Centre set. Hold the Micro:bit at neutral and click Start.")
            elif job == "release":
                self.status.set("Tool release acknowledged.")
            elif job == "start":
                self.pose, self.neutral = data
                if not self.abort.is_set() and self.sample and monotonic() - self.sample.timestamp < 0.6:
                    self._begin_live()
            elif job == "verify-playback":
                self.pose, targets, reverse = data
                if not self.abort.is_set():
                    self._begin_playback(targets, reverse)
            elif job in ("move", "tool"):
                if job == "move":
                    self.pose = data
                    self.traces = (*self.traces[-100:], data)
                    if not self.studio.demo:
                        self.studio.position = data
                if self.recording:
                    if len(self.records) >= MAX_STEPS or (job == "move" and not inside(self.path_origin, data)):
                        self.recording = False
                        self.status.set("Recording reached its size or travel limit.")
                    else:
                        self.records.append((job, data))
                        self.dirty = True
                        self._sync_timeline()
        if self.link:
            previous = self.sample
            self.sample, buttons = self.link.read()
            if self.sample and previous is None:
                self.status.set("Micro:bit connected. Hold it at neutral and click Start after homing.")
            if self.live and (not self.sample or monotonic()-self.sample.timestamp > 0.7):
                self.stop()
                self.status.set("Micro:bit data lost. Teaching stopped.")
            elif self.live and not self.paused and not self.busy:
                fresh = next((value.button for value in reversed(buttons) if monotonic()-value.timestamp < 0.3), None)
                if fresh:
                    self.tool(fresh == "A")
                elif (self.sample and (not self.use_clutch.get() or self.sample.clutch)
                      and monotonic()-self.last_jog >= 0.19):
                    self.last_jog = monotonic()
                    axes = (self.sample.x-self.neutral[0], self.sample.y-self.neutral[1])
                    self.move(axes)
        if self.playing and not self.paused and not self.busy:
            if self.play_queue:
                kind, value = self.play_queue.pop(0)
                self._motion(value) if kind == "move" else self._tool_job(value)
            else:
                self.playing = False
                self.status.set("Playback complete.")
        self._render()
        self.window.after(60, self._tick)

    def _draw(self):
        canvas = self.canvas
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if min(w,h) < 8:
            return
        canvas.delete("all")
        centre = self.path_origin or self.origin or HOME
        scale = min(w/82, h/82)
        point = lambda p: (w/2+(p.x-centre.x)*scale, h/2-(p.y-centre.y)*scale)
        for offset in range(-30,31,10):
            canvas.create_line(w/2+offset*scale, h/2-33*scale,
                               w/2+offset*scale,h/2+33*scale, fill="#28425e")
            canvas.create_line(w/2-33*scale, h/2+offset*scale,
                               w/2+33*scale,h/2+offset*scale, fill="#28425e")
        poses = [self.path_origin, *(v for kind,v in self.records if kind == "move")] if self.records else self.traces
        if len(poses) > 1:
            canvas.create_line(*(coord for pose in poses for coord in point(pose)), fill="#71e0e5", width=3)
        if self.pose:
            x,y = point(self.pose)
            canvas.create_oval(x-6,y-6,x+6,y+6,fill="#edc07c",outline="#fff4d4")
        canvas.create_text(11, 11, text=f"{len(self.records)} recorded steps", anchor="nw", fill="#a4c3de")

    def _render(self):
        idle = not self.live and not self.playing and not self.busy
        self.pose_label.set(self.pose.label() if self.pose else "Position unavailable")
        for button, enabled in (
            (self.home_button, idle and (self.studio.demo or self.studio.robot)),
            (self.centre_button, idle and self.homed),
            (self.start_button, idle and self.homed and self.origin and (self.studio.demo or self.sample)),
            (self.record_button, self.live and not self.recording and not self.paused and not self.busy),
            (self.pause_button, self.live or self.playing),
            (self.cut_button, idle and bool(self.timeline.selection())),
            (self.save_button, idle and bool(self.records)), (self.open_button, idle),
            (self.play_button, idle and self.homed and bool(self.records)),
            (self.rewind_button, idle and self.homed and bool(self.records)),

            (self.stop_button, self.live or self.playing or
             self.busy in ("move", "home", "start", "verify-playback")),
        ):
            self.studio._set_button(button, enabled)
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        self.tool_picker.configure(state="readonly" if idle else "disabled")
        if not self.studio.demo:
            self.clutch_box.state(["!disabled"] if idle else ["disabled"])
            self.studio._set_button(self.arm_button, idle and not self.studio.robot)
            self.studio._set_button(self.micro_button, idle)
            self.studio._set_button(self.release_button, idle and self.studio.robot is not None)
            self.micro_button.configure(text="Disconnect" if self.link else "Connect")
        self._draw()

    def close(self):
        if self.busy:
            self.stop()
            return
        if not self._discard_unsaved():
            return
        if self.link:
            self.link.close()
        self.window.destroy()
        self.studio.end_workcell()


def read_path(data):
    def pose(values):
        if (not isinstance(values, list) or len(values) != 4
                or any(type(value) not in (float, int) or not isfinite(value) for value in values)):
            raise ValueError("Invalid recorded position.")
        return Pose(*values)

    tool = data["tool"]
    if data["version"] != 1 or tool not in ATTACHMENTS or not 1 <= len(data["steps"]) <= MAX_STEPS:
        raise ValueError("Unsupported teaching path.")
    origin = pose(data["origin"])
    records = []
    previous = origin
    for kind, value in data["steps"]:
        if kind == "move":
            value = pose(value)
            if not inside(origin, value) or dist(previous.xyz(), value.xyz()) > 8:
                raise ValueError("A recorded move is outside the taught area or exceeds a teaching step.")
            previous = value
        elif kind != "tool" or type(value) is not bool:
            raise ValueError("Unknown recorded action.")
        records.append((kind, value))
    return origin, tool, records
