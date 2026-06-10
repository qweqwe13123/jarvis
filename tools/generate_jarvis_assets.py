from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ICONSET = ASSETS / "JarvisMark.iconset"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def make_logo(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx = cy = size / 2

    for i in range(16, 0, -1):
        r = size * (0.20 + i * 0.018)
        alpha = int(12 + i * 5)
        g.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 212, 255, alpha), width=max(2, i))

    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.018)))
    d = ImageDraw.Draw(img)

    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / size
        col = (
            int(0 + 6 * t),
            int(18 + 18 * t),
            int(26 + 32 * t),
            255,
        )
        bd.line((0, y, size, y), fill=col)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((64, 64, size - 64, size - 64), radius=220, fill=255)
    img.alpha_composite(bg, (0, 0))
    img.putalpha(mask)
    d = ImageDraw.Draw(img)

    for idx, radius in enumerate([400, 330, 255]):
        color = (0, 212, 255, 225 - idx * 35)
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=10 - idx * 2)

    for deg in range(0, 360, 10):
        rad = math.radians(deg)
        outer = size * 0.39
        inner = size * (0.355 if deg % 30 == 0 else 0.372)
        x1, y1 = cx + math.cos(rad) * outer, cy + math.sin(rad) * outer
        x2, y2 = cx + math.cos(rad) * inner, cy + math.sin(rad) * inner
        d.line((x1, y1, x2, y2), fill=(143, 252, 255, 170), width=3)

    arc_box = (cx - 430, cy - 430, cx + 430, cy + 430)
    for start, color in [(20, (255, 107, 0, 230)), (152, (0, 255, 136, 210)), (265, (0, 212, 255, 240))]:
        d.arc(arc_box, start, start + 58, fill=color, width=18)

    shield = [
        (cx, cy - 250),
        (cx + 190, cy - 140),
        (cx + 150, cy + 170),
        (cx, cy + 285),
        (cx - 150, cy + 170),
        (cx - 190, cy - 140),
    ]
    d.polygon(shield, fill=(2, 21, 31, 245), outline=(0, 212, 255, 255))
    d.line(shield + [shield[0]], fill=(0, 212, 255, 255), width=8)

    text = "J"
    font = _font(310)
    bbox = d.textbbox((0, 0), text, font=font)
    tx = cx - (bbox[2] - bbox[0]) / 2
    ty = cy - (bbox[3] - bbox[1]) / 2 - 42
    d.text((tx + 4, ty + 4), text, font=font, fill=(0, 0, 0, 180))
    d.text((tx, ty), text, font=font, fill=(216, 248, 255, 255))

    small = _font(54)
    label = "MARK XXXIX"
    bbox = d.textbbox((0, 0), label, font=small)
    d.text((cx - (bbox[2] - bbox[0]) / 2, cy + 260), label, font=small, fill=(255, 204, 0, 230))
    return img


def save_iconset(logo: Image.Image) -> None:
    ASSETS.mkdir(exist_ok=True)
    ICONSET.mkdir(exist_ok=True)
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in sizes:
        logo.resize((px, px), Image.Resampling.LANCZOS).save(ICONSET / name)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    logo = make_logo()
    logo.save(ASSETS / "jarvis_logo.png")
    logo.resize((512, 512), Image.Resampling.LANCZOS).save(ROOT / "face.png")
    save_iconset(logo)
    icns_path = ASSETS / "JarvisMark.icns"
    try:
        logo.save(
            icns_path,
            format="ICNS",
            sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
        )
    except Exception:
        try:
            subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns_path)], check=True)
        except Exception:
            print("ICNS generation failed; PNG logo was generated.")
    print(f"Generated logo: {ASSETS / 'jarvis_logo.png'}")


if __name__ == "__main__":
    main()
