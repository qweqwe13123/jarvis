#!/usr/bin/env python3
"""Generate Inno Setup wizard images (Cursor-style branding)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging" / "windows" / "wizard"
LOGO_CANDIDATES = (
    ROOT / "assets" / "aura_logo_square_bg.png",
    ROOT / "assets" / "JarvisMark.iconset" / "icon_256x256.png",
    ROOT / "assets" / "aura_logo_onboarding.png",
    ROOT / "assets" / "aura_logo.png",
)


def _pick_logo() -> Path:
    for path in LOGO_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError("No AURA logo PNG found under assets/")


def _fit_logo(im, box: tuple[int, int], *, pad: float = 0.72):
    from PIL import Image

    tw, th = box
    max_w = int(tw * pad)
    max_h = int(th * pad)
    logo = im.convert("RGBA")
    logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    x = (tw - logo.width) // 2
    y = (th - logo.height) // 2
    canvas.paste(logo, (x, y), logo)
    return canvas


def build() -> dict[str, Path]:
    from PIL import Image, ImageDraw, ImageFilter

    OUT.mkdir(parents=True, exist_ok=True)
    logo = Image.open(_pick_logo()).convert("RGBA")

    # Large left panel (welcome / finish) — dark premium pane like Cursor.
    # Classic Inno size ~164x314; modern WizardStyle scales up — use 2x.
    big_w, big_h = 328, 628
    bg = Image.new("RGB", (big_w, big_h), (6, 16, 24))  # near AURA HUD #061018
    # Soft cyan glow behind mark
    glow = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    cx, cy = big_w // 2, big_h // 2 - 20
    for r, a in ((180, 28), (130, 40), (90, 55)):
        gdraw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 209, 255, a))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")

    mark = _fit_logo(logo, (big_w, big_h), pad=0.55)
    panel = bg.convert("RGBA")
    panel.paste(mark, (0, 0), mark)
    big_bmp = OUT / "wizard-image.bmp"
    big_png = OUT / "wizard-image.png"
    panel.convert("RGB").save(big_bmp, format="BMP")
    panel.save(big_png, format="PNG")

    # Small top-right header mark (~55x55 classic; use 110 for retina-ish).
    small_size = 110
    small_bg = Image.new("RGBA", (small_size, small_size), (6, 16, 24, 255))
    # Rounded-ish square by covering corners lightly isn't needed; paste logo.
    small_mark = _fit_logo(logo, (small_size, small_size), pad=0.86)
    small = Image.alpha_composite(small_bg, small_mark)
    small_bmp = OUT / "wizard-small-image.bmp"
    small_png = OUT / "wizard-small-image.png"
    small.convert("RGB").save(small_bmp, format="BMP")
    small.save(small_png, format="PNG")

    print(f"wrote {big_bmp}")
    print(f"wrote {small_bmp}")
    return {
        "wizard_image": big_bmp,
        "wizard_small": small_bmp,
        "wizard_image_png": big_png,
        "wizard_small_png": small_png,
    }


def main() -> int:
    try:
        build()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
