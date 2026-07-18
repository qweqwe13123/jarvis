"""Keep the double-clap LaunchAgent on the clap-filter installer.

The frozen AURA binary may reinstall an older wake plist on launch. This
module (loaded from disk via prefer-disk) re-applies the good agent shortly
after the UI starts — unless the user disabled wake in Settings.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import threading
import time
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "AURA" / "wake"
_SUPPORT_INSTALLER = _SUPPORT_DIR / "install_launch_agent.py"
_SUPPORT_LISTENER = _SUPPORT_DIR / "wake_listener.py"
_PREFS_PATH = _SUPPORT_DIR / "prefs.json"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.jarvis.wake.plist"

_INSTALLER_CANDIDATES = (
    _REPO_ROOT / "launcher" / "install_launch_agent.py",
    Path("/Applications/AURA.app/Contents/Frameworks/launcher/install_launch_agent.py"),
    Path("/Applications/AURA.app/Contents/Resources/launcher/install_launch_agent.py"),
    _SUPPORT_INSTALLER,
)
_LISTENER_CANDIDATES = (
    _REPO_ROOT / "launcher" / "wake_listener.py",
    Path("/Applications/AURA.app/Contents/Frameworks/launcher/wake_listener.py"),
    Path("/Applications/AURA.app/Contents/Resources/launcher/wake_listener.py"),
    _SUPPORT_LISTENER,
)


def _is_clap_filter(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return "_is_clap_candidate" in text and "clap-filter" in text


def _safe_copy(src: Path, dst: Path) -> None:
    try:
        if src.resolve() == dst.resolve():
            return
    except Exception:
        pass
    shutil.copy2(src, dst)


def _copy_support_files() -> Path | None:
    src_install = next((p for p in _INSTALLER_CANDIDATES if p.is_file()), None)
    src_listener = next((p for p in _LISTENER_CANDIDATES if p.is_file() and _is_clap_filter(p)), None)
    if src_install is None or src_listener is None:
        return None
    _SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    _safe_copy(src_install, _SUPPORT_INSTALLER)
    _safe_copy(src_listener, _SUPPORT_LISTENER)
    return _SUPPORT_INSTALLER


def _load_installer_module():
    installer = _copy_support_files()
    if installer is None:
        # Fall back to importable launcher package (dev runs).
        from launcher import install_launch_agent as mod

        return mod
    spec = importlib.util.spec_from_file_location(
        "aura_wake_install_launch_agent", installer
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load wake installer")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plist_is_clap_filter() -> bool:
    try:
        text = _PLIST_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    # Broken legacy: AURA binary invoked with a .py path (not --wake-listener).
    if "AURA.app/Contents/MacOS/AURA" in text and "wake_listener.py" in text:
        if "--wake-listener" not in text:
            return False
    # Good: shipped app wake mode.
    if "--wake-listener" in text and "AURA.app/Contents/MacOS/AURA" in text:
        return True
    # Good: python + clap-filter script (local dev / Application Support).
    return (
        "wake_listener.py" in text
        and ("2.40" in text or "2.4" in text or "1.80" in text or "0.90" in text)
        and ("python" in text.lower() or ".venv" in text)
    )


def _read_prefs() -> dict:
    try:
        if _PREFS_PATH.is_file():
            return json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_prefs(data: dict) -> None:
    _SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_wake_enabled_pref() -> bool:
    """User preference. Default True when unset (product ships with wake on)."""
    prefs = _read_prefs()
    if "enabled" not in prefs:
        return True
    return bool(prefs.get("enabled"))


def is_wake_installed() -> bool:
    return _PLIST_PATH.is_file()


def set_wake_enabled(enabled: bool) -> None:
    """Install or uninstall the LaunchAgent and persist the preference."""
    enabled = bool(enabled)
    prefs = _read_prefs()
    prefs["enabled"] = enabled
    _write_prefs(prefs)
    mod = _load_installer_module()
    if enabled:
        mod.install()
    else:
        mod.uninstall()


def ensure_clap_wake_async(delay_s: float = 1.5) -> None:
    """Re-install clap-filter wake after the frozen installer may have run."""

    def _run() -> None:
        log = Path.home() / "Library" / "Logs" / "mark_xxxix_wake.log"
        try:
            time.sleep(max(0.0, delay_s))
            if not is_wake_enabled_pref():
                try:
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("a", encoding="utf-8") as f:
                        f.write("[wake_bootstrap] skipped — disabled in Settings.\n")
                except Exception:
                    pass
                return
            # Retry: frozen main.py may overwrite the plist a few seconds in.
            for attempt in range(4):
                mod = _load_installer_module()
                mod.install()
                if _plist_is_clap_filter():
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("a", encoding="utf-8") as f:
                        f.write("[wake_bootstrap] clap-filter agent confirmed.\n")
                    return
                time.sleep(2.0 + attempt)
            raise RuntimeError("plist still not clap-filter after retries")
        except Exception as e:
            try:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"[wake_bootstrap] reinstall failed: {e}\n")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="AuraWakeBootstrap").start()
