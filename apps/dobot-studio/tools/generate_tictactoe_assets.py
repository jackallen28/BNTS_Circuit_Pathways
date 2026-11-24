"""Generate the 3D print files: the playing pieces and the flat, two-colour mats.

The mats are built from the same SVG artwork as the paper mats, so the 3D print
and the paper print cannot drift apart. Each mat is a Body and a Mark. The Mark is
the artwork (rings, grid and camera markers) as a flush inlay in the first
layers, so the build-plate face is flat and solid for multicolour printing.

Requires Shapely 2.1+ and trimesh. Run with PYTHONPATH=. from apps/dobot-studio.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from shapely import constrained_delaunay_triangles, set_precision, unary_union
from shapely.affinity import affine_transform, rotate
from shapely.geometry import LineString, Point, box
from shapely.geometry.polygon import orient
from trimesh import Trimesh

from dobot_studio.tictactoe import (
    A3_MAT, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, MARK_DEPTH, MAT_MARK_DEPTH, MAT_TOP,
    NOUGHT_INNER, NOUGHT_OUTER, PIECE_HEIGHT, PIECE_RADIUS,
)

# Beside each mat OBJ, so Bambu Studio assigns the colours on import: light Body, black Mark.
MAT_MATERIAL_FILE = "mat-colours.mtl"
MAT_MATERIALS = """newmtl Body
Ka 0 0 0
Kd 0.92 0.92 0.92
Ks 0 0 0
d 1.0
illum 1

