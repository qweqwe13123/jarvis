"""Open / quit applications by name (local + remote job target).

Keeps process matching conservative: never kills AURA itself or core OS shells.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path

try:
    import psutil

    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_OS = platform.system()

# Substrings that must never be terminated by close_all / named quit fallbacks.
_PROTECTED = {
    "aura",
    "jarvis",
    "explorer",
    "finder",
    "dock",
    "systemuiserver",
    "windowserver",
    "loginwindow",
    "csrss",
    "winlogon",
    "dwm",
    "sihost",
    "taskhostw",
    "runtimebroker",
    "searchhost",
    "startmenuexperiencehost",
    "shellexperiencehost",
    "applicationframehost",
    "systemsettings",
    "securityhealth",
    "widgets",
    "textinputhost",
}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace(".exe", "").replace(".app", "").split())


def process_hints_for_app(app_name: str) -> list[str]:
    """Return likely process / bundle name fragments for matching."""
    from actions.open_app import _APP_ALIASES, _normalize

    raw = (app_name or "").strip()
    if not raw:
        return []
    hints: list[str] = []
    key = _norm(raw)
    hints.append(key)
    hints.append(key.replace(" ", ""))

    mapped = _normalize(raw)
    if mapped:
        hints.append(_norm(mapped))
        hints.append(_norm(Path(mapped).stem if "/" in mapped or "\\" in mapped else mapped))

    # Alias table: collect all OS mappings for fuzzy match.
    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key == key or alias_key in key or key in alias_key:
            hints.append(alias_key)
            for v in os_map.values():
                hints.append(_norm(v))
                hints.append(_norm(Path(str(v)).stem))

    # Yandex Browser on Windows often runs as browser.exe under a Yandex path.
    if "yandex" in key or "яндекс" in key:
        hints.extend(["yandex", "browser", "yandexbrowser"])

    # Dedupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for h in hints:
        h = _norm(h)
        if h and h not in seen and len(h) >= 2:
            seen.add(h)
            out.append(h)
    return out


def _is_protected(name: str) -> bool:
    n = _norm(name)
    if not n:
        return True
    return any(p in n for p in _PROTECTED)


def _match_hint(name: str, hints: list[str]) -> bool:
    n = _norm(name)
    if not n or _is_protected(n):
        return False
    for h in hints:
        if h in n or n in h:
            return True
    return False


def quit_named_app(app_name: str) -> str:
    """Gracefully quit an application by name. Falls back to terminate."""
    name = (app_name or "").strip()
    if not name:
        return "No application name provided to close."

    hints = process_hints_for_app(name)
    if not hints:
        return f"Could not resolve app name “{name}”."

    if _OS == "Darwin":
        # Prefer AppleScript quit by display name.
        for candidate in (name, name.replace(".app", ""), hints[0].title()):
            try:
                r = subprocess.run(
                    ["osascript", "-e", f'tell application "{candidate}" to quit'],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if r.returncode == 0:
                    time.sleep(0.4)
                    return f"Closed {candidate}."
            except Exception:
                pass

    closed = 0
    if _PSUTIL:
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pname = proc.info.get("name") or ""
                pexe = proc.info.get("exe") or ""
                blob = f"{pname} {pexe}"
                if not _match_hint(pname, hints) and not _match_hint(blob, hints):
                    continue
                if _is_protected(pname) or _is_protected(pexe):
                    continue
                # Never kill our own process tree by vague "python" matches.
                if proc.pid == os.getpid():
                    continue
                try:
                    proc.terminate()
                    closed += 1
                except Exception:
                    try:
                        proc.kill()
                        closed += 1
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        if closed:
            time.sleep(0.6)
            return f"Closed {name} ({closed} process{'es' if closed != 1 else ''})."

    if _OS == "Windows":
        # Last resort: taskkill by common image names from hints.
        images = []
        for h in hints:
            images.append(f"{h}.exe")
        if "yandex" in _norm(name) or "яндекс" in _norm(name):
            images.extend(["browser.exe", "Yandex.exe", "yandex.exe"])
        tried = []
        for img in images:
            if img.lower() in tried:
                continue
            tried.append(img.lower())
            try:
                r = subprocess.run(
                    ["taskkill", "/IM", img, "/T"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if r.returncode == 0 or "SUCCESS" in (r.stdout or "").upper():
                    return f"Closed {name} ({img})."
            except Exception:
                pass

    # Focused-app hotkey fallback when we could not match a process.
    try:
        import pyautogui

        if _OS == "Darwin":
            pyautogui.hotkey("command", "q")
        else:
            pyautogui.hotkey("alt", "f4")
        return (
            f"Could not find a running process for “{name}”; "
            "sent close to the focused window instead."
        )
    except Exception as e:
        return f"Could not close “{name}”: {e}"


def close_all_user_apps(*, confirmed: bool = False) -> str:
    """Quit visible / known user apps. Requires confirmed=True."""
    if not confirmed:
        return (
            "This will close open user applications on this computer "
            "(AURA and system apps stay). Confirm with confirmed=yes."
        )

    if not _PSUTIL:
        return "close_all_apps needs psutil (not installed)."

    # Build hint set from open_app aliases so we only touch known user apps.
    from actions.open_app import _APP_ALIASES

    hints: list[str] = []
    for alias_key, os_map in _APP_ALIASES.items():
        hints.append(alias_key)
        for v in os_map.values():
            hints.append(_norm(v))
            hints.append(_norm(Path(str(v)).stem))
    hints.extend(["yandex", "browser", "chrome", "msedge", "firefox", "code", "spotify"])

    # Deduplicate
    uniq: list[str] = []
    seen: set[str] = set()
    for h in hints:
        h = _norm(h)
        if h and h not in seen and len(h) >= 3:
            seen.add(h)
            uniq.append(h)

    closed_names: list[str] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            pname = proc.info.get("name") or ""
            pexe = proc.info.get("exe") or ""
            if proc.pid == os.getpid():
                continue
            if _is_protected(pname) or _is_protected(pexe):
                continue
            if not (_match_hint(pname, uniq) or _match_hint(f"{pname} {pexe}", uniq)):
                continue
            try:
                proc.terminate()
                closed_names.append(pname or str(proc.pid))
            except Exception:
                try:
                    proc.kill()
                    closed_names.append(pname or str(proc.pid))
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not closed_names:
        return "No matching user apps were running."
    # Unique display
    shown = sorted({_norm(n) for n in closed_names})
    return f"Closed {len(closed_names)} process(es): " + ", ".join(shown[:12]) + (
        "…" if len(shown) > 12 else ""
    )


def windows_yandex_candidates() -> list[Path]:
    """Known install paths for Yandex Browser on Windows."""
    local = os.environ.get("LOCALAPPDATA") or ""
    prog = os.environ.get("PROGRAMFILES") or r"C:\Program Files"
    prog86 = os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)"
    paths = [
        Path(local) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe",
        Path(prog) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe",
        Path(prog86) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe",
    ]
    return [p for p in paths if p.is_file()]
