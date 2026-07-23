"""Local OS input permission checks for the built-in KVM.

Capturing global mouse/keyboard (server) and injecting it (client) needs an OS
permission on macOS — Accessibility. Windows and Linux don't gate this the same
way, so they return trusted. These helpers let the manager fail fast with a
clear, actionable message instead of "running but nothing happens".
"""

from __future__ import annotations

import platform
import subprocess

_OS = platform.system()


def input_trusted() -> bool:
    """True if this process may capture/inject global input right now.

    macOS → AXIsProcessTrusted(). If the check itself is unavailable we return
    True so we never block a machine we can't actually evaluate.
    """
    if _OS != "Darwin":
        return True
    for mod in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            m = __import__(mod, fromlist=["AXIsProcessTrusted"])
            fn = getattr(m, "AXIsProcessTrusted", None)
            if fn is not None:
                return bool(fn())
        except Exception:
            continue
    return True


def request_input_trust() -> bool:
    """Ask macOS to show the Accessibility prompt (adds AURA to the list)."""
    if _OS != "Darwin":
        return True
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        return bool(
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        )
    except Exception:
        return input_trusted()


def open_input_settings() -> None:
    """Open the OS pane where the user grants input access."""
    try:
        if _OS == "Darwin":
            subprocess.Popen(
                [
                    "open",
                    "x-apple.systempreferences:com.apple.preference.security"
                    "?Privacy_Accessibility",
                ]
            )
        elif _OS == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "ms-settings:privacy"], shell=False)
    except Exception:
        pass


def trust_hint() -> str:
    """Human-readable instruction for granting input permission."""
    if _OS == "Darwin":
        return (
            "macOS needs Accessibility permission for AURA. Open "
            "System Settings › Privacy & Security › Accessibility, enable AURA, "
            "then press Start again."
        )
    return ""
