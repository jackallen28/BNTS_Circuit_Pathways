"""Generate the playable fixture from the same dimensions as camera registration.

Requires Shapely 2.1+ and trimesh. Run with PYTHONPATH=. from apps/dobot-studio.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from shapely import constrained_delaunay_triangles, unary_union
from shapely.affinity import rotate
from shapely.geometry import Point, box
from shapely.geometry.polygon import orient
from trimesh import Trimesh

from dobot_studio.tictactoe import (
    A3_MAT, ANCHORS, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, MARK_DEPTH, MAT_FLOOR, MAT_HEIGHT,
    MAT_POSITIONS, MAT_TOP, MAT_WIDTH, NEST_RADIUS, NOUGHT_INNER, NOUGHT_OUTER,
    PIECE_HEIGHT, PIECE_RADIUS, SUGGESTED_PARK,
)

WELL_COLOUR_DEPTH = 0.6
MAT_MATERIAL_FILE = "mat-colours.mtl"
MAT_MATERIALS = """newmtl Body
Ka 0 0 0
Kd 0.92 0.92 0.92
Ks 0 0 0
d 1.0
illum 1

newmtl Black_Circles
Ka 0 0 0
Kd 0 0 0
Ks 0 0 0
d 1.0
illum 1
"""


def polygon_parts(shape):
    return shape.geoms if shape.geom_type == "MultiPolygon" else (shape,)


def mesh_from_surfaces(solid, height, recesses=()):
    """Closed extrusion with disjoint recesses in its build-plate face."""
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
    underside = solid.difference(unary_union([shape for shape, _ in recesses])) if recesses else solid
    cap(underside, 0, upward=False)
    for shape, depth in recesses:
        cap(shape, depth, upward=False)
        walls(shape, 0, depth, inward=True)
    model = Trimesh(vertices=vertices, faces=faces, process=False, validate=False)
    if not model.is_volume:
        raise ValueError("Fixture mesh is not a consistently wound, watertight solid.")
    return model


def circle(x, y, radius, segments=12):
    return Point(x, y).buffer(radius, quad_segs=segments)


def mat_meshes():
    outline = box(4, 4, MAT_WIDTH - 4, MAT_HEIGHT - 4).buffer(4, quad_segs=8)

    def flat(label):
        x, y = label
        return x, MAT_HEIGHT - y

    wells = unary_union([circle(*flat(centre), NEST_RADIUS) for centre in MAT_POSITIONS.values()])
    grooves = []
    for x in (107, 161):
        grooves.append(box(x - 0.65, 79, x + 0.65, 247))
    for y in (192.5, 137.5):
        grooves.append(box(53, y - 0.65, 215, y + 0.65))
    grooves.append(box(209, 62, 211, 238))
    for centre in ANCHORS.values():
        x, y = flat(centre)
        grooves.append(box(x - 11, y - 11, x + 11, y + 11).difference(
            box(x - 10, y - 10, x + 10, y + 10)))
    x, y = flat(SUGGESTED_PARK)
    grooves.extend((box(x-5, y-0.45, x+5, y+0.45), box(x-0.45, y-5, x+0.45, y+5)))
    seams = box(149.25, 0, 150.75, MAT_HEIGHT).union(box(0, 149.25, MAT_WIDTH, 150.75))
    grooves = unary_union([groove.difference(seams) for groove in grooves])
    well_depth = MAT_TOP - MAT_FLOOR
    flip = np.array(((1,0,0,0), (0,1,0,0), (0,0,-1,MAT_TOP), (0,0,0,1)))

    def make(solid):
        discs = wells.intersection(solid)
        cutouts = ((grooves.intersection(solid), well_depth), (discs, well_depth + WELL_COLOUR_DEPTH))
        body = mesh_from_surfaces(solid, MAT_TOP, cutouts)
        body.apply_transform(flip)
        inlays = mesh_from_surfaces(discs, WELL_COLOUR_DEPTH)
        inlays.apply_translation((0, 0, MAT_FLOOR - WELL_COLOUR_DEPTH))
        return [("Body", body), ("Black_Circles", inlays)]

    yield "mat-300x300.obj", make(outline)
    for name, bounds in (
        ("top-left", (0,150,150,300)), ("top-right", (150,150,300,300)),
        ("bottom-left", (0,0,150,150)), ("bottom-right", (150,0,300,150)),
    ):
        parts = make(outline.intersection(box(*bounds)))
        for _, mesh in parts:
            mesh.apply_translation((-bounds[0], -bounds[1], 0))
        yield f"tiles/mat-{name}.obj", parts


def piece_meshes(kind):
    disc = circle(0, 0, PIECE_RADIUS, segments=16)
    if kind == "nought":
        glyph = circle(0, 0, NOUGHT_OUTER).difference(circle(0, 0, NOUGHT_INNER))
    else:
        stroke = box(-CROSS_HALF_LENGTH, -CROSS_HALF_WIDTH, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH)
        glyph = rotate(stroke, 45, origin=(0,0)).union(rotate(stroke, -45, origin=(0,0)))
    body = mesh_from_surfaces(disc, PIECE_HEIGHT, ((glyph, MARK_DEPTH),))
    colour = mesh_from_surfaces(glyph, MARK_DEPTH)
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


def write_mat(output):
    for name, parts in mat_meshes():
        write_obj(output / name, parts, MAT_MATERIAL_FILE)
    for folder in (output, output / "tiles"):
        (folder / MAT_MATERIAL_FILE).write_text(MAT_MATERIALS, encoding="ascii", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("printables/tictactoe"))
    output = parser.parse_args().output
    write_mat(output)
    write_pieces(output)
    write_pieces(output / "a3-pieces", A3_MAT.piece_scale)


if __name__ == "__main__":
    main()
