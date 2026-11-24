"""Write printables/tictactoe/mat-a4.svg from the compact layout in dobot_studio/tictactoe.py.

The artwork comes from the same numbers the camera uses, so the sheet cannot drift from the
software. Needs opencv-contrib (a Dobot Studio dependency) for the marker patterns.
Run from apps/dobot-studio with PYTHONPATH=.: python tools/make_a4_svg.py
"""
from pathlib import Path

import cv2

from dobot_studio.tictactoe import COMPACT_CENTRE, COMPACT_HEIGHT, COMPACT_MAT, COMPACT_WIDTH

OUTPUT = Path("printables/tictactoe/mat-a4.svg")
CIRCLE = 11.725        # solid circles: the old ring's outer edge, so the camera geometry is unchanged
FRAME, LINE = 1.4, 1.0  # grid frame and divider widths (mm)
CELL_PITCH = (54, 55)   # across and down
PARK_RING, PARK_GAP = 2.3, 4.0
BLACK = "#000000"
SEAM = 0.03            # mm


def number(value):
    return f"{value:.5f}".rstrip("0").rstrip(".")


def grid():
    cx, cy = COMPACT_CENTRE
    left, right = cx - 1.5 * CELL_PITCH[0], cx + 1.5 * CELL_PITCH[0]
    top, bottom = cy - 1.5 * CELL_PITCH[1], cy + 1.5 * CELL_PITCH[1]
    park_x, park_y = COMPACT_MAT.park
    stroke = f'fill="none" stroke="{BLACK}"'
    items = [f'<rect x="{number(left)}" y="{number(top)}" width="{number(right - left)}" '
             f'height="{number(bottom - top)}" rx="3" {stroke} stroke-width="{FRAME}" />']

    def line(x1, y1, x2, y2):
        items.append(f'<line x1="{number(x1)}" y1="{number(y1)}" x2="{number(x2)}" y2="{number(y2)}" '
                     f'{stroke} stroke-width="{LINE}" />')

    for column in (1, 2):
        x = left + column * CELL_PITCH[0]
        line(x, top, x, bottom)
    line(left, top + CELL_PITCH[1], right, top + CELL_PITCH[1])
    # The lower divider breaks around the Park ring.
    line(left, park_y, park_x - PARK_GAP, park_y)
    line(park_x + PARK_GAP, park_y, right, park_y)
    for x, y in COMPACT_MAT.positions.values():
        items.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="{CIRCLE}" fill="{BLACK}" />')
    items.append(f'<circle cx="{number(park_x)}" cy="{number(park_y)}" r="{PARK_RING}" {stroke} stroke-width="0.6" />')
    return items


def markers():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    size = COMPACT_MAT.anchor_size
    cell = size / 6
    items = []
    for marker, (x, y) in COMPACT_MAT.anchors.items():
        items.append(f'<rect x="{number(x - size / 2 - 3)}" y="{number(y - size / 2 - 3)}" '
                     f'width="{number(size + 6)}" height="{number(size + 6)}" rx="0" fill="#ffffff" />')
        bits = cv2.aruco.generateImageMarker(dictionary, marker, 6)
        black = lambda row, column: 0 <= row < 6 and 0 <= column < 6 and bits[row, column] == 0
        for row in range(6):
            for column in range(6):
                if black(row, column):
                    # A cell reaches into a black neighbour, so no hairline shows between them. The marker's
                    # outer edge, and so its 16 mm size, does not change.
                    wide = cell + (SEAM if black(row, column + 1) else 0)
                    high = cell + (SEAM if black(row + 1, column) else 0)
                    items.append(f'<rect x="{number(x - size / 2 + column * cell)}" y="{number(y - size / 2 + row * cell)}" '
                                 f'width="{number(wide)}" height="{number(high)}" rx="0" fill="{BLACK}" />')
    return items


def scale_bar():
    """A 100 mm line to check the printed scale. It is for paper only and is not part of the 3D mat."""
    y = COMPACT_HEIGHT - 10
    x0 = COMPACT_CENTRE[0] - 50
    return [f'<line x1="{number(x0)}" y1="{y}" x2="{number(x0 + 100)}" y2="{y}" fill="none" stroke="#17283b" stroke-width="0.42" />',
            f'<line x1="{number(x0)}" y1="{y - 2}" x2="{number(x0)}" y2="{y + 2}" fill="none" stroke="#17283b" stroke-width="0.42" />',
            f'<line x1="{number(x0 + 100)}" y1="{y - 2}" x2="{number(x0 + 100)}" y2="{y + 2}" fill="none" stroke="#17283b" stroke-width="0.42" />',
            f'<text x="{number(x0 + 105)}" y="{y + 1.4}" fill="#17283b" text-anchor="start" font-size="3.7" font-weight="bold">100 mm</text>']


def main():
    def group(name, items):
        return f'  <g id="{name}">\n' + "".join(f"    {item}\n" for item in items) + "  </g>\n"

    svg = ("<?xml version='1.0' encoding='utf-8'?>\n"
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{COMPACT_WIDTH}mm" height="{COMPACT_HEIGHT}mm" '
           f'viewBox="0 0 {COMPACT_WIDTH} {COMPACT_HEIGHT}" role="img" aria-labelledby="title description" '
           'font-family="Arial, sans-serif">\n'
           '  <title id="title">Dobot Studio compact tic-tac-toe mat</title>\n'
           '  <desc id="description">A4 landscape sheet with nine solid black circles, separate X and O reserves '
           'and four camera markers, centred on the sheet.</desc>\n'
           + group("board-grid", grid()) + group("camera-markers", markers()) + group("print-scale", scale_bar())
           + "</svg>\n")
    OUTPUT.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
