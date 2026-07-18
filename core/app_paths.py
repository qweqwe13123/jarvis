"""Writable vs bundled paths for frozen AURA.app and source runs.

Never write secrets inside the .app / DMG — that breaks codesign and fails
on read-only volumes (Gatekeeper / SIGABRT after Gemini key submit).
"""

from __future__ import annotations

import sys
from pathlib import Path


def support_dir() -> Path:
    """User data root (always writable)."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "AURA"
    elif sys.platform == "win32":
        d = Path.home() / "AppData" / "Local" / "AURA"
    else:
        d = Path.home() / ".local" / "share" / "AURA"
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    """Where account + secrets are read/written."""
    if getattr(sys, "frozen", False):
        return support_dir()
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Bundled read-only assets (prompt, packaged UI, cloud defaults)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        exe = Path(sys.executable).resolve()
        resources = exe.parent.parent / "Resources"
        if resources.is_dir():
            return resources
        return exe.parent
    return Path(__file__).resolve().parent.parent


def _legacy_writable_api_keys() -> list[Path]:
    """Old mistaken locations next to the binary (never use Resources — may ship templates)."""
    out: list[Path] = []
    if getattr(sys, "frozen", False):
        try:
            out.append(Path(sys.executable).resolve().parent / "config" / "api_keys.json")
        except Exception:
            pass
    return out


def api_keys_path() -> Path:
    """Gemini/provider keys — Application Support when frozen."""
    path = data_dir() / "config" / "api_keys.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        for legacy in _legacy_writable_api_keys():
            if legacy.is_file():
                try:
                    path.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
                    break
                except Exception:
                    pass
    return path


def has_gemini_setup() -> bool:
    """True when a usable Gemini key + OS were saved to the writable config."""
    import json

    path = api_keys_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(str(data.get("gemini_api_key", "")).strip()) and bool(
            data.get("os_system")
        )
    except Exception:
        return False
