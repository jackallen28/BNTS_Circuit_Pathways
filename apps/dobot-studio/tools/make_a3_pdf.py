"""Rebuild mat-a3.pdf from mat-a3.svg at exactly A3 landscape (420 x 297 mm).

The PDF asks viewers to print at 100%, with no Fit or Shrink. Requires cairosvg and pypdf.
Run from apps/dobot-studio: python tools/make_a3_pdf.py
"""
from io import BytesIO
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

FOLDER = Path("printables/tictactoe")


def main():
    document = BytesIO(cairosvg.svg2pdf(url=str(FOLDER / "mat-a3.svg")))
    writer = PdfWriter()
    writer.append(PdfReader(document))
    writer.add_metadata({
        "/Title": "Dobot Studio Tic-tac-toe | A3 paper mat",
        "/Subject": "A3 landscape mat with separate reserve banks and camera markers",
        "/Author": "Dobot Studio",
    })
    writer._root_object[NameObject("/ViewerPreferences")] = DictionaryObject(
        {NameObject("/PrintScaling"): NameObject("/None")})
    with (FOLDER / "mat-a3.pdf").open("wb") as stream:
        writer.write(stream)


if __name__ == "__main__":
    main()