newmtl Mark
Ka 0 0 0
Kd 0 0 0
Ks 0 0 0
d 1.0
illum 1
"""
SVG = "{http://www.w3.org/2000/svg}"
PRINTABLES = Path("printables/tictactoe")
# Printability for a 0.4 mm nozzle. Paper artwork finer than this is thickened, and the
# generator refuses to write a mat that still has detail below the limit.
MIN_LINE = 0.6        # grid lines, rings and the Park ring
MIN_DETAIL = 0.58     # nothing in the artwork may be thinner than this
OPEN = 0.01           # cells that only touch at a corner are parted by this much (mm)
GRID = 0.001          # shapes are snapped to this grid (mm) so vertices agree exactly
SEAM_CLEARANCE = 0.2  # marks stop this far from a tile edge so the Body stays closed
# Paper-only guides that have no place on a printed mat.
PAPER_ONLY = {"print-area", "300-mm-outline", "print-scale"}
# (SVG file, output name, folder for the pieces it can be cut into, cut at x, cut at y), cuts
# in millimetres across the finished mat, chosen where no ring or marker is crossed.
# The 300 mm mat fits a Bambu H2D bed (325 x 320 mm) whole, and splits in four for 256 mm beds.
# A3 (420 x 297 mm) splits in two for the H2D, whose bed is 325 mm wide at most.
MATS = (
    ("mat-300x300.svg", "mat-300x300", "tiles", 150, 160),
    ("mat-a3.svg", "mat-a3", "a3-halves", 155, None),
)


def polygon_parts(shape):
    return shape.geoms if shape.geom_type == "MultiPolygon" else (shape,)


def mesh_from_surfaces(solid, recess, cut_depth, height):
    """Closed extrusion with a recess cut into its build-plate face."""
    vertices, faces, lookup = [], [], {}

    def vertex(x, y, z):
        key = tuple(round(value, 5) for value in (x, y, z))
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append(key)
        return lookup[key]

    def face(points, flip=False):
        indices = [vertex(*point) for point in points]
        faces.append(indices[::-1] if flip else indices)

    def cap(shape, z, upward):
        for patch in polygon_parts(shape):
            for triangle in constrained_delaunay_triangles(patch).geoms:
                coordinates = orient(triangle, sign=1).exterior.coords[:3]
                face([(x, y, z) for x, y in coordinates], flip=not upward)

    def walls(shape, start, end, inward=False):
        for patch in polygon_parts(shape):
            p = orient(patch, sign=1)
            for ring in (p.exterior, *p.interiors):
                for (ax, ay), (bx, by) in zip(ring.coords, ring.coords[1:]):
                    a, b, c, d = (ax, ay, start), (bx, by, start), (bx, by, end), (ax, ay, end)
                    face((a, b, c), flip=inward)
                    face((a, c, d), flip=inward)

    cap(solid, height, upward=True)
    walls(solid, 0, height)
    if recess is None:
        cap(solid, 0, upward=False)
    else:
        cap(solid.difference(recess), 0, upward=False)
        cap(recess, cut_depth, upward=False)
        walls(recess, 0, cut_depth, inward=True)
    model = Trimesh(vertices=vertices, faces=faces, process=False, validate=False)
    if not model.is_volume:
        raise ValueError("Fixture mesh is not a consistently wound, watertight solid.")
    return model


def circle(x, y, radius, segments=12):
    return Point(x, y).buffer(radius, quad_segs=segments)


def ring(centre, radius, stroke):
    return centre.buffer(radius + stroke / 2, quad_segs=16).difference(
        centre.buffer(radius - stroke / 2, quad_segs=16))


def svg_marks(path):
    """The dark artwork of a paper mat as shapes in millimetres, with y running down.

    The mats carry no printed position names (A1, X3 and so on). Dobot Studio's setup
    screen names and highlights each position instead.
    """
    root = ET.parse(path).getroot()
    width, height = (float(value) for value in root.attrib["viewBox"].split()[2:])
    shapes, fragile = [], []   # fragile: rings and markers, which a cut must never touch
    for group in root.findall(f"{SVG}g"):
        if group.attrib.get("id") in PAPER_ONLY:
            continue
        for element in group:
            tag = element.tag.removeprefix(SVG)
            number = lambda name, default=0.0: float(element.attrib.get(name, default))
            stroke = max(MIN_LINE, number("stroke-width"))
            outlined = element.attrib.get("stroke") and element.attrib.get("fill", "none") == "none"
            if tag == "circle" and outlined:
                shapes.append(ring(Point(number("cx"), number("cy")), number("r"), stroke))
                fragile.append(shapes[-1])
            elif tag == "line":
                shapes.append(LineString([(number("x1"), number("y1")), (number("x2"), number("y2"))])
                              .buffer(stroke / 2, cap_style="flat"))
            elif tag == "rect" and outlined:
                x, y, w, h, corner = number("x"), number("y"), number("width"), number("height"), number("rx")
                path_shape = (box(x + corner, y + corner, x + w - corner, y + h - corner).buffer(corner, quad_segs=8)
                              if corner else box(x, y, x + w, y + h))
                shapes.append(path_shape.buffer(stroke / 2).difference(path_shape.buffer(-stroke / 2)))
            elif tag == "rect" and element.attrib.get("fill") == "#000000":
                shapes.append(box(number("x"), number("y"), number("x") + number("width"),
                                  number("y") + number("height")))
                fragile.append(shapes[-1])
            elif tag == "text":
                raise ValueError(f"{path.name}: the mat has no printed labels. Remove the text {element.text!r}.")
    artwork = unary_union(shapes)
    lost = artwork.difference(artwork.buffer(-MIN_DETAIL / 2, join_style="mitre")
                              .buffer(MIN_DETAIL / 2, join_style="mitre")).area
    if lost > 1:
        raise ValueError(f"{path.name}: {lost:.1f} mm2 of the artwork is thinner than {MIN_DETAIL} mm.")
    return width, height, artwork, unary_union(fragile)


def mat_meshes(source):
    """Yield (name, [(part, mesh), ...]) for each mat and its pieces, from the SVGs in ``source``.

    The mat prints face-down so its play face is the flat first layer, like the pieces.
    The model is therefore the play face seen from behind: turned end for end,
    which mirrors it left to right once the print is flipped over.
    """
    for svg, name, folder, cut_x_play, cut_y_play in MATS:
        width, height, artwork, fragile = svg_marks(source / svg)
        turn = [-1, 0, 0, -1, width, height]
        artwork, fragile = affine_transform(artwork, turn), affine_transform(fragile, turn)
        # Diagonal marker cells touch at a point, which would pinch the solid. Part them.
        artwork = artwork.buffer(-OPEN, join_style="mitre").buffer(OPEN, join_style="round")
        outline = box(4, 4, width - 4, height - 4).buffer(4, quad_segs=8)
        if not outline.contains(artwork):
            raise ValueError(f"{svg}: the artwork reaches the edge of the mat.")

        def make(solid, marks):
            solid = set_precision(solid, GRID)
            marks = set_precision(marks.intersection(solid), GRID).intersection(solid)
            body = mesh_from_surfaces(solid, marks, MAT_MARK_DEPTH, MAT_TOP)
            mark = mesh_from_surfaces(marks, None, 0, MAT_MARK_DEPTH)
            if abs(body.volume + mark.volume - solid.area*MAT_TOP) > 0.5:
                raise ValueError("The two print colours leave a gap or overlap.")
            return [("Body", body), ("Mark", mark)]

        yield name, make(outline, artwork)
        # Cut lines run across the mat as it looks when played; the model is turned end for end.
        cut_x = width - cut_x_play
        cut_y = None if cut_y_play is None else height - cut_y_play
        seams = box(cut_x - SEAM_CLEARANCE, 0, cut_x + SEAM_CLEARANCE, height)
        if cut_y is not None:
            seams = seams.union(box(0, cut_y - SEAM_CLEARANCE, width, cut_y + SEAM_CLEARANCE))
        if fragile.intersects(seams):
            raise ValueError(f"{svg}: a cut line runs through a ring or marker.")
        columns = (("left", cut_x, width), ("right", 0, cut_x))
        rows = ((("top", cut_y, height), ("bottom", 0, cut_y)) if cut_y is not None else (("", 0, height),))
        for row, y0, y1 in rows:
            for column, x0, x1 in columns:
                parts = make(outline.intersection(box(x0, y0, x1, y1)), artwork.difference(seams))
                for _, mesh in parts:
                    mesh.apply_translation((-x0, -y0, 0))
                label = "-".join(part for part in (row, column) if part)
                yield f"{folder}/mat-{label}", parts


def piece_meshes(kind):
    disc = circle(0, 0, PIECE_RADIUS, segments=16)
    if kind == "nought":
        glyph = circle(0, 0, NOUGHT_OUTER).difference(circle(0, 0, NOUGHT_INNER))
    else:
        stroke = box(-CROSS_HALF_LENGTH, -CROSS_HALF_WIDTH, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH)
        glyph = rotate(stroke, 45, origin=(0,0)).union(rotate(stroke, -45, origin=(0,0)))
    body = mesh_from_surfaces(disc, glyph, MARK_DEPTH, PIECE_HEIGHT)
    colour = mesh_from_surfaces(glyph, None, 0, MARK_DEPTH)
    if abs(body.volume + colour.volume - disc.area*PIECE_HEIGHT) > 0.03:
        raise ValueError("The two print colours leave a gap or overlap.")
    return [("Body", body), ("Mark", colour)]


def write_obj(path, parts, material_file=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Dobot Studio tic-tac-toe · coordinates in millimetres\n")
        if material_file:
            stream.write(f"mtllib {material_file}\n")
        offset = 1
        for name, mesh in parts:
            stream.write(f"o {name}\n")
            for x, y, z in mesh.vertices:
                stream.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
            stream.write(f"g {name}\n")
            if material_file:
                stream.write(f"usemtl {name}\n")
            for a, b, c in mesh.faces:
                stream.write(f"f {offset+a} {offset+b} {offset+c}\n")
            offset += len(mesh.vertices)


def write_3mf(path, parts):
    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    model = ET.Element("model", {"xmlns": ns, "unit": "millimeter"})
    resources = ET.SubElement(model, "resources")
    for index, (name, mesh) in enumerate(parts, 1):
        obj = ET.SubElement(resources, "object", id=str(index), name=name, type="model")
        mesh_node = ET.SubElement(obj, "mesh")
        vertices = ET.SubElement(mesh_node, "vertices")
        triangles = ET.SubElement(mesh_node, "triangles")
        for x, y, z in mesh.vertices:
            ET.SubElement(vertices, "vertex", x=str(x), y=str(y), z=str(z))
        for a, b, c in mesh.faces:
            ET.SubElement(triangles, "triangle", v1=str(a), v2=str(b), v3=str(c))
    group = ET.SubElement(resources, "object", id="3", name=path.stem, type="model")
    components = ET.SubElement(group, "components")
    for number in ("1", "2"):
        ET.SubElement(components, "component", objectid=number)
    ET.SubElement(ET.SubElement(model, "build"), "item", objectid="3")

    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml",
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                         '</Types>')
        package.writestr("_rels/.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Target="/3D/3dmodel.model" '
                         'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Id="rel0"/>'
                         '</Relationships>')
        package.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))


def write_pieces(output, scale=1.0):
    for kind in ("nought", "cross"):
        parts = piece_meshes(kind)
        if scale != 1.0:
            for _, mesh in parts:
                mesh.apply_scale(scale)
        write_obj(output / f"{kind}.obj", parts)
        for name, mesh in parts:
            write_obj(output / "parts" / f"{kind}-{name.lower()}.obj", [(name, mesh)])
        write_3mf(output / f"{kind}.3mf", parts)


def write_zip(folder):
    """Bundle the whole print set for download. Fixed timestamps keep the zip reproducible."""
    with ZipFile(folder.parent / "tictactoe-300mm.zip", "w", ZIP_DEFLATED) as package:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                info = ZipInfo(f"{folder.name}/{path.relative_to(folder).as_posix()}", (2026, 1, 1, 0, 0, 0))
                info.compress_type, info.external_attr = ZIP_DEFLATED, 0o644 << 16
                package.writestr(info, path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PRINTABLES)
    parser.add_argument("--source", type=Path, default=PRINTABLES, help="folder holding the mat SVG artwork")
    parser.add_argument("--only", choices=("all", "mat", "pieces"), default="all",
                        help="regenerate only the mat or only the pieces")
    parser.add_argument("--zip", action="store_true", help="also rebuild the download zip beside --output")
    arguments = parser.parse_args()
    output = arguments.output
    if arguments.only != "pieces":
        for path, parts in mat_meshes(arguments.source):
            write_obj(output / f"{path}.obj", parts, MAT_MATERIAL_FILE)
            write_3mf(output / f"{path}.3mf", parts)
            (output / path).parent.joinpath(MAT_MATERIAL_FILE).write_text(MAT_MATERIALS, encoding="ascii", newline="\n")
    if arguments.only != "mat":
        write_pieces(output)
        write_pieces(output / "a3-pieces", A3_MAT.piece_scale)
    if arguments.zip:
        write_zip(output)


if __name__ == "__main__":
    main()
