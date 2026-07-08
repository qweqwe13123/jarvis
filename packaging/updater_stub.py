"""Detached updater process — waits for the main app to exit, applies the package, relaunches."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.updater.installer import apply_update  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: updater_stub.py <package.zip> <parent_pid>")
        return 1
    package = Path(sys.argv[1])
    parent_pid = int(sys.argv[2])
    return apply_update(package, parent_pid=parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
