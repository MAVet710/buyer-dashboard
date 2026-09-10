"""Presentation-only label geometry. Authoritative content stays in the run snapshot."""
from __future__ import annotations

import math

BLOCKS = {"header", "dates", "sources", "parties", "warning", "qr", "barcode", "tag", "unit"}


def validate_design(value: dict) -> dict:
    def number(raw, minimum, maximum):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or not minimum <= raw <= maximum:
            raise ValueError("Label dimensions and positions must be finite numbers within the supported range.")
        return float(raw)

    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported label design version.")
    width = number(value.get("width_in"), 0.1, 200)
    height = number(value.get("height_in"), 0.1, 200)
    rows = value.get("blocks")
    if not isinstance(rows, list) or len(rows) != len(BLOCKS) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Keep every generated label block in the design.")
    if any(not isinstance(row.get("id"), str) for row in rows) or {row["id"] for row in rows} != BLOCKS:
        raise ValueError("Keep every generated label block in the design.")
    blocks = []
    for row in rows:
        x, y = number(row.get("x"), 0, width), number(row.get("y"), 0, height)
        w, h = number(row.get("width"), 0.01, width), number(row.get("height"), 0.01, height)
        if x + w > width + 0.00001 or y + h > height + 0.00001:
            raise ValueError("A label block extends beyond the label stock.")
        align = row.get("align", "left")
        if align not in {"left", "center", "right"}:
            raise ValueError("Choose left, center, or right alignment.")
        blocks.append(dict(id=row["id"], x=x, y=y, width=w, height=h,
                           font_size=number(row.get("font_size"), 4, 72),
                           bold=bool(row.get("bold", False)), align=align))
    for index, left in enumerate(blocks):
        for right in blocks[index + 1:]:
            if (min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"]) > 0.00001
                    and min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"]) > 0.00001):
                raise ValueError("Label blocks overlap. Move or resize them before saving.")
    return dict(version=1, width_in=width, height_in=height, blocks=blocks)
