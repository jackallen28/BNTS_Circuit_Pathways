# Dobot tic-tac-toe print set

There is also a **small A4 mat** for the Dobot's limited reach. See the end of this page.

There are three mats. Use the **compact mat** unless you have a reason not to. It is the
same layout in 3D and on paper:

| Mat | 3D print | Paper | Pieces | Camera markers |
| --- | --- | --- | --- | --- |
| **Compact** (recommended) | **254 × 200 mm**, one piece | **A4 landscape** | Ø25 mm | 16 mm, IDs 28–31 |
| 300 mm square | 300 × 300 mm, or four tiles | 300 mm SVG | Ø25 mm | 16 mm, IDs 36–39 |
| A3 | 420 × 297 mm, in two halves | A3 landscape | Ø40 mm | 20 mm, IDs 32–35 |

All three have nine play circles, an **X bank** of five reserve circles on the left, an
**O bank** of five on the right, a heavy grid, a small Park ring and four camera markers. The
circles are solid black. The mats carry **no printed names** such as A1 or X3. Dobot Studio names
and highlights each position during setup, and the camera finds every position from the four
markers, so the mat can sit any way round.

The compact mat has its grid and both banks **centred**, with the banks centred on the grid, and
it wastes little space. Its footprint is about 44% smaller than the 300 mm mat's. It uses the same
Ø25 mm pieces and the same 16 mm marker size as the 300 mm mat and the marker cards, so nothing
that is printed changes size. The 300 mm and A3 mats keep their own marker IDs and sizes, so
anything already printed for them still works.

The 3D mats are **2.8 mm** thick and made of two parts, **Body** and **Mark**, as the pieces are.
The artwork is a flush inlay in the first **0.6 mm**, so the face on the build plate is flat and
solid. That is the first layer you colour in Bambu Studio. Models use millimetres.

| File | Use |
| --- | --- |
| [mat-compact.obj](mat-compact.obj), [3MF](mat-compact.3mf), [mat-colours.mtl](mat-colours.mtl) | The compact 3D mat, whole. It fits a 256 mm bed (P1, X1, A1) and a Bambu **H2D** (325 × 320 mm). |
| [mat-a4.pdf](mat-a4.pdf), [mat-a4.svg](mat-a4.svg) | The compact mat on **A4 landscape** paper. |
| [mat-300x300.obj](mat-300x300.obj), [3MF](mat-300x300.3mf) | The 300 mm 3D mat whole. It fits an **H2D** bed. |
| [tiles/](tiles/) | The 300 mm mat as four tiles for **256 mm** beds. Largest tile 150 × 160 mm. |
| [mat-300x300.svg](mat-300x300.svg) | The 300 mm artwork. |
| [mat-a3.obj](mat-a3.obj), [3MF](mat-a3.3mf) | The whole A3 3D mat, 420 × 297 mm, for a printer with a bed over 420 mm. |
| [a3-halves/](a3-halves/) | The A3 3D mat in **two pieces** for a **Bambu H2D**. Left 155 × 297 mm, right 265 × 297 mm. |
| [mat-a3.pdf](mat-a3.pdf), [mat-a3.svg](mat-a3.svg) | The A3 landscape paper mat. |
| [cross.obj](cross.obj), [nought.obj](nought.obj) | Ø25 mm tokens for the compact and 300 mm mats. [Cross 3MF](cross.3mf), [nought 3MF](nought.3mf), [OBJ parts](parts/). |
| [A3 cross.obj](a3-pieces/cross.obj), [A3 nought.obj](a3-pieces/nought.obj) | Ø40 mm tokens for the A3 mat. [Cross 3MF](a3-pieces/cross.3mf), [nought 3MF](a3-pieces/nought.3mf), [OBJ parts](a3-pieces/parts/). |
| [mat-markers.pdf](mat-markers.pdf) | Marker cards 44–47, 16 mm, for an **older single-bank** 3D mat only. The current mats have the markers built in. |

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

1. Import `mat-compact.obj`. Import it as you did the pieces: accept a single object with multiple
   parts, or use **Split → To Parts**. Use the matching `.3mf` if OBJ import merges the parts.
   For the 300 mm mat on a 256 mm bed use the four files in `tiles/`. For the A3 mat on an H2D
   use the two files in `a3-halves/`, each as its own object.
2. Keep `mat-colours.mtl` in the same folder as the OBJ. Bambu Studio then offers a light colour
   for **Body** and black for **Mark** on import. Otherwise assign a **light matte** filament to
   **Body** and a **dark matte** filament to **Mark** yourself, as on the paper mat. The camera
   reads the markers as black on white, so the Body needs to be white or very light, and the Mark
   black or very dark. Avoid glossy filament, which can glare under the camera. Choose piece
   colours a little different from the mat so their edges show.
3. Keep the supplied orientation and scale. The artwork starts at the build plate.
   In the slicer preview, check that layer one is solid, with the Body and Mark
   sharing a flat face. The Mark is **0.6 mm** deep, the same as the piece marks.
4. The mat looks **mirrored** in the slicer, with the X bank on the right. That is
   correct: you print it face-down. When it is done, turn it over like a page. The
   flat first layer is the play surface, with the X bank on the left, the O bank on
   the right and a marker in each corner.

