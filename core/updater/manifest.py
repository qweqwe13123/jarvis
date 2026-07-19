from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.platform_detect import platform_key
from core.version import (
    DEFAULT_UPDATE_MANIFEST_URL,
    MAX_RELEASES_BEHIND,
    RELEASE_INDEX,
    VERSION,
)


@dataclass(frozen=True)
class ReleaseAsset:
    url: str
    sha256: str
    size: int
    filename: str = ""
    blockmap_url: str = ""
    blockmap_sha256: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    released_at: str
    notes: str
    asset: ReleaseAsset
    platform: str
    min_supported_version: str = ""
    release_index: int = 0
    min_release_index: int = 0
    force_required: bool = False


def manifest_url() -> str:
    return (
        os.environ.get("AURA_UPDATE_MANIFEST_URL")
        or os.environ.get("JARVIS_UPDATE_MANIFEST_URL")
        or DEFAULT_UPDATE_MANIFEST_URL
    ).strip()


def _parse_version(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in re.split(r"[.\-+]", value.strip()):
        if chunk.isdigit():
            parts.append(int(chunk))
    return tuple(parts or [0])


def is_newer(remote: str, local: str | None = None) -> bool:
    if local is None:
        local = VERSION
    return _parse_version(remote) > _parse_version(local)


def is_below(local: str, minimum: str) -> bool:
    """True when local version is strictly older than minimum."""
    if not minimum:
        return False
    return _parse_version(local) < _parse_version(minimum)


def force_update_required(
    data: dict[str, Any],
    *,
    local_version: str = VERSION,
    local_index: int = RELEASE_INDEX,
) -> tuple[bool, str]:
    """Return (required, min_supported_label) from a release manifest.

    Policy:
    1. Explicit ``min_supported_version`` wins (hotfix / kill-switch).
    2. Else ``min_release_index`` / computed from ``release_index - MAX_RELEASES_BEHIND``.
    3. Env ``AURA_SIMULATE_FORCE_UPDATE=1`` forces the gate for UI preview.
    """
    if os.environ.get("AURA_SIMULATE_FORCE_UPDATE", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        latest = str(data.get("version") or local_version).strip() or local_version
        return True, latest

    min_ver = str(data.get("min_supported_version") or "").strip()
    if min_ver and is_below(local_version, min_ver):
        return True, min_ver

    try:
        remote_index = int(data.get("release_index") or 0)
    except (TypeError, ValueError):
        remote_index = 0
    try:
        min_index = int(data.get("min_release_index") or 0)
    except (TypeError, ValueError):
        min_index = 0
    if min_index <= 0 and remote_index > 0:
        min_index = max(1, remote_index - MAX_RELEASES_BEHIND)
    if min_index > 0 and int(local_index) < min_index:
        label = min_ver or str(data.get("version") or "").strip() or f"build #{min_index}"
        return True, label

    return False, min_ver


def fetch_manifest(url: str | None = None, timeout: int = 20) -> dict[str, Any]:
    target = url or manifest_url()
    req = urllib.request.Request(
        target,
        headers={"User-Agent": f"AURA-Updater/{VERSION}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _platform_candidates(key: str) -> list[str]:
    if key.startswith("darwin"):
        # Universal DMG/zip is published under both arch keys + darwin-universal.
        return ["darwin-universal", key, "darwin-arm64", "darwin-x64"]
    if key.startswith("linux"):
        return [key, "linux-x64"]
    if key.startswith("win"):
        return [key, "win-x64"]
    return [key]


def _pick_asset_fields(entry: dict[str, Any]) -> tuple[str, str, str, int, str, str]:
    """Choose the best package for in-app replace for this runtime.

    Returns: url, sha256, filename, size, blockmap_url, blockmap_sha256
    """
    try:
        from core.updater.installer import appimage_path
    except Exception:
        appimage_path = lambda: None  # noqa: E731

    primary_name = str(entry.get("filename") or "").strip()
    update_name = str(entry.get("update_filename") or "").strip()
    primary_url = str(entry.get("url") or "").strip()
    update_url = str(entry.get("update_url") or "").strip()
    primary_sha = str(entry.get("sha256") or "").strip().lower()
    update_sha = str(entry.get("update_sha256") or "").strip().lower()
    primary_size = int(entry.get("size") or 0)
    update_size = int(entry.get("update_size") or 0)
    blockmap_url = str(
        entry.get("update_blockmap_url") or entry.get("blockmap_url") or ""
    ).strip()
    blockmap_sha = str(
        entry.get("update_blockmap_sha256") or entry.get("blockmap_sha256") or ""
    ).strip().lower()

    running_appimage = appimage_path() is not None
    primary_is_appimage = primary_name.lower().endswith(".appimage") or primary_url.lower().endswith(
        ".appimage"
    )
    update_is_zip = update_name.lower().endswith(".zip") or update_url.lower().endswith(".zip")

    primary_blockmap_url = str(entry.get("blockmap_url") or "").strip()
    primary_blockmap_sha = str(entry.get("blockmap_sha256") or "").strip().lower()

    # AppImage runtime must download an AppImage (zip onedir won't replace APPIMAGE).
    if running_appimage and primary_is_appimage and primary_url and primary_sha:
        bm_url = primary_blockmap_url
        bm_sha = primary_blockmap_sha
        # Never reuse a zip blockmap for an AppImage payload.
        if bm_url and ".zip.blockmap" in bm_url.lower():
            bm_url, bm_sha = "", ""
        if not bm_url:
            bm_url = primary_url + ".blockmap"
        return primary_url, primary_sha, primary_name, primary_size, bm_url, bm_sha

    primary_is_exe = primary_name.lower().endswith(".exe") or primary_url.lower().endswith(".exe")
    update_is_exe = update_name.lower().endswith(".exe") or update_url.lower().endswith(".exe")

    # Windows: prefer the Inno Setup .exe. ZIP replace often fails under Program Files
    # ACLs / file locks after the app has already quit.
    if primary_is_exe and primary_url and primary_sha:
        return primary_url, primary_sha, primary_name, primary_size, "", ""
    if update_is_exe and update_url and update_sha:
        return update_url, update_sha, update_name, update_size, "", ""

    # Packaged .app / Linux zip fallback: prefer zip update package.
    if update_url and update_sha and (update_is_zip or not primary_is_appimage):
        if not blockmap_url and update_url.lower().endswith(".zip"):
            blockmap_url = update_url + ".blockmap"
        return update_url, update_sha, update_name, update_size, blockmap_url, blockmap_sha

    if primary_url and primary_sha:
        bm_url = primary_blockmap_url or blockmap_url
        bm_sha = primary_blockmap_sha or blockmap_sha
        if not bm_url and (
            primary_url.lower().endswith(".zip") or primary_url.lower().endswith(".appimage")
        ):
            bm_url = primary_url + ".blockmap"
        return primary_url, primary_sha, primary_name, primary_size, bm_url, bm_sha

    return "", "", "", 0, "", ""


def _platform_asset_version(entry: dict[str, Any], fallback: str = "") -> str:
    """Prefer per-platform version so Win-only deploys don't fake a Mac update."""
    explicit = str(entry.get("version") or "").strip()
    if explicit:
        return explicit
    for key in ("update_filename", "filename", "url"):
        raw = str(entry.get(key) or "")
        m = re.search(r"AURA-(\d+\.\d+\.\d+)", raw, re.I)
        if m:
            return m.group(1)
    return str(fallback or "").strip()


def parse_release(
    data: dict[str, Any],
    target: str | None = None,
    *,
    require_newer: bool = True,
) -> ReleaseInfo | None:
    key = target or platform_key()
    platforms = data.get("platforms") or {}
    entry = None
    resolved_key = key
    for candidate in _platform_candidates(key):
        if platforms.get(candidate):
            entry = platforms[candidate]
            resolved_key = candidate
            break
    if not entry:
        return None

    top_version = str(data.get("version", "")).strip()
    version = _platform_asset_version(entry, top_version)
    if not version:
        return None

    forced, min_supported = force_update_required(data)
    # Never offer an update unless THIS platform actually has a newer package.
    # (Win-only bumps must not force Mac to "update" to the same 1.0.22 zip.)
    if require_newer and not is_newer(version):
        return None

    url, sha256, filename, size, blockmap_url, blockmap_sha = _pick_asset_fields(entry)
    if not url or not sha256:
        return None

    try:
        release_index = int(data.get("release_index") or 0)
    except (TypeError, ValueError):
        release_index = 0
    try:
        min_release_index = int(data.get("min_release_index") or 0)
    except (TypeError, ValueError):
        min_release_index = 0
    if min_release_index <= 0 and release_index > 0:
        min_release_index = max(1, release_index - MAX_RELEASES_BEHIND)

    asset = ReleaseAsset(
        url=url,
        sha256=sha256,
        size=size,
        filename=filename,
        blockmap_url=blockmap_url,
        blockmap_sha256=blockmap_sha,
    )
    return ReleaseInfo(
        version=version,
        released_at=str(data.get("released_at", "")),
        notes=str(data.get("notes", "")).strip(),
        asset=asset,
        platform=resolved_key,
        min_supported_version=min_supported
        or str(data.get("min_supported_version") or "").strip(),
        release_index=release_index,
        min_release_index=min_release_index,
        force_required=forced,
    )
