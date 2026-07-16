#!/usr/bin/env python3
"""Build A.U.R.A desktop installers and a release manifest for auto-updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "releases"
SPEC = ROOT / "packaging" / "jarvis.spec"
APP_NAME = "AURA"


def _load_version() -> str:
    text = (ROOT / "core" / "version.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _platform_key() -> str:
    os_name = platform.system().lower()
    machine = platform.machine().lower()
    if os_name == "darwin":
        os_key = "darwin"
    elif os_name == "windows":
        os_key = "win"
    else:
        os_key = "linux"
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    return f"{os_key}-{arch}"


def _zip_tree(source: Path, dest_zip: Path) -> None:
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if source.is_file():
            zf.write(source, source.name)
            return
        parent = source.parent
        for path in source.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(parent).as_posix())


def _make_dmg(app_path: Path, dmg_path: Path, volume_name: str = "A.U.R.A") -> None:
    if dmg_path.exists():
        dmg_path.unlink()
    staging = DIST / "_dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copytree(app_path, staging / app_path.name, symlinks=True)
    try:
        (staging / "Applications").symlink_to("/Applications")
    except OSError:
        pass
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ],
        check=True,
    )
    shutil.rmtree(staging, ignore_errors=True)


def build_pyinstaller(clean: bool = True) -> Path:
    (ROOT / "resources" / "skills").mkdir(parents=True, exist_ok=True)
    if clean:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        shutil.rmtree(ROOT / "dist" / APP_NAME, ignore_errors=True)
        shutil.rmtree(ROOT / "dist" / f"{APP_NAME}.app", ignore_errors=True)
        shutil.rmtree(ROOT / "dist" / "JARVIS", ignore_errors=True)
        shutil.rmtree(ROOT / "dist" / "JARVIS.app", ignore_errors=True)
        for leftover in (ROOT / "dist").glob(f"{APP_NAME}*"):
            if leftover.is_file():
                leftover.unlink(missing_ok=True)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"],
        cwd=str(ROOT),
        check=True,
    )

    if platform.system() == "Darwin":
        return ROOT / "dist" / f"{APP_NAME}.app"
    return ROOT / "dist" / APP_NAME


def build_windows_onefile() -> Path:
    """Single AURA.exe for direct download (unsigned)."""
    out = ROOT / "dist" / f"{APP_NAME}.exe"
    if out.exists():
        out.unlink()
    sep = ";" if platform.system() == "Windows" else ":"
    prompt = ROOT / "core" / "prompt.txt"
    config = ROOT / "config"
    ui = ROOT / "jarvis_ui"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name=%s" % APP_NAME,
        "--distpath=%s" % (ROOT / "dist"),
        "--workpath=%s" % (ROOT / "build" / "onefile"),
        "--add-data=%s%s%s" % (prompt, sep, "core"),
        "--add-data=%s%s%s" % (config, sep, "config"),
        "--add-data=%s%s%s" % (ui, sep, "jarvis_ui"),
        "--hidden-import=PyQt6.QtWebEngineWidgets",
        "--hidden-import=PyQt6.QtWebEngineCore",
        "--hidden-import=google.genai",
        str(ROOT / "main.py"),
    ]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    return ROOT / "dist" / f"{APP_NAME}.exe"


def package_release(version: str, notes: str, base_url: str) -> dict:
    DIST.mkdir(parents=True, exist_ok=True)
    key = _platform_key()
    system = platform.system()
    base = base_url.rstrip("/")

    if system == "Darwin":
        artifact_root = build_pyinstaller(clean=True)
        arch = "arm64" if key.endswith("arm64") else "x64"
        primary_name = "AURA-%s-macos-%s.dmg" % (version, arch)
        primary_path = DIST / primary_name
        _make_dmg(artifact_root, primary_path)
        update_name = "AURA-%s-macos-%s.zip" % (version, arch)
        update_path = DIST / update_name
        _zip_tree(artifact_root, update_path)
    elif system == "Windows":
        onedir = build_pyinstaller(clean=True)
        update_name = "AURA-%s-win-x64.zip" % version
        update_path = DIST / update_name
        _zip_tree(onedir, update_path)
        exe = build_windows_onefile()
        primary_name = "AURA-%s-win-x64.exe" % version
        primary_path = DIST / primary_name
        shutil.copy2(exe, primary_path)
    else:
        artifact_root = build_pyinstaller(clean=True)
        primary_name = "AURA-%s-linux-x64.zip" % version
        primary_path = DIST / primary_name
        _zip_tree(artifact_root, primary_path)
        update_name, update_path = primary_name, primary_path

    manifest_path = DIST / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    manifest.update(
        {
            "version": version,
            "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "notes": notes,
            "releases_base_url": base,
            "platforms": manifest.get("platforms", {}),
        }
    )

    entry: dict = {
        "url": "%s/%s" % (base, primary_name),
        "sha256": _sha256(primary_path),
        "size": primary_path.stat().st_size,
        "filename": primary_name,
    }
    if update_name != primary_name:
        entry["update_filename"] = update_name
        entry["update_url"] = "%s/%s" % (base, update_name)
        entry["update_sha256"] = _sha256(update_path)
        entry["update_size"] = update_path.stat().st_size

    manifest["platforms"][key] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Built: %s (%s bytes)" % (primary_path, entry["size"]))
    if update_name != primary_name:
        print("Update package: %s" % update_path)
    print("Manifest: %s" % manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build A.U.R.A desktop release artifacts")
    parser.add_argument("--version", default=_load_version())
    parser.add_argument(
        "--notes",
        default=(
            "## A.U.R.A 1.0.0\n\n"
            "- Desktop builds for macOS / Windows / Linux\n"
            "- Unsigned installers (Gatekeeper/SmartScreen warnings expected)"
        ),
    )
    parser.add_argument(
        "--base-url",
        default="https://www.hiauraai.com/releases",
        help="Public CDN/base URL where release files are hosted",
    )
    args = parser.parse_args()
    package_release(args.version, args.notes, args.base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
