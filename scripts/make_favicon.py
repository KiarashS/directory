#!/usr/bin/env python3
"""Generate the favicon set from one SVG source.

    python3 scripts/make_favicon.py

The mark matches the one in the site header: a folder on the indigo-to-teal
gradient, in a rounded square. The header draws it as a thin outline, which
turns to mush at 16px, so the icon uses a solid folder instead — same shape,
legible at a tab's size.

Rerun this after editing static/icon.svg; it rewrites every size.
"""
from __future__ import annotations

import io
import pathlib
import sys

import cairosvg
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static" / "icon.svg"

# Rounded-square background matching .brand-mark, with a solid folder on top.
SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4f5bd5"/>
      <stop offset="1" stop-color="#2f8fb8"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="116" fill="url(#g)"/>
  <path fill="#ffffff"
        d="M112 154a30 30 0 0 1 30-30h74a30 30 0 0 1 21 9l25 25h140a30 30 0 0 1 30 30v170a30 30 0 0 1-30 30H142a30 30 0 0 1-30-30z"/>
  <path fill="#ffffff" opacity="0.55"
        d="M112 214h288v-26a30 30 0 0 0-30-30H262l-25-25a30 30 0 0 0-21-9h-74a30 30 0 0 0-30 30z"/>
</svg>
'''

# (filename, pixel size)
PNGS = [
    ("favicon-16x16.png", 16),
    ("favicon-32x32.png", 32),
    ("apple-touch-icon.png", 180),
    ("android-chrome-192x192.png", 192),
    ("android-chrome-512x512.png", 512),
    ("mstile-150x150.png", 150),
]

# A Safari pinned tab is a single-colour silhouette, so it gets the folder
# alone with no background or gradient.
PINNED = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <path d="M56 132a34 34 0 0 1 34-34h96a34 34 0 0 1 24 10l30 30h172a34 34 0 0 1 34 34v206a34 34 0 0 1-34 34H90a34 34 0 0 1-34-34z"/>
</svg>
'''


def render(svg: str, size: int) -> Image.Image:
    data = cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                            output_width=size, output_height=size)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def main() -> int:
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text(SVG, encoding="utf-8")
    (ROOT / "safari-pinned-tab.svg").write_text(PINNED, encoding="utf-8")

    for name, size in PNGS:
        render(SVG, size).save(ROOT / name, "PNG", optimize=True)
        print(f"  {name} ({size}x{size})")

    # One .ico holding the three sizes Windows and older browsers ask for.
    base = render(SVG, 256)
    base.save(ROOT / "favicon.ico", "ICO",
              sizes=[(16, 16), (32, 32), (48, 48)])
    print("  favicon.ico (16, 32, 48)")
    print("  static/icon.svg, safari-pinned-tab.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
