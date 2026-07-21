"""Ensure numpy.libs (OpenBLAS / MSVC) are on the DLL search path before import.

PyInstaller 6.13 and some frozen layouts can leave delvewheel DLLs undiscoverable,
which surfaces as: Importing the numpy C-extensions failed / _multiarray_umath.
"""

from __future__ import annotations

import os
import sys


def _add(path: str) -> None:
    if not path or not os.path.isdir(path):
        return
    try:
        os.add_dll_directory(path)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    try:
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _meipass() -> str:
    return str(getattr(sys, "_MEIPASS", "") or "")


base = _meipass()
if base:
    _add(os.path.join(base, "numpy.libs"))
    _add(os.path.join(base, "numpy", ".libs"))
    # OpenCV / Qt ship extra MSVC runtimes some numpy builds resolve via PATH.
    _add(os.path.join(base, "PyQt6", "Qt6", "bin"))
    _add(os.path.join(base, "cv2"))
