"""Install the macOS LaunchAgent that listens for a double clap and opens AURA."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SUPPORT_WAKE = Path.home() / "Library" / "Application Support" / "AURA" / "wake"
LABEL = "com.jarvis.wake"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"
LISTENER = _SUPPORT_WAKE / "wake_listener.py"
AURA_BIN = Path("/Applications/AURA.app/Contents/MacOS/AURA")


def _app_bundle_roots() -> list[Path]:
    roots: list[Path] = []
    exe = Path(sys.executable).resolve()
    if "AURA.app" in str(exe):
        contents = exe.parent.parent
        roots.append(contents / "Frameworks")
        roots.append(contents / "Resources")
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
    if (_HERE.parent / "main.py").is_file():
        candidates.insert(0, _HERE / "wake_listener.py")
    for root in _app_bundle_roots():
        candidates.append(root / "launcher" / "wake_listener.py")

    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("wake_listener.py not found")


def _safe_copy(src: Path, dst: Path) -> None:
    try:
        if src.resolve() == dst.resolve():
            return
    except Exception:
        pass
    shutil.copy2(src, dst)


def _sync_listener() -> None:
    _SUPPORT_WAKE.mkdir(parents=True, exist_ok=True)
    _safe_copy(_listener_src(), LISTENER)
    try:
        _safe_copy(Path(__file__).resolve(), _SUPPORT_WAKE / "install_launch_agent.py")
    except Exception:
        pass


def _find_dev_repo() -> Path | None:
    """Locate a local jarvis122 checkout with .venv (installer may live in Support/)."""
    env = (os.environ.get("AURA_REPO") or os.environ.get("JARVIS_REPO") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    # When copied to Application Support, _HERE.parent is not the git root.
    for p in (_HERE.parent, *_HERE.parents):
        candidates.append(p)
    candidates.extend(
        [
            Path.home() / "jarvis122",
            Path("/Users/khalilisaiev/jarvis122"),
        ]
    )
    seen: set[Path] = set()
    for root in candidates:
        try:
            root = root.resolve()
        except Exception:
            continue
        if root in seen:
            continue
        seen.add(root)
        if (root / "main.py").is_file() and (root / ".venv" / "bin" / "python").is_file():
            return root
    return None


def _program_args() -> tuple[list[str], str]:
    """
    Local dev checkout: python + wake_listener.py (fast iterate).
    Published installs: AURA.app --wake-listener (bundled sounddevice).
    Force app mode with AURA_WAKE_USE_APP=1 (release QA on a machine that also
    has the git repo).
    """
    args_tail = [
        "--threshold",
        "0.08",
        "--min-gap",
        "0.12",
        "--max-gap",
        "2.40",
        "--cooldown",
        "8.0",
    ]
    repo = _find_dev_repo()
    force_app = os.environ.get("AURA_WAKE_USE_APP", "").strip() == "1"

    # End-user installs (and release QA): run clap wake inside the signed app.
    if AURA_BIN.is_file() and (force_app or repo is None):
        return (
            [str(AURA_BIN), "--wake-listener", *args_tail],
            str(AURA_BIN.parent.parent / "Frameworks"),
        )

    if repo is not None:
        return [str(repo / ".venv" / "bin" / "python"), str(LISTENER), *args_tail], str(repo)

    env_py = os.environ.get("AURA_WAKE_PYTHON")
    if env_py and Path(env_py).is_file():
        python = Path(env_py)
    else:
        python = Path(sys.executable)
        if python.name == "AURA" or "AURA.app" in str(python):
            which = shutil.which("python3")
            python = Path(which) if which else python

    workdir = str(repo) if repo is not None else str(_SUPPORT_WAKE)
    return [str(python), str(LISTENER), *args_tail], workdir


def _plist() -> dict:
    program, workdir = _program_args()
    return {
        "Label": LABEL,
        "ProgramArguments": program,
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True, "SuccessfulExit": False},
        "WorkingDirectory": workdir,
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
