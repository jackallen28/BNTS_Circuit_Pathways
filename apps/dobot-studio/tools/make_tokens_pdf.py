"""Write the cut-out tokens: printables/tictactoe/tokens-cutout.svg and .pdf.

Paper X and O tokens to cut out, on one A4 portrait sheet: 15 crosses and 15 noughts, each a Ø25 mm disc with a
solid black mark. Two sheets: white tokens, and a colour sheet with pink crosses and yellow noughts, which the
camera can also tell apart by colour once it has been shown them from a distance. They are drawn from the same numbers as the 3D pieces and the camera's reading
(tictactoe.py), so a printed token is read the same way as a printed 3D piece. Black on white, on matte paper,
is the strongest contrast the camera can have.

Needs cairosvg and pypdf (as make_mat_pdf.py does). Run from apps/dobot-studio with PYTHONPATH=.:
    python tools/make_tokens_pdf.py
"""
from io import BytesIO
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from dobot_studio.tictactoe import CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, NOUGHT_INNER, NOUGHT_OUTER, PIECE_RADIUS

FOLDER = Path("printables/tictactoe")
SHEETS = {"tokens-cutout": {"X": "#ffffff", "O": "#ffffff"},
          "tokens-cutout-colour": {"X": "#f06496", "O": "#fadc3c"}}      # pink crosses, yellow noughts
WIDTH, HEIGHT = 210, 297          # A4 portrait, millimetres
COLUMNS, ROWS = 5, 6              # the first three rows are crosses, the last three noughts
PITCH = 33                        # between token centres: 8 mm between neighbouring discs for the scissors
TOP = 60                          # the first row's centre
CUT = "#9a9a9a"                   # the line to cut along
BLACK = "#000000"


def number(value):
    return f"{value:.4f}".rstrip("0").rstrip(".")


def token(kind, x, y, fill):
    """One token: the disc to cut out, and its mark."""
    parts = [f'<circle cx="{number(x)}" cy="{number(y)}" r="{PIECE_RADIUS}" fill="{fill}" stroke="{CUT}" stroke-width="0.25" />']
    if kind == "O":
        parts.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="{NOUGHT_OUTER}" fill="{BLACK}" />')
        parts.append(f'<circle cx="{number(x)}" cy="{number(y)}" r="{NOUGHT_INNER}" fill="{fill}" />')
    else:
        for angle in (45, -45):
            parts.append(f'<rect x="{-CROSS_HALF_LENGTH}" y="{-CROSS_HALF_WIDTH}" width="{2 * CROSS_HALF_LENGTH}" '
                         f'height="{2 * CROSS_HALF_WIDTH}" fill="{BLACK}" '
                         f'transform="translate({number(x)} {number(y)}) rotate({angle})" />')
    return parts


def svg(colours, coloured):
    left = (WIDTH - (COLUMNS - 1) * PITCH) / 2
    tokens = []
    for row in range(ROWS):
        for column in range(COLUMNS):
            kind = "X" if row < ROWS // 2 else "O"
            tokens += token(kind, left + column * PITCH, TOP + row * PITCH, colours[kind])
    bottom = TOP + (ROWS - 1) * PITCH + PITCH / 2 + 8
    line_x = WIDTH / 2 - 50
    paper = "paper or card" if coloured else "white paper or card"
    last = ("Crosses are pink and noughts are yellow. Keep the black marks sharp: no gloss." if coloured
            else "Keep the black marks sharp: no gloss, no colour, no pencil.")
    return ("<?xml version='1.0' encoding='utf-8'?>\n"
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}mm" height="{HEIGHT}mm" viewBox="0 0 {WIDTH} {HEIGHT}" '
            'role="img" aria-labelledby="title description" font-family="Arial, sans-serif">\n'
            '  <title id="title">Dobot Studio tic-tac-toe tokens to cut out</title>\n'
            '  <desc id="description">Fifteen crosses and fifteen noughts, each a 25 millimetre disc with a black mark.</desc>\n'
            '  <g id="heading" fill="#17283b">\n'
            '    <text x="15" y="18" font-size="6" font-weight="bold">Dobot Studio tic-tac-toe tokens</text>\n'
            f'    <text x="15" y="26" font-size="3.4">Print at 100% (not Fit) on matte {paper}. Each token is 25 mm across.</text>\n'
            '    <text x="15" y="32" font-size="3.4">Cut along the grey circles. For a firmer token, glue the sheet to 3 mm foam board first.</text>\n'
            f'    <text x="15" y="38" font-size="3.4">{last}</text>\n'
            '  </g>\n'
            '  <g id="tokens">\n' + "".join(f"    {part}\n" for part in tokens) + "  </g>\n"
            '  <g id="print-scale" fill="none" stroke="#17283b" stroke-width="0.42">\n'
            f'    <line x1="{number(line_x)}" y1="{number(bottom)}" x2="{number(line_x + 100)}" y2="{number(bottom)}" />\n'
            f'    <line x1="{number(line_x)}" y1="{number(bottom - 2)}" x2="{number(line_x)}" y2="{number(bottom + 2)}" />\n'
            f'    <line x1="{number(line_x + 100)}" y1="{number(bottom - 2)}" x2="{number(line_x + 100)}" y2="{number(bottom + 2)}" />\n'
            '  </g>\n'
            f'  <text x="{number(line_x + 104)}" y="{number(bottom + 1.3)}" font-size="3.4" font-weight="bold" fill="#17283b">100 mm</text>\n'
            "</svg>\n")


def main():
    for name, colours in SHEETS.items():
        coloured = colours["X"] != colours["O"]
        (FOLDER / f"{name}.svg").write_text(svg(colours, coloured), encoding="utf-8")
        document = BytesIO(cairosvg.svg2pdf(url=str(FOLDER / f"{name}.svg")))
        writer = PdfWriter()
        writer.append(PdfReader(document))
        writer.add_metadata({"/Title": "Dobot Studio Tic-tac-toe | cut-out tokens" + (" (colour)" if coloured else ""),
                             "/Author": "Dobot Studio", "/Subject": "Fifteen X and fifteen O tokens, 25 mm, to cut out"})
        writer._root_object[NameObject("/ViewerPreferences")] = DictionaryObject(
            {NameObject("/PrintScaling"): NameObject("/None")})
        with (FOLDER / f"{name}.pdf").open("wb") as stream:
            writer.write(stream)


if __name__ == "__main__":
    main()
