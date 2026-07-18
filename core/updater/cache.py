"""Local cache of update packages for differential downloads (Cursor-style)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from core.platform_detect import normalize_os
from core.updater.blockmap import BlockMap, generate_blockmap, sha256_file


def cache_root() -> Path:
    os_name = normalize_os()
    if os_name == "darwin":
        root = Path.home() / "Library" / "Application Support" / "AURA" / "updates" / "cache"
    elif os_name == "windows":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) / "AURA" if local else Path.home() / "AppData" / "Local" / "AURA"
        root = base / "updates" / "cache"
    else:
        root = Path.home() / ".cache" / "AURA" / "updates"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _meta_path() -> Path:
    return cache_root() / "cache.json"


def _load_meta() -> dict:
    try:
        return json.loads(_meta_path().read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def _save_meta(meta: dict) -> None:
    _meta_path().write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def blockmap_path_for(package: Path) -> Path:
    return package.with_suffix(package.suffix + ".blockmap")


def find_cached_package(prefer_filename: str = "") -> tuple[Path, BlockMap] | None:
    """Return the best cached zip + its blockmap for differential reuse."""
    meta = _load_meta()
    entries = list(meta.get("entries") or [])
    # Prefer exact filename match, then newest entry.
    ordered = sorted(entries, key=lambda e: int(e.get("saved_at") or 0), reverse=True)
    if prefer_filename:
        exact = [e for e in ordered if e.get("filename") == prefer_filename]
        ordered = exact + [e for e in ordered if e.get("filename") != prefer_filename]

    for entry in ordered:
        path = Path(str(entry.get("path") or ""))
        if not path.is_file():
            continue
        bm_path = Path(str(entry.get("blockmap") or "")) or blockmap_path_for(path)
        try:
            if bm_path.is_file():
                bm = BlockMap.load(bm_path)
            else:
                bm = generate_blockmap(path)
                bm.save(bm_path)
            # Quick size sanity check.
            if path.stat().st_size != bm.size:
                continue
            return path, bm
        except Exception:
            continue
    return None


def save_package(
    package: Path,
    *,
    version: str = "",
    blockmap: BlockMap | None = None,
    keep: int = 2,
) -> Path:
    """
    Copy package (+ blockmap) into the persistent cache.
    Returns the cached package path.
    """
    if not package.is_file():
        raise FileNotFoundError(package)

    root = cache_root()
    dest = root / package.name
    if package.resolve() != dest.resolve():
        shutil.copy2(package, dest)

    bm = blockmap
    if bm is None or bm.size != dest.stat().st_size or sha256_file(dest).lower() != bm.sha256.lower():
        bm = generate_blockmap(dest)
    bm_path = blockmap_path_for(dest)
    bm.save(bm_path)

    import time

    meta = _load_meta()
    entries = [e for e in (meta.get("entries") or []) if Path(str(e.get("path") or "")).name != dest.name]
    entries.append(
        {
            "filename": dest.name,
            "path": str(dest),
            "blockmap": str(bm_path),
            "version": version,
            "sha256": bm.sha256,
            "size": bm.size,
            "saved_at": int(time.time()),
        }
    )
    entries.sort(key=lambda e: int(e.get("saved_at") or 0), reverse=True)
    # Prune old caches.
    for stale in entries[keep:]:
        for key in ("path", "blockmap"):
            try:
                Path(str(stale.get(key) or "")).unlink(missing_ok=True)
            except Exception:
                pass
    meta["entries"] = entries[:keep]
    _save_meta(meta)
    return dest

