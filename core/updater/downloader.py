from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from core.updater.manifest import ReleaseAsset


ProgressCallback = Callable[[int, int | None], None]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(
    asset: ReleaseAsset,
    dest_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    dest_dir = dest_dir or Path(tempfile.gettempdir()) / "jarvis-updates"
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = asset.filename or Path(asset.url.split("?", 1)[0]).name or "jarvis-update.zip"
    dest = dest_dir / filename
    part = dest.with_suffix(dest.suffix + ".part")

    req = urllib.request.Request(asset.url, headers={"User-Agent": "JARVIS-Updater"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or asset.size or 0) or None
        downloaded = 0
        with part.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded, total)

    digest = _sha256_file(part)
    if digest.lower() != asset.sha256.lower():
        part.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch: expected {asset.sha256}, got {digest}")

    if dest.exists():
        dest.unlink()
    part.replace(dest)
    return dest
