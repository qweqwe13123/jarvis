#!/usr/bin/env python3
"""Build assets/AURA.ico from the JarvisMark iconset (Windows exe icon)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "assets" / "JarvisMark.iconset"
OUT = ROOT / "assets" / "AURA.ico"


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("error: Pillow required (pip install Pillow)", file=sys.stderr)
        return 1

    if not ICONSET.is_dir():
        print(f"error: missing iconset: {ICONSET}", file=sys.stderr)
        return 1

    base = Image.open(ICONSET / "icon_256x256.png").convert("RGBA")
    sizes = (16, 32, 48, 64, 128, 256)
    named = {
        16: ICONSET / "icon_16x16.png",
        32: ICONSET / "icon_32x32.png",
        128: ICONSET / "icon_128x128.png",
        256: ICONSET / "icon_256x256.png",
    }
    images: list[Image.Image] = []
    for size in sizes:
        src = named.get(size)
        if src is not None and src.is_file():
            im = Image.open(src).convert("RGBA")
            if im.size != (size, size):
                im = im.resize((size, size), Image.Resampling.LANCZOS)
        else:
            im = base.resize((size, size), Image.Resampling.LANCZOS)
        images.append(im)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(
        OUT,
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[:-1],
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
