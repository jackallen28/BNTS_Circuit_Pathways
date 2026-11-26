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
from .pieces import KINDS, WANTED, lab_to_rgb
from .tictactoe_vision import _patch_colour, body_colour, circle_positions, look, pixels_per_mm
from .theme import BORDER, DARK, GREEN, MUTED, PANEL, PURPLE, RED
from .tictactoe import O, X

PREVIEW = (180, 101)
TILE = 48                      # a circle as the Pi sees it, in the pieces tab
HARDWARE_HEIGHT = 118          # the camera controls scroll inside this much room
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
        window = self.window = tk.Toplevel(program.window, bg=PANEL, padx=14, pady=6)
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
        header = tk.Frame(self.window, bg="#dcebf7", padx=12, pady=3)
        header.pack(fill="x")
        ui._label(header, "Camera and pieces", size=13, weight="bold", fg=PURPLE, bg="#dcebf7").pack(anchor="w")
        ui._label(header, "Only here, while setting up. Playing uses what you set and shows the camera's own picture.",
                  size=9, fg=MUTED, bg="#dcebf7").pack(anchor="w")
        previews = tk.Frame(self.window, bg=PANEL)
        previews.pack(fill="x", pady=(6, 2))
        self.canvases = []
        for title in ("What you see", "What the Pi reads"):
            box = tk.Frame(previews, bg=PANEL)
            box.pack(side="left", expand=True)
            ui._label(box, title, size=9, weight="bold", fg=MUTED).pack()
            canvas = tk.Canvas(box, width=PREVIEW[0], height=PREVIEW[1], bg="#0d1b2a", highlightthickness=1,
                               highlightbackground=BORDER)
            canvas.pack()
            self.canvases.append(canvas)
        self.size_text = tk.StringVar()
        self.size_label = ui._label(self.window, textvariable=self.size_text, size=8, fg=MUTED, wraplength=640, justify="left")
        self.size_label.pack(fill="x")
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
        scroller = tk.Frame(tab, bg=PANEL)
        scroller.pack(fill="x")
        canvas = tk.Canvas(scroller, height=HARDWARE_HEIGHT, bg=PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(scroller, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="x", expand=True)
        self.hardware_frame = tk.Frame(canvas, bg=PANEL)
        window = canvas.create_window(0, 0, window=self.hardware_frame, anchor="nw")
        self.hardware_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        for widget in (canvas, self.hardware_frame):          # the wheel scrolls the list under the mouse
            widget.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            widget.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", pady=(4, 0))
        self.lock_button = ui._button(row, "Lock exposure, focus and colour", self.lock_camera)
        self.lock_button.pack(side="left")
        self.look_button = ui._button(row, "Look again", self.look_again)
        self.look_button.pack(side="left", padx=(6, 0))
        ui._label(tab, "Locking stops the camera changing its own exposure and focus when pieces move in front of it.",
                  size=8, fg=MUTED, wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))

    def _build_pieces(self):
        ui, tab = self.studio, self.pieces_tab
        ui._label(tab, "Optional: show the camera your own X and O pieces so it can tell them apart more reliably. "
                       f"Take about {WANTED} pictures of each kind for each mark.", size=9, fg=DARK, wraplength=600,
                  justify="left").pack(anchor="w")
        self.teach_buttons, self.swatches = {}, {}
        grid = tk.Frame(tab, bg=PANEL)
        grid.pack(fill="x", pady=(6, 0))
        kinds = {"close": ("Close-up", "Hold one piece under the camera, on a dark surface, filling most of the picture."),
                 "distance": ("From a distance", "Camera in its place, and only pieces of this mark on the mat.")}
        for column, mark in enumerate((X, O)):
            box = tk.Frame(grid, bg=PANEL, padx=6)
            box.grid(row=0, column=column, sticky="nsew")
            grid.columnconfigure(column, weight=1)
            title_row = tk.Frame(box, bg=PANEL)
            title_row.pack(fill="x")
            ui._label(title_row, f"{mark} pieces", size=10, weight="bold", fg=PURPLE).pack(side="left")
            swatch = tk.Canvas(title_row, width=18, height=18, bg=PANEL, highlightthickness=0)
            swatch.pack(side="left", padx=(8, 0))
            self.swatches[mark] = swatch
            for kind in KINDS:
                title, how = kinds[kind]
                button = ui._button(box, "", lambda mark=mark, kind=kind: self.teach(mark, kind))
                button.pack(fill="x", pady=(3, 0))
                self.teach_buttons[(mark, kind)] = (button, title)
        ui._label(tab, "Close-up: one piece under the camera, on a dark surface.  From a distance: the camera in its place and "
                       "only this mark's pieces on the mat. That also learns their colour, to tell X from O.",
                  size=8, fg=MUTED, wraplength=600, justify="left").pack(anchor="w", pady=(3, 0))
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", pady=(4, 0))
        self.forget_button = ui._button(row, "Forget what was taught", self.forget)
        self.forget_button.pack(side="left")
        self.watching = tk.BooleanVar(value=True)
        tk.Checkbutton(row, text="Show what the Pi sees on the banks", variable=self.watching, bg=PANEL, activebackground=PANEL,
                       highlightthickness=0, font=ui.theme.font(9), command=self.look_at_banks).pack(side="left", padx=10)
        self.seen = tk.Canvas(tab, width=5 * (TILE + 40), height=2 * (TILE + 26), bg=PANEL, highlightthickness=0)
        self.seen.pack(anchor="w", pady=(2, 0))
        self.seen_photos = []
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

    def look_at_banks(self):
        """Draw each bank circle as the Pi sees it: the picture, the mark it found in red, and what it made of it."""
        from PIL import Image, ImageTk
        import numpy as np

        canvas, p = self.seen, self.p
        canvas.delete("all")
        self.seen_photos = []
        view, reference = p.rectified, p.reference
        if not self.watching.get():
            return
        if view is None or reference is None or view.layout is not reference.layout:
            canvas.create_text(8, 8, anchor="nw", fill=MUTED, font=self.studio.theme.font(9),
                               text="Capture the empty mat first, then put pieces in the banks.")
            return
        slots = [(slot, mark) for mark in p.layout.reserve_marks(p.dobot) for slot in p.layout.bank(mark)]
        for index, (slot, expected) in enumerate(slots):
            mark, why, report = look(view.grey, reference.grey, view.layout, slot, p.learned, view.colour, p.centres)
            tile = report.get("tile")
            column, row = index % 5, index // 5
            x, y = column * (TILE + 40) + 6, row * (TILE + 26) + 2
            if tile is None:
                continue
            picture = np.dstack([tile] * 3).copy()
            ink = report.get("ink")
            if ink is not None:
                picture[ink] = (0.45 * picture[ink] + 0.55 * np.array((255, 40, 40))).astype(np.uint8)
            photo = ImageTk.PhotoImage(Image.fromarray(picture).resize((TILE, TILE), Image.Resampling.BILINEAR), master=self.window)
            self.seen_photos.append(photo)
            good = mark == expected
            canvas.create_image(x, y, image=photo, anchor="nw")
            canvas.create_rectangle(x - 1, y - 1, x + TILE, y + TILE, outline=GREEN if good else RED, width=2)
            if report.get("changed", 0) >= 0.55:          # the colour of the piece, as the Pi judges it
                _, rgb = body_colour(_patch_colour(view.colour, circle_positions(view.layout, p.centres)[slot], view.layout.piece_scale))
                canvas.create_rectangle(x + TILE - 14, y + 2, x + TILE - 2, y + 14, fill="#%02x%02x%02x" % rgb, outline="#ffffff")
            scores = report.get("scores") or {}
            verdict = "empty" if mark == "" else ("?" if mark == "?" else mark)
            canvas.create_text(x, y + TILE + 1, anchor="nw", fill=GREEN if good else RED, font=self.studio.theme.font(8, "bold"),
                               text=f"{slot}: {verdict}")
            if report.get("colour_vote") and not scores:
                detail = f"colour says {report['colour_vote']}"
            elif scores:
                detail = f"X {scores.get(X, 0):.0%} O {scores.get(O, 0):.0%}" + (
                    f" ·{report['colour_vote']}" if report.get("colour_vote") else "")
            elif report.get("changed", 0) >= 0.55:
                detail = f"mark {report.get('size', 0)} px"        # a piece is there, but its mark barely shows
            else:
                detail = f"changed {report.get('changed', 0):.0%}"
            canvas.create_text(x, y + TILE + 12, anchor="nw", fill=MUTED, font=self.studio.theme.font(7), text=detail)

    def forget(self):
        self.p.learned.clear()
        self.p.latest, self.p.seen = None, 0
        self._say("Forgotten. The built-in reading is used.", MUTED)
        self._refresh_pieces()

    def _refresh_pieces(self):
        for mark, swatch in self.swatches.items():
            swatch.delete("all")
            if self.p.learned.colours[mark]:
                colour = "#%02x%02x%02x" % lab_to_rgb(self.p.learned.colour_of(mark)[0])
                swatch.create_rectangle(1, 1, 17, 17, fill=colour, outline=DARK)
            else:
                swatch.create_rectangle(1, 1, 17, 17, outline=BORDER, dash=(2, 2))
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
        found = self.p.found or self.p.rectified
        if found is not None:
            ppmm = pixels_per_mm(found)
            advice = ("  Move the camera closer so the mat fills more of the picture. The marks read better at 3 or more."
                      if ppmm < 2.5 else "")
            self.size_text.set(f"The mat is {ppmm:.1f} pixels for every millimetre in the picture.{advice}")
            self.size_label.configure(fg=RED if ppmm < 2.0 else MUTED)
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 4 == 0 and self.tabs.index(self.tabs.select()) == 1:
            self.look_at_banks()
        self.window.after(150, self._preview)

    def close(self):
        program = self.p
        program.tune_dialog = None
        if self.window.winfo_exists():
            self.window.grab_release()
            self.window.destroy()
        # Let the pictures and variables go now, on this thread, while Tk is still running.
        self.photos, self.seen_photos, self.variables, self.hardware = [], [], {}, {}
        if program.window.winfo_exists():
            program.window.grab_set()
