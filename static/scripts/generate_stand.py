#!/usr/bin/env python3
"""Generate the original parametric phone-holder assets for CAD Experience."""
import math
from pathlib import Path

from shapely.geometry import Polygon
import trimesh

PARAMS = {
    "stand_width": 65,
    "base_depth_min": 70,
    "base_height": 8,
    "lip_height": 12,
    "lip_thickness": 6,
    "slot_width": 11,
    "back_height": 95,
    "back_thickness": 10,
    "lean_angle_deg": 12,
    "corner_radius": 1.5,
}


def profile(p):
    run = (p["back_height"] - p["base_height"]) * math.tan(math.radians(p["lean_angle_deg"]))
    x0 = 0.0
    x1 = p["lip_thickness"]
    x2 = x1 + p["slot_width"]
    x3 = x2 + run
    x4 = x3 + p["back_thickness"]
    x5 = x4 - run
    xmax = max(x5, p["base_depth_min"])
    base, lip, top = p["base_height"], p["lip_height"], p["back_height"]
    return [(x0, 0), (x0, lip), (x1, lip), (x1, base), (x2, base),
            (x3, top), (x4, top), (x5, base), (xmax, base), (xmax, 0), (x0, 0)]


def main():
    output = Path(__file__).resolve().parent.parent / "model"
    output.mkdir(parents=True, exist_ok=True)
    shape = Polygon(profile(PARAMS)).buffer(0)
    radius = PARAMS["corner_radius"]
    rounded = shape.buffer(-radius, join_style="round").buffer(radius, join_style="round")
    points = list(rounded.exterior.coords)
    mesh = trimesh.creation.extrude_polygon(Polygon(points), height=PARAMS["stand_width"])
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    mesh.export(output / "stand.stl")
    mesh.export(output / "stand.glb")
    mesh.export(output / "stand.3mf")
    xs, ys = zip(*points)
    width, height = max(xs) + 10, max(ys) + 10
    path = "M " + " L ".join(f"{x:.2f},{height-y:.2f}" for x, y in points) + " Z"
    (output / "profile.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}">'
        f'<path d="{path}" fill="#e8e2d4" stroke="#2b2b2b" stroke-width="1.2"/></svg>',
        encoding="utf-8",
    )
    print("Generated CAD phone holder:", output)


if __name__ == "__main__":
    main()
