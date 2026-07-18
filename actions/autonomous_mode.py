from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


STATE_PATH = _base_dir() / "runtime" / "autonomous_mode.json"
_OS = platform.system()


def _save_state(enabled: bool, note: str = "") -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "enabled": enabled,
                "note": note,
                "updated": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"enabled": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False}


def _run(cmd: list[str], timeout: int = 8) -> tuple[bool, str]:
    try:
        if _OS == "Windows":
            from core.win_subprocess import run as _win_run

            # Hide powershell/cmd flashes when toggling Focus Assist helpers.
            if cmd and str(cmd[0]).lower().startswith("powershell"):
                cmd = [cmd[0], "-WindowStyle", "Hidden", *cmd[1:]]
            result = _win_run(cmd, capture_output=True, text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, out
    except Exception as e:
        return False, str(e)


def _mac_focus(enabled: bool) -> str:
    # macOS Focus has no single stable public CLI across versions, so try safe options.
    value = "true" if enabled else "false"
    legacy_cmds = [
        ["defaults", "-currentHost", "write", "com.apple.notificationcenterui", "doNotDisturb", "-boolean", value],
        ["defaults", "-currentHost", "write", "com.apple.notificationcenterui", "dndStart", "-int", "0"],
        ["defaults", "-currentHost", "write", "com.apple.notificationcenterui", "dndEnd", "-int", "1440"],
    ]
    successes = 0
    for cmd in legacy_cmds:
        ok, _ = _run(cmd)
        successes += int(ok)

    _run(["killall", "NotificationCenter"], timeout=4)

    shortcut_name = "Jarvis Focus On" if enabled else "Jarvis Focus Off"
    ok, out = _run(["shortcuts", "run", shortcut_name], timeout=6)
    if ok:
        return f"Focus shortcut ran: {shortcut_name}"

    if successes:
        return "Do Not Disturb preference updated. If macOS Focus does not change, create Shortcuts named 'Jarvis Focus On' and 'Jarvis Focus Off'."
    return f"Could not control Focus automatically: {out}"


def _windows_focus(enabled: bool) -> str:
    # Focus Assist settings are not reliably exposed on all Windows versions.
    # This opens the settings page as a fallback after saving autonomous mode state.
    if enabled:
        _run(["powershell", "-NoProfile", "-Command", "Start-Process ms-settings:quiethours"])
        return "Autonomous mode saved. Opened Focus Assist settings."
    return "Autonomous mode disabled. Turn off Focus Assist from Windows settings if it is still active."


def _linux_focus(enabled: bool) -> str:
    if enabled:
        for cmd in (
            ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false"],
            ["gsettings", "set", "org.gnome.desktop.notifications", "show-in-lock-screen", "false"],
        ):
            _run(cmd)
        return "GNOME notification banners disabled."
    for cmd in (
        ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "true"],
        ["gsettings", "set", "org.gnome.desktop.notifications", "show-in-lock-screen", "true"],
    ):
        _run(cmd)
    return "GNOME notification banners enabled."


def _apply_focus(enabled: bool) -> str:
    if _OS == "Darwin":
        return _mac_focus(enabled)
    if _OS == "Windows":
        return _windows_focus(enabled)
    if _OS == "Linux":
        return _linux_focus(enabled)
    return "Focus control is not supported on this OS."


def autonomous_mode(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()
    note = (params.get("note") or "").strip()

    if action in ("on", "enable", "start", "autonomous", "focus"):
        _save_state(True, note)
        focus_result = _apply_focus(True)
        result = f"Autonomous mode enabled. {focus_result}"
    elif action in ("off", "disable", "stop", "normal"):
        _save_state(False, note)
        focus_result = _apply_focus(False)
        result = f"Autonomous mode disabled. {focus_result}"
    elif action == "status":
        state = _load_state()
        status = "enabled" if state.get("enabled") else "disabled"
        result = f"Autonomous mode is {status}."
    else:
        result = "Unknown autonomous_mode action. Use on, off, or status."

    print(f"[Autonomous] {result}")
    if player:
        player.write_log(f"[Autonomous] {result[:120]}")
    return result
