"""The disarmed camera training window."""
from copy import deepcopy
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from .learning import (
    ACTIONS, CUSTOM_HAND, MAX_CLASSES, MAX_EXAMPLES, MIN_EXAMPLES, NEUTRAL, NO_ACTION,
    Examples, save_classes, train, valid_name,
)
from .theme import DARK, MUTED, PANEL, PURPLE, WHITE


class TrainingWindow:
    def __init__(self, studio, mode, classes):
        self.studio, self.mode = studio, mode
        self.classes = deepcopy(classes)
        self.dirty = False
        self.last_capture = 0.0
        self.detection = self.frame = self.photo = None
        self.window = tk.Toplevel(studio.root, bg="#e9eff8", padx=12, pady=10)
        self.window.title("Train recognition")
        self.window.transient(studio.root)
        width = min(931, studio.root.winfo_screenwidth() - 32)
        height = min(575, studio.root.winfo_screenheight() - 60)
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(750, 450)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Select Neutral or add a class to collect examples.")
        self.recognition = tk.StringVar(value="Waiting for camera")
        self.name = tk.StringVar()
        self.action = tk.StringVar(value=NO_ACTION)
        self._build()
        self._refresh(NEUTRAL)

    def _build(self):
        ui = self.studio
        title = tk.Frame(self.window, bg="#d9e8f6", padx=12, pady=7)
        title.pack(fill="x", pady=(0, 8))
        ui._label(title, self.mode, size=16, weight="bold", fg=PURPLE, bg="#d9e8f6").pack(side="left")
        ui._label(title, "Motion disarmed", size=9, weight="bold", fg=PURPLE,
                  bg="#d9e8f6").pack(side="right")

        workspace = tk.Frame(self.window, bg="#e9eff8")
        workspace.pack(fill="both", expand=True)
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)

        view, preview = ui._pane(workspace, "Camera preview")
        view.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.canvas = tk.Canvas(preview, width=330, height=230, bg=DARK, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_frame())
        ui._label(preview, textvariable=self.recognition, size=9, weight="bold").pack(fill="x", pady=4)
        guidance = (
            "Keep one whole hand in view. Vary the angle and distance."
            if self.mode == CUSTOM_HAND else
            "Fill the guide with light paper. Use one dark, bold symbol."
        )
        ui._label(preview, guidance, size=9, fg=MUTED, wraplength=310,
                  justify="left").pack(fill="x")

        panel, controls = ui._pane(workspace, "Training examples",
                                   f"{MIN_EXAMPLES} or more per class")
        panel.grid(row=0, column=1, sticky="nsew")
        rows = tk.Frame(controls, bg=PANEL)
        rows.pack(fill="both", expand=True)
        self.table = ttk.Treeview(rows, columns=("label", "action", "count"), show="headings",
                                  height=5, selectmode="browse")
        for column, text, width in (("label", "Class", 125), ("action", "Action", 108), ("count", "Samples", 72)):
            self.table.heading(column, text=text)
            self.table.column(column, width=width, minwidth=width, stretch=column == "label")
        scrollbar = ttk.Scrollbar(rows, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self._select_class)

        add = tk.Frame(controls, bg=PANEL)
        add.pack(fill="x", pady=(6, 0))
        name = ttk.Entry(add, textvariable=self.name, width=16)
        name.pack(side="left", fill="x", expand=True)
        name.bind("<Return>", lambda _event: self.add_class())
        ui._button(add, "Add named class", self.add_class).pack(side="right", padx=(4, 0))

        mapping = tk.Frame(controls, bg=PANEL)
        mapping.pack(fill="x", pady=(6, 0))
        ui._label(mapping, "Action", size=9, fg=MUTED).pack(side="left", padx=(0, 5))
        self.mapping = ttk.Combobox(mapping, state="readonly", values=tuple(ACTIONS),
                                    textvariable=self.action, width=12)
        self.mapping.pack(side="left")
        self.mapping.bind("<<ComboboxSelected>>", self.map_action)
        self.remove_button = ui._button(mapping, "Remove class", self.remove_class)
        self.remove_button.pack(side="right")

        buttons = tk.Frame(controls, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self.capture_button = ui._button(buttons, "Capture example", self.capture, "Teal")
        self.capture_button.pack(side="left")
        self.undo_button = ui._button(buttons, "Undo last", self.undo)
        self.undo_button.pack(side="left", padx=5)
        self.save_button = ui._button(controls, "Train & save", self.fit, "Purple")
        self.save_button.pack(fill="x", pady=(7, 0))
        ui._label(controls, textvariable=self.status, size=9, fg=PURPLE, wraplength=280,
                  justify="left").pack(fill="x", pady=(6, 0))

        footer = tk.Frame(self.window, bg="#e9eff8")
        footer.pack(fill="x", pady=(6, 0))
        neutral = "a relaxed hand shape" if self.mode == CUSTOM_HAND else "a blank card"
        ui._label(footer, f"Use {neutral} for Neutral. Keep Neutral visible between commands.",
                  size=9, fg=MUTED, bg="#e9eff8").pack(side="left")
        ui._button(footer, "Done", self.close).pack(side="right")

    def _selected(self):
        items = self.table.selection()
        return items[0] if items else None

    def _refresh(self, selected):
        self.table.delete(*self.table.get_children())
        for name, group in self.classes.items():
            item = self.table.insert("", "end", iid=name, values=(name, group.action, len(group.vectors)))
            if name == selected:
                self.table.selection_set(item)
                self.table.see(item)
        self._select_class()

    def _select_class(self, _event=None):
        name = self._selected()
        group = self.classes.get(name)
        if group:
            self.action.set(group.action)
        self.mapping.configure(state="readonly" if group and name != NEUTRAL else "disabled")
        self.studio._set_button(self.remove_button, group and name != NEUTRAL)
        self.studio._set_button(self.undo_button, group and group.vectors)
        self._update_capture()

    def _update_capture(self):
        ready = (self.detection is not None and self.detection.features is not None
                 and self.detection.timestamp - self.last_capture >= 0.24
                 and monotonic() - self.detection.timestamp < 0.65)
        self.studio._set_button(self.capture_button, ready and self._selected())

    def show(self, detection, image):
        self.detection, self.frame = detection, image
        if detection.tracked:
            action = next(label for label, code in ACTIONS.items() if code == detection.command)
            self.recognition.set(f"Recognised: {detection.label} → {action}")
        elif detection.features is not None:
            self.recognition.set(f"{detection.sample_hint}  ·  {detection.label}")
        else:
            self.recognition.set(detection.label)
        self._draw_frame()
        self._update_capture()

    def camera_lost(self, reason):
        self.detection = self.frame = None
        self.recognition.set("Camera unavailable")
        self.status.set(reason)
        self._draw_frame()
        self._update_capture()

    def _draw_frame(self):
        canvas = self.canvas
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 5 or h < 5:
            return
        canvas.delete("all")
        if self.frame is None:
            canvas.create_text(w/2, h/2, text="Waiting for a camera frame", fill=WHITE,
                               font=self.studio.theme.font(10))
            return
        from PIL import Image, ImageTk

        resized = self.frame.copy()
        resized.thumbnail((w, h), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(resized, master=self.window)
        canvas.create_image(w/2, h/2, image=self.photo)

    def add_class(self):
        name = self.name.get().strip()
        if not valid_name(name):
            self.status.set("Enter a name of 1 to 24 characters.")
        elif any(name.casefold() == current.casefold() for current in self.classes):
            self.status.set("That class name is already in use.")
        elif len(self.classes) >= MAX_CLASSES:
            self.status.set(f"You can train up to {MAX_CLASSES} classes per mode.")
        else:
            self.classes[name] = Examples(NO_ACTION)
            self.name.set("")
            self.dirty = True
            self._refresh(name)
            self.status.set(f"Select an action for {name}, then capture examples.")

    def map_action(self, _event=None):
        name = self._selected()
        if name and name != NEUTRAL and self.action.get() in ACTIONS:
            self.classes[name].action = self.action.get()
            self.dirty = True
            self._refresh(name)

    def capture(self):
        name = self._selected()
        detection = self.detection
        if (not name or not detection or detection.features is None
                or monotonic() - detection.timestamp >= 0.65
                or detection.timestamp - self.last_capture < 0.24):
            self.status.set("Wait for a fresh camera sample inside the guide.")
            return
        group = self.classes[name]
        if len(group.vectors) >= MAX_EXAMPLES:
            self.status.set(f"{name} already has {MAX_EXAMPLES} samples.")
            return
        group.vectors.append(detection.features.tolist())
        self.last_capture = detection.timestamp
        self.dirty = True
        self._refresh(name)
        self.status.set(f"Captured example {len(group.vectors)} for {name}.")

    def undo(self):
        name = self._selected()
        if name and self.classes[name].vectors:
            self.classes[name].vectors.pop()
            self.dirty = True
            self._refresh(name)
            self.status.set(f"Removed the last example for {name}.")

    def remove_class(self):
        name = self._selected()
        if name and name != NEUTRAL:
            del self.classes[name]
            self.dirty = True
            self._refresh(NEUTRAL)
            self.status.set(f"Removed {name} from this training session.")

    def fit(self):
        try:
            classifier, correct, total = train(self.mode, self.classes)
            save_classes(self.studio.training_folder, self.mode, self.classes)
        except (ImportError, OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.studio.update_training(self.mode, classifier)
        self.dirty = False
        self.status.set(f"Saved. Held-out check: {correct}/{total} correct. "
                        "Try fresh examples in the preview.")

    def close(self):
        if self.dirty and not messagebox.askokcancel(
                "Discard training changes?", "Close this window and discard unsaved examples and changes?",
                parent=self.window):
            return
        self.window.destroy()
        self.studio.end_training()
