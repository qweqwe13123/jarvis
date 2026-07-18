"""Stable paths for source runs and the frozen AURA.app bundle."""

from __future__ import annotations

import sys
from pathlib import Path

from core.app_paths import (
    api_keys_path,
    data_dir,
    has_gemini_setup,
    resource_dir,
    support_dir,
)

__all__ = [
    "api_keys_path",
    "brand_asset_path",
    "brand_asset_candidates",
    "cloud_config_path",
    "data_dir",
    "has_gemini_setup",
    "resource_dir",
    "support_dir",
]


def cloud_config_path():
    """Prefer bundled config, then user override in Application Support."""
    bundled = resource_dir() / "config" / "aura_cloud.json"
    if bundled.exists():
        return bundled
    return support_dir() / "config" / "aura_cloud.json"


def brand_asset_candidates(*names: str) -> list[Path]:
    """Resolve logo / Google mark across repo + frozen Contents/{Resources,Frameworks}."""
    roots: list[Path] = []
    try:
        roots.append(Path(resource_dir()))
    except Exception:
        pass
    # Repo root when running from source (jarvis_ui/paths.py → parents[1])
    roots.append(Path(__file__).resolve().parents[1])

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
        try:
            contents = Path(sys.executable).resolve().parent.parent
            roots.extend([contents / "Resources", contents / "Frameworks"])
        except Exception:
            pass

    # When prefer-disk loads jarvis_ui from Frameworks/Resources, check sibling assets.
    try:
        here = Path(__file__).resolve()
        if here.parents[1].name in {"Frameworks", "Resources"}:
            contents = here.parents[2]
            roots.extend([contents / "Resources", contents / "Frameworks"])
    except Exception:
        pass

    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for name in names:
            path = root / "assets" / name
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return out


def brand_asset_path(*names: str) -> Path | None:
    """First existing brand asset among candidate names, or None."""
    for path in brand_asset_candidates(*names):
        if path.is_file():
            return path
    return None
