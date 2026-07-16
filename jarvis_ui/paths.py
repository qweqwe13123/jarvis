"""Stable paths for source runs and the frozen AURA.app bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def support_dir() -> Path:
    """Writable user data (tokens, memory) — never inside the .app bundle."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "AURA"
    elif sys.platform == "win32":
        d = Path.home() / "AppData" / "Local" / "AURA"
    else:
        d = Path.home() / ".local" / "share" / "AURA"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_dir() -> Path:
    """Bundled read-only assets (config/aura_cloud.json, packaged UI)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # macOS .app: …/Contents/MacOS/AURA → …/Contents/Resources
        exe = Path(sys.executable).resolve()
        resources = exe.parent.parent / "Resources"
        if resources.is_dir():
            return resources
        return exe.parent
    # jarvis_ui/paths.py → repo root
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Where account + secrets are read/written."""
    if getattr(sys, "frozen", False):
        return support_dir()
    return Path(__file__).resolve().parent.parent


def cloud_config_path() -> Path:
    """Prefer bundled config, then user override in Application Support."""
    bundled = resource_dir() / "config" / "aura_cloud.json"
    if bundled.exists():
        return bundled
    override = support_dir() / "config" / "aura_cloud.json"
    return override
