"""Dobot Studio program picker."""
import tkinter as tk

from .theme import BORDER, GREEN, MUTED, PANEL, PURPLE, gradient, icon


PROGRAMS = (
    ("control", "Gesture & pose control", "Move the simulated or USB-connected arm with camera inputs."),
    ("train", "Recognition training", "Teach your own hand signs and printed or drawn symbols."),
    ("sort", "Chip sorting", "Use the overhead camera to route colour or labelled chips to bins."),
    ("inspect", "Assembly inspection", "Compare tabletop stages and check what has changed."),
    ("blocks", "3D Block Lab", "Build a stepped pyramid or box, or rebuild mixed stacks by colour."),
    ("math", "Equation Lab", "Read arithmetic from a chip tray and place an answer."),
    ("teach", "Micro:bit Teach", "Record and replay a path with tilt and tool commands."),
    ("tictactoe", "Tic-tac-toe", "Play X or O on the camera-tracked mat. Dobot takes its turns automatically."),
)


def build_program_picker(studio, notice=None):
    root = studio.root
    canvas = tk.Canvas(root, highlightthickness=0, bg="#295775")
    card = tk.Frame(canvas, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=18, pady=14)
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
        canvas.itemconfigure(window, width=min(820, width-54))

    canvas.bind("<Configure>", background)

    header = tk.Frame(card, bg="#dcebf7", padx=14, pady=11)
    header.pack(fill="x", pady=(0, 12))
    badge = tk.Canvas(header, width=51, height=51, bg="#e3f7f8", bd=0,
                      highlightthickness=1, highlightbackground="#a4c5d9")
    badge.pack(side="left", padx=(0, 12))
    icon(badge, "arm", 26, 26, 1.65)
    introduction = tk.Frame(header, bg="#dcebf7")
    introduction.pack(side="left")
    studio._label(introduction, "Dobot Studio", size=21, weight="bold", fg=PURPLE,
                  bg="#dcebf7").pack(anchor="w")
    studio._label(introduction, "Choose a program", size=11, fg=MUTED,
                  bg="#dcebf7").pack(anchor="w")

    status = tk.Frame(card, bg=PANEL)
    status.pack(fill="x", pady=(0, 9))
    live = studio.robot is not None
    studio._label(status, "Dobot connected and homed" if live and studio.homed else
                  "Dobot connected, not homed" if live else "Demo mode: a simulated Dobot",
                  size=10, weight="bold", fg=GREEN if live and studio.homed else MUTED).pack(side="left")
    if notice is not None:
        studio._label(card, textvariable=notice, size=9, weight="bold", fg=PURPLE, wraplength=700,
                      justify="left").pack(fill="x", pady=(0, 6))
    studio._button(status, "Dobot connection…", studio.show_connect).pack(side="right")
    studio._button(status, "Check for updates…", studio.show_updates).pack(side="right", padx=(0, 6))

    tiles = tk.Frame(card, bg=PANEL)
    tiles.pack(fill="x")
    for col in range(3):
        tiles.columnconfigure(col, weight=1, uniform="program")
    for index, (key, title, description) in enumerate(PROGRAMS):
        row, col = divmod(index, 3)
        tile = tk.Frame(tiles, bg="#edf4fb", highlightbackground=BORDER,
                        highlightthickness=1, padx=10, pady=8)
        tile.grid(row=row, column=col, sticky="nsew", padx=4, pady=(0, 7))
        studio._button(tile, title, lambda program=key: studio.open_program(program),
                       "Purple" if key == "control" else "Teal").pack(fill="x")
        studio._label(tile, description, size=9, fg=MUTED, bg="#edf4fb",
                      wraplength=210, justify="left").pack(fill="x", pady=(6, 2))
    version = studio.version()
    studio._label(card, "Dobot Studio  ·  " + version if version else "Dobot Studio", size=8, fg=MUTED).pack(anchor="e")
    return canvas
