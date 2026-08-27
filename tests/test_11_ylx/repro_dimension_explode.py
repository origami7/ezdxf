"""Reproduce DIMENSION geometry block corruption in ezdxf explode().

Bug summary
-----------
Insert.explode() rebuilds the DIMENSION's anonymous geometry block via
``dim.override().render()``. The renderer (``LinearDimension``) reads the
``oblique_angle`` DXF value with a hard-coded default of **90** in
``src/ezdxf/render/dim_linear.py``:

    self.oblique_angle = self.dimension.get_dxf_attrib("oblique_angle", 90)

But the file produced by AutoCAD/RVT stores ``oblique_angle = 0`` (the
natural meaning: extension lines are perpendicular to the dimension line).
As a result ``LinearDimension`` computes:

    ext_line_angle = dim_line_angle + oblique_angle
                   = 90 + 90 = 180 degrees   # wrong
instead of
                   = 90 + 0  = 90 degrees    # right

That wrong angle is fed into ``extension_line_points()`` which uses
``direction = (end - start).normalize()`` when the points differ; in this
file the points are *almost* the same, but the direction ends up being
(-1, 0) instead of (0, -1), producing extension-line start points that
are ~3.4 million units away from the measurement point.

The output anonymous block ``*D0``, ``*D1``, ... is then used by every
DXF consumer (AutoCAD, dxf2svg, BricsCAD) to *display* the dimension, so
the user sees lines that jump far outside the drawing even though
``defpoint``/``defpoint2``/``defpoint3`` look fine in the property panel.

Run with::

    python repro_dimension_explode.py
"""

from __future__ import annotations
import math
import ezdxf
from ezdxf.explode import explode_block_reference
from ezdxf.render.dim_linear import LinearDimension

DXF = "tests/test_11_ylx/水施-101~105 给排水平面图_t3_t3.dxf"
BLOCK_NAME = "二层平面图"


def fmt(v):
    return f"{v:.6f}"


def main():
    doc = ezdxf.readfile(DXF)
    msp = doc.modelspace()

    inserts = [e for e in msp if e.dxftype() == "INSERT" and e.dxf.name == BLOCK_NAME]
    assert inserts, "no INSERT for 二层平面图"
    insert = inserts[0]

    exploded = explode_block_reference(insert, msp)
    dims = [e for e in exploded if e.dxftype() == "DIMENSION"]
    assert dims, "no DIMENSION produced by explode()"

    bad = 0
    for i, dim in enumerate(dims[:20]):  # inspect first 20 for brevity
        # what the property panel shows
        dxf_oblique = dim.dxf.get("oblique_angle", 0)

        # what the ezdxf renderer uses
        renderer = LinearDimension(dim)
        used_oblique = renderer.oblique_angle
        ext_angle = math.degrees(renderer.ext_line_angle) % 360

        geom_name = dim.dxf.get("geometry")
        block = doc.blocks.get(geom_name)
        # collect LINE entities only
        lines = [e for e in block if e.dxftype() == "LINE"]
        if not lines:
            continue
        # check whether ext-lines start "near" the measurement point (defpoint2/3)
        # if they are ~millions away, the block is corrupt
        ext_starts = [lines[0].dxf.start, lines[1].dxf.start]
        max_dist = max(
            abs(p.x - dim.dxf.defpoint2.x) for p in ext_starts
        )

        if max_dist > 1e4:
            bad += 1
            print(
                f"#{i:3d}  dxf.oblique={dxf_oblique:>6.2f}  "
                f"renderer.oblique={used_oblique:>6.2f}  "
                f"ext_angle={ext_angle:7.2f}°  "
                f"line.start.x={fmt(ext_starts[0].x)}  "
                f"defpoint2.x={fmt(dim.dxf.defpoint2.x)}  "
                f"Δx={fmt(ext_starts[0].x - dim.dxf.defpoint2.x)}  "
                f"[CORRUPT]"
            )
        else:
            print(
                f"#{i:3d}  dxf.oblique={dxf_oblique:>6.2f}  "
                f"renderer.oblique={used_oblique:>6.2f}  "
                f"ext_angle={ext_angle:7.2f}°  [ok]"
            )

    print()
    print(f"total inspected : {min(20, len(dims))}")
    print(f"corrupted blocks: {bad}")
    print()
    if bad:
        print("ROOT CAUSE: src/ezdxf/render/dim_linear.py:47-49")
        print("    self.oblique_angle = self.dimension.get_dxf_attrib(")
        print("        'oblique_angle', 90   <-- default 90 is wrong; should be 0")


if __name__ == "__main__":
    main()