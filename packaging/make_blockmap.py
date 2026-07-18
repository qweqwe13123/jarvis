#!/usr/bin/env python3
"""Generate an AURA Cursor-style .blockmap for a release package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.updater.blockmap import DEFAULT_BLOCK_SIZE, generate_blockmap  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate AURA update blockmap")
    ap.add_argument("package", type=Path, help="Path to .zip / package file")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .blockmap path (default: <package>.blockmap)",
    )
    ap.add_argument(
        "--block-size",
        type=int,
        default=DEFAULT_BLOCK_SIZE,
        help=f"Block size in bytes (default {DEFAULT_BLOCK_SIZE})",
    )
    args = ap.parse_args()
    package: Path = args.package
    if not package.is_file():
        print(f"error: not a file: {package}", file=sys.stderr)
        return 1
    out = args.output or Path(str(package) + ".blockmap")
    bm = generate_blockmap(package, block_size=args.block_size)
    bm.save(out)
    print(f"wrote {out}")
    print(f"  size={bm.size}")
    print(f"  sha256={bm.sha256}")
    print(f"  blocks={bm.block_count} × {bm.block_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
