#!/usr/bin/env python3
"""Generate a system-style DMG background (Claude / standard macOS installer).

Light off-white canvas + simple gray arrow. Icon captions come from Finder
(black system text) — do NOT paint labels on the artwork.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "dmg_assets"

# Finder window content size
WIN_W, WIN_H = 660, 400

# Icon drop targets — must match make_dmg.py
APP_XY = (160, 180)
APPS_XY = (500, 180)


def _arrow(layer: Image.Image, scale: int) -> None:
    """Simple dark-gray chevron like Claude / standard macOS DMGs."""
    w, h = layer.size
    # Between the two icon slots
    x0 = int((APP_XY[0] + 70) * scale)
    x1 = int((APPS_XY[0] - 70) * scale)
    y = int(APP_XY[1] * scale)

    shaft_h = max(8, 10 * scale)
    head_w = max(22, 28 * scale)
    head_h = max(28, 36 * scale)
    color = (110, 110, 115, 220)

    solid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(solid)
    # Shaft
    sd.rounded_rectangle(
        (x0, y - shaft_h // 2, x1 - head_w // 2, y + shaft_h // 2),
        radius=shaft_h // 2,
        fill=color,
    )
    # Head
    tip = x1
    sd.polygon(
        [
            (tip - head_w, y - head_h // 2),
            (tip, y),
            (tip - head_w, y + head_h // 2),
        ],
        fill=color,
    )
    layer.alpha_composite(solid)


def render(scale: int = 1) -> Image.Image:
    w, h = WIN_W * scale, WIN_H * scale
    # Classic Finder light gray / off-white
    base = Image.new("RGBA", (w, h), (246, 246, 246, 255))
    _arrow(base, scale)
    return base


def build_assets() -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    img1 = render(1)
    img2 = render(2)
    p1 = OUT / "background.png"
    p2 = OUT / "background@2x.png"
    tiff = OUT / "background.tiff"
    img1.save(p1, format="PNG", optimize=True)
    img2.save(p2, format="PNG", optimize=True)

    made = False
    try:
        import subprocess

        subprocess.run(
            [
                "tiffutil",
                "-cathidpicheck",
                str(p1),
                str(p2),
                "-out",
                str(tiff),
            ],
            check=True,
            capture_output=True,
        )
        made = True
    except Exception as exc:
        print(f"[dmg_bg] tiffutil failed ({exc}); falling back to single TIFF")

    if not made:
        img2.convert("RGB").save(tiff, format="TIFF", compression="tiff_adobe_deflate")

    print(f"Wrote {p1} ({img1.size})")
    print(f"Wrote {p2} ({img2.size})")
    print(f"Wrote {tiff} ({tiff.stat().st_size} bytes)")
    return {"1x": p1, "2x": p2, "tiff": tiff}


if __name__ == "__main__":
    build_assets()
