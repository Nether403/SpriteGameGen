"""Atlas metadata writer (pure, byte-stable).

Serializes a packer layout to either JSON (sorted keys, stable formatting) or a
simple TexturePacker-style XML. Deterministic output so a golden-file test can
pin the format.
"""
from __future__ import annotations

import json
from xml.sax.saxutils import quoteattr

Layout = list[dict[str, int]]


def _json_atlas(layout: Layout, sheet_size: tuple[int, int]) -> str:
    w, h = sheet_size
    doc = {
        "frames": [
            {
                "index": item["index"],
                "filename": f"frame_{item['index']}.png",
                "frame": {
                    "x": item["x"],
                    "y": item["y"],
                    "w": item["w"],
                    "h": item["h"],
                },
            }
            for item in sorted(layout, key=lambda it: it["index"])
        ],
        "meta": {
            "app": "sprite-game-asset-tool",
            "format": "RGBA8888",
            "size": {"w": w, "h": h},
        },
    }
    # sort_keys + fixed indent => byte-stable across runs.
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def _xml_atlas(
    layout: Layout, sheet_size: tuple[int, int], sheet_filename: str
) -> str:
    w, h = sheet_size
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        f'<TextureAtlas imagePath={quoteattr(sheet_filename)} width="{w}" height="{h}">'
    )
    for item in sorted(layout, key=lambda it: it["index"]):
        name = quoteattr(f"frame_{item['index']}.png")
        lines.append(
            f"  <SubTexture name={name} "
            f'x="{item["x"]}" y="{item["y"]}" '
            f'width="{item["w"]}" height="{item["h"]}"/>'
        )
    lines.append("</TextureAtlas>")
    return "\n".join(lines) + "\n"


def write_atlas(
    layout: Layout,
    sheet_size: tuple[int, int],
    fmt: str = "json",
    *,
    sheet_filename: str = "sprite_sheet.png",
) -> str:
    """Serialize ``layout`` for a sheet of ``sheet_size`` to ``fmt`` ('json'|'xml')."""
    fmt = fmt.lower()
    if fmt == "json":
        return _json_atlas(layout, sheet_size)
    if fmt == "xml":
        return _xml_atlas(layout, sheet_size, sheet_filename)
    raise ValueError(f"unknown atlas format: {fmt!r} (expected 'json' or 'xml')")
