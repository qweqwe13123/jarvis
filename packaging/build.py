#!/usr/bin/env python3
"""Build A.U.R.A desktop installers with optional Developer ID sign + notarize."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
ENTITLEMENTS = ROOT / "packaging" / "entitlements.plist"
ENTITLEMENTS_WAKE = ROOT / "packaging" / "entitlements-wake.plist"
DEFAULT_IDENTITY = "Developer ID Application: Khalil Isaiev (PNY6NC68X3)"
DEFAULT_NOTARY_PROFILE = "AURA-notarize"


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
    """Zip a file/dir. On macOS .app bundles use ditto so codesign survives."""
    if dest_zip.exists():
        dest_zip.unlink()
    dest_zip.parent.mkdir(parents=True, exist_ok=True)

    if (
        platform.system() == "Darwin"
        and source.is_dir()
        and (source.suffix == ".app" or (source / "Contents" / "MacOS").is_dir())
    ):
        # ditto preserves symlinks + resource forks; Python zipfile breaks Frameworks.
        _run(["ditto", "-c", "-k", "--keepParent", str(source), str(dest_zip)])
        return

    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if source.is_file():
            zf.write(source, source.name)
            return
        parent = source.parent
        for path in source.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(parent).as_posix())


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, capture_output=False)


def _codesign_identity(explicit: str | None = None) -> str:
    identity = (
        explicit
        or os.environ.get("AURA_CODESIGN_IDENTITY")
        or DEFAULT_IDENTITY
    ).strip()
    result = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout or ""
    if identity and identity in out:
        return identity
    for line in out.splitlines():
        if "Developer ID Application:" in line:
            start = line.find('"')
            end = line.rfind('"')
            if start >= 0 and end > start:
                return line[start + 1 : end]
    raise RuntimeError(
        "No Developer ID Application identity found. "
        "Set AURA_CODESIGN_IDENTITY or install the certificate."
    )


def _macho_candidates(root: Path) -> list[Path]:
    exts = {".so", ".dylib", ""}
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix in exts or path.name in {"AURA", "AURAWake", "Python"}:
            # Skip obvious non-binaries
            if path.suffix in {".py", ".pyc", ".txt", ".json", ".md", ".plist", ".icns", ".png"}:
                continue
            out.append(path)
    return out


def codesign_app(app_path: Path, identity: str, entitlements: Path) -> None:
    """Deep-sign an .app bundle for notarization (Hardened Runtime)."""
    # Sign nested binaries inside-out (deepest paths first).
    for path in sorted(_macho_candidates(app_path), key=lambda p: len(p.parts), reverse=True):
        if path.name == APP_NAME and path.parent.name == "MacOS":
            continue
        ent = str(ENTITLEMENTS_WAKE) if "AURAWake.app" in str(path) and ENTITLEMENTS_WAKE.exists() else str(entitlements)
        subprocess.run(
            [
                "codesign",
                "--force",
                "--options",
                "runtime",
                "--timestamp",
                "--entitlements",
                ent,
                "--sign",
                identity,
                str(path),
            ],
            check=False,
            capture_output=True,
        )

    for wake in app_path.rglob("AURAWake.app"):
        if wake.is_dir() and (wake / "Contents").exists():
            _run(
                [
                    "codesign",
                    "--force",
                    "--deep",
                    "--options",
                    "runtime",
                    "--timestamp",
                    "--entitlements",
                    str(ENTITLEMENTS_WAKE if ENTITLEMENTS_WAKE.exists() else entitlements),
                    "--sign",
                    identity,
                    str(wake),
                ]
            )

    _run(
        [
            "codesign",
            "--force",
            "--deep",
            "--options",
            "runtime",
            "--timestamp",
            "--entitlements",
            str(entitlements),
            "--sign",
            identity,
            str(app_path),
        ]
    )
    _run(["codesign", "--verify", "--deep", "--strict", str(app_path)])


def embed_wake_helper(app_path: Path) -> Path | None:
    """Build AURAWake.app and copy into AURA.app/Contents/Resources/."""
    try:
        sys.path.insert(0, str(ROOT))
        from tools.build_wake_helper import build as build_wake

        wake_app = build_wake()
    except Exception as exc:
        print(f"[Wake] embed skipped: {exc}")
        return None

    dest = app_path / "Contents" / "Resources" / "AURAWake.app"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(wake_app, dest, symlinks=True)
    print(f"[Wake] embedded → {dest}")
    return dest


def notarize_and_staple(path: Path, profile: str) -> None:
    """Submit to Apple notary service and staple the ticket.

    Prefers keychain profile. Falls back to App Store Connect API key env vars
    used in GitHub Actions:
      APPLE_API_KEY_PATH / APPLE_API_KEY_ID / APPLE_API_ISSUER
    """
    api_key = os.environ.get("APPLE_API_KEY_PATH") or os.environ.get("APP_STORE_CONNECT_API_KEY_PATH")
    api_id = os.environ.get("APPLE_API_KEY_ID") or os.environ.get("APP_STORE_CONNECT_KEY_ID")
    api_issuer = os.environ.get("APPLE_API_ISSUER") or os.environ.get("APP_STORE_CONNECT_ISSUER_ID")

    if api_key and api_id and api_issuer and Path(api_key).exists():
        _run(
            [
                "xcrun",
                "notarytool",
                "submit",
                str(path),
                "--key",
                api_key,
                "--key-id",
                api_id,
                "--issuer",
                api_issuer,
                "--wait",
            ]
        )
    else:
        _run(
            [
                "xcrun",
                "notarytool",
                "submit",
                str(path),
                "--keychain-profile",
                profile,
                "--wait",
            ]
        )
    _run(["xcrun", "stapler", "staple", str(path)])
    _run(["xcrun", "stapler", "validate", str(path)], check=False)


def _make_dmg(app_path: Path, dmg_path: Path, volume_name: str = "AURA") -> None:
    """Create a Chrome/Cursor-style DMG: branded Retina bg + Applications shortcut."""
    import importlib.util

    mod_path = ROOT / "packaging" / "make_dmg.py"
    spec = importlib.util.spec_from_file_location("aura_make_dmg", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dmg_path.parent.mkdir(parents=True, exist_ok=True)
    mod.make_dmg(app_path, dmg_path, volume_name=volume_name, staging_parent=DIST)


def build_pyinstaller(
    clean: bool = True,
    *,
    python: str | None = None,
    distpath: Path | None = None,
    workpath: Path | None = None,
    arch_prefix: list[str] | None = None,
) -> Path:
    """Run PyInstaller. On macOS returns the .app path."""
    (ROOT / "resources" / "skills").mkdir(parents=True, exist_ok=True)
    py = python or sys.executable
    distpath = distpath or (ROOT / "dist")
    workpath = workpath or (ROOT / "build" / "pyinstaller")

    if clean:
        shutil.rmtree(workpath, ignore_errors=True)
        shutil.rmtree(distpath / APP_NAME, ignore_errors=True)
        shutil.rmtree(distpath / f"{APP_NAME}.app", ignore_errors=True)
        if distpath == ROOT / "dist":
            shutil.rmtree(ROOT / "dist" / "JARVIS", ignore_errors=True)
            shutil.rmtree(ROOT / "dist" / "JARVIS.app", ignore_errors=True)
            for leftover in (ROOT / "dist").glob(f"{APP_NAME}*"):
                if leftover.is_file():
                    leftover.unlink(missing_ok=True)

    distpath.mkdir(parents=True, exist_ok=True)
    workpath.mkdir(parents=True, exist_ok=True)
    cmd = list(arch_prefix or []) + [
        py,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        f"--distpath={distpath}",
        f"--workpath={workpath}",
    ]
    _run(cmd, check=True)

    if platform.system() == "Darwin":
        return distpath / f"{APP_NAME}.app"
    return distpath / APP_NAME


def _default_x86_python() -> Path | None:
    env = (os.environ.get("AURA_X86_PYTHON") or "").strip()
    if env and Path(env).is_file():
        return Path(env)
    candidates = sorted(
        (ROOT / ".python-x86").glob("cpython-*-macos-x86_64-none/bin/python3.*")
    )
    for path in candidates:
        if path.name.endswith("-config"):
            continue
        if path.is_file():
            return path
    return None


def build_universal_app() -> Path:
    """Build arm64 + x86_64 apps under Rosetta, lipo-merge into dist/AURA.app."""
    if platform.system() != "Darwin":
        raise RuntimeError("--universal is only supported on macOS")

    import importlib.util

    merge_path = ROOT / "packaging" / "merge_universal_app.py"
    spec = importlib.util.spec_from_file_location("aura_merge_universal_app", merge_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {merge_path}")
    merge_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge_mod)
    merge_apps = merge_mod.merge_apps

    x86_py = _default_x86_python()
    if x86_py is None:
        raise RuntimeError(
            "No x86_64 Python found. Install with:\n"
            "  UV_PYTHON_INSTALL_DIR=.python-x86 "
            "uv python install cpython-3.12.13-macos-x86_64-none\n"
            "Or set AURA_X86_PYTHON=/path/to/x86_64/python3"
        )

    # Ensure Rosetta can run it.
    probe = subprocess.run(
        ["arch", "-x86_64", str(x86_py), "-c", "import platform; print(platform.machine())"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or "x86_64" not in (probe.stdout or ""):
        raise RuntimeError(
            f"x86_64 Python not runnable under Rosetta: {x86_py}\n"
            f"{probe.stderr or probe.stdout}"
        )

    venv_x86 = ROOT / ".venv-x86"
    pip_x86 = venv_x86 / "bin" / "pip"
    py_x86 = venv_x86 / "bin" / "python"
    if not py_x86.is_file():
        print(f"[universal] creating {venv_x86} with {x86_py}")
        _run(["arch", "-x86_64", str(x86_py), "-m", "venv", str(venv_x86)])
    print("[universal] installing x86_64 deps (may take a while)…")
    _run(
        [
            "arch",
            "-x86_64",
            str(pip_x86),
            "install",
            "-q",
            "--upgrade",
            "pip",
        ]
    )
    _run(
        [
            "arch",
            "-x86_64",
            str(pip_x86),
            "install",
            "-q",
            "-r",
            str(ROOT / "requirements-desktop.txt"),
            "-r",
            str(ROOT / "packaging" / "requirements-packaging.txt"),
        ]
    )

    arm_dist = ROOT / "dist" / "arm64"
    x86_dist = ROOT / "dist" / "x86_64"
    print("[universal] building arm64 app…")
    arm_app = build_pyinstaller(
        clean=True,
        python=sys.executable,
        distpath=arm_dist,
        workpath=ROOT / "build" / "arm64",
    )
    print("[universal] building x86_64 app under Rosetta…")
    x86_app = build_pyinstaller(
        clean=True,
        python=str(py_x86),
        distpath=x86_dist,
        workpath=ROOT / "build" / "x86_64",
        arch_prefix=["arch", "-x86_64"],
    )

    out_app = ROOT / "dist" / f"{APP_NAME}.app"
    print("[universal] merging with lipo…")
    merge_apps(arm_app, x86_app, out_app)
    return out_app


def build_windows_onefile() -> Path:
    out = ROOT / "dist" / f"{APP_NAME}.exe"
    if out.exists():
        out.unlink()
    sep = ";" if platform.system() == "Windows" else ":"
    prompt = ROOT / "core" / "prompt.txt"
    config = ROOT / "config"
    ui = ROOT / "jarvis_ui"
    assets = ROOT / "assets"
    ico = assets / "AURA.ico"
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
        # Brand logos for onboarding / tray — without this, Windows falls back to "A".
        "--add-data=%s%s%s" % (assets, sep, "assets"),
        "--hidden-import=PyQt6.QtWebEngineWidgets",
        "--hidden-import=PyQt6.QtWebEngineCore",
        "--hidden-import=google.genai",
        str(ROOT / "main.py"),
    ]
    if ico.is_file():
        cmd.insert(-1, "--icon=%s" % ico)
    _run(cmd)
    return ROOT / "dist" / f"{APP_NAME}.exe"


def package_release(
    version: str,
    notes: str,
    base_url: str,
    *,
    sign: bool = False,
    notarize: bool = False,
    identity: str | None = None,
    notary_profile: str = DEFAULT_NOTARY_PROFILE,
    universal: bool = False,
) -> dict:
    DIST.mkdir(parents=True, exist_ok=True)
    key = _platform_key()
    system = platform.system()
    base = base_url.rstrip("/")
    mac_keys: list[str] = []

    if system == "Darwin":
        if universal:
            artifact_root = build_universal_app()
            arch = "universal"
            mac_keys = ["darwin-arm64", "darwin-x64"]
            key = "darwin-universal"
        else:
            artifact_root = build_pyinstaller(clean=True)
            arch = "arm64" if key.endswith("arm64") else "x64"
            mac_keys = [key]

        embed_wake_helper(artifact_root)

        if sign or notarize:
            if not ENTITLEMENTS.exists():
                raise FileNotFoundError(f"Missing entitlements: {ENTITLEMENTS}")
            ident = _codesign_identity(identity)
            print(f"[Sign] identity={ident}")
            codesign_app(artifact_root, ident, ENTITLEMENTS)

        primary_name = "AURA-%s-macos-%s.dmg" % (version, arch)
        primary_path = DIST / primary_name
        _make_dmg(artifact_root, primary_path, volume_name="AURA")

        if sign or notarize:
            ident = _codesign_identity(identity)
            _run(
                [
                    "codesign",
                    "--force",
                    "--timestamp",
                    "--sign",
                    ident,
                    str(primary_path),
                ]
            )

        if notarize:
            print(f"[Notary] profile={notary_profile}")
            notarize_and_staple(primary_path, notary_profile)

        update_name = "AURA-%s-macos-%s.zip" % (version, arch)
        update_path = DIST / update_name
        _zip_tree(artifact_root, update_path)
        if notarize:
            # Zip of signed app for in-app updater; staple is on DMG (user install).
            pass
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
        # Keep zip for debugging / fallback; public primary is AppImage.
        update_name = "AURA-%s-linux-x64.zip" % version
        update_path = DIST / update_name
        _zip_tree(artifact_root, update_path)

        import importlib.util

        appimage_mod_path = ROOT / "packaging" / "make_appimage.py"
        spec = importlib.util.spec_from_file_location("aura_make_appimage", appimage_mod_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {appimage_mod_path}")
        appimage_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(appimage_mod)
        primary_name = "AURA-%s-linux-x64.AppImage" % version
        primary_path = DIST / primary_name
        appimage_mod.make_appimage(artifact_root, primary_path, version=version)

    manifest_path = DIST / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    signed_note = ""
    if notarize:
        signed_note = "\n- Signed + notarized macOS build (Developer ID)"
    elif sign:
        signed_note = "\n- Developer ID signed (not notarized)"

    manifest.update(
        {
            "version": version,
            "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "notes": notes + signed_note,
            "releases_base_url": base,
            "platforms": manifest.get("platforms", {}),
            "links": {
                "homepage": "https://www.hiauraai.com",
                "download": "https://www.hiauraai.com/download",
                "docs": "https://www.hiauraai.com/download",
            },
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

    # Cursor-style blockmaps for differential in-app updates (same as macOS).
    def _attach_blockmap(pkg: Path, *, prefix: str) -> Path | None:
        if not pkg.is_file():
            return None
        try:
            from core.updater.blockmap import generate_blockmap

            bm_path = Path(str(pkg) + ".blockmap")
            bm = generate_blockmap(pkg)
            bm.save(bm_path)
            entry["%s_url" % prefix] = "%s/%s" % (base, bm_path.name)
            entry["%s_sha256" % prefix] = _sha256(bm_path)
            entry["%s_size" % prefix] = bm_path.stat().st_size
            print("Blockmap: %s (%s blocks)" % (bm_path.name, bm.block_count))
            return bm_path
        except Exception as exc:
            print("WARN: blockmap failed for %s: %s" % (pkg.name, exc))
            return None

    if update_name != primary_name and update_path.is_file() and update_name.lower().endswith(".zip"):
        _attach_blockmap(update_path, prefix="update_blockmap")
    # Linux AppImage is the live update package — give it its own blockmap too.
    if primary_name.lower().endswith(".appimage"):
        _attach_blockmap(primary_path, prefix="blockmap")

    # Universal macOS: same DMG for Apple Silicon + Intel download keys.
    targets = mac_keys if system == "Darwin" and mac_keys else [key]
    for platform_key in targets:
        manifest["platforms"][platform_key] = dict(entry)
    if system == "Darwin" and universal:
        manifest["platforms"]["darwin-universal"] = dict(entry)

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
            "## A.U.R.A 1.0.1\n\n"
            "- Signed + notarized macOS installer (system-style DMG)\n"
            "- Double-clap wake (AURA Wake)\n"
            "- Voice assistant + orchestrator agents\n"
            "- First-run permissions checklist"
        ),
    )
    parser.add_argument(
        "--base-url",
        default="https://github.com/qweqwe13123/jarvis/releases/download/v1.0.1",
        help="Public CDN/base URL where release files are hosted",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="codesign with Developer ID Application",
    )
    parser.add_argument(
        "--notarize",
        action="store_true",
        help="codesign + notarytool submit + stapler (implies --sign)",
    )
    parser.add_argument(
        "--identity",
        default=os.environ.get("AURA_CODESIGN_IDENTITY", DEFAULT_IDENTITY),
        help="codesign identity string",
    )
    parser.add_argument(
        "--notary-profile",
        default=os.environ.get("AURA_NOTARY_PROFILE", DEFAULT_NOTARY_PROFILE),
        help="notarytool keychain profile name",
    )
    parser.add_argument(
        "--universal",
        action="store_true",
        help="macOS: build arm64+x86_64, lipo-merge into one .app/.dmg",
    )
    args = parser.parse_args()
    sign = args.sign or args.notarize
    package_release(
        args.version,
        args.notes,
        args.base_url,
        sign=sign,
        notarize=args.notarize,
        identity=args.identity,
        notary_profile=args.notary_profile,
        universal=args.universal,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
