"""Camera and pieces: how the Pi reads the picture, and teaching it the X and O pieces.

It opens only from the setup steps. The live view people watch while playing is the camera's own picture. What
is set here changes the Pi's reading, and (for the camera's own controls) what the camera sends.
"""
import tkinter as tk
from tkinter import ttk

from .camera_tune import (
    AUTO_EXPOSURE_NAMES, AUTOMATIC, CameraControls, EXPOSURE_NAMES, FOCUS_AUTO_NAMES, MANUAL, WHITE_AUTO_NAMES, Tune,
    apply, interesting,
)
from .pieces import KINDS, WANTED
from .theme import BORDER, DARK, GREEN, MUTED, PANEL, PURPLE, RED
from .tictactoe import O, X

PREVIEW = (300, 169)
SLIDERS = (("brightness", "Brightness", -100, 100), ("contrast", "Contrast", 0.5, 3.0),
           ("gamma", "Shadows (gamma)", 0.4, 2.5), ("sharpen", "Sharpen", 0.0, 3.0))


class TuneDialog:
    def __init__(self, program, controls=None):
        self.p = program
        self.studio = program.studio
        self.controls = controls or CameraControls(program.device.get().strip())
        self.listed = []
        self.hardware = {}               # control name -> its variable
        self.photos = []
        self.message = tk.StringVar()
        window = self.window = tk.Toplevel(program.window, bg=PANEL, padx=14, pady=10)
        window.title("Camera and pieces")
        window.transient(program.window)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda _event: self.close())
        self._build()
        window.update_idletasks()
        x = program.window.winfo_rootx() + max(10, (program.window.winfo_width() - window.winfo_reqwidth()) // 2)
        y = program.window.winfo_rooty() + 20
        window.geometry(f"+{x}+{y}")
        window.wait_visibility()
        window.grab_set()
        self.look_again()
        self._preview()

    # ---- the layout
    def _build(self):
        ui = self.studio
        header = tk.Frame(self.window, bg="#dcebf7", padx=12, pady=7)
        header.pack(fill="x")
        ui._label(header, "Camera and pieces", size=14, weight="bold", fg=PURPLE, bg="#dcebf7").pack(anchor="w")
        ui._label(header, "Only here, while setting up. Playing uses what you set, and shows the camera's own picture.",
                  size=9, fg=MUTED, bg="#dcebf7", wraplength=620, justify="left").pack(anchor="w")
        previews = tk.Frame(self.window, bg=PANEL)
        previews.pack(fill="x", pady=(8, 4))
        self.canvases = []
        for title in ("What you see", "What the Pi reads"):
            box = tk.Frame(previews, bg=PANEL)
            box.pack(side="left", expand=True)
            ui._label(box, title, size=9, weight="bold", fg=MUTED).pack()
            canvas = tk.Canvas(box, width=PREVIEW[0], height=PREVIEW[1], bg="#0d1b2a", highlightthickness=1,
                               highlightbackground=BORDER)
            canvas.pack()
            self.canvases.append(canvas)
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True, pady=(4, 0))
        self.camera_tab, self.pieces_tab = tk.Frame(self.tabs, bg=PANEL, padx=8, pady=6), tk.Frame(self.tabs, bg=PANEL, padx=8, pady=6)
        self.tabs.add(self.camera_tab, text="Camera")
        self.tabs.add(self.pieces_tab, text="Teach the pieces")
        self._build_camera()
        self._build_pieces()
        footer = tk.Frame(self.window, bg=PANEL)
        footer.pack(fill="x", pady=(8, 0))
        self.message_label = ui._label(footer, textvariable=self.message, size=9, weight="bold", wraplength=470,
                                       justify="left")
        self.message_label.pack(side="left", fill="x", expand=True)
        self.close_button = ui._button(footer, "Done", self.close, "Purple")
        self.close_button.pack(side="right", ipadx=10)

    def _build_camera(self):
        ui, tab = self.studio, self.camera_tab
        ui._label(tab, "How the Pi reads the picture  (the live view is not changed)", size=9, weight="bold",
                  fg=DARK).pack(anchor="w")
        self.variables = {}
        for key, label, low, high in SLIDERS:
            row = tk.Frame(tab, bg=PANEL)
            row.pack(fill="x")
            ui._label(row, label, size=9, fg=MUTED).pack(side="left", padx=(0, 6))
            variable = tk.DoubleVar(value=getattr(self.p.tune, key))
            self.variables[key] = variable
            shown = tk.StringVar()
            variable.trace_add("write", lambda *_, key=key, shown=shown: self._tune_changed(key, shown))
            ttk.Scale(row, from_=low, to=high, variable=variable, length=250).pack(side="left", fill="x", expand=True)
            ui._label(row, textvariable=shown, size=9, fg=DARK).pack(side="left", padx=(6, 0))
            self._tune_changed(key, shown)
        self.reset_button = ui._button(tab, "Reset the Pi's reading", self.reset_tune)
        self.reset_button.pack(anchor="w", pady=(4, 8))
        ui._label(tab, "The camera itself  (this also changes the live view)", size=9, weight="bold", fg=DARK).pack(anchor="w")
        self.hardware_frame = tk.Frame(tab, bg=PANEL)
        self.hardware_frame.pack(fill="x")
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", pady=(4, 0))
        self.lock_button = ui._button(row, "Lock exposure, focus and colour", self.lock_camera)
        self.lock_button.pack(side="left")
        self.look_button = ui._button(row, "Look again", self.look_again)
        self.look_button.pack(side="left", padx=(6, 0))
        ui._label(tab, "Locking stops the camera changing its own exposure and focus when pieces move in front of it.",
                  size=9, fg=MUTED, wraplength=560, justify="left").pack(anchor="w", pady=(3, 0))

    def _build_pieces(self):
        ui, tab = self.studio, self.pieces_tab
        ui._label(tab, "Show the camera your own X and O pieces so it can tell them apart more reliably. It is optional. "
                       f"Take about {WANTED} pictures of each kind for each mark.", size=9, fg=DARK, wraplength=580,
                  justify="left").pack(anchor="w")
        self.teach_buttons = {}
        grid = tk.Frame(tab, bg=PANEL)
        grid.pack(fill="x", pady=(6, 0))
        kinds = {"close": ("Close-up", "Hold one piece under the camera, on a dark surface, filling most of the picture."),
                 "distance": ("From a distance", "Camera in its place, and only pieces of this mark on the mat.")}
        for column, mark in enumerate((X, O)):
            box = tk.Frame(grid, bg=PANEL, padx=6)
            box.grid(row=0, column=column, sticky="nsew")
            grid.columnconfigure(column, weight=1)
            ui._label(box, f"{mark} pieces", size=10, weight="bold", fg=PURPLE).pack(anchor="w")
            for kind in KINDS:
                title, how = kinds[kind]
                button = ui._button(box, "", lambda mark=mark, kind=kind: self.teach(mark, kind))
                button.pack(fill="x", pady=(3, 0))
                self.teach_buttons[(mark, kind)] = (button, title)
                ui._label(box, how, size=8, fg=MUTED, wraplength=270, justify="left").pack(anchor="w")
        self.forget_button = ui._button(tab, "Forget what was taught", self.forget)
        self.forget_button.pack(anchor="w", pady=(8, 0))
        self._refresh_pieces()

    # ---- the Pi's reading
    def _tune_changed(self, key, shown):
        variable = self.variables[key]
        value = variable.get()
        shown.set(f"{value:+.0f}" if key == "brightness" else f"{value:.2f}")
        tune = self.p.tune.with_(**{key: value})
        if tune != self.p.tune:
            self.p.set_tune(tune)

    def reset_tune(self):
        for key, variable in self.variables.items():
            variable.set(getattr(Tune(), key))
        self.p.set_tune(Tune())

    # ---- the camera's own controls
    def look_again(self):
        self.listed = interesting(self.controls.list())
        for child in self.hardware_frame.winfo_children():
            child.destroy()
        self.hardware.clear()
        ui = self.studio
        if not self.listed:
            self._say(self.controls.problem or "This camera has no controls to change here.", RED if self.controls.problem else MUTED)
            ui._set_button(self.lock_button, False)
            return
        ui._set_button(self.lock_button, True)
        for control in self.listed:
            row = tk.Frame(self.hardware_frame, bg=PANEL)
            row.pack(fill="x")
            if control.kind in ("bool", "menu") and control.maximum <= 3:
                automatic = control.name in AUTO_EXPOSURE_NAMES
                on = control.value == AUTOMATIC if automatic else bool(control.value)
                variable = tk.BooleanVar(value=on)
                tk.Checkbutton(row, text=control.label, variable=variable, bg=PANEL, activebackground=PANEL, anchor="w",
                               highlightthickness=0, font=ui.theme.font(9),
                               command=lambda c=control, v=variable: self._toggle(c, v)).pack(side="left")
            else:
                ui._label(row, control.label, size=9, fg=MUTED).pack(side="left", padx=(0, 6))
                variable = tk.DoubleVar(value=control.value)
                scale = ttk.Scale(row, from_=control.minimum, to=control.maximum, variable=variable, length=250)
                scale.pack(side="left", fill="x", expand=True)
                shown = ui._label(row, text=str(control.value), size=9, fg=DARK)
                shown.pack(side="left", padx=(6, 0))
                scale.bind("<ButtonRelease-1>", lambda _e, c=control, v=variable, s=shown: self._slide(c, v, s))
            self.hardware[control.name] = variable
        self._say(f"{len(self.listed)} camera controls found.", MUTED)

    def _toggle(self, control, variable):
        value = bool(variable.get())
        if control.name in AUTO_EXPOSURE_NAMES:
            ok = self.controls.set(control.name, AUTOMATIC if value else MANUAL)
        else:
            ok = self.controls.set(control.name, int(value))
        self._report(ok, control)

    def _slide(self, control, variable, shown):
        value = round(variable.get() / max(control.step, 1)) * max(control.step, 1)
        value = min(control.maximum, max(control.minimum, value))
        if control.name in EXPOSURE_NAMES:              # a hand-set exposure means no automatic exposure
            self.controls.set_auto_exposure(False, self.listed)
            for name in AUTO_EXPOSURE_NAMES:
                if name in self.hardware:
                    self.hardware[name].set(False)
        shown.configure(text=str(value))
        self._report(self.controls.set(control.name, value), control)

    def _report(self, ok, control):
        self._say(f"{control.label} set." if ok else (self.controls.problem or f"The camera would not change {control.label}."),
                  GREEN if ok else RED)

    def lock_camera(self):
        """Stop automatic exposure, focus and white balance, keeping what they have settled on."""
        done = []
        for control in self.listed:
            if control.name in AUTO_EXPOSURE_NAMES:
                done.append(self.controls.set(control.name, MANUAL))
            elif control.name in FOCUS_AUTO_NAMES or control.name in WHITE_AUTO_NAMES:
                done.append(self.controls.set(control.name, 0))
        problem = self.controls.problem
        self.look_again()                       # show what the camera settled on
        if done and all(done):
            self._say("Exposure, focus and colour are locked. Move a slider if the picture is too dark or too bright.", GREEN)
        else:
            self._say(problem or "The camera would not lock some of these.", RED)

    # ---- teaching
    def teach(self, mark, kind):
        try:
            text = self.p.teach_piece(mark, kind)
        except ValueError as error:
            self._say(str(error), RED)
            return
        warnings = self.p.learned.warnings()
        self._say(text + (" " + warnings[0] if warnings else ""), RED if warnings else GREEN)
        self._refresh_pieces()

    def forget(self):
        self.p.learned.clear()
        self.p.latest, self.p.seen = None, 0
        self._say("Forgotten. The built-in reading is used.", MUTED)
        self._refresh_pieces()

    def _refresh_pieces(self):
        for (mark, kind), (button, title) in self.teach_buttons.items():
            button.configure(text=f"{title} of an {mark}  ({self.p.learned.count(mark, kind)} of {WANTED})")
        self.studio._set_button(self.forget_button, self.p.learned.ready())

    # ---- the pictures
    def _say(self, text, colour=MUTED):
        self.message.set(text)
        self.message_label.configure(fg=colour)

    def _preview(self):
        if not self.window.winfo_exists():
            return
        from PIL import Image, ImageTk
        import numpy as np

        feed = self.p.feed
        if feed is not None:
            small = feed.resize(PREVIEW, Image.Resampling.BILINEAR)
            adjusted = Image.fromarray(apply(np.asarray(small), self.p.tune))
            self.photos = [ImageTk.PhotoImage(picture, master=self.window) for picture in (small, adjusted)]
            for canvas, photo in zip(self.canvases, self.photos):
                canvas.delete("all")
                canvas.create_image(0, 0, image=photo, anchor="nw")
        else:
            for canvas in self.canvases:
                canvas.delete("all")
                canvas.create_text(PREVIEW[0] / 2, PREVIEW[1] / 2, text="Start the camera", fill="#ffffff")
        self.window.after(150, self._preview)

    def close(self):
        program = self.p
        program.tune_dialog = None
        self.window.grab_release()
        self.window.destroy()
        if program.window.winfo_exists():
            program.window.grab_set()
