# Dobot tic-tac-toe print set

The 3D mat is **300 × 300 × 2.8 mm**. It has nine recessed play cells, five reserve
slots for the Dobot’s pieces, and four corner outlines for camera markers.
The play pieces are **Ø25 × 3.2 mm**. Models use millimetres.

| File | Use |
| --- | --- |
| [mat-300x300.obj](mat-300x300.obj) | Print the entire mat on a bed that can fit it. |
| [mat-300x300.svg](mat-300x300.svg) | Edit or print the vector artwork with its full 300 mm outline. |
| [mat-a3.pdf](mat-a3.pdf) | Print one A3 landscape paper mat at actual size. |
| [tiles/](tiles/) | Print four 150 × 150 mm quadrants for smaller beds. |
| [cross.obj](cross.obj), [nought.obj](nought.obj) | Two-part OBJ files with named **Body** and **Mark** meshes. |
| [parts/](parts/) | Separate Body and Mark OBJs with the same origin. |
| [cross.3mf](cross.3mf), [nought.3mf](nought.3mf) | Multipart geometry with the two colour parts aligned. |
| [mat-markers.pdf](mat-markers.pdf) | Attach the four camera markers to the mat. |

## Colour the pieces in Bambu Studio

1. Import `cross.obj` or `nought.obj`. Use **Split → To Parts** if the parts
   appear together in the object list. The separate OBJs in `parts/` can
   also be imported together as a single object with multiple parts. Use the
   matching 3MF if OBJ import merges or shifts the two parts.
2. Assign a light matte filament to **Body** and a dark filament to **Mark**.
   Keep the pieces a different brightness from the mat so the camera can see
   their edges. Use a similar material for both parts.
3. Keep the supplied orientation. The mark starts at the build plate and
   occupies the first 0.6 mm of the piece. At 0.20 mm layers it shows from the
   first layer. In the slicer preview, check that the Body and Mark are both
   present on layer one and share a flat face. Duplicate the whole assembled
   piece five times for each symbol.
4. Flip each piece over so the first printed face and symbol face up during
   play. Check the suction cup on a spare piece before using the arm.

## Print the paper mat

Print **mat-a3.pdf** on **A3 landscape** at **Actual Size (100%)**. Measure the
100 mm scale line. Use the **300 × 300 mm SVG** when you want the full square.
Both paper formats outline the play, reserve and Park positions.

The paper layouts have five X reserve slots on the left and five O reserve
slots on the right, spaced 30 mm apart. Keep the solid dark squares and white
border of each built-in camera marker so the camera can read its pattern.
Use Dobot Studio to register and teach this layout. The app also recognises
the single-reserve 3D mat and earlier paper mats.

Secure the sheet flat, capture it empty and teach the tool using a sample
piece centred on each circle. If the camera sees the tool over the mat,
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