The artwork is flat colour, not shallow wells, so pieces sit on the surface. Each play
and reserve position is a **solid black circle**, the same as on the paper mats. Place a
piece over a circle. A light piece on the black circle also gives the camera strong
contrast, so keep the pieces light, as in the piece steps above.

**Printable detail.** Lines and the Park ring are at least **0.6 mm** wide, and the grid is much
heavier. The generator refuses to write a mat with detail thinner than 0.58 mm. Where a mat is
split, the cut runs between circles, so only grid lines are interrupted, and each interruption
is about 0.4 mm wide.

**Which bed?** The compact mat is 254 × 200 mm, so it prints whole on a 256 mm bed. A Bambu
**H2D** (325 × 320 mm) prints any mat except the whole A3 mat, which is 420 mm wide. It prints the
A3 mat as the two halves, and the right half is 265 mm wide.

## Print the paper mat

Print **mat-a4.pdf** on **A4 landscape at 100%**. The A3 mat is **mat-a3.pdf** on A3, and the
300 mm SVG has its own sheet size. Print each at 100%. The sheets keep their ink away from the
paper edge (at least 8 mm), so they need no borderless printing.

**Check the scale.** The 100 mm line near the bottom of each sheet must measure **100 mm** with a
ruler. The PDF is exact and asks viewers not to scale it, but printers and viewers often shrink a
page to fit the area they can print, which is about 3 mm short over 100 mm on A3. If the line is
short, turn the scaling off:

- **Adobe Acrobat or Reader:** Page Sizing & Handling → **Actual size**. Do not
  choose Fit or Shrink oversized pages.
- **Chrome or Edge print dialog:** More settings → Scale → **Default** or **Custom
  100**, and untick Fit to page or Fit to printable area.
- **The printer driver:** turn off Fit to page, Scale to fit paper, Shrink to
  printable area and Borderless.

Print again and re-measure. **Do not use a mat that is more than about 1% short.**
Dobot Studio checks every taught position against the real distances between the
circles, and refuses positions that are off by more than 7 mm. On the compact mat the farthest
circles are 233 mm apart, so a sheet 3% short would be about 7 mm out and could fail that check.

Use the Ø25 mm pieces with the A4 and 300 mm sheets, and the Ø40 mm pieces in **a3-pieces/** with
the A3 sheet. The Park ring marks the clearance position above the mat. On the compact mat it sits in
the middle of the lower grid line.

The reserve banks have five circles each, X on the left and O on the right. Keep the
solid black squares and white border of each built-in camera marker so the camera can read its
pattern.

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

## Regenerate the files

The compact mat's layout lives in `dobot_studio/tictactoe.py`. Everything else comes from it:

```sh
cd apps/dobot-studio
pip install shapely trimesh cairosvg pypdf
PYTHONPATH=. python tools/make_a4_svg.py        # the A4 sheet, from the layout
python tools/make_mat_pdf.py                    # the A3 and A4 PDFs, at exact paper size
PYTHONPATH=. python tools/generate_tictactoe_assets.py --only mat --zip   # 3D files and the zip
```

`--only mat` leaves the pieces untouched. `--zip` rebuilds the download zip, so run it last.
The generator refuses to write a mat if it has printed text, detail too fine to print, or
a cut line through a circle or marker.

For camera and robot setup, see [Tic-tac-toe in Dobot Studio](../../README.md#tic-tac-toe).

## Small A4 mat (for the Dobot's reach)

| File | Use |
| --- | --- |
| [mat-a4-small.pdf](mat-a4-small.pdf), [mat-a4-small.svg](mat-a4-small.svg) | The small mat on **A4 landscape** paper. Print at **100%**, with no Fit or Shrink. |

The Dobot Magician can reach circles that are **130 to 310 mm** from its base. The compact mat is 200 mm
between its banks, so most placements put some circle out of reach. The small mat packs the same Ø25 mm
pieces and 16 mm camera markers (**IDs 24-27**) into a ring about 90 mm out from the middle: grid
pitch 36 mm, banks 68 mm either side of the middle with 30 mm between circles. Nothing about the pieces
or markers changes size.

**Where to put it.** With 8 mm to spare at each end of the arm's 130 to 310 mm reach, and room for the arm to
wait **off the mat** between its base and the mat during a game (no nearer the base than 138 mm), every circle is
reachable when the Dobot faces the middle of a **long edge** of the sheet (either one) and the middle of the mat is
**207 to 234 mm** from the arm's base. About **220 mm** works. If the sheet is turned up to 15 degrees, keep the
middle 207 to 222 mm out. Facing a short edge leaves the arm nowhere to wait, so do not. Keep the area between the
arm's base and the mat clear. Dobot Studio checks every circle against the reach when the corners are saved and
names any it cannot reach, and it warns if the resting place is too near the mat.

**The scale line.** The line at the foot of the sheet is **100 mm** and carries no number. Measure what it
printed as with a ruler. It should be within 5 mm of 100. Type the length into **Printed line measures**
on the Dobot Studio setup and the arm allows for it.

