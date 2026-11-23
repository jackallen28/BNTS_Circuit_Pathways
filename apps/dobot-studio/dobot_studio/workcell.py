"""The common overhead camera for chip sorting and assembly inspection."""
from pathlib import Path
from queue import Empty, SimpleQueue
from tempfile import NamedTemporaryFile
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .math_lab import EquationLab
from .learning import SYMBOL, Recognizer, load_classes, new_symbol_descriptor
from .robot import ATTACHMENTS, GRIPPER_TOOL, SUCTION_TOOL, MotionStopped, Pose
from .tabletop import COLOURS, Calibration, find_chips, inspect_assembly, inspection_view, same_chip
from .theme import DARK, MUTED, PANEL, PURPLE, WHITE
from .vision import Camera, TABLETOP


MARKS = ("Mark 1", "Mark 2", "Mark 3")
LOCATIONS = (*MARKS, "Bin A", "Bin B", "Park")
COLOUR_MODE, TEXT_MODE = "Colour", "Trained text/symbols"
MAX_STAGES = 100


class Workcell:
    def __init__(self, studio, program):
        self.studio = studio
        self.frame = self.empty = self.photo = None
        self.image_area = None
        self.last_frame = 0.0
        self.marks, self.poses, self.stages = {}, {}, {}
        self.stages_dirty = False
        self.pending_mark = None
        self.chips, self.findings = [], []
        self.events = SimpleQueue()
        self.stop_event = Event()
        self.busy = self.camera = None
        self.classifier = self.descriptor = None
        self.transfer_count = 0
        self.window = tk.Toplevel(studio.root, bg="#e9eff8", padx=11, pady=10)
        self.window.title("Tabletop workcell")
        self.window.transient(studio.root)
        width = min(1040, studio.root.winfo_screenwidth()-32)
        height = min(685, studio.root.winfo_screenheight()-50)
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(820, 510)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.stop())
        self.status = tk.StringVar(value="Open the overhead USB camera to begin.")
        self.teaching = tk.StringVar(value=MARKS[0])
        self.colour_a, self.colour_b = tk.StringVar(value="Red"), tk.StringVar(value="Blue")
        self.chip_mode = tk.StringVar(value=COLOUR_MODE)
        self.stage_name, self.stage_note, self.stage_ref = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.goal = tk.StringVar(value="Build")
        self.device = tk.StringVar(value=studio.camera_device.get())
        self.attachment = tk.StringVar(value=SUCTION_TOOL)
        self._build()
        self.tabs.select({"inspect": self.inspect_tab, "math": self.math_tab}.get(program, self.sort_tab))
        self.window.after(50, self._tick)

    def _build(self):
        ui = self.studio
        top = tk.Frame(self.window, bg="#dce9f6", padx=11, pady=6)
        top.pack(fill="x", pady=(0, 7))
        ui._label(top, "Tabletop workcell", size=15, weight="bold", fg=PURPLE,
                  bg="#dce9f6").pack(side="left")
        ui._label(top, "DEMO" if ui.demo else "LOCAL USB", size=9, fg=PURPLE,
                  bg="#dce9f6").pack(side="left", padx=10)
        self.close_button = ui._button(top, "Done", self.close)
        self.close_button.pack(side="right")
        self.camera_button = ui._button(top, "Start camera", self.toggle_camera, "Teal")
        self.camera_button.pack(side="right", padx=5)
        if ui.demo:
            self.usb_setup = ui._button(top, "Set up USB arm", self.setup_usb)
            self.usb_setup.pack(side="right")
        self.camera_entry = ttk.Entry(top, textvariable=self.device, width=6)
        self.camera_entry.pack(side="right")
        ui._label(top, "Camera", size=9, fg=MUTED, bg="#dce9f6").pack(side="right", padx=5)

        body = tk.Frame(self.window, bg="#e9eff8")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        preview, image_box = ui._pane(body, "Overhead view")
        preview.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.canvas = tk.Canvas(image_box, width=340, height=300, bg=DARK, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.canvas.bind("<Button-1>", self._select_mark)
        ui._button(image_box, "Capture empty tray", self.capture_empty).pack(anchor="w", pady=(5, 0))

        self.tabs = ttk.Notebook(body)
        self.tabs.grid(row=0, column=1, sticky="nsew")
        self.sort_tab = tk.Frame(self.tabs, bg=PANEL, padx=8, pady=7)
        self.inspect_tab = tk.Frame(self.tabs, bg=PANEL, padx=8, pady=7)
        self.tabs.add(self.sort_tab, text="Sort chips")
        self.tabs.add(self.inspect_tab, text="Inspect assembly")
        self.math_tab = tk.Frame(self.tabs, bg=PANEL, padx=8, pady=7)
        self.tabs.add(self.math_tab, text="Equation lab")
        self.math = EquationLab(self, self.math_tab)
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._draw())

        guide = ("Choose a mark, click it in the camera, and teach the tool position."
                 if not ui.demo else "Use demo coordinates to test routing with the camera.")
        ui._label(self.sort_tab, guide, size=9, fg=MUTED, wraplength=318,
                  justify="left").pack(fill="x", pady=(0, 4))
        teach_row = tk.Frame(self.sort_tab, bg=PANEL)
        teach_row.pack(fill="x")
        ttk.Combobox(teach_row, textvariable=self.teaching, values=LOCATIONS,
                     state="readonly", width=12).pack(side="left")
        self.teach_button = ui._button(teach_row, "Teach point", self.teach)
        self.teach_button.pack(side="left", padx=5)
        if ui.demo:
            ui._button(teach_row, "Demo coordinates", self.demo_coordinates).pack(side="left")
        self.points_status = ui._label(self.sort_tab, size=9, fg=PURPLE, wraplength=318,
                                       justify="left")
        self.points_status.pack(fill="x", pady=(4, 6))

        method = tk.Frame(self.sort_tab, bg=PANEL)
        method.pack(fill="x")
        ui._label(method, "Read by", size=9, fg=MUTED).pack(side="left", padx=(0, 5))
        self.methods = ttk.Combobox(method, textvariable=self.chip_mode,
                                    values=(COLOUR_MODE, TEXT_MODE), width=18, state="readonly")
        self.methods.pack(side="left")
        self.methods.bind("<<ComboboxSelected>>", self.change_sort_mode)
        colours = tk.Frame(self.sort_tab, bg=PANEL)
        colours.pack(fill="x", pady=(5, 0))
        for label, value in (("Bin A", self.colour_a), ("Bin B", self.colour_b)):
            ui._label(colours, label, size=9, fg=MUTED).pack(side="left", padx=(3, 4))
            chooser = ttk.Combobox(colours, textvariable=value, values=COLOURS, width=8, state="readonly")
            chooser.pack(side="left")
            chooser.bind("<<ComboboxSelected>>", self.change_sort_mode)

        self.sort_report = tk.StringVar(value="Scan shows chip labels, bins and estimated areas.")
        report = ui._label(self.sort_tab, textvariable=self.sort_report, size=9, wraplength=325,
                           justify="left")
        report.configure(anchor="nw")
        report.pack(fill="both", expand=True, pady=(7, 3))
        controls = tk.Frame(self.sort_tab, bg=PANEL)
        controls.pack(fill="x")
        self.scan_button = ui._button(controls, "Scan tray", self.scan)
        self.scan_button.pack(side="left")
        self.sort_button = ui._button(controls, "Sort next", self.sort_next, "Teal")
        self.sort_button.pack(side="left", padx=5)
        if not ui.demo:
            self.release_button = ui._button(controls, "Release tool", self.release)
            self.release_button.pack(side="left")

        form = tk.Frame(self.inspect_tab, bg=PANEL)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        for row, label, var in ((0, "Stage name", self.stage_name), (1, "Step note", self.stage_note)):
            ui._label(form, label, size=9, fg=MUTED).grid(row=row, column=0, sticky="w", padx=(0, 5))
            ttk.Entry(form, textvariable=var, width=23).grid(row=row, column=1, sticky="ew", pady=2)
        ui._button(self.inspect_tab, "Capture stage", self.capture_stage).pack(anchor="w", pady=4)
        reference = tk.Frame(self.inspect_tab, bg=PANEL)
        reference.pack(fill="x", pady=(3, 0))
        ttk.Combobox(reference, values=("Build", "Repair", "Disassemble"), textvariable=self.goal,
                     width=11, state="readonly").pack(side="left")
        self.stage_picker = ttk.Combobox(reference, values=(), textvariable=self.stage_ref,
                                         width=14, state="readonly")
        self.stage_picker.pack(side="left", padx=4)
        ui._button(reference, "Inspect", self.inspect, "Teal").pack(side="left")
        self.inspection_report = tk.StringVar(value="Capture ordered reference stages under fixed lighting. "
                                                    "Choose a reference and inspect the live view.")
        report = ui._label(self.inspect_tab, textvariable=self.inspection_report, size=9,
                           wraplength=325, justify="left")
        report.configure(anchor="nw")
        report.pack(fill="both", expand=True, pady=5)
        file_row = tk.Frame(self.inspect_tab, bg=PANEL)
        file_row.pack(fill="x")
        ui._button(file_row, "Save stages…", self.save_stages).pack(side="left")
        ui._button(file_row, "Open stages…", self.open_stages).pack(side="left", padx=5)

        footer = tk.Frame(self.window, bg="#dce9f6", padx=8, pady=4)
        footer.pack(fill="x", pady=(6, 0))
        self.stop_button = ui._button(footer, "Stop  ·  Esc", self.stop, "Stop")
        self.stop_button.pack(side="right")
        if not ui.demo:
            self.attachment_box = ttk.Combobox(footer, values=ATTACHMENTS, textvariable=self.attachment,
                                               width=11, state="readonly")
            self.attachment_box.pack(side="right", padx=5)
            self.attachment_box.bind("<<ComboboxSelected>>", self.change_attachment)
        ui._label(footer, textvariable=self.status, size=9, bg="#dce9f6", wraplength=740,
                  justify="left").pack(side="left", fill="x", expand=True)
        self._controls()

    def setup_usb(self):
        if self.camera or self.studio.camera_closing or self.busy:
            self.status.set("Stop the camera before switching to USB setup.")
            return
        self.close()
        if self.studio.workcell:
            return
        self.studio.set_mode(False)
        self.studio.status_text.set("Connect and home the arm, then return to Chip sorting from Programs.")

    def _forget_view(self):
        self.frame = self.empty = None
        self.marks.clear()
        self.poses.clear()
        self.chips = []
        self.findings = []
        self.pending_mark = None
        self.math.divider = None
        self.math.reset()

    def change_attachment(self, _event=None):
        self.poses.clear()
        self.chips = []
        self.math.reset()
        self.status.set("Attachment changed. Teach pickup marks, bins and Park for the fitted tool.")
        self._controls()

    def toggle_camera(self):
        if self.busy:
            return
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
            self.camera = None
            self._forget_view()
            self.status.set("Camera closed. Calibrate again after reopening it.")
        else:
            if self.studio.camera_closing or not self.device.get().strip():
                self.status.set("Wait for the camera to close or enter a camera device.")
                return
            self.last_frame = 0
            self.camera = Camera(self.device.get().strip(), TABLETOP, self.studio.models,
                                 lambda error: self.events.put(("camera", None, error)))
            self.status.set("Opening the overhead camera…")
        self._controls()
        self._draw()

    def _fresh_frame(self):
        now = monotonic()
        if self.frame is None or now - self.last_frame > 0.65:
            raise ValueError("Wait for a fresh overhead camera frame.")
        return self.frame

    def capture_empty(self):
        if self.busy:
            return
        try:
            self.empty = self._fresh_frame().copy()
        except ValueError as error:
            self.status.set(str(error))
            return
        self.chips = []
        self.findings = []
        self.status.set("Empty tray captured. Place separated chips or an assembly in the view.")
        self._controls()

    def _select_mark(self, event):
        label = self.teaching.get()
        if self._inspection() or self.busy or self.image_area is None:
            return
        left, top, width, height, scale = self.image_area
        x, y = event.x - left, event.y - top
        if 0 <= x < width and 0 <= y < height:
            if self.tabs.select() == str(self.math_tab):
                self.math.click(y / scale)
                return
            if label not in MARKS:
                return
            self.pending_mark = label, (x / scale, y / scale)
            self.status.set(f"{label} selected. Align the fitted tool at this mark, then click Teach point.")
            self._draw()

    def _start_job(self, name, action):
        self.busy = name
        self.stop_event.clear()

        def run():
            try:
                self.events.put((name, action(), None))
            except Exception as error:
                self.events.put((name, None, error))

        Thread(target=run, name=f"workcell-{name}", daemon=True).start()
        self._controls()

    def teach(self):
        if self.busy:
            return
        name = self.teaching.get()
        mark = self.pending_mark
        if name in MARKS and (not mark or mark[0] != name):
            self.status.set("Click the matching mark in the overhead image first.")
            return
        if self.studio.demo:
            self.status.set("Use Demo coordinates to set sample calibration and bins.")
            return
        if not self.studio.robot or not self.studio.homed:
            self.status.set("Connect and home the Dobot in the control program first.")
            return
        self._start_job("teach", lambda: (name, self.studio.robot.pose(), mark))

    def demo_coordinates(self):
        if self.busy:
            return
        try:
            height, width = self._fresh_frame().shape[:2]
        except ValueError as error:
            self.status.set(str(error))
            return
        pixels = ((width*.18, height*.83), (width*.82, height*.83), (width*.5, height*.14))
        self.marks = dict(zip(MARKS, pixels))
        self.poses = dict(zip(LOCATIONS, (
            Pose(195, -55, 30, 0), Pose(195, 55, 30, 0), Pose(278, 0, 30, 0),
            Pose(184, -65, 35, 0), Pose(184, 65, 35, 0), Pose(165, 0, 65, 0),
        )))
        self.chips = []
        self.status.set("Demo calibration and bins set.")
        self._controls()
        self._draw()

    def change_sort_mode(self, _event=None):
        self.chips = []
        if self.chip_mode.get() == TEXT_MODE:
            self.sort_report.set("Uses text or symbol classes trained with Position A or B.")
        else:
            self.sort_report.set("Select distinct colours for each bin.")
        self._controls()
        self._draw()

    def _calibration(self):
        if not all(label in self.marks and label in self.poses for label in MARKS):
            raise ValueError("Teach the three calibrated pickup marks.")
        return Calibration(tuple(self.marks[name] for name in MARKS), tuple(self.poses[name] for name in MARKS))

    def _recognise(self):
        frame = self._fresh_frame()
        if self.empty is None:
            raise ValueError("Capture the empty tray before scanning.")
        calibration = self._calibration()
        if self.chip_mode.get() == COLOUR_MODE:
            a, b = self.colour_a.get(), self.colour_b.get()
            if a == b:
                raise ValueError("Choose two different bin colours.")
            return find_chips(frame, self.empty, calibration, {a: "A", b: "B"})
        return self.recognise_text()

    def recognise_text(self):
        frame = self._fresh_frame()
        if self.empty is None:
            raise ValueError("Capture the empty tray before scanning.")
        calibration = self._calibration()
        if self.classifier is None:
            classes = load_classes(self.studio.training_folder, SYMBOL)
            if len(classes) < 2:
                raise ValueError("Train a printed/drawn symbol profile before sorting text.")
            self.classifier = Recognizer(SYMBOL, classes)
            self.descriptor = new_symbol_descriptor()
        return find_chips(frame, self.empty, calibration, None, self.classifier, self.descriptor)

    def scan(self):
        if self.busy:
            return
        try:
            self.chips = self._recognise()
        except (ImportError, OSError, ValueError) as error:
            self.chips = []
            self.status.set(str(error))
        else:
            self.status.set(f"Found {len(self.chips)} chips inside the calibrated area.")
            self.sort_report.set("\n".join(
                f"{chip.label} · {chip.area_mm2:.0f} mm² · {('Bin ' + chip.bin_name) if chip.bin_name else 'Unmapped'}"
                for chip in self.chips[:5]) or "No isolated chips found inside the triangle.")
        self._controls()
        self._draw()

    def sort_next(self):
        if self.busy:
            return
        previous = next((chip for chip in self.chips if chip.bin_name), None)
        if previous is None:
            self.status.set("Scan the tray and find a chip with a bin first.")
            return
        try:
            if not all(name in self.poses for name in ("Bin A", "Bin B", "Park")):
                raise ValueError("Teach both bins and the park pose.")
            if not self.studio.demo and (not self.studio.robot or not self.studio.homed):
                raise ValueError("Connect and home the Dobot before sorting.")
            tool = self.attachment.get()
            instruction = "Check that the selected tool is fitted and the path is clear."
            if tool == GRIPPER_TOOL:
                instruction += " Confirm jaw clearance and a grippable chip."
            if not self.studio.demo and not messagebox.askokcancel(
                    "Sort one chip", instruction, parent=self.window):
                return
            chip = next((value for value in self._recognise() if same_chip(previous, value)), None)
            if chip is None:
                raise ValueError("The selected chip changed or moved. Scan the tray again.")
            park = self.poses["Park"]
            calibration = self._calibration()
            if any(calibration.contains_robot(self.poses[name]) for name in ("Bin A", "Bin B", "Park")):
                raise ValueError("Keep the bins and park position outside the calibrated pickup triangle.")
            pick = calibration.pick(chip.centre, park.r)
            drop = self.poses[f"Bin {chip.bin_name}"]
        except (ImportError, OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.chips = []
        self.status.set(f"{'Simulating' if self.studio.demo else 'Transferring'} {chip.label} to Bin {chip.bin_name}.")

        def perform():
            if self.studio.demo:
                if self.stop_event.wait(0.7):
                    raise MotionStopped("Demo transfer stopped.")
                return park
            return self.studio.robot.sort_chip(pick, drop, park, self.stop_event, tool)

        self._start_job("sort", perform)

    def release(self):
        if self.busy or not self.studio.robot:
            return
        if messagebox.askokcancel("Release tool", "Support the chip before releasing it.", parent=self.window):
            tool = self.attachment.get()
            self._start_job("release", lambda: self.studio.robot.set_attachment(tool, False))

    def stop(self):
        if self.busy in ("sort", "math"):
            self.stop_event.set()
            self.status.set("Stopping the transfer…")

    def _inspection(self):
        return self.tabs.select() == str(self.inspect_tab)

    def capture_stage(self):
        name = self.stage_name.get().strip()
        if len(self.stages) >= MAX_STAGES:
            self.status.set(f"A plan can contain up to {MAX_STAGES} stages.")
            return
        if not name or len(name) > 32 or name in self.stages:
            self.status.set("Enter a unique stage name of up to 32 characters.")
            return
        try:
            image = inspection_view(self._fresh_frame())
        except ValueError as error:
            self.status.set(str(error))
            return
        self.stages[name] = (self.stage_note.get().strip()[:200], image)
        self.stages_dirty = True
        self._show_stages(name)
        self.stage_name.set("")
        self.stage_note.set("")
        self.status.set(f"Captured {name}.")

    def _show_stages(self, active):
        self.stage_picker.configure(values=tuple(self.stages))
        self.stage_ref.set(active)

    def inspect(self):
        reference = self.stage_ref.get()
        if reference not in self.stages:
            self.status.set("Choose a captured stage to compare against.")
            return
        try:
            current = inspection_view(self._fresh_frame())
        except ValueError as error:
            self.status.set(str(error))
            return
        note, expected = self.stages[reference]
        baseline = inspection_view(self.empty) if self.empty is not None else None
        self.findings = inspect_assembly(current, expected, baseline)
        if self.findings:
            summary = "; ".join(f"{zone}: {cause.lower()}" for zone, cause in self.findings)
            self.inspection_report.set(f"Check {reference}. {summary}. {note}")
        else:
            names = tuple(self.stages)
            index = names.index(reference)
            goal = self.goal.get()
            if goal == "Build" and index + 1 < len(names):
                step = names[index + 1]
                self.inspection_report.set(f"{reference} matches. Next stage: {step}. {self.stages[step][0]}")
            elif goal == "Disassemble" and index:
                self.inspection_report.set(f"{reference} matches. Return to the previous stage: {names[index - 1]}.")
            else:
                self.inspection_report.set(f"No changes detected at this scale from {reference}. {note}")
        self._draw()

    def save_stages(self):
        if not self.stages:
            self.status.set("Capture at least one reference stage.")
            return
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".npz",
                                            filetypes=[("Dobot assembly stages", "*.npz")])
        if not path:
            return
        import numpy as np
        target = Path(path)
        temporary = None
        try:
            names = tuple(self.stages)
            notes, images = zip(*self.stages.values())
            with NamedTemporaryFile(dir=target.parent, suffix=".npz", delete=False) as file:
                temporary = Path(file.name)
                np.savez_compressed(file, names=names, notes=notes, images=np.stack(images))
            temporary.replace(target)
        except OSError as error:
            self.status.set(str(error))
        else:
            self.stages_dirty = False
            self.status.set(f"Saved {len(names)} reference stages in {target.name}.")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _discard_unsaved(self):
        return not self.stages_dirty or messagebox.askokcancel(
            "Unsaved assembly stages", "Discard unsaved reference stages?", parent=self.window)

    def open_stages(self):
        if not self._discard_unsaved():
            return
        path = filedialog.askopenfilename(parent=self.window,
                                          filetypes=[("Dobot assembly stages", "*.npz")])
        if not path:
            return
        import numpy as np
        try:
            with np.load(path, allow_pickle=False) as saved:
                names, notes, images = saved["names"], saved["notes"], saved["images"]
                if (names.ndim != 1 or notes.ndim != 1 or not 0 < len(names) <= MAX_STAGES
                        or images.shape != (len(names), 180, 180, 3) or images.dtype != np.uint8
                        or names.dtype.kind != "U" or notes.dtype.kind != "U" or len(notes) != len(names)
                        or len(set(names)) != len(names)
                        or any(not name or len(name) > 32 for name in names)):
                    raise ValueError("Invalid assembly stages file.")
                self.stages = {str(name): (str(note)[:200], image)
                               for name, note, image in zip(names, notes, images)}
        except (OSError, KeyError, TypeError, ValueError) as error:
            self.status.set(str(error))
        else:
            self._show_stages(next(iter(self.stages)))
            self.stages_dirty = False
            self.findings = []
            self.status.set("Assembly stages opened. Use the same camera position, scale and lighting.")

    def _draw(self):
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 8 or height < 8:
            return
        canvas.delete("all")
        self.image_area = None
        if self.frame is None:
            canvas.create_text(width/2, height/2, text="Overhead camera offline", fill=WHITE)
            return
        from PIL import Image, ImageTk

        h, w = self.frame.shape[:2]
        scale = min(width/w, height/h)
        iw, ih = round(w*scale), round(h*scale)
        left, top = (width-iw)/2, (height-ih)/2
        self.image_area = left, top, iw, ih, scale
        image = Image.fromarray(self.frame).resize((iw, ih), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        canvas.create_image(left, top, image=self.photo, anchor="nw")

        def point(x, y):
            return left+x*scale, top+y*scale

        if self._inspection():
            extent = min(w, h) * 3 // 4
            x0, y0 = (w-extent)/2, (h-extent)/2
            changed = {zone for zone, _ in self.findings}
            for row in range(3):
                for col in range(3):
                    zone = f"{'ABC'[row]}{col+1}"
                    x, y = point(x0+col*extent/3, y0+row*extent/3)
                    rx, by = x+extent*scale/3, y+extent*scale/3
                    active = zone in changed
                    canvas.create_rectangle(x, y, rx, by, outline="#eb8d79" if active else "#6ad7e2",
                                            width=3 if active else 1)
                    canvas.create_text(x+5, y+4, anchor="nw", text=zone, fill="#137385" if not active else "#b52c23")
        else:
            marks = self.marks.copy()
            if self.pending_mark:
                label, value = self.pending_mark
                marks[label] = value
            if len(marks) == 3:
                triangle = [value for name in MARKS for value in point(*marks[name])]
                canvas.create_polygon(*triangle, outline="#39cbd2", width=2, fill="")
            for name, location in marks.items():
                x, y = point(*location)
                canvas.create_oval(x-5, y-5, x+5, y+5, outline="#c9faff", fill="#287888")
                canvas.create_text(x+7, y-3, text=name, fill=WHITE, anchor="sw")
            if self.tabs.select() == str(self.math_tab) and self.math.divider is not None:
                first, last = point(0, self.math.divider), point(w, self.math.divider)
                canvas.create_line(*first, *last, fill="#72e1e2", width=2, dash=(6, 4))
            for chip in self.chips:
                x, y, w, h = chip.bounds
                first, last = point(x, y), point(x+w, y+h)
                tag = f"{chip.label} → {chip.bin_name}" if chip.bin_name else chip.label
                canvas.create_rectangle(*first, *last, outline="#4dd6de", width=2)
                canvas.create_text(first[0], first[1]-3, text=tag, fill=WHITE, anchor="sw")

    def _controls(self):
        ui = self.studio
        enabled = self.busy is None
        points = len(self.marks)
        places = sum(name in self.poses for name in ("Bin A", "Bin B", "Park"))
        self.points_status.configure(text=f"Pickup marks {points}/3  ·  Bins and park {places}/3")
        self.camera_button.configure(text="Stop camera" if self.camera else "Start camera")
        self.camera_entry.configure(state="normal" if enabled and not self.camera else "disabled")
        ui._set_button(self.camera_button, enabled)
        ui._set_button(self.teach_button, enabled)
        ui._set_button(self.scan_button, enabled)
        ui._set_button(self.sort_button, enabled and any(chip.bin_name for chip in self.chips))
        ui._set_button(self.stop_button, self.busy in ("sort", "math"))
        if not ui.demo:
            self.attachment_box.configure(state="readonly" if enabled else "disabled")
            ui._set_button(self.release_button, enabled and ui.robot is not None)
        self.math._render()

    def _tick(self):
        while True:
            try:
                job, data, error = self.events.get_nowait()
            except Empty:
                break
            if job == "camera":
                self.status.set(str(error))
                if self.busy in ("sort", "math"):
                    self.stop_event.set()
                if self.camera:
                    self.studio.camera_closing = self.camera
                self.camera = None
                self._forget_view()
                self._controls()
                self._draw()
            else:
                self.busy = None
                if error:
                    self.status.set(str(error))
                    if job == "math":
                        self.math.complete(error)
                    if job in ("sort", "math") and not self.studio.demo:
                        self.studio.homed = False
                        self.studio.points.clear()
                elif job == "teach":
                    name, pose, mark = data
                    self.poses[name] = pose
                    if name in MARKS:
                        self.marks[name] = mark[1]
                    self.pending_mark = None
                    self.chips = []
                    self.status.set(f"{name} taught.")
                elif job == "sort":
                    self.studio.position = data
                    self.transfer_count += 1
                    action = "Simulated transfers" if self.studio.demo else "Completed transfer commands"
                    self.status.set(f"{action}: {self.transfer_count}. Check the chip and scan again.")
                elif job == "math":
                    if data:
                        self.studio.position = data
                    self.math.complete(None)
                elif job == "release":
                    self.status.set("Tool release acknowledged.")
                self._controls()
        if self.camera:
            latest = self.camera.read()
            if latest and latest[0].timestamp > self.last_frame:
                import numpy as np
                self.last_frame = latest[0].timestamp
                self.frame = np.asarray(latest[1])
                self._draw()
        if self.busy in ("sort", "math") and not self.stop_event.is_set() and monotonic() - self.last_frame > 0.8:
            self.stop_event.set()
            self.status.set("Overhead camera stalled. Stopping the transfer.")
        self.window.after(50, self._tick)

    def close(self):
        if self.busy:
            self.stop()
            return
        if not self._discard_unsaved():
            return
        if self.camera:
            self.camera.close()
            self.studio.camera_closing = self.camera
        self.window.destroy()
        self.studio.end_workcell()
