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
    ANCHORS, CROSS_HALF_LENGTH, CROSS_HALF_WIDTH, MARK_DEPTH, MAT_FLOOR, MAT_HEIGHT,
    MAT_POSITIONS, MAT_TOP, MAT_WIDTH, NEST_RADIUS, NOUGHT_INNER, NOUGHT_OUTER,
    PIECE_HEIGHT, PIECE_RADIUS, SUGGESTED_PARK,
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


def mat_meshes():
    outline = box(4, 4, MAT_WIDTH - 4, MAT_HEIGHT - 4).buffer(4, quad_segs=8)

    def flat(label):
        x, y = label
        return x, MAT_HEIGHT - y

    wells = [circle(*flat(centre), NEST_RADIUS) for centre in MAT_POSITIONS.values()]
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
    pockets = unary_union(wells + [groove.difference(seams) for groove in grooves])

    def make(solid):
        result = mesh_from_surfaces(solid, pockets.intersection(solid), MAT_TOP-MAT_FLOOR, MAT_TOP)
        result.apply_transform(np.array(((1,0,0,0), (0,1,0,0), (0,0,-1,MAT_TOP), (0,0,0,1))))
        if not result.is_volume:
            raise ValueError("Mat recesses did not produce a solid upper face.")
        return result

    yield "mat-300x300.obj", make(outline)
    for name, bounds in (
        ("top-left", (0,150,150,300)), ("top-right", (150,150,300,300)),
        ("bottom-left", (0,0,150,150)), ("bottom-right", (150,0,300,150)),
    ):
        tile = make(outline.intersection(box(*bounds)))
        tile.apply_translation((-bounds[0], -bounds[1], 0))
        yield f"tiles/mat-{name}.obj", tile


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


def write_obj(path, parts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Dobot Studio tic-tac-toe · coordinates in millimetres\n")
        offset = 1
        for name, mesh in parts:
            stream.write(f"o {name}\n")
            for x, y, z in mesh.vertices:
                stream.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
            stream.write(f"g {name}\n")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("printables/tictactoe"))
    output = parser.parse_args().output
    for path, mesh in mat_meshes():
        write_obj(output / path, [("Mat", mesh)])
    for kind in ("nought", "cross"):
        parts = piece_meshes(kind)
        write_obj(output / f"{kind}.obj", parts)
        for name, mesh in parts:
            write_obj(output / "parts" / f"{kind}-{name.lower()}.obj", [(name, mesh)])
        write_3mf(output / f"{kind}.3mf", parts)


if __name__ == "__main__":
    main()
