"""Cursor-style blockmap for differential zip updates.

Format (JSON):
{
  "version": 1,
  "algorithm": "sha256",
  "blockSize": 4194304,
  "size": <file bytes>,
  "sha256": "<full file sha256>",
  "blocks": ["<sha256 of each block>", ...]
}
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_BLOCK_SIZE = 4 * 1024 * 1024  # 4 MiB — same ballpark as electron-updater


ProgressCallback = Callable[[int, int | None], None]


@dataclass(frozen=True)
class BlockMap:
    size: int
    sha256: str
    block_size: int
    blocks: tuple[str, ...]

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "algorithm": "sha256",
            "blockSize": self.block_size,
            "size": self.size,
            "sha256": self.sha256.lower(),
            "blocks": list(self.blocks),
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "BlockMap":
        blocks = tuple(str(b).lower() for b in (data.get("blocks") or []))
        if not blocks:
            raise ValueError("blockmap has no blocks")
        size = int(data.get("size") or 0)
        sha = str(data.get("sha256") or "").lower()
        block_size = int(data.get("blockSize") or DEFAULT_BLOCK_SIZE)
        if size <= 0 or not sha:
            raise ValueError("blockmap missing size/sha256")
        return cls(size=size, sha256=sha, block_size=block_size, blocks=blocks)

    @classmethod
    def loads(cls, text: str) -> "BlockMap":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: Path) -> "BlockMap":
        return cls.loads(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_blockmap(path: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> BlockMap:
    """Compute blockmap for a local package file."""
    if block_size < 64 * 1024:
        raise ValueError("block_size too small")
    size = path.stat().st_size
    full = hashlib.sha256()
    blocks: list[str] = []
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(block_size)
            if not chunk:
                break
            full.update(chunk)
            blocks.append(hashlib.sha256(chunk).hexdigest())
    if not blocks:
        # Empty file — one empty block for consistency.
        blocks.append(hashlib.sha256(b"").hexdigest())
    return BlockMap(
        size=size,
        sha256=full.hexdigest(),
        block_size=block_size,
        blocks=tuple(blocks),
    )


def fetch_blockmap(url: str, timeout: int = 60) -> BlockMap:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AURA-Updater", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return BlockMap.loads(resp.read().decode("utf-8"))


def _block_offset_size(bm: BlockMap, index: int) -> tuple[int, int]:
    offset = index * bm.block_size
    remaining = bm.size - offset
    if remaining <= 0:
        return offset, 0
    return offset, min(bm.block_size, remaining)


def _index_blocks(path: Path, bm: BlockMap) -> dict[str, list[int]]:
    """Map block hash → list of byte offsets in path."""
    index: dict[str, list[int]] = {}
    with path.open("rb") as fh:
        for i, digest in enumerate(bm.blocks):
            offset, length = _block_offset_size(bm, i)
            if length <= 0:
                continue
            fh.seek(offset)
            chunk = fh.read(length)
            if hashlib.sha256(chunk).hexdigest() != digest:
                # Corrupt/mismatched local map — skip this block for reuse.
                continue
            index.setdefault(digest, []).append(offset)
    return index


def _download_range(url: str, start: int, end_inclusive: int, timeout: int = 120) -> bytes:
    """Download bytes [start, end] inclusive via HTTP Range."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AURA-Updater",
            "Accept": "*/*",
            "Range": f"bytes={start}-{end_inclusive}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    expected = end_inclusive - start + 1
    if len(data) != expected:
        raise IOError(f"Range {start}-{end_inclusive}: got {len(data)} bytes, want {expected}")
    return data


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent [start, end) ranges."""
    if not ranges:
        return []
    ordered = sorted(ranges)
    out = [ordered[0]]
    for start, end in ordered[1:]:
        prev_s, prev_e = out[-1]
        if start <= prev_e:
            out[-1] = (prev_s, max(prev_e, end))
        else:
            out.append((start, end))
    return out


def assemble_from_blockmap(
    url: str,
    new_map: BlockMap,
    old_path: Path | None,
    old_map: BlockMap | None,
    dest: Path,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    """
    Build dest by reusing blocks from old_path and Range-fetching the rest.

    Returns (network_bytes, reused_bytes).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists():
        part.unlink()

    reuse_index: dict[str, list[int]] = {}
    if old_path is not None and old_path.is_file() and old_map is not None:
        try:
            reuse_index = _index_blocks(old_path, old_map)
        except Exception:
            reuse_index = {}

    # Pre-allocate output.
    with part.open("wb") as out:
        out.truncate(new_map.size)

    missing_ranges: list[tuple[int, int]] = []  # [start, end)
    reused_bytes = 0

    with part.open("r+b") as out:
        src = old_path.open("rb") if (old_path is not None and old_path.is_file()) else None
        try:
            for i, digest in enumerate(new_map.blocks):
                offset, length = _block_offset_size(new_map, i)
                if length <= 0:
                    continue
                reused = False
                if src is not None and digest in reuse_index and reuse_index[digest]:
                    src_off = reuse_index[digest][0]
                    src.seek(src_off)
                    chunk = src.read(length)
                    if len(chunk) == length and hashlib.sha256(chunk).hexdigest() == digest:
                        out.seek(offset)
                        out.write(chunk)
                        reused_bytes += length
                        reused = True
                if not reused:
                    missing_ranges.append((offset, offset + length))
        finally:
            if src is not None:
                src.close()

    merged = _merge_ranges(missing_ranges)
    network_total = sum(e - s for s, e in merged)
    network_done = 0
    if on_progress:
        on_progress(0, network_total or None)

    with part.open("r+b") as out:
        for start, end in merged:
            pos = start
            while pos < end:
                chunk_end = min(pos + new_map.block_size * 2, end)
                data = _download_range(url, pos, chunk_end - 1)
                out.seek(pos)
                out.write(data)
                network_done += len(data)
                pos = chunk_end
                if on_progress:
                    on_progress(network_done, network_total or None)

    digest = sha256_file(part)
    if digest.lower() != new_map.sha256.lower():
        part.unlink(missing_ok=True)
        raise ValueError(
            f"Differential assemble checksum mismatch: expected {new_map.sha256}, got {digest}"
        )

    if dest.exists():
        dest.unlink()
    part.replace(dest)
    if on_progress and network_total:
        on_progress(network_total, network_total)
    return network_done, reused_bytes
