"""Dobot Studio program picker."""
import tkinter as tk

from .theme import BORDER, MUTED, PANEL, PURPLE, gradient, icon


PROGRAMS = (
    ("control", "Gesture & pose control", "Move the simulated or USB-connected arm with camera inputs."),
    ("train", "Recognition training", "Teach your own hand signs and printed or drawn symbols."),
    ("sort", "Chip sorting", "Use the overhead camera to route colour or labelled chips to bins."),
    ("inspect", "Assembly inspection", "Compare tabletop stages and check what has changed."),
)


def build_program_picker(studio):
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

    tiles = tk.Frame(card, bg=PANEL)
    tiles.pack(fill="x")
    for col in range(2):
        tiles.columnconfigure(col, weight=1, uniform="program")
    for index, (key, title, description) in enumerate(PROGRAMS):
        row, col = divmod(index, 2)
        tile = tk.Frame(tiles, bg="#edf4fb", highlightbackground=BORDER,
                        highlightthickness=1, padx=10, pady=8)
        tile.grid(row=row, column=col, sticky="nsew", padx=(0, 5) if col == 0 else (5, 0),
                  pady=(0, 9) if row == 0 else 0)
        studio._button(tile, title, lambda program=key: studio.open_program(program),
                       "Purple" if key == "control" else "Teal").pack(fill="x")
        studio._label(tile, description, size=9, fg=MUTED, bg="#edf4fb",
                      wraplength=290, justify="left").pack(fill="x", pady=(6, 2))
    return canvas
