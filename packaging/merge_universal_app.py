#!/usr/bin/env python3
"""Merge two single-arch AURA.app bundles into one universal (arm64 + x86_64) app.

Typical flow:
  1. Build arm64 and x86_64 apps with PyInstaller into separate dist folders
  2. merge_apps(arm_app, x86_app, out_app)
  3. codesign --deep the result, then package/notarize
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    # MH_MAGIC_64 / MH_CIGAM_64 / FAT_MAGIC / FAT_CIGAM
    return magic in {
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    }


def _lipo_archs(path: Path) -> set[str]:
    result = subprocess.run(
        ["lipo", "-archs", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {a for a in (result.stdout or "").split() if a}


def _same_file(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
    except OSError:
        return False
    # Compare in chunks — enough for resources; Mach-O handled via lipo.
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca = fa.read(1024 * 1024)
            cb = fb.read(1024 * 1024)
            if ca != cb:
                return False
            if not ca:
                return True


def merge_apps(arm_app: Path, x86_app: Path, out_app: Path) -> Path:
    """Create out_app as a universal merge of arm_app (base) + x86_app."""
    arm_app = arm_app.resolve()
    x86_app = x86_app.resolve()
    out_app = out_app.resolve()

    if not (arm_app / "Contents").is_dir():
        raise FileNotFoundError(f"arm64 app missing Contents: {arm_app}")
    if not (x86_app / "Contents").is_dir():
        raise FileNotFoundError(f"x86_64 app missing Contents: {x86_app}")

    if out_app.exists():
        shutil.rmtree(out_app)
    out_app.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(arm_app, out_app, symlinks=True)

    lipo_count = 0
    copy_count = 0
    skip_same = 0
    conflicts: list[str] = []

    for x86_path in x86_app.rglob("*"):
        if x86_path.is_symlink() or not x86_path.is_file():
            continue
        rel = x86_path.relative_to(x86_app)
        out_path = out_app / rel
        arm_path = arm_app / rel

        if not arm_path.is_file():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(x86_path, out_path)
            copy_count += 1
            continue

        if _is_macho(arm_path) and _is_macho(x86_path):
            arm_archs = _lipo_archs(arm_path)
            x86_archs = _lipo_archs(x86_path)
            if "arm64" in arm_archs and "x86_64" in arm_archs:
                skip_same += 1
                continue
            if arm_archs == x86_archs and "arm64" in arm_archs and "x86_64" in arm_archs:
                skip_same += 1
                continue
            # Prefer thin slices: arm64 from arm build, x86_64 from intel build.
            tmp = out_path.with_suffix(out_path.suffix + ".universal.tmp")
            try:
                _run(
                    [
                        "lipo",
                        "-create",
                        str(arm_path),
                        str(x86_path),
                        "-output",
                        str(tmp),
                    ]
                )
                os.replace(tmp, out_path)
                lipo_count += 1
            except subprocess.CalledProcessError as exc:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                # Some binaries are arch-specific helpers that cannot merge;
                # keep arm64 slice (Apple Silicon primary) and warn.
                conflicts.append(f"{rel}: lipo failed ({exc.stderr or exc.stdout})")
            continue

        if _same_file(arm_path, x86_path):
            skip_same += 1
            continue

        # Non-Mach-O divergence: keep arm64 copy (already in out_app).
        conflicts.append(f"{rel}: non-Mach-O content differs; kept arm64")

    main_bin = out_app / "Contents" / "MacOS" / "AURA"
    archs = _lipo_archs(main_bin)
    if not {"arm64", "x86_64"}.issubset(archs):
        raise RuntimeError(
            f"Main binary is not universal after merge: {main_bin} archs={sorted(archs)}"
        )

    print(
        f"[universal] lipo={lipo_count} copied_unique={copy_count} "
        f"identical={skip_same} notes={len(conflicts)}"
    )
    for note in conflicts[:40]:
        print(f"  ! {note}")
    if len(conflicts) > 40:
        print(f"  ! … {len(conflicts) - 40} more")
    print(f"[universal] main archs: {' '.join(sorted(archs))}")
    print(f"[universal] → {out_app}")
    return out_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge arm64 + x86_64 AURA.app")
    parser.add_argument("arm_app", type=Path)
    parser.add_argument("x86_app", type=Path)
    parser.add_argument("out_app", type=Path)
    args = parser.parse_args()
    merge_apps(args.arm_app, args.x86_app, args.out_app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
