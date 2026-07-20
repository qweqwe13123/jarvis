"""Install the double-clap wake agent on macOS, Windows, and Linux.

macOS  → LaunchAgent (com.jarvis.wake)
Windows → Startup folder .cmd (+ optional schtasks AURAWake)
Linux   → systemd --user unit, with autostart .desktop fallback
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


LABEL = "com.jarvis.wake"
WIN_TASK = "AURAWake"
LINUX_UNIT = "aura-wake.service"
ARGS_TAIL = (
    "--threshold",
    "0.08",
    "--min-gap",
    "0.12",
    "--max-gap",
    "2.40",
    "--cooldown",
    "8.0",
)


def _support_wake() -> Path:
    try:
        from core.app_paths import support_dir

        return support_dir() / "wake"
    except Exception:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "AURA" / "wake"
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Local" / "AURA" / "wake"
        return Path.home() / ".local" / "share" / "AURA" / "wake"


def _marker_path() -> Path:
    return _support_wake() / "installed"


def _write_marker(payload: str) -> None:
    path = _marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.strip() + "\n", encoding="utf-8")


def _clear_marker() -> None:
    path = _marker_path()
    try:
        if path.is_file():
            path.unlink()
    except Exception:
        pass


def _wake_flags() -> list[str]:
    return ["--wake-listener", *ARGS_TAIL]


def _find_dev_repo() -> Path | None:
    env = (os.environ.get("AURA_REPO") or os.environ.get("JARVIS_REPO") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    here = Path(__file__).resolve().parent
    for p in (here.parent, *here.parents):
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
        venv_py = (
            root / ".venv" / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else root / ".venv" / "bin" / "python"
        )
        if (root / "main.py").is_file() and venv_py.is_file():
            return root
    return None


def _windows_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.is_file():
            return exe
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    candidate = Path(local) / "Programs" / "AURA" / "AURA.exe"
    return candidate if candidate.is_file() else None


def _linux_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.is_file():
            return exe
    for path in (
        Path.home() / ".local" / "bin" / "AURA",
        Path.home() / ".local" / "bin" / "aura",
        Path("/usr/local/bin/AURA"),
        Path("/usr/bin/AURA"),
    ):
        if path.is_file() and os.access(path, os.X_OK):
            return path
    for folder in (
        Path.home() / "Applications",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ):
        if not folder.is_dir():
            continue
        try:
            matches = sorted(folder.glob("AURA*.AppImage"), reverse=True)
        except Exception:
            matches = []
        for path in matches:
            if path.is_file() and os.access(path, os.X_OK):
                return path
    return None


def _program_command() -> list[str]:
    """Command that runs the clap listener (frozen app preferred)."""
    force_app = os.environ.get("AURA_WAKE_USE_APP", "").strip() == "1"
    repo = _find_dev_repo()

    if sys.platform == "win32":
        exe = _windows_exe()
        if exe is not None and (force_app or repo is None or getattr(sys, "frozen", False)):
            return [str(exe), *_wake_flags()]
        if repo is not None:
            py = repo / ".venv" / "Scripts" / "python.exe"
            listener = repo / "launcher" / "wake_listener.py"
            return [str(py), str(listener), *ARGS_TAIL]
        return [sys.executable, str(Path(__file__).resolve().parent / "wake_listener.py"), *ARGS_TAIL]

    if sys.platform.startswith("linux"):
        exe = _linux_exe()
        if exe is not None and (force_app or repo is None or getattr(sys, "frozen", False)):
            return [str(exe), *_wake_flags()]
        if repo is not None:
            py = repo / ".venv" / "bin" / "python"
            listener = repo / "launcher" / "wake_listener.py"
            return [str(py), str(listener), *ARGS_TAIL]
        return [sys.executable, str(Path(__file__).resolve().parent / "wake_listener.py"), *ARGS_TAIL]

    # macOS handled by install_launch_agent — this path is for shared helpers/tests.
    aura_bin = Path("/Applications/AURA.app/Contents/MacOS/AURA")
    if aura_bin.is_file() and (force_app or repo is None):
        return [str(aura_bin), *_wake_flags()]
    if repo is not None:
        return [
            str(repo / ".venv" / "bin" / "python"),
            str(repo / "launcher" / "wake_listener.py"),
            *ARGS_TAIL,
        ]
    return [sys.executable, str(Path(__file__).resolve().parent / "wake_listener.py"), *ARGS_TAIL]


def _quote_cmd(parts: list[str]) -> str:
    """Windows schtasks /TR style quoting."""
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if any(ch in p for ch in (' ', '\t', '"')):
            out.append('"' + p.replace('"', '\\"') + '"')
        else:
            out.append(p)
    return " ".join(out)


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess:
    kw: dict = {"capture_output": True, "text": True}
    if sys.platform == "win32":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flag:
            kw["creationflags"] = flag
    return subprocess.run(cmd, check=check, **kw)


# ── Windows ──────────────────────────────────────────────────────────────────


def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_startup_cmd() -> Path:
    return _win_startup_dir() / "AURA Wake.cmd"


def _win_wrapper_cmd() -> Path:
    return _support_wake() / "aura-wake.cmd"


def _win_cmd_escape(path: str) -> str:
    """Quote a path for .cmd / schtasks when it has spaces."""
    if not path:
        return '""'
    if any(ch in path for ch in (' ', '\t', '&', '^', '(', ')', '%')):
        return '"' + path.replace('"', "") + '"'
    return path


def _write_windows_wake_cmd(cmd: list[str]) -> Path:
    """Write a one-line launcher .cmd (schtasks + Startup both point here)."""
    if not cmd:
        raise RuntimeError("empty wake command")
    exe, *args = cmd
    support = _support_wake()
    support.mkdir(parents=True, exist_ok=True)
    wrapper = _win_wrapper_cmd()
    # `start ""` detaches so Startup/.cmd exits immediately (no stuck console).
    line = "start \"\" " + " ".join(_win_cmd_escape(p) for p in [exe, *args])
    wrapper.write_text("@echo off\r\n" + line + "\r\n", encoding="utf-8")
    return wrapper


def _install_windows_startup(wrapper: Path) -> Path:
    startup = _win_startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    dest = _win_startup_cmd()
    shutil.copy2(wrapper, dest)
    return dest


def _start_windows_wake_now(cmd: list[str]) -> None:
    """Spawn the listener immediately (do not wait for next logon)."""
    kw: dict = {}
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flag:
        kw["creationflags"] = flag
    # Avoid inheriting the UI console; listener is long-lived.
    kw["stdout"] = subprocess.DEVNULL
    kw["stderr"] = subprocess.DEVNULL
    kw["stdin"] = subprocess.DEVNULL
    try:
        # CREATE_NEW_PROCESS_GROUP keeps the child alive if parent UI exits.
        if sys.platform == "win32":
            kw["creationflags"] = int(kw.get("creationflags", 0)) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        subprocess.Popen(cmd, **kw)
    except Exception as e:
        raise RuntimeError(f"failed to start wake listener: {e}") from e


def _try_schtasks(wrapper: Path) -> tuple[bool, str]:
    """Best-effort scheduled task. Returns (ok, detail)."""
    tr = str(wrapper)
    _run(["schtasks", "/Delete", "/TN", WIN_TASK, "/F"])
    # /IT = interactive token (needed for mic access in some Windows builds).
    # Point /TR at a single .cmd so quoting never breaks on multi-arg lines.
    create = _run(
        [
            "schtasks",
            "/Create",
            "/TN",
            WIN_TASK,
            "/TR",
            tr,
            "/SC",
            "ONLOGON",
            "/RL",
            "LIMITED",
            "/IT",
            "/F",
        ]
    )
    if create.returncode != 0:
        detail = (create.stderr or create.stdout or "schtasks /Create failed").strip()
        return False, detail
    _run(["schtasks", "/Run", "/TN", WIN_TASK])
    return True, f"task:{WIN_TASK}"


def _win_task_exists() -> bool:
    result = _run(["schtasks", "/Query", "/TN", WIN_TASK])
    return result.returncode == 0


def _install_windows() -> None:
    cmd = _program_command()
    wrapper = _write_windows_wake_cmd(cmd)
    startup = _install_windows_startup(wrapper)
    task_ok, task_detail = _try_schtasks(wrapper)
    # Always start now — Startup only helps on next login; schtasks often fails
    # on locked-down machines (the 1.0.42 failure mode).
    _start_windows_wake_now(cmd)
    parts = [f"startup:{startup}", f"wrapper:{wrapper}", f"cmd:{_quote_cmd(cmd)}"]
    if task_ok:
        parts.append(task_detail)
    else:
        parts.append(f"schtasks_skipped:{task_detail}")
    _write_marker("\n".join(parts))
    print(f"Installed Windows wake via Startup: {startup}")
    if not task_ok:
        print(f"[Wake] schtasks unavailable ({task_detail}); Startup folder is enough.")


def _uninstall_windows() -> None:
    _run(["schtasks", "/End", "/TN", WIN_TASK])
    _run(["schtasks", "/Delete", "/TN", WIN_TASK, "/F"])
    for path in (_win_startup_cmd(), _win_wrapper_cmd()):
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass
    _clear_marker()
    print("Uninstalled Windows wake agent")


def _is_installed_windows() -> bool:
    if _win_startup_cmd().is_file() or _marker_path().is_file():
        return True
    return _win_task_exists()


# ── Linux ────────────────────────────────────────────────────────────────────


def _systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _unit_path() -> Path:
    return _systemd_user_dir() / LINUX_UNIT


def _autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "aura-wake.desktop"


def _systemd_available() -> bool:
    if not shutil.which("systemctl"):
        return False
    result = _run(["systemctl", "--user", "show-environment"])
    return result.returncode == 0


def _shell_join(parts: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(p) for p in parts)


def _install_linux_systemd(cmd: list[str]) -> None:
    unit_dir = _systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    exe_line = _shell_join(cmd)
    body = "\n".join(
        [
            "[Unit]",
            "Description=AURA double-clap wake listener",
            "After=default.target",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart={exe_line}",
            "Restart=on-failure",
            "RestartSec=3",
            "Environment=PYTHONUNBUFFERED=1",
            "Environment=MARK_WAKE_THRESHOLD=0.08",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    _unit_path().write_text(body, encoding="utf-8")
    _run(["systemctl", "--user", "daemon-reload"])
    enable = _run(["systemctl", "--user", "enable", "--now", LINUX_UNIT])
    if enable.returncode != 0:
        # enable may fail if lingering is off; still try start.
        start = _run(["systemctl", "--user", "start", LINUX_UNIT])
        if start.returncode != 0:
            err = (enable.stderr or start.stderr or "systemctl enable/start failed").strip()
            raise RuntimeError(err)
    _write_marker(f"linux-systemd:{LINUX_UNIT}\ncmd:{exe_line}")
    print(f"Installed Linux wake unit: {LINUX_UNIT}")


def _install_linux_autostart(cmd: list[str]) -> None:
    path = _autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exe_line = _shell_join(cmd)
    body = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=AURA Wake",
            "Comment=Double-clap wake listener for AURA",
            f"Exec={exe_line}",
            "X-GNOME-Autostart-enabled=true",
            "Hidden=false",
            "NoDisplay=true",
            "",
        ]
    )
    path.write_text(body, encoding="utf-8")
    # Start now so it works before next login.
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass
    _write_marker(f"linux-autostart:{path}\ncmd:{exe_line}")
    print(f"Installed Linux wake autostart: {path}")


def _install_linux() -> None:
    cmd = _program_command()
    if _systemd_available():
        try:
            _install_linux_systemd(cmd)
            return
        except Exception as e:
            print(f"[Wake] systemd install failed ({e}); falling back to autostart.")
    _install_linux_autostart(cmd)


def _uninstall_linux() -> None:
    if _unit_path().is_file() or _systemd_available():
        _run(["systemctl", "--user", "disable", "--now", LINUX_UNIT])
        try:
            if _unit_path().is_file():
                _unit_path().unlink()
        except Exception:
            pass
        _run(["systemctl", "--user", "daemon-reload"])
    try:
        if _autostart_path().is_file():
            _autostart_path().unlink()
    except Exception:
        pass
    _clear_marker()
    print("Uninstalled Linux wake agent")


def _is_installed_linux() -> bool:
    if _marker_path().is_file():
        return True
    return _unit_path().is_file() or _autostart_path().is_file()


# ── macOS ────────────────────────────────────────────────────────────────────


def _install_darwin() -> None:
    from launcher.install_launch_agent import install as mac_install

    mac_install()
    _write_marker("darwin-launchagent:com.jarvis.wake")


def _uninstall_darwin() -> None:
    from launcher.install_launch_agent import uninstall as mac_uninstall

    mac_uninstall()
    _clear_marker()


def _is_installed_darwin() -> bool:
    from launcher.install_launch_agent import PLIST_PATH

    return PLIST_PATH.is_file()


# ── Public API ───────────────────────────────────────────────────────────────


def is_installed() -> bool:
    if sys.platform == "darwin":
        return _is_installed_darwin()
    if sys.platform == "win32":
        return _is_installed_windows()
    if sys.platform.startswith("linux"):
        return _is_installed_linux()
    return False


def install() -> None:
    if sys.platform == "darwin":
        _install_darwin()
        return
    if sys.platform == "win32":
        _install_windows()
        return
    if sys.platform.startswith("linux"):
        _install_linux()
        return
    raise RuntimeError(f"double-clap wake is not supported on {sys.platform}")


def uninstall() -> None:
    if sys.platform == "darwin":
        _uninstall_darwin()
        return
    if sys.platform == "win32":
        _uninstall_windows()
        return
    if sys.platform.startswith("linux"):
        _uninstall_linux()
        return
    raise RuntimeError(f"double-clap wake is not supported on {sys.platform}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
