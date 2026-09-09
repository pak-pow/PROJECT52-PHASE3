#!/usr/bin/env python3
"""
SVG Status Badge Generator for CI/CD Pipelines
Generates Shields.io-style clean SVG badges for:
- Build Status (passing / failing / running)
- Test Coverage (percentage with color thresholding)
- Deployment Status (staging / production / pending)
- Test Results (e.g. 19 passed)
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_BADGES_DIR = Path(__file__).resolve().parent.parent / "badges"

COLOR_MAP = {
    "brightgreen": "#4c1",
    "green": "#97ca00",
    "yellowgreen": "#a4a61d",
    "yellow": "#dfb317",
    "orange": "#fe7d37",
    "red": "#e05d44",
    "blue": "#007ec6",
    "grey": "#555",
    "lightgrey": "#9f9f9f",
}


def get_coverage_color(pct):
    """Determine badge color based on test coverage percentage."""
    if pct >= 90.0:
        return COLOR_MAP["brightgreen"]
    elif pct >= 80.0:
        return COLOR_MAP["yellow"]
    elif pct >= 70.0:
        return COLOR_MAP["orange"]
    else:
        return COLOR_MAP["red"]


def get_status_color(status):
    """Map status string to appropriate badge color."""
    status_lower = str(status).lower()
    if status_lower in ["passing", "passed", "success"]:
        return COLOR_MAP["brightgreen"]
    elif status_lower in ["failing", "failed", "failure"]:
        return COLOR_MAP["red"]
    elif status_lower in ["running", "pending"]:
        return COLOR_MAP["yellow"]
    elif status_lower in ["staging"]:
        return COLOR_MAP["orange"]
    elif status_lower in ["production"]:
        return COLOR_MAP["blue"]
    return COLOR_MAP["lightgrey"]


def generate_svg_badge(label, message, color=None):
    """Generate a clean SVG badge matching Shields.io style."""
    if color is None:
        color = get_status_color(message)
    elif color in COLOR_MAP:
        color = COLOR_MAP[color]

    # Calculate proportional widths based on string lengths
    label_len = len(str(label))
    msg_len = len(str(message))
    label_width = max(label_len * 7 + 12, 40)
    msg_width = max(msg_len * 7 + 12, 40)
    total_width = label_width + msg_width

    label_x = label_width / 2.0
    msg_x = label_width + (msg_width / 2.0)

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {message}">
  <title>{label}: {message}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{msg_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_x * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(label_width - 12) * 10}">{label}</text>
    <text x="{label_x * 10}" y="140" transform="scale(.1)" fill="#fff" textLength="{(label_width - 12) * 10}">{label}</text>
    <text aria-hidden="true" x="{msg_x * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(msg_width - 12) * 10}">{message}</text>
    <text x="{msg_x * 10}" y="140" transform="scale(.1)" fill="#fff" textLength="{(msg_width - 12) * 10}">{message}</text>
  </g>
</svg>"""
    return svg_content


def save_badge(label, message, output_path, color=None):
    """Generate and write SVG badge to disk."""
    svg_data = generate_svg_badge(label, message, color=color)
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_data)
    print(f"[BADGE] Saved: {output_path} ({label}: {message})")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="SVG Status Badge Generator")
    parser.add_argument("--label", default="build", help="Left side label text")
    parser.add_argument(
        "--message", default="passing", help="Right side message text"
    )
    parser.add_argument(
        "--color", default=None, help="Custom color name or hex"
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_BADGES_DIR / "build.svg"),
        help="Target output SVG path",
    )
    args = parser.parse_args()

    save_badge(
        label=args.label,
        message=args.message,
        output_path=args.output,
        color=args.color,
    )


if __name__ == "__main__":
    main()
