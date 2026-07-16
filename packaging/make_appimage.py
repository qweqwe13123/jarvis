#!/usr/bin/env python3
"""Pack a PyInstaller onedir tree into a Linux AppImage."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "AURA"
APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/"
    "continuous/appimagetool-x86_64.AppImage"
)


def _run(cmd: list[str], *, env: dict | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def _ensure_appimagetool(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tool = cache_dir / "appimagetool-x86_64.AppImage"
    if not tool.is_file():
        print(f"[AppImage] downloading appimagetool → {tool}")
        urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return tool


def _pick_icon() -> Path:
    candidates = [
        ROOT / "assets" / "JarvisMark.iconset" / "icon_256x256.png",
        ROOT / "assets" / "JarvisMark.iconset" / "icon_512x512.png",
        ROOT / "assets" / "aura_logo_square_bg.png",
        ROOT / "assets" / "aura_logo.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("No icon PNG found under assets/")


def make_appimage(onedir: Path, out_path: Path, *, version: str) -> Path:
    """
    Build out_path AppImage from a PyInstaller onedir (…/AURA with binary AURA).
    """
    onedir = onedir.resolve()
    binary = onedir / APP_NAME
    if not binary.is_file():
        raise FileNotFoundError(f"PyInstaller binary missing: {binary}")

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    icon_src = _pick_icon()
    tool = _ensure_appimagetool(ROOT / "build" / "appimagetool")

    with tempfile.TemporaryDirectory(prefix="aura-appdir-") as tmp:
        appdir = Path(tmp) / f"{APP_NAME}.AppDir"
        lib_dir = appdir / "usr" / "lib" / APP_NAME
        bin_dir = appdir / "usr" / "bin"
        share_apps = appdir / "usr" / "share" / "applications"
        share_icons = appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"

        for d in (lib_dir.parent, bin_dir, share_apps, share_icons):
            d.mkdir(parents=True, exist_ok=True)

        # Copy the whole onedir next to a stable launch path.
        shutil.copytree(onedir, lib_dir, symlinks=True)

        apprun = appdir / "AppRun"
        apprun.write_text(
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'HERE="$(dirname "$(readlink -f "$0")")"\n'
            f'export APPDIR="$HERE"\n'
            f'exec "$HERE/usr/lib/{APP_NAME}/{APP_NAME}" "$@"\n',
            encoding="utf-8",
        )
        apprun.chmod(0o755)

        desktop_name = "aura.desktop"
        desktop = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            "Comment=A.U.R.A desktop assistant\n"
            f"Exec={APP_NAME}\n"
            "Icon=aura\n"
            "Categories=Utility;Office;\n"
            "Terminal=false\n"
            f"X-AppImage-Version={version}\n"
        )
        (appdir / desktop_name).write_text(desktop, encoding="utf-8")
        (share_apps / desktop_name).write_text(desktop, encoding="utf-8")

        # Symlink so `Exec=AURA` resolves inside the runtime.
        link = bin_dir / APP_NAME
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(f"../lib/{APP_NAME}/{APP_NAME}", link)

        shutil.copy2(icon_src, appdir / "aura.png")
        shutil.copy2(icon_src, share_icons / "aura.png")

        env = os.environ.copy()
        # CI runners often lack FUSE; extract-and-run avoids mounting the tool.
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        env.setdefault("ARCH", "x86_64")

        _run(
            [
                str(tool),
                "--no-appstream",
                str(appdir),
                str(out_path),
            ],
            env=env,
        )

    if not out_path.is_file():
        raise RuntimeError(f"appimagetool did not create {out_path}")
    out_path.chmod(out_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[AppImage] ready → {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build AURA AppImage from PyInstaller onedir")
    parser.add_argument("onedir", type=Path, help="Path to dist/AURA onedir")
    parser.add_argument("out", type=Path, help="Output .AppImage path")
    parser.add_argument("--version", default="0.0.0")
    args = parser.parse_args()
    make_appimage(args.onedir, args.out, version=args.version)
