from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.platform_detect import platform_key
from core.version import DEFAULT_UPDATE_MANIFEST_URL, VERSION


@dataclass(frozen=True)
class ReleaseAsset:
    url: str
    sha256: str
    size: int
    filename: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    released_at: str
    notes: str
    asset: ReleaseAsset
    platform: str


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


def is_newer(remote: str, local: str = VERSION) -> bool:
    return _parse_version(remote) > _parse_version(local)


def fetch_manifest(url: str | None = None, timeout: int = 20) -> dict[str, Any]:
    target = url or manifest_url()
    req = urllib.request.Request(
        target,
        headers={"User-Agent": f"AURA-Updater/{VERSION}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_release(data: dict[str, Any], target: str | None = None) -> ReleaseInfo | None:
    version = str(data.get("version", "")).strip()
    if not version or not is_newer(version):
        return None

    key = target or platform_key()
    platforms = data.get("platforms") or {}
    entry = platforms.get(key)
    if not entry:
        return None

    # Prefer zip update package for auto-updater; site can still advertise .dmg/.exe.
    url = str(entry.get("update_url") or entry.get("url") or "").strip()
    sha256 = str(
        entry.get("update_sha256") or entry.get("sha256") or ""
    ).strip().lower()
    filename = str(
        entry.get("update_filename") or entry.get("filename") or ""
    ).strip()
    size = int(entry.get("update_size") or entry.get("size") or 0)
    if not url or not sha256:
        return None

    asset = ReleaseAsset(
        url=url,
        sha256=sha256,
        size=size,
        filename=filename,
    )
    return ReleaseInfo(
        version=version,
        released_at=str(data.get("released_at", "")),
        notes=str(data.get("notes", "")).strip(),
        asset=asset,
        platform=key,
    )
