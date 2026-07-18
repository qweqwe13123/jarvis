"""Windows subprocess helpers — hide console flashes (CREATE_NO_WINDOW)."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


# Avoid flashing cmd/powershell consoles when AURA spawns helpers.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def is_windows() -> bool:
    return sys.platform == "win32"


def hidden_kwargs() -> dict[str, Any]:
    """Extra kwargs for subprocess.* on Windows to suppress console windows."""
    if not is_windows():
        return {}
    return {"creationflags": _CREATE_NO_WINDOW}


def merge_flags(existing: int = 0) -> int:
    if not is_windows():
        return existing
    return int(existing) | _CREATE_NO_WINDOW


def run(cmd, **kwargs):
    """subprocess.run with console hidden on Windows."""
    if is_windows():
        flags = int(kwargs.pop("creationflags", 0)) | _CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    return subprocess.run(cmd, **kwargs)


def popen(cmd, **kwargs):
    """subprocess.Popen with console hidden on Windows."""
    if is_windows():
        flags = int(kwargs.pop("creationflags", 0)) | _CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    return subprocess.Popen(cmd, **kwargs)
