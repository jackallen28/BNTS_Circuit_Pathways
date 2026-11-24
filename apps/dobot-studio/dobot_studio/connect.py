"""The first screen: connect and home the Dobot, then try it out before choosing a program."""
import tkinter as tk
from tkinter import ttk

from .robot import ATTACHMENTS
from .theme import BORDER, GREEN, MUTED, PANEL, PURPLE, RED, gradient, icon

STEPS = ("1 mm", "5 mm", "10 mm", "20 mm")
# (label, (dx, dy, dz) for one step). The arm's x runs away from its base and y to its left.
MOVES = {
    "forward": ("▲  Forward", (1, 0, 0)), "back": ("▼  Back", (-1, 0, 0)),
    "left": ("◀  Left", (0, 1, 0)), "right": ("Right  ▶", (0, -1, 0)),
    "up": ("⬆  Up", (0, 0, 1)), "down": ("⬇  Down", (0, 0, -1)),
}


class ConnectScreen:
    def __init__(self, studio):
        self.studio = studio
        self.step = tk.StringVar(value=STEPS[1])
        self.tool = tk.StringVar(value=ATTACHMENTS[0])
        self.position_text = tk.StringVar(value="Tool position: not known yet")
        root = studio.root
        self.canvas = canvas = tk.Canvas(root, highlightthickness=0, bg="#295775")
        card = tk.Frame(canvas, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=18, pady=12)
        window = canvas.create_window(0, 0, anchor="center", window=card)

        def background(event):
            width, height = event.width, event.height
            canvas.delete("paint")
            gradient(canvas, width, height, "#15566c", "#46366a")
            canvas.create_polygon(0, height*.65, width*.78, 0, width, 0, 0, height,
                                  fill="#2c6986", outline="", tags="paint")
            canvas.create_polygon(0, height, width, height*.27, width, height,
                                  fill="#4c4c79", outline="", tags="paint")
            canvas.tag_lower("paint")
            canvas.coords(window, width/2, height/2)
            canvas.itemconfigure(window, width=min(860, width-40))

        canvas.bind("<Configure>", background)
        self._build(card)

    def _build(self, card):
        ui = self.studio
        header = tk.Frame(card, bg="#dcebf7", padx=14, pady=9)
        header.pack(fill="x", pady=(0, 9))
        badge = tk.Canvas(header, width=46, height=46, bg="#e3f7f8", bd=0,
                          highlightthickness=1, highlightbackground="#a4c5d9")
        badge.pack(side="left", padx=(0, 12))
        icon(badge, "arm", 23, 23, 1.5)
        intro = tk.Frame(header, bg="#dcebf7")
        intro.pack(side="left")
        ui._label(intro, "Connect your Dobot", size=20, weight="bold", fg=PURPLE, bg="#dcebf7").pack(anchor="w")
        ui._label(intro, "Check the arm works before you choose a program.", size=10, fg=MUTED,
                  bg="#dcebf7").pack(anchor="w")
        ui._button(header, "Check for updates…", ui.show_updates).pack(side="right", anchor="n")

        columns = tk.Frame(card, bg=PANEL)
        columns.pack(fill="x")
        columns.columnconfigure(0, weight=1, uniform="half")
        columns.columnconfigure(1, weight=1, uniform="half")
        left = tk.Frame(columns, bg=PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = tk.Frame(columns, bg=PANEL)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        pane, body = ui._pane(left, "1 · Connect", "USB")
        pane.pack(fill="x")
        body.columnconfigure(0, weight=1)
        self.port_box = ttk.Combobox(body, textvariable=ui.port, width=14)
        self.port_box.grid(row=0, column=0, sticky="ew")
        self.scan_button = ui._button(body, "Scan", ui.scan_ports)
        self.scan_button.grid(row=0, column=1, padx=(4, 0))
        self.connect_button = ui._button(body, "Connect", ui.connect, "Teal")
        self.connect_button.grid(row=0, column=2, padx=(4, 0))
        self.connection_label = ui._label(body, size=9, weight="bold", wraplength=330, justify="left")
        self.connection_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ui._label(body, "Plug in the Dobot’s USB cable and power it on. If you see Permission denied, "
                  "see the setup guide.", size=9, fg=MUTED, wraplength=330, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))

        pane, body = ui._pane(left, "2 · Home", "the arm will move")
        pane.pack(fill="x", pady=(8, 0))
        body.columnconfigure(0, weight=1)
        self.home_button = ui._button(body, "Home the arm", ui.home, "Teal")
        self.home_button.grid(row=0, column=0, sticky="ew")
        self.home_label = ui._label(body, size=9, weight="bold", wraplength=330, justify="left")
        self.home_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ui._label(body, "Clear the workspace first. Keep the physical stop within reach.", size=9,
                  fg=MUTED, wraplength=330, justify="left").grid(row=2, column=0, sticky="w", pady=(3, 0))

        pane, body = ui._pane(right, "3 · Try it", "move the arm")
        pane.pack(fill="both", expand=True)
        controls = tk.Frame(body, bg=PANEL)
        controls.pack(fill="x")
        ui._label(controls, "Step", size=9, fg=MUTED).pack(side="left")
        ttk.Combobox(controls, textvariable=self.step, values=STEPS, state="readonly", width=6).pack(side="left", padx=5)
        pad = tk.Frame(body, bg=PANEL)
        pad.pack(pady=(7, 4))
        self.move_buttons = {}
        layout = {"left": (0, 0), "forward": (0, 1), "right": (0, 2), "up": (1, 0), "back": (1, 1), "down": (1, 2)}
        for key, (row, column) in layout.items():
            label, delta = MOVES[key]
            button = ui._button(pad, label, lambda delta=delta: self.move(delta))
            button.grid(row=row, column=column, padx=2, pady=2, ipadx=3, sticky="ew")
            self.move_buttons[key] = button
        tools = tk.Frame(body, bg=PANEL)
        tools.pack(fill="x", pady=(3, 0))
        ttk.Combobox(tools, textvariable=self.tool, values=ATTACHMENTS, state="readonly", width=11).pack(side="left")
        self.hold_button = ui._button(tools, "Suction on / grip", lambda: self.hold(True))
        self.hold_button.pack(side="left", padx=(5, 0))
        self.release_button = ui._button(tools, "Release", lambda: self.hold(False))
        self.release_button.pack(side="left", padx=(4, 0))
        ui._label(body, textvariable=self.position_text, size=9, weight="bold", wraplength=330,
                  justify="left").pack(anchor="w", pady=(7, 0))
        ui._label(body, "Try each direction in small steps, and check the suction before a program uses it.",
                  size=9, fg=MUTED, wraplength=330, justify="left").pack(anchor="w", pady=(3, 0))

        footer = tk.Frame(card, bg=PANEL)
        footer.pack(fill="x", pady=(10, 0))
        ui._label(footer, textvariable=ui.status_text, size=9, wraplength=470, justify="left").pack(side="left")
        self.continue_button = ui._button(footer, "Choose a program  ▶", self.finish, "Purple")
        self.continue_button.pack(side="right", ipadx=10)
        self.demo_button = ui._button(footer, "Use Demo mode (no Dobot)", self.use_demo)
        self.demo_button.pack(side="right", padx=(0, 8))
        self.stop_button = ui._button(footer, "Stop  ·  Esc", lambda: ui.stop("Stopped."), "Stop")
        self.stop_button.pack(side="right", padx=(0, 8), ipadx=8)
        self.refresh()

    def move(self, delta):
        millimetres = int(self.step.get().split()[0])
        self.studio.jog(tuple(value * millimetres for value in delta))

    def hold(self, holding):
        self.studio.hold(self.tool.get(), holding)

    def use_demo(self):
        studio = self.studio
        if studio.robot or studio.busy:
            return
        studio.set_mode(True)
        self.finish()

    def finish(self):
        """Go on to the programs page."""
        studio = self.studio
        if studio.busy or not (studio.demo or (studio.robot and studio.homed)):
            return
        studio.leave_connect()

    def refresh(self):
        ui = self.studio
        if not self.canvas.winfo_exists():
            return
        connected, homed = ui.robot is not None, ui.homed
        idle = ui.busy is None and not ui.closing and not ui.armed
        live = not ui.demo
        self.port_box.configure(state="normal" if live and idle and not connected else "disabled")
        ui._set_button(self.scan_button, live and idle and not connected)
        ui._set_button(self.connect_button, live and idle)
        self.connect_button.configure(text="Disconnect" if connected else "Connect")
        ui._set_button(self.home_button, live and connected and idle)
        self.home_button.configure(text="Home again" if homed else "Home the arm")
        ready = live and connected and homed and idle
        for button in self.move_buttons.values():
            ui._set_button(button, ready)
        ui._set_button(self.hold_button, live and connected and idle)
        ui._set_button(self.release_button, live and connected and idle)
        ui._set_button(self.continue_button, idle and (ui.demo or (connected and homed)))
        ui._set_button(self.demo_button, idle and not connected)
        ui._set_button(self.stop_button, not ui.closing and (ui.busy is not None or connected))
        if ui.demo:
            self.connection_label.configure(text="Demo mode: a simulated Dobot.", fg=MUTED)
        elif connected:
            self.connection_label.configure(text="✔  Connected", fg=GREEN)
        else:
            self.connection_label.configure(text="Not connected yet.", fg=RED if ui.port.get() else MUTED)
        self.home_label.configure(text="✔  Homed. The arm is ready." if homed else "Not homed yet.",
                                  fg=GREEN if homed else MUTED)
        if ui.position is not None and connected:
            self.position_text.set("Tool position  " + ui.position.label())
        elif connected:
            self.position_text.set("Tool position: not known yet")
        else:
            self.position_text.set("Connect and home the arm to try it.")
