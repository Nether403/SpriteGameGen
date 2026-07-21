"""Atlas metadata writer: JSON (golden) + XML, byte-stable."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.pipeline.atlas import write_atlas

FIXTURES = Path(__file__).parent / "fixtures"

# Representative layout matching packer output (2x2 grid of 10x8 frames).
LAYOUT = [
    {"index": 0, "x": 0, "y": 0, "w": 10, "h": 8},
    {"index": 1, "x": 10, "y": 0, "w": 10, "h": 8},
    {"index": 2, "x": 0, "y": 8, "w": 10, "h": 8},
    {"index": 3, "x": 10, "y": 8, "w": 10, "h": 8},
]
SHEET_SIZE = (20, 16)


def test_json_matches_golden():
    out = write_atlas(LAYOUT, SHEET_SIZE, fmt="json")
    golden = (FIXTURES / "atlas_golden.json").read_text(encoding="utf-8")
    assert out == golden


def test_json_is_byte_stable_across_calls():
    a = write_atlas(LAYOUT, SHEET_SIZE, fmt="json")
    b = write_atlas(LAYOUT, SHEET_SIZE, fmt="json")
    assert a == b


def test_json_content_shape():
    data = json.loads(write_atlas(LAYOUT, SHEET_SIZE, fmt="json"))
    assert data["meta"]["size"] == {"w": 20, "h": 16}
    assert len(data["frames"]) == 4
    first = data["frames"][0]
    assert first["frame"] == {"x": 0, "y": 0, "w": 10, "h": 8}


def test_xml_is_valid_and_has_all_frames():
    out = write_atlas(LAYOUT, SHEET_SIZE, fmt="xml")
    root = ET.fromstring(out)
    assert root.tag == "TextureAtlas"
    assert root.attrib["imagePath"] == "sprite_sheet.png"
    sub = root.findall("SubTexture")
    assert len(sub) == 4
    assert sub[1].attrib["x"] == "10"
    assert sub[1].attrib["width"] == "10"


def test_xml_is_byte_stable():
    assert write_atlas(LAYOUT, SHEET_SIZE, fmt="xml") == write_atlas(
        LAYOUT, SHEET_SIZE, fmt="xml"
    )


def test_rejects_unknown_format():
    with pytest.raises(ValueError):
        write_atlas(LAYOUT, SHEET_SIZE, fmt="tga")
