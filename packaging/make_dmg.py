#!/usr/bin/env python3
"""Create a system-style macOS DMG installer (Claude / standard Finder look).

Layout:
  [ AURA.app ]  ----arrow---->  [ Applications ]

Light off-white background, gray arrow, normal black Finder labels.
Staged bundle is ALWAYS named AURA.app.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "dmg_assets"

# Must stay in sync with packaging/dmg_background.py
WIN_X, WIN_Y = 200, 140
WIN_W, WIN_H = 660, 400
ICON_SIZE = 128
APP_XY = (160, 180)
APPS_XY = (500, 180)

STAGED_APP_NAME = "AURA.app"


def _run(cmd: list[str], *, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, **kwargs)


def _ensure_background(*, force: bool = True) -> Path:
    import importlib.util

    mod_path = Path(__file__).parent / "dmg_background.py"
    spec = importlib.util.spec_from_file_location("aura_dmg_background", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if force or not (ASSETS / "background.tiff").exists():
        return mod.build_assets()["tiff"]
    return ASSETS / "background.tiff"


def _detach(mount: Path) -> None:
    for _ in range(8):
        r = subprocess.run(
            ["hdiutil", "detach", str(mount), "-quiet"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return
        time.sleep(0.6)
    subprocess.run(["hdiutil", "detach", str(mount), "-force"], check=False)


def _find_mount(volume_name: str) -> Path | None:
    candidate = Path("/Volumes") / volume_name
    if candidate.exists():
        return candidate
    return None


def _apply_finder_layout(volume_name: str, app_name: str) -> None:
    vol = volume_name.replace('"', '\\"')
    app = app_name.replace('"', '\\"')
    script = f'''
tell application "Finder"
  tell disk "{vol}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {{{WIN_X}, {WIN_Y}, {WIN_X + WIN_W}, {WIN_Y + WIN_H}}}
    set theViewOptions to the icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to {ICON_SIZE}
    try
      set text size of theViewOptions to 12
    end try
    set background picture of theViewOptions to file ".background:background.tiff"

    try
      set extension hidden of item "{app}" to true
    end try
    try
      set position of item "{app}" of container window to {{{APP_XY[0]}, {APP_XY[1]}}}
    end try
    try
      set position of item "Applications" of container window to {{{APPS_XY[0]}, {APPS_XY[1]}}}
    end try

    update without registering applications
    delay 1
    close
    open
    delay 1
    set the bounds of container window to {{{WIN_X}, {WIN_Y}, {WIN_X + WIN_W}, {WIN_Y + WIN_H}}}
    try
      set position of item "{app}" of container window to {{{APP_XY[0]}, {APP_XY[1]}}}
    end try
    try
      set position of item "Applications" of container window to {{{APPS_XY[0]}, {APPS_XY[1]}}}
    end try
    close
  end tell
end tell
'''
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        print("[DMG] Finder layout warning:", (r.stderr or r.stdout or "").strip())
    else:
        print("[DMG] Finder layout applied (system-style)")


def _eject_existing(volume_name: str) -> None:
    for path in sorted(Path("/Volumes").glob(f"{volume_name}*"), reverse=True):
        if path.is_dir():
            _detach(path)


def make_dmg(
    app_path: Path,
    dmg_path: Path,
    *,
    volume_name: str = "AURA",
    staging_parent: Path | None = None,
) -> Path:
    app_path = app_path.resolve()
    dmg_path = dmg_path.resolve()
    if not app_path.is_dir() or not (app_path / "Contents").exists():
        raise FileNotFoundError(f"Not a macOS app bundle: {app_path}")

    _eject_existing(volume_name)
    bg_tiff = _ensure_background(force=True)
    staging_parent = staging_parent or dmg_path.parent
    staging = staging_parent / "_dmg_staging"
    rw_dmg = staging_parent / f"_{volume_name}-rw.dmg"

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    dest_app = staging / STAGED_APP_NAME
    if dest_app.exists():
        shutil.rmtree(dest_app)
    # ditto preserves codesign + stapler ticket xattrs; shutil.copytree does not.
    _run(["ditto", str(app_path), str(dest_app)])

    apps_link = staging / "Applications"
    if apps_link.exists() or apps_link.is_symlink():
        apps_link.unlink()
    apps_link.symlink_to("/Applications")

    bg_dir = staging / ".background"
    bg_dir.mkdir(exist_ok=True)
    shutil.copy2(bg_tiff, bg_dir / "background.tiff")
    for name in ("background.png", "background@2x.png"):
        src = ASSETS / name
        if src.exists():
            shutil.copy2(src, bg_dir / name)

    if dmg_path.exists():
        dmg_path.unlink()
    if rw_dmg.exists():
        rw_dmg.unlink()

    app_bytes = sum(p.stat().st_size for p in staging.rglob("*") if p.is_file())
    size_mb = max(120, int(app_bytes / (1024 * 1024)) + 80)

    _run(
        [
            "hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(staging),
            "-ov",
            "-fs",
            "HFS+",
            "-format",
            "UDRW",
            "-size",
            f"{size_mb}m",
            str(rw_dmg),
        ]
    )

    _run(["hdiutil", "attach", str(rw_dmg), "-readwrite", "-noverify", "-noautoopen"])
    mount = _find_mount(volume_name)
    if mount is None:
        info = subprocess.run(["hdiutil", "info"], capture_output=True, text=True, check=False)
        for line in (info.stdout or "").splitlines():
            if "/Volumes/" in line and volume_name in line:
                mount = Path(line.split()[-1])
                break
    if mount is None or not mount.exists():
        raise RuntimeError(f"Could not mount RW DMG for volume {volume_name!r}")

    try:
        subprocess.run(
            ["SetFile", "-a", "V", str(mount / ".background")],
            check=False,
            capture_output=True,
        )
        staged = mount / STAGED_APP_NAME
        if not staged.exists():
            for child in mount.iterdir():
                if child.suffix == ".app" and child.is_dir():
                    child.rename(staged)
                    break
        _apply_finder_layout(volume_name, STAGED_APP_NAME)
        time.sleep(1.5)
        subprocess.run(["sync"], check=False)
    finally:
        _detach(mount)

    _run(
        [
            "hdiutil",
            "convert",
            str(rw_dmg),
            "-format",
            "UDZO",
            "-imagekey",
            "zlib-level=9",
            "-o",
            str(dmg_path),
        ]
    )

    rw_dmg.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)

    print(f"[DMG] ready → {dmg_path} ({dmg_path.stat().st_size} bytes)")
    return dmg_path


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Build system-style AURA DMG")
    p.add_argument("--app", type=Path, default=ROOT / "dist" / "AURA.app")
    p.add_argument("--out", type=Path, default=ROOT / "dist" / "releases" / "AURA.dmg")
    p.add_argument("--volume", default="AURA")
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    make_dmg(args.app, args.out, volume_name=args.volume)
    return 0


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
