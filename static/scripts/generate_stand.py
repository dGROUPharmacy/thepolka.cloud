#!/usr/bin/env python3
"""Generate committed phone-holder assets using only the Python standard library."""

import json
import math
import struct
import zipfile
from pathlib import Path


def add_box(vertices, triangles, center, size, angle_x=0):
    cx, cy, cz = center
    sx, sy, sz = (value / 2 for value in size)
    start = len(vertices)
    cosine, sine = math.cos(angle_x), math.sin(angle_x)
    for x, y, z in [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]:
        rotated_y = y * cosine - z * sine
        rotated_z = y * sine + z * cosine
        vertices.append((x + cx, rotated_y + cy, rotated_z + cz))
    for a, b, c in [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]:
        triangles.append((start + a, start + b, start + c))


def geometry():
    vertices, triangles = [], []
    add_box(vertices, triangles, (0, 0, 4), (65, 76, 8))
    add_box(vertices, triangles, (0, -34, 10), (65, 7, 20))
    add_box(vertices, triangles, (0, 25, 50), (65, 9, 88), math.radians(-12))
    add_box(vertices, triangles, (0, 30, 8), (65, 22, 8))
    return vertices, triangles


def glb_bytes(vertices, triangles):
    positions = b"".join(struct.pack("<3f", *vertex) for vertex in vertices)
    indices_flat = [index for triangle in triangles for index in triangle]
    indices = b"".join(struct.pack("<H", index) for index in indices_flat)
    binary = positions + (b"\0" * ((4 - len(positions) % 4) % 4)) + indices
    binary += b"\0" * ((4 - len(binary) % 4) % 4)
    mins = [min(vertex[i] for vertex in vertices) for i in range(3)]
    maxs = [max(vertex[i] for vertex in vertices) for i in range(3)]
    document = {
        "asset": {"version": "2.0", "generator": "ThePolka.Cloud pure-Python CAD"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "rotation": [-0.7071068, 0, 0, 0.7071068]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.15, 0.66, 0.78, 1], "metallicFactor": 0.18, "roughnessFactor": 0.38}, "doubleSided": True}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions) + ((4 - len(positions) % 4) % 4), "byteLength": len(indices), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3", "min": mins, "max": maxs},
            {"bufferView": 1, "componentType": 5123, "count": len(indices_flat), "type": "SCALAR"},
        ],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(encoded), b"JSON") + encoded
        + struct.pack("<I4s", len(binary), b"BIN\0") + binary
    )


def normal(a, b, c):
    u = tuple(b[i] - a[i] for i in range(3))
    v = tuple(c[i] - a[i] for i in range(3))
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(value * value for value in cross)) or 1
    return tuple(value / length for value in cross)


def stl_bytes(vertices, triangles):
    data = bytearray(b"ThePolka.Cloud parametric phone holder".ljust(80, b"\0"))
    data.extend(struct.pack("<I", len(triangles)))
    for triangle in triangles:
        points = [vertices[index] for index in triangle]
        data.extend(struct.pack("<3f", *normal(*points)))
        for point in points:
            data.extend(struct.pack("<3f", *point))
        data.extend(struct.pack("<H", 0))
    return bytes(data)


def write_3mf(path, vertices, triangles):
    vertex_xml = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in vertices)
    triangle_xml = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles)
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<metadata name="Title">ThePolka.Cloud Parametric Phone Holder</metadata>
<resources><object id="1" type="model"><mesh><vertices>{vertex_xml}</vertices><triangles>{triangle_xml}</triangles></mesh></object></resources>
<build><item objectid="1"/></build></model>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr("3D/3dmodel.model", model)


def main():
    output = Path(__file__).resolve().parent.parent / "model"
    output.mkdir(parents=True, exist_ok=True)
    vertices, triangles = geometry()
    (output / "stand.glb").write_bytes(glb_bytes(vertices, triangles))
    (output / "stand.stl").write_bytes(stl_bytes(vertices, triangles))
    write_3mf(output / "stand.3mf", vertices, triangles)
    (output / "stand-poster.svg").write_text(
        '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 560"><defs><linearGradient id="b" x2="1" y2="1"><stop stop-color="#081b2d"/><stop offset="1" stop-color="#173b51"/></linearGradient><linearGradient id="m" x2="1" y2="1"><stop stop-color="#96ecf3"/><stop offset="1" stop-color="#198ca4"/></linearGradient></defs><rect width="900" height="560" fill="url(#b)"/><g transform="translate(185 78)"><path d="M74 362 520 362 570 409 116 409Z" fill="#106479"/><path d="M116 409 570 409 570 440 116 440Z" fill="#083c4e"/><path d="M407 103 472 76 526 356 458 376Z" fill="url(#m)"/><path d="M72 320 125 304 125 408 72 409Z" fill="#51c9d8"/><path d="M72 320 125 304 164 324 109 342Z" fill="#a5f2f4"/><ellipse cx="324" cy="468" rx="260" ry="23" fill="#03101b" opacity=".55"/></g><text x="450" y="48" text-anchor="middle" fill="#d7f9fa" font-family="system-ui" font-size="19">PARAMETRIC PHONE HOLDER · INTERACTIVE 3D</text></svg>''',
        encoding="utf-8",
    )
    print("Generated CAD assets:", output)


if __name__ == "__main__":
    main()
