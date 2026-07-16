"""Install the macOS LaunchAgent that listens for a double clap and opens AURA."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


# This file may live in the repo OR be copied into Application Support.
_HERE = Path(__file__).resolve().parent
_SUPPORT_WAKE = Path.home() / "Library" / "Application Support" / "AURA" / "wake"
LABEL = "com.jarvis.wake"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"
LISTENER = _SUPPORT_WAKE / "wake_listener.py"


def _app_bundle_roots() -> list[Path]:
    roots: list[Path] = []
    # Running from AURA.app
    exe = Path(sys.executable).resolve()
    if "AURA.app" in str(exe):
        contents = exe.parent.parent  # .../AURA.app/Contents
        roots.append(contents / "Frameworks")
        roots.append(contents / "Resources")
    # Installed app even if installer runs from elsewhere
    app = Path("/Applications/AURA.app/Contents")
    if app.is_dir():
        roots.append(app / "Frameworks")
        roots.append(app / "Resources")
    return roots


def _listener_src() -> Path:
    env = os.environ.get("AURA_WAKE_LISTENER")
    if env:
        p = Path(env)
        if p.is_file():
            return p

    candidates = [
        _HERE / "wake_listener.py",
        _SUPPORT_WAKE / "wake_listener.py",
    ]
    # Repo checkout: launcher/ next to project root
    if (_HERE.parent / "main.py").is_file():
        candidates.insert(0, _HERE / "wake_listener.py")
    for root in _app_bundle_roots():
        candidates.append(root / "launcher" / "wake_listener.py")

    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("wake_listener.py not found")


def _python() -> Path:
    """Interpreter for the wake agent — never the AURA GUI binary."""
    env = os.environ.get("AURA_WAKE_PYTHON")
    if env and Path(env).is_file():
        return Path(env)

    support_venv = _SUPPORT_WAKE / ".venv" / "bin" / "python"
    if support_venv.is_file():
        return support_venv

    # Dev checkout next to this file
    repo_venv = _HERE.parent / ".venv" / "bin" / "python"
    if repo_venv.is_file():
        return repo_venv

    exe = Path(sys.executable)
    if exe.name != "AURA" and "AURA.app" not in str(exe):
        return exe

    which = shutil.which("python3")
    if which:
        return Path(which)
    return exe


def _workdir() -> str:
    if (_HERE.parent / "main.py").is_file():
        return str(_HERE.parent)
    for root in _app_bundle_roots():
        if (root / "launcher").is_dir():
            return str(root)
    return str(_SUPPORT_WAKE)


def _sync_listener() -> None:
    _SUPPORT_WAKE.mkdir(parents=True, exist_ok=True)
    src = _listener_src()
    shutil.copy2(src, LISTENER)
    try:
        shutil.copy2(Path(__file__).resolve(), _SUPPORT_WAKE / "install_launch_agent.py")
    except Exception:
        pass


def _plist() -> dict:
    python = _python()
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(LISTENER),
            "--threshold",
            "0.08",
            "--min-gap",
            "0.12",
            "--max-gap",
            "1.80",
            "--cooldown",
            "8.0",
        ],
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True, "SuccessfulExit": False},
        "WorkingDirectory": _workdir(),
        "StandardOutPath": str(LOG_DIR / "jarvis_wake.out.log"),
        "StandardErrorPath": str(LOG_DIR / "jarvis_wake.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "MARK_WAKE_THRESHOLD": "0.08",
        },
    }


def install() -> None:
    _sync_listener()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as f:
        plistlib.dump(_plist(), f, sort_keys=False)

    uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST_PATH)], capture_output=True, text=True)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, text=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], capture_output=True, text=True)
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"],
            capture_output=True,
            text=True,
        )
        print(f"Installed and bootstrapped: {PLIST_PATH}")
        return

    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl load failed")

    print(f"Installed and loaded: {PLIST_PATH}")


def uninstall() -> None:
    uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST_PATH)], capture_output=True, text=True)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, text=True)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print(f"Uninstalled: {PLIST_PATH}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
