"""Locate Input Leap (preferred) or Barrier server/client binaries."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EngineBinaries:
    engine: str  # "input_leap" | "barrier"
    label: str
    server: Path
    client: Path
    download_url: str


_INPUT_LEAP_URL = "https://github.com/input-leap/input-leap/releases"
_BARRIER_URL = "https://github.com/debauchee/barrier/releases"


def _candidates() -> list[tuple[str, str, list[str], list[str], str]]:
    """(engine_id, label, server_names, client_names, download_url)."""
    if sys.platform == "darwin":
        leap_srv = [
            "/Applications/Input Leap.app/Contents/MacOS/input-leaps",
            "/Applications/InputLeap.app/Contents/MacOS/input-leaps",
            "/opt/homebrew/bin/input-leaps",
            "/usr/local/bin/input-leaps",
        ]
        leap_cli = [
            "/Applications/Input Leap.app/Contents/MacOS/input-leapc",
            "/Applications/InputLeap.app/Contents/MacOS/input-leapc",
            "/opt/homebrew/bin/input-leapc",
            "/usr/local/bin/input-leapc",
        ]
        bar_srv = [
            "/Applications/Barrier.app/Contents/MacOS/barriers",
            "/opt/homebrew/bin/barriers",
            "/usr/local/bin/barriers",
        ]
        bar_cli = [
            "/Applications/Barrier.app/Contents/MacOS/barrierc",
            "/opt/homebrew/bin/barrierc",
            "/usr/local/bin/barrierc",
        ]
    elif sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        leap_srv = [
            str(Path(pf) / "Input Leap" / "input-leaps.exe"),
            str(Path(pf) / "InputLeap" / "input-leaps.exe"),
            str(Path(pf86) / "Input Leap" / "input-leaps.exe"),
            str(Path(local) / "Programs" / "Input Leap" / "input-leaps.exe") if local else "",
        ]
        leap_cli = [
            str(Path(pf) / "Input Leap" / "input-leapc.exe"),
            str(Path(pf) / "InputLeap" / "input-leapc.exe"),
            str(Path(pf86) / "Input Leap" / "input-leapc.exe"),
            str(Path(local) / "Programs" / "Input Leap" / "input-leapc.exe") if local else "",
        ]
        bar_srv = [
            str(Path(pf) / "Barrier" / "barriers.exe"),
            str(Path(pf86) / "Barrier" / "barriers.exe"),
        ]
        bar_cli = [
            str(Path(pf) / "Barrier" / "barrierc.exe"),
            str(Path(pf86) / "Barrier" / "barrierc.exe"),
        ]
    else:
        leap_srv = ["/usr/bin/input-leaps", "/usr/local/bin/input-leaps"]
        leap_cli = ["/usr/bin/input-leapc", "/usr/local/bin/input-leapc"]
        bar_srv = ["/usr/bin/barriers", "/usr/local/bin/barriers"]
        bar_cli = ["/usr/bin/barrierc", "/usr/local/bin/barrierc"]

    return [
        ("input_leap", "Input Leap", leap_srv, leap_cli, _INPUT_LEAP_URL),
        ("barrier", "Barrier", bar_srv, bar_cli, _BARRIER_URL),
    ]


def _resolve_pair(server_paths: list[str], client_paths: list[str]) -> tuple[Path, Path] | None:
    srv: Path | None = None
    cli: Path | None = None

    def _ok(p: Path) -> bool:
        if not p.is_file():
            return False
        if sys.platform == "win32":
            return True
        return os.access(p, os.X_OK)

    # Explicit paths
    for raw in server_paths:
        if not raw:
            continue
        p = Path(raw)
        if _ok(p):
            srv = p
            break
    for raw in client_paths:
        if not raw:
            continue
        p = Path(raw)
        if _ok(p):
            cli = p
            break

    # PATH basenames
    if srv is None:
        for raw in server_paths:
            if not raw:
                continue
            found = shutil.which(Path(raw).name)
            if found:
                srv = Path(found)
                break
    if cli is None:
        for raw in client_paths:
            if not raw:
                continue
            found = shutil.which(Path(raw).name)
            if found:
                cli = Path(found)
                break

    if srv is not None and cli is not None:
        return srv, cli
    return None


def detect_engine() -> EngineBinaries | None:
    """Return preferred installed engine (Input Leap > Barrier), or None."""
    for engine_id, label, srv_paths, cli_paths, url in _candidates():
        pair = _resolve_pair(srv_paths, cli_paths)
        if pair:
            return EngineBinaries(
                engine=engine_id,
                label=label,
                server=pair[0],
                client=pair[1],
                download_url=url,
            )
    return None


def preferred_download_url() -> str:
    return _INPUT_LEAP_URL


def install_hint() -> str:
    if sys.platform == "darwin":
        return (
            "Install Input Leap (recommended) or Barrier, then reopen Devices.\n"
            "• Input Leap: github.com/input-leap/input-leap/releases\n"
            "• or: brew tap vancluever/input-leap && brew install input-leap\n"
            "• Barrier: github.com/debauchee/barrier/releases"
        )
    if sys.platform == "win32":
        return (
            "Install Input Leap (recommended) or Barrier from GitHub Releases, "
            "then reopen Devices.\n"
            "• Input Leap: github.com/input-leap/input-leap/releases\n"
            "• Barrier: github.com/debauchee/barrier/releases"
        )
    return (
        "Install input-leap or barrier via your package manager "
        "(e.g. apt / pacman / flatpak), then reopen Devices."
    )
