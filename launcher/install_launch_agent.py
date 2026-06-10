from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = BASE_DIR / ".venv" / "bin" / "python"
LISTENER = BASE_DIR / "launcher" / "wake_listener.py"
LABEL = "com.jarvis.wake"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"


def _plist() -> dict:
    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(LISTENER),
            "--threshold",
            "0.12",
            "--max-gap",
            "2.8",
        ],
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True, "SuccessfulExit": False},
        "WorkingDirectory": str(BASE_DIR),
        "StandardOutPath": str(LOG_DIR / "jarvis_wake.out.log"),
        "StandardErrorPath": str(LOG_DIR / "jarvis_wake.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "MARK_WAKE_THRESHOLD": "0.12",
        },
    }


def install() -> None:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as f:
        plistlib.dump(_plist(), f, sort_keys=False)

    uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST_PATH)], capture_output=True, text=True)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, text=True)
    result = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST_PATH)], capture_output=True, text=True)
    if result.returncode == 0:
        subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], capture_output=True, text=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], capture_output=True, text=True)
        print(f"Installed and bootstrapped: {PLIST_PATH}")
        return

    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl load failed")

    print(f"Installed and loaded: {PLIST_PATH}")


def uninstall() -> None:
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
