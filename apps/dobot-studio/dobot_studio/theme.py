"""Tk styling based on the CircuitPath BNTS Aero palette."""
import tkinter as tk
from tkinter import font, ttk

INK, MUTED, PURPLE = "#17283b", "#52657c", "#4b2a63"
TEAL, PANEL, BORDER = "#19c1ca", "#f7faff", "#adbed3"
DARK, DARKER, WHITE = "#101b32", "#0d1629", "#ffffff"
GREEN, RED = "#247454", "#a32b25"


def colour(a, b, fraction):
    channels = (round(int(a[i:i+2], 16) * (1-fraction) + int(b[i:i+2], 16) * fraction)
                for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def gradient(canvas, width, height, top, bottom, tag="paint"):
    for y in range(0, height, 4):
        canvas.create_rectangle(0, y, width, min(y + 4, height), width=0,
                                fill=colour(top, bottom, y / max(1, height)), tags=tag)


class Theme:
    def __init__(self, root):
        families = {name.casefold(): name for name in font.families(root)}
        choices = ("segoe ui", "noto sans", "dejavu sans", "liberation sans", "helvetica")
        self.family = next((families[name] for name in choices if name in families),
                           font.nametofont("TkDefaultFont").actual("family"))
        root.option_add("*Font", self.font(10))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", padding=(6, 4), arrowcolor=PURPLE, foreground=INK,
                        bordercolor=BORDER, fieldbackground=WHITE, background="#e7edf5")
        style.map("TCombobox", fieldbackground=[("readonly", WHITE), ("disabled", "#edf1f5")],
                  foreground=[("disabled", MUTED), ("readonly", INK)])
        style.configure("TEntry", padding=(6, 4), bordercolor=BORDER, fieldbackground=WHITE)
        self.images = []
        palettes = {
            "Glass": ("#ffffff", "#edf3fa", "#dce7f4", "#f0f5fa", "#9fb2c9", INK),
            "Teal": ("#caf8fc", "#8ee5ea", "#56cad3", "#a7e9ed", "#25848c", "#11363e"),
            "Purple": ("#e5dbf4", "#c9b5e3", "#ad91cf", "#d6c3eb", "#8764a5", "#331e4b"),
            "Stop": ("#fff1ed", "#ffdbd3", "#f5bcb4", "#ffd8ce", "#c0776b", "#7b251c"),
        }
        for name, palette in palettes.items():
            self._button(style, name, palette)

    def font(self, size, weight="normal"):
        return self.family, size, weight

    def _button(self, style, name, palette):
        top, upper, lower, base, border, text = palette
        normal = self._button_image(top, upper, lower, base, border)
        hover = self._button_image(colour(top, WHITE, 0.3), colour(upper, WHITE, 0.25),
                                   colour(lower, "#70ddea", 0.18), base, "#537fa9")
        depressed = self._button_image(upper, lower, base, upper, border)
        disabled = self._button_image("#f5f7fa", "#edf0f4", "#e6ebf0", "#eff2f6", "#c7d0dc")
        element = name + ".glass"
        style.element_create(element, "image", normal, ("disabled", disabled),
                             ("pressed", depressed), ("active", hover), ("focus", hover),
                             border=(5, 5, 5, 5), sticky="nsew")
        selector = name + ".TButton"
        style.layout(selector, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [
                ("Button.label", {"sticky": "nsew"})
            ]})
        ]})])
        style.configure(selector, font=self.font(10, "bold"), foreground=text, padding=(8, 3))
        style.map(selector, foreground=[("disabled", "#687a8c")])

    def _button_image(self, top, upper, lower, base, border):
        image = tk.PhotoImage(width=32, height=30)
        for y in range(30):
            fill = colour(top, upper, y / 14) if y < 15 else colour(lower, base, (y-15) / 14)
            inset = 3 if y in (0, 29) else 2 if y in (1, 28) else 1 if y in (2, 27) else 0
            image.put(border, to=(inset, y, 32-inset, y+1))
            if 0 < y < 29:
                image.put(fill, to=(inset+1, y, 31-inset, y+1))
        self.images.append(image)
        return image


def icon(canvas, name, cx, cy, scale=1, foreground="#4b2a63", background=TEAL):
    def line(*points, **options):
        coordinates = [(cx if i % 2 == 0 else cy) + value * scale
                       for i, value in enumerate(points)]
        canvas.create_line(*coordinates, fill=foreground, width=max(1, 2*scale),
                           capstyle="round", joinstyle="round", **options)

    if name == "arm":
        line(-10, 9, 1, 9, -3, 7, -3, 4, -8, -3, -3, -8, 5, -5, 7, 0)
        line(5, 0, 9, 0, 9, 4)
        for x, y in ((-8, -3), (-3, -8), (5, -5)):
            canvas.create_oval(cx+(x-2)*scale, cy+(y-2)*scale,
                               cx+(x+2)*scale, cy+(y+2)*scale, width=0, fill=background)
    elif name == "camera":
        line(-11, -6, 3, -6, 3, 6, -11, 6, -11, -6)
        line(3, -2, 10, -6, 10, 6, 3, 2)
    else:
        line(0, -9, 8, -5, 7, 4, 0, 9, -7, 4, -8, -5, 0, -9)
        line(-3, 0, -1, 3, 4, -3)
