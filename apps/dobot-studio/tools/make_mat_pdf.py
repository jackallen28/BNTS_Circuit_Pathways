"""Rebuild a mat PDF from its SVG at the exact paper size (A3 or A4 landscape).

Each PDF asks viewers to print at 100%, with no Fit or Shrink. Requires cairosvg and pypdf.
Run from apps/dobot-studio: python tools/make_mat_pdf.py [a3] [a4]   (both, by default)
"""
from io import BytesIO
from pathlib import Path
import sys

import cairosvg
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

FOLDER = Path("printables/tictactoe")
SHEETS = {
    "a3": ("mat-a3", "Dobot Studio Tic-tac-toe | A3 paper mat",
           "A3 landscape mat with separate reserve banks and camera markers"),
    "a4": ("mat-a4", "Dobot Studio Tic-tac-toe | A4 paper mat",
           "A4 landscape compact mat with separate reserve banks and camera markers"),
    "a4-small": ("mat-a4-small", "Dobot Studio Tic-tac-toe | A4 small paper mat",
                 "A4 landscape small mat, packed to fit the Dobot's reach, with separate reserve banks and camera markers"),
}


def build(name, title, subject):
    document = BytesIO(cairosvg.svg2pdf(url=str(FOLDER / f"{name}.svg")))
    writer = PdfWriter()
    writer.append(PdfReader(document))
    writer.add_metadata({"/Title": title, "/Subject": subject, "/Author": "Dobot Studio"})
    writer._root_object[NameObject("/ViewerPreferences")] = DictionaryObject(
        {NameObject("/PrintScaling"): NameObject("/None")})
    with (FOLDER / f"{name}.pdf").open("wb") as stream:
        writer.write(stream)


def main():
    for key in sys.argv[1:] or SHEETS:
        build(*SHEETS[key])


if __name__ == "__main__":
    main()
