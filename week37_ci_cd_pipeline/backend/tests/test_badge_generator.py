import xml.etree.ElementTree as ET
from scripts.badge_generator import (
    COLOR_MAP,
    generate_svg_badge,
    get_coverage_color,
    get_status_color,
    save_badge,
)


def test_generate_svg_badge_valid_xml():
    """Verify generated badge content is valid SVG XML."""
    svg = generate_svg_badge("build", "passing")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "build" in svg
    assert "passing" in svg

    # Parse with ElementTree to guarantee well-formed XML
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.attrib["width"].isdigit() or float(root.attrib["width"]) > 0


def test_coverage_color_thresholds():
    """Verify coverage color mapping matches quality thresholds."""
    assert get_coverage_color(95.0) == COLOR_MAP["brightgreen"]
    assert get_coverage_color(90.0) == COLOR_MAP["brightgreen"]
    assert get_coverage_color(85.0) == COLOR_MAP["yellow"]
    assert get_coverage_color(75.0) == COLOR_MAP["orange"]
    assert get_coverage_color(55.0) == COLOR_MAP["red"]


def test_status_color_mapping():
    """Verify status string mapping to hex colors."""
    assert get_status_color("passing") == COLOR_MAP["brightgreen"]
    assert get_status_color("failed") == COLOR_MAP["red"]
    assert get_status_color("pending") == COLOR_MAP["yellow"]
    assert get_status_color("staging") == COLOR_MAP["orange"]
    assert get_status_color("production") == COLOR_MAP["blue"]


def test_save_badge_to_disk(tmp_path):
    """Verify save_badge writes SVG file to disk with proper content."""
    badge_file = tmp_path / "test_badge.svg"
    out_path = save_badge("tests", "19 passed", str(badge_file))
    assert badge_file.exists()
    assert badge_file.stat().st_size > 100
    content = badge_file.read_text(encoding="utf-8")
    assert "19 passed" in content
