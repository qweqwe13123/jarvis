from __future__ import annotations

import hashlib
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from core.updater.blockmap import (
    BlockMap,
    assemble_from_blockmap,
    fetch_blockmap,
    generate_blockmap,
)
from core.updater.cache import find_cached_package, save_package
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
    """Full package download (fallback)."""
    dest_dir = dest_dir or Path(tempfile.gettempdir()) / "jarvis-updates"
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = asset.filename or Path(asset.url.split("?", 1)[0]).name or "jarvis-update.zip"
    dest = dest_dir / filename
    part = dest.with_suffix(dest.suffix + ".part")

    req = urllib.request.Request(
        asset.url,
        headers={"User-Agent": "AURA-Updater", "Accept": "*/*"},
    )
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


def _resolve_new_blockmap(asset: ReleaseAsset) -> BlockMap | None:
    urls: list[str] = []
    if asset.blockmap_url:
        urls.append(asset.blockmap_url)
    if asset.url.lower().endswith(".zip"):
        sibling = asset.url + ".blockmap"
        if sibling not in urls:
            urls.append(sibling)

    for url in urls:
        try:
            bm = fetch_blockmap(url)
        except Exception:
            continue
        if asset.sha256 and bm.sha256.lower() != asset.sha256.lower():
            continue
        if asset.size and bm.size and bm.size != asset.size:
            continue
        if asset.blockmap_sha256:
            # Optional integrity check of the blockmap document itself.
            try:
                import hashlib
                import urllib.request

                req = urllib.request.Request(
                    url, headers={"User-Agent": "AURA-Updater", "Accept": "*/*"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                if hashlib.sha256(raw).hexdigest().lower() != asset.blockmap_sha256.lower():
                    continue
                return BlockMap.loads(raw.decode("utf-8"))
            except Exception:
                continue
        return bm
    return None


def download_asset_smart(
    asset: ReleaseAsset,
    *,
    version: str = "",
    dest_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
    prefer_differential: bool = True,
) -> Path:
    """
    Cursor-style download:
    1) Try differential assemble from cached previous zip + blockmap
    2) Fall back to full download
    3) Save successful package into cache for the next update
    """
    dest_dir = dest_dir or Path(tempfile.gettempdir()) / "jarvis-updates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = asset.filename or Path(asset.url.split("?", 1)[0]).name or "jarvis-update.zip"
    dest = dest_dir / filename

    used_differential = False
    # Same differential path as macOS ZIP — also AppImage on Linux.
    name_l = filename.lower()
    if prefer_differential and (name_l.endswith(".zip") or name_l.endswith(".appimage")):
        new_map = _resolve_new_blockmap(asset)
        cached = find_cached_package(prefer_filename=filename)
        if new_map is not None and cached is not None:
            old_path, old_map = cached
            # Skip differential if almost nothing can be reused (still try if any overlap).
            try:
                network_bytes, reused = assemble_from_blockmap(
                    asset.url,
                    new_map,
                    old_path,
                    old_map,
                    dest,
                    on_progress=on_progress,
                )
                # Final sha already checked inside assemble; also match manifest.
                if asset.sha256 and _sha256_file(dest).lower() != asset.sha256.lower():
                    dest.unlink(missing_ok=True)
                    raise ValueError("assembled package sha mismatch vs manifest")
                used_differential = True
                _ulog_diff(network_bytes, reused, new_map.size)
            except Exception as exc:
                dest.unlink(missing_ok=True)
                _ulog_diff_fail(exc)
                used_differential = False

    if not used_differential:
        dest = download_asset(asset, dest_dir=dest_dir, on_progress=on_progress)

    # Persist for next differential update (installer may delete the temp package).
    try:
        bm = None
        if asset.blockmap_url:
            try:
                bm = fetch_blockmap(asset.blockmap_url)
            except Exception:
                bm = None
        if bm is None:
            bm = generate_blockmap(dest)
        save_package(dest, version=version, blockmap=bm)
    except Exception as exc:
        _ulog_cache_fail(exc)

    return dest


def _ulog_diff(network: int, reused: int, total: int) -> None:
    try:
        from core.updater.installer import _ulog

        _ulog(
            f"differential download ok network={network} reused={reused} total={total} "
            f"saved={max(0, total - network)}"
        )
    except Exception:
        pass


def _ulog_diff_fail(exc: BaseException) -> None:
    try:
        from core.updater.installer import _ulog

        _ulog(f"differential download failed, falling back to full: {exc}")
    except Exception:
        pass


def _ulog_cache_fail(exc: BaseException) -> None:
    try:
        from core.updater.installer import _ulog

        _ulog(f"update cache save failed: {exc}")
    except Exception:
        pass
