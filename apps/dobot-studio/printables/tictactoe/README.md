# Dobot tic-tac-toe print set

There are two mats, a **300 × 300 mm** mat and an **A3 landscape (420 × 297 mm)**
mat. Each comes as a 3D print and as a paper print, and the two are the same
artwork. Both have nine play circles, an **X bank** of five reserve circles on the
left, an **O bank** of five on the right, the grid, a small Park ring and four
camera markers. The mats carry **no printed names** such as A1 or X3. Dobot Studio
names and highlights each position during setup, and the camera finds every
position from the four markers, so the mat can sit any way round.

The 3D mats are **2.8 mm** thick and made of two parts, **Body** and **Mark**, as
the pieces are. The artwork is a flush inlay in the first **0.6 mm**, so the face
on the build plate is flat and solid. That is the first layer you colour in
Bambu Studio. The 300 mm mat and its **Ø25 × 3.2 mm** pieces suit the 300 mm
paper SVG. The A3 mat uses the **Ø40 × 5.12 mm** pieces. Models use millimetres.

| File | Use |
| --- | --- |
| [mat-300x300.obj](mat-300x300.obj), [3MF](mat-300x300.3mf), [mat-colours.mtl](mat-colours.mtl) | The whole 300 mm mat. It fits a Bambu **H2D** bed (325 × 320 mm). |
| [tiles/](tiles/) | The 300 mm mat as four tiles for **256 mm** beds (P1, X1, A1). Largest tile 150 × 160 mm. |
| [mat-a3.obj](mat-a3.obj), [3MF](mat-a3.3mf) | The whole A3 mat, 420 × 297 mm. Only for a printer with a bed over 420 mm. |
| [a3-halves/](a3-halves/) | The A3 mat in **two pieces** for a **Bambu H2D**. Left 155 × 297 mm, right 265 × 297 mm. |
| [mat-300x300.svg](mat-300x300.svg) | Edit or print the vector artwork with its full 300 mm outline. |
| [mat-a3.pdf](mat-a3.pdf), [mat-a3.svg](mat-a3.svg) | Print or edit the A3 landscape paper mat. |
| [cross.obj](cross.obj), [nought.obj](nought.obj) | Ø25 mm tokens for the 300 mm mats. [Cross 3MF](cross.3mf), [nought 3MF](nought.3mf), [OBJ parts](parts/). |
| [A3 cross.obj](a3-pieces/cross.obj), [A3 nought.obj](a3-pieces/nought.obj) | Ø40 mm tokens for the A3 mat. [Cross 3MF](a3-pieces/cross.3mf), [nought 3MF](a3-pieces/nought.3mf), [OBJ parts](a3-pieces/parts/). |
| [mat-markers.pdf](mat-markers.pdf) | Marker cards for an **older single-bank** 3D mat only. The current mats have the markers built in. |

## Colour the pieces in Bambu Studio

1. Import `cross.obj` or `nought.obj` in the size for your mat. Use **Split → To
   Parts** if the parts appear together in the object list. The separate OBJs
   in `parts/` can also be imported together as a single object with multiple
   parts. Use the matching 3MF if OBJ import merges or shifts the two parts.
2. Assign a light matte filament to **Body** and a dark filament to **Mark**.
   Keep the pieces a different brightness from the mat so the camera can see
   their edges. Use a similar material for both parts.
3. Keep the supplied orientation and scale. The mark starts at the build plate.
   In the slicer preview, check that the Body and Mark are both present on layer
   one and share a flat face. Print five copies of each assembled token.
4. Flip each piece over so the first printed face and symbol face up during
   play. Check the suction cup on a spare piece before using the arm.

## Colour the mat in Bambu Studio

1. Import `mat-300x300.obj`, or the two files in `a3-halves/` for the A3 mat.
   On a 256 mm bed use the four files in `tiles/`. Import it as you did the pieces:
   accept a single object with multiple parts, or use **Split → To Parts**. Use the
   matching `.3mf` if OBJ import merges the parts. For the A3 halves, import each
   half as its own object.
2. Keep `mat-colours.mtl` in the same folder as the OBJ. Bambu Studio then
   offers a light colour for **Body** and black for **Mark** on import. Otherwise
   assign a **light matte** filament to **Body** and a **dark matte** filament to
   **Mark** yourself, as on the paper mat. The camera reads the markers as black on white,
   so the Body needs to be white or very light, and the Mark black or very dark.
   Avoid glossy filament, which can glare under the camera. Choose piece colours
   a little different from the mat so their edges show.
