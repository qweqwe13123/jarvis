"""Windows subprocess helpers — hide console flashes (CREATE_NO_WINDOW)."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


# Avoid flashing cmd/powershell consoles when AURA spawns helpers.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def is_windows() -> bool:
    return sys.platform == "win32"


def _startupinfo() -> Any | None:
    if not is_windows():
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    except Exception:
        return None


def hidden_kwargs() -> dict[str, Any]:
    """Extra kwargs for subprocess.* on Windows to suppress console windows."""
    if not is_windows():
        return {}
    out: dict[str, Any] = {"creationflags": _CREATE_NO_WINDOW}
    si = _startupinfo()
    if si is not None:
        out["startupinfo"] = si
    return out


def merge_flags(existing: int = 0) -> int:
    if not is_windows():
        return existing
    return int(existing) | _CREATE_NO_WINDOW


def run(cmd, **kwargs):
    """subprocess.run with console hidden on Windows."""
    if is_windows():
        flags = int(kwargs.pop("creationflags", 0)) | _CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
        if "startupinfo" not in kwargs:
            si = _startupinfo()
            if si is not None:
                kwargs["startupinfo"] = si
    return subprocess.run(cmd, **kwargs)


def popen(cmd, **kwargs):
    """subprocess.Popen with console hidden on Windows."""
    if is_windows():
        flags = int(kwargs.pop("creationflags", 0)) | _CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
        if "startupinfo" not in kwargs:
            si = _startupinfo()
            if si is not None:
                kwargs["startupinfo"] = si
    return subprocess.Popen(cmd, **kwargs)
