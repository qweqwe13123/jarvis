"""Keep the double-clap wake agent installed across platforms.

macOS may reinstall a legacy LaunchAgent from the frozen binary; this module
re-applies the clap-filter agent after UI start unless the user disabled wake.
On Windows/Linux it installs/refreshes the scheduled task or systemd unit.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _support_dir() -> Path:
    try:
        from core.app_paths import support_dir

        return support_dir() / "wake"
    except Exception:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "AURA" / "wake"
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Local" / "AURA" / "wake"
        return Path.home() / ".local" / "share" / "AURA" / "wake"


def _prefs_path() -> Path:
    return _support_dir() / "prefs.json"


def _log_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "mark_xxxix_wake.log"
    return _support_dir() / "logs" / "aura_wake.log"


_SUPPORT_INSTALLER = None  # resolved lazily via _support_dir()


def _installer_candidates() -> tuple[Path, ...]:
    support = _support_dir()
    return (
        _REPO_ROOT / "launcher" / "install_wake_agent.py",
        _REPO_ROOT / "launcher" / "install_launch_agent.py",
        Path("/Applications/AURA.app/Contents/Frameworks/launcher/install_wake_agent.py"),
        Path("/Applications/AURA.app/Contents/Resources/launcher/install_wake_agent.py"),
        Path("/Applications/AURA.app/Contents/Frameworks/launcher/install_launch_agent.py"),
        Path("/Applications/AURA.app/Contents/Resources/launcher/install_launch_agent.py"),
        support / "install_wake_agent.py",
        support / "install_launch_agent.py",
    )


def _listener_candidates() -> tuple[Path, ...]:
    support = _support_dir()
    return (
        _REPO_ROOT / "launcher" / "wake_listener.py",
        Path("/Applications/AURA.app/Contents/Frameworks/launcher/wake_listener.py"),
        Path("/Applications/AURA.app/Contents/Resources/launcher/wake_listener.py"),
        support / "wake_listener.py",
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
    """Copy installer + listener into writable support dir (macOS LaunchAgent path)."""
    src_install = next((p for p in _installer_candidates() if p.is_file()), None)
    src_listener = next(
        (p for p in _listener_candidates() if p.is_file() and _is_clap_filter(p)), None
    )
    if src_install is None or src_listener is None:
        return None
    support = _support_dir()
    support.mkdir(parents=True, exist_ok=True)
    # Prefer the multi-platform installer name when available.
    dst_name = (
        "install_wake_agent.py"
        if src_install.name == "install_wake_agent.py"
        else src_install.name
    )
    dst_install = support / dst_name
    _safe_copy(src_install, dst_install)
    _safe_copy(src_listener, support / "wake_listener.py")
    # Keep legacy filename for older macOS bootstrap paths.
    if dst_name == "install_wake_agent.py":
        try:
            legacy = _REPO_ROOT / "launcher" / "install_launch_agent.py"
            if legacy.is_file():
                _safe_copy(legacy, support / "install_launch_agent.py")
        except Exception:
            pass
    return dst_install


def _load_installer_module():
    # Prefer in-package multi-platform module when importable.
    try:
        from launcher import install_wake_agent as mod

        return mod
    except Exception:
        pass

    installer = _copy_support_files()
    if installer is None:
        from launcher import install_launch_agent as mod

        return mod
    spec = importlib.util.spec_from_file_location("aura_wake_install_agent", installer)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load wake installer")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.jarvis.wake.plist"


def _plist_is_clap_filter() -> bool:
    try:
        text = _plist_path().read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if "AURA.app/Contents/MacOS/AURA" in text and "wake_listener.py" in text:
        if "--wake-listener" not in text:
            return False
    if "--wake-listener" in text and "AURA.app/Contents/MacOS/AURA" in text:
        return True
    return (
        "wake_listener.py" in text
        and ("2.40" in text or "2.4" in text or "1.80" in text or "0.90" in text)
        and ("python" in text.lower() or ".venv" in text)
    )


def _agent_looks_healthy(mod) -> bool:
    if not mod.is_installed():
        return False
    if sys.platform == "darwin":
        return _plist_is_clap_filter()
    return True


def _read_prefs() -> dict:
    try:
        path = _prefs_path()
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_prefs(data: dict) -> None:
    support = _support_dir()
    support.mkdir(parents=True, exist_ok=True)
    _prefs_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_wake_enabled_pref() -> bool:
    """User preference. Default True when unset (product ships with wake on)."""
    prefs = _read_prefs()
    if "enabled" not in prefs:
        return True
    return bool(prefs.get("enabled"))


def is_wake_installed() -> bool:
    try:
        mod = _load_installer_module()
        return bool(mod.is_installed())
    except Exception:
        if sys.platform == "darwin":
            return _plist_path().is_file()
        marker = _support_dir() / "installed"
        return marker.is_file()


def set_wake_enabled(enabled: bool) -> None:
    """Install or uninstall the wake agent and persist the preference."""
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
        log = _log_path()
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
            for attempt in range(4):
                mod = _load_installer_module()
                mod.install()
                if _agent_looks_healthy(mod):
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("a", encoding="utf-8") as f:
                        f.write("[wake_bootstrap] clap-filter agent confirmed.\n")
                    return
                time.sleep(2.0 + attempt)
            raise RuntimeError("wake agent still unhealthy after retries")
        except Exception as e:
            try:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"[wake_bootstrap] reinstall failed: {e}\n")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="AuraWakeBootstrap").start()