3. Keep the supplied orientation and scale. The artwork starts at the build plate.
   In the slicer preview, check that layer one is solid, with the Body and Mark
   sharing a flat face. The Mark is **0.6 mm** deep, the same as the piece marks.
4. The mat looks **mirrored** in the slicer, with the X bank on the right. That is
   correct: you print it face-down. When it is done, turn it over like a page. The
   flat first layer is the play surface, with the X bank on the left, the O bank on
   the right and a marker in each corner.

The artwork is flat colour, not shallow wells, so pieces sit on the surface. Use the
rings to place pieces, as on the paper mats.

**Printable detail.** Lines and rings are at least **0.6 mm** wide. The paper
artwork has some finer lines, and these are thickened for the 3D mat. The generator
refuses to write a mat with detail thinner than 0.58 mm. Where a mat is split, the
cut runs between rings, so only thin grid lines are interrupted, and each
interruption is about 0.4 mm wide.

**Which bed?** A Bambu **H2D** prints the 300 mm mat whole. It prints the A3 mat as
the two halves: the right half is 265 mm wide and the bed is 325 mm wide. The A3
mat does not fit in one piece, because 420 mm is wider than the bed. A 256 mm bed
prints the 300 mm mat as four tiles. The A3 mat does not fit that bed in two pieces.

## Print the paper mat

Print **mat-a3.pdf** on **A3 landscape at 100%**. The 300 mm SVG has its own
sheet size, so print it at 100% too. The A3 sheet keeps all ink at least 8 mm from
the paper edge, so it needs no borderless printing.

**Check the scale.** The 100 mm line near the bottom of the A3 sheet must measure
**100 mm** with a ruler. The PDF is exact and asks viewers not to scale it, but
printers and viewers often shrink an A3 page to fit the area they can print. That
is about 3 mm short over 100 mm, because the usual printer margin is 6.35 mm on each
side. If the line is short, turn the scaling off:

- **Adobe Acrobat or Reader:** Page Sizing & Handling → **Actual size**. Do not
  choose Fit or Shrink oversized pages.
- **Chrome or Edge print dialog:** More settings → Scale → **Default** or **Custom
  100**, and untick Fit to page or Fit to printable area.
- **The printer driver:** turn off Fit to page, Scale to fit paper, Shrink to
  printable area and Borderless.

Print again and re-measure. **Do not use a mat that is more than about 1% short.**
Dobot Studio checks every taught position against the real distances between the
circles, and refuses positions that are off by more than 7 mm. A sheet that is 3%
short fails that check for the A3 mat, because the far circles are 365 mm apart.

Use the Ø40 mm pieces in **a3-pieces/**. The Ø25 mm pieces fit the 300 mm SVG. Both
paper layouts outline the play, reserve and Park positions. The small Park ring on the
A3 grid divider guides the clearance position above the mat.

The paper layouts have five X reserve slots on the left and five O reserve
slots on the right. The A3 slots have 48 mm spacing, and the 300 mm SVG uses
30 mm spacing. Keep the solid dark squares and white border of each built-in
camera marker so the camera can read its pattern.

Secure the sheet flat and check the fitted tool can reach both banks and all
nine cells. Capture the mat empty and teach each circle using a matching
sample piece centred on it. If the camera sees the tool over the mat,
capture the empty mat again with the tool at Park. Load the reserves, choose
**Play as**, then start a new game. X goes first. The Dobot takes pieces from
its bank automatically after the camera sees a clear mat for 1.5 seconds.

## Assemble the mat

Print the mat as supplied, face-down, then turn it over so the flat first layer is
the play surface. If you printed tiles or halves, name each piece by where it sits
on the finished mat, with the X bank on the left. Join the pieces edge to edge on a
flat backing, keeping the play surface level. Secure the mat against sliding
before calibrating the arm.

The markers are part of the mat, in the four corners, so there is nothing to
attach. Keep the white border around each marker clear of tape and glue. If a
piece is lifted, capture the empty mat again.

## Regenerate the 3D files

The mats are generated from the SVG artwork, so edit the SVG and rebuild the files:

```sh
cd apps/dobot-studio
pip install shapely trimesh
PYTHONPATH=. python tools/generate_tictactoe_assets.py --only mat --zip
```

`--only mat` leaves the pieces untouched. `--zip` rebuilds the download zip. After
editing `mat-a3.svg`, rebuild the paper PDF with `pip install cairosvg pypdf` and
`python tools/make_a3_pdf.py`, then rebuild the zip. The
generator refuses to write a mat if it has printed text, detail too fine to print, or
a cut line through a ring or marker.

For camera and robot setup, see [Tic-tac-toe in Dobot Studio](../../README.md#tic-tac-toe).
