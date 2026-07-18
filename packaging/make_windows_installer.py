#!/usr/bin/env python3
"""Build a Cursor-style Windows installer with Inno Setup (ISCC)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "packaging" / "windows" / "aura.iss"
DEFAULT_ICON = ROOT / "assets" / "AURA.ico"
WIZARD_DIR = ROOT / "packaging" / "windows" / "wizard"
LICENSE = ROOT / "packaging" / "windows" / "LICENSE.txt"


def _find_iscc() -> Path:
    env = (os.environ.get("ISCC") or os.environ.get("INNO_SETUP_ISCC") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p

    which = shutil.which("ISCC") or shutil.which("iscc")
    if which:
        return Path(which)

    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Inno Setup compiler (ISCC.exe) not found. "
        "Install with: choco install innosetup -y"
    )


def _ensure_wizard_art() -> tuple[Path, Path]:
    big = WIZARD_DIR / "wizard-image.bmp"
    small = WIZARD_DIR / "wizard-small-image.bmp"
    # Always regenerate so logo updates ship with each release.
    art = ROOT / "packaging" / "make_windows_wizard_art.py"
    subprocess.run([sys.executable, str(art)], check=True)
    if not big.is_file() or not small.is_file():
        raise FileNotFoundError(f"Wizard art missing after generate: {WIZARD_DIR}")
    return big, small


def make_installer(
    source_dir: Path,
    out_path: Path,
    *,
    version: str,
    icon: Path | None = None,
) -> Path:
    source_dir = source_dir.resolve()
    out_path = out_path.resolve()
    icon = (icon or DEFAULT_ICON).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Missing onedir payload: {source_dir}")
    exe = source_dir / "AURA.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"Missing AURA.exe in {source_dir}")
    if not icon.is_file():
        raise FileNotFoundError(f"Missing icon: {icon}")
    if not ISS.is_file():
        raise FileNotFoundError(f"Missing Inno script: {ISS}")
    if not LICENSE.is_file():
        raise FileNotFoundError(f"Missing license: {LICENSE}")

    wizard_image, wizard_small = _ensure_wizard_art()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    iscc = _find_iscc()
    # Inno OutputBaseFilename has no .exe suffix.
    base = out_path.name[:-4] if out_path.name.lower().endswith(".exe") else out_path.name

    def _d(name: str, value: str | Path) -> str:
        # Quote paths so spaces (e.g. Program Files) survive ISCC parsing.
        text = str(value)
        if " " in text and not (text.startswith('"') and text.endswith('"')):
            text = f'"{text}"'
        return f"/D{name}={text}"

    cmd = [
        str(iscc),
        _d("MyAppVersion", version),
        _d("MyAppSourceDir", source_dir),
        _d("MyAppOutputDir", out_path.parent),
        _d("MyAppOutputBase", base),
        _d("MyAppIcon", icon),
        _d("MyWizardImage", wizard_image),
        _d("MyWizardSmallImage", wizard_small),
        _d("MyLicenseFile", LICENSE),
        str(ISS),
    ]
    print("[Inno] ", " ".join(cmd))
    subprocess.run(cmd, check=True)
    if not out_path.is_file():
        produced = out_path.parent / f"{base}.exe"
        if produced.is_file():
            if produced.resolve() != out_path.resolve():
                shutil.move(str(produced), str(out_path))
        else:
            raise RuntimeError(f"ISCC finished but installer missing: {out_path}")
    print(f"[Inno] wrote {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build AURA Windows Inno Setup installer")
    ap.add_argument("--source", type=Path, required=True, help="PyInstaller onedir (…/AURA)")
    ap.add_argument("--output", type=Path, required=True, help="Output Setup .exe path")
    ap.add_argument("--version", required=True)
    ap.add_argument("--icon", type=Path, default=DEFAULT_ICON)
    args = ap.parse_args()
    make_installer(args.source, args.output, version=args.version, icon=args.icon)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
