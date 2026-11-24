# Dobot tic-tac-toe print set

The 3D mat is **300 × 300 × 2.8 mm**. It has nine recessed play cells, five reserve
slots for the Dobot’s pieces, and four corner outlines for camera markers.
The 3D mat and 300 mm paper SVG use **Ø25 × 3.2 mm** pieces. The full-size A3
mat uses **Ø40 × 5.12 mm** pieces. Models use millimetres.

| File | Use |
| --- | --- |
| [mat-300x300.obj](mat-300x300.obj) | Print the entire mat on a bed that can fit it. |
| [mat-300x300.svg](mat-300x300.svg) | Edit or print the vector artwork with its full 300 mm outline. |
| [mat-a3.pdf](mat-a3.pdf), [mat-a3.svg](mat-a3.svg) | Print or edit the full-size A3 landscape mat. |
| [tiles/](tiles/) | Print four 150 × 150 mm quadrants for smaller beds. |
| [cross.obj](cross.obj), [nought.obj](nought.obj) | Ø25 mm tokens for the 300 mm mats. [Cross 3MF](cross.3mf), [nought 3MF](nought.3mf), [OBJ parts](parts/). |
| [A3 cross.obj](a3-pieces/cross.obj), [A3 nought.obj](a3-pieces/nought.obj) | Ø40 mm tokens for the A3 mat. [Cross 3MF](a3-pieces/cross.3mf), [nought 3MF](a3-pieces/nought.3mf), [OBJ parts](a3-pieces/parts/). |
| [mat-markers.pdf](mat-markers.pdf) | Attach the four camera markers to the mat. |

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

## Print the paper mat

Print **mat-a3.pdf** on **A3 landscape** at **Actual Size (100%)**. Measure the
100 mm scale line. The drawing uses a 410 × 287 mm area with 5 mm margins.
Use the Ø40 mm pieces in **a3-pieces/**. The Ø25 mm pieces fit the 300 mm SVG.
Both paper layouts outline the play, reserve and Park positions. The small Park
ring on the A3 grid divider guides the clearance position above the mat.

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

Print the mat face up with the shallow wells on top. For the tiled version,
follow the filenames with the reserve rack on the right. Join the tiles
edge to edge on a flat backing, keeping the top surface level. Secure the
mat against sliding before calibrating the arm.

Print the marker PDF at **Actual Size**, check the 50 mm scale line, and keep
the white border around each black marker. Attach 44 at top left, 45 at top
right, 46 at bottom right and 47 at bottom left, centred inside the corner
outlines. Keep the markers outside the play and reserve wells.

For camera and robot setup, see [Tic-tac-toe in Dobot Studio](../../README.md#tic-tac-toe).
