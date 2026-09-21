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

# The maskable variant, for Android's adaptive icons. It is a different
# picture, not the same one relabelled: the launcher crops to its own shape —
# circle, squircle, teardrop — and only the centre 72 of 108dp is guaranteed to
# survive. That is 66.7%, not the 80% usually quoted.
#
# So the background bleeds to the edges with no rx — the launcher supplies the
# shape, and baked-in corners either vanish or show as slivers inside it — and
# the mark is re-centred (its box is centred at x=272, not 256) and scaled.
#
# The scale is the safe-zone fraction itself, and that is not a coincidence.
# The launcher does not merely crop to the centre 72 of 108dp; it magnifies
# that square to fill the tile. So whatever is drawn here appears 108/72 =
# 1.5x larger on the phone than the same drawing in an ordinary icon. Scaling
# by 72/108 cancels that exactly, and the folder reads at the size it has in a
# browser tab. Fitting inside the safe circle is the floor — anything up to
# about 0.87 clears it — but a mark that merely fits is a mark that looks
# swollen.
MASKABLE_SCALE = 0.6667          # 72/108, the safe-zone fraction

MASKABLE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4f5bd5"/>
      <stop offset="1" stop-color="#2f8fb8"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#g)"/>
  <g transform="translate(256 256) scale(%s) translate(-272 -256)">
    <path fill="#ffffff"
          d="M112 154a30 30 0 0 1 30-30h74a30 30 0 0 1 21 9l25 25h140a30 30 0 0 1 30 30v170a30 30 0 0 1-30 30H142a30 30 0 0 1-30-30z"/>
    <path fill="#ffffff" opacity="0.55"
          d="M112 214h288v-26a30 30 0 0 0-30-30H262l-25-25a30 30 0 0 0-21-9h-74a30 30 0 0 0-30 30z"/>
  </g>
</svg>
''' % MASKABLE_SCALE

# (filename, pixel size)
PNGS = [
    ("favicon-16x16.png", 16),
    ("favicon-32x32.png", 32),
    ("apple-touch-icon.png", 180),
    ("android-chrome-192x192.png", 192),
    ("android-chrome-512x512.png", 512),
    ("android-chrome-1024x1024.png", 1024),
    ("mstile-150x150.png", 150),
]

# One maskable size, and it is large on purpose.
#
# A maskable icon spends a third of each axis outside the visible area, so its
# nominal size is not the size anyone sees: only the centre 72 of 108dp
# survives the launcher's crop. Android then draws the result at up to 432px
# (xxxhdpi). So 192 supplies 128 visible pixels and is stretched 3.4x — which
# is exactly what a blurry home-screen icon looks like — and even 512 supplies
# only 341 and is stretched 1.27x. 1024 gives 683 and clears it outright.
#
# Only one size is offered because a smaller maskable has no upside: a
# launcher picking it gets a worse picture, and that is the entire effect.
# The ordinary android-chrome-*.png still cover 192 and 512 for everything
# that shows an icon without masking it.
MASKABLE_SIZES = (1024,)

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

    for size in MASKABLE_SIZES:
        name = f"maskable-{size}x{size}.png"
        render(MASKABLE, size).save(ROOT / name, "PNG", optimize=True)
        print(f"  {name} ({size}x{size}, {round(size * 72 / 108)} of it visible "
              "once the launcher crops)")

    # One .ico holding the three sizes Windows and older browsers ask for.
    base = render(SVG, 256)
    base.save(ROOT / "favicon.ico", "ICO",
              sizes=[(16, 16), (32, 32), (48, 48)])
    print("  favicon.ico (16, 32, 48)")
    print("  static/icon.svg, safari-pinned-tab.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
