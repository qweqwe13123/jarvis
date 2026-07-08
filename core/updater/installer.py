from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from core.platform_detect import is_frozen, normalize_os


def install_dir() -> Path:
    if is_frozen():
        exe = Path(sys.executable).resolve()
        if normalize_os() == "darwin" and exe.parent.name == "MacOS":
            return exe.parent.parent.parent  # JARVIS.app
        if normalize_os() == "windows":
            return exe.parent
        return exe.parent
    return Path(__file__).resolve().parents[2]


def apply_update(package: Path, parent_pid: int | None = None) -> int:
    """Standalone updater entry. Replaces the installed app and relaunches."""
    meta_path = package.with_suffix(package.suffix + ".json")
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing update metadata: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    target = Path(meta["install_dir"])
    launch = meta.get("launch")
    wait_pid = int(meta.get("parent_pid") or parent_pid or 0)

    if wait_pid > 0:
        _wait_for_pid(wait_pid, timeout=120)

    staging = target.parent / f".jarvis-update-{int(time.time())}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        if package.suffix.lower() == ".zip":
            _install_zip(package, target, staging)
        else:
            raise ValueError(f"Unsupported update package: {package.name}")

        if launch:
            subprocess.Popen(launch, cwd=str(target if target.is_dir() else target.parent))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        package.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    return 0


def _wait_for_pid(pid: int, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.4)


def _install_zip(package: Path, target: Path, staging: Path) -> None:
    with zipfile.ZipFile(package, "r") as zf:
        zf.extractall(staging)

    children = [p for p in staging.iterdir() if p.name not in {".DS_Store"}]
    if len(children) == 1 and children[0].is_dir():
        payload = children[0]
    else:
        payload = staging

    backup = target.parent / f"{target.name}.backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)

    if target.exists():
        if normalize_os() == "darwin" and target.suffix == ".app":
            shutil.move(str(target), str(backup))
            shutil.copytree(payload, target, symlinks=True)
            shutil.rmtree(backup, ignore_errors=True)
        elif target.is_dir():
            shutil.move(str(target), str(backup))
            shutil.copytree(payload, target)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(target), str(backup))
            shutil.copy2(payload / target.name if (payload / target.name).exists() else payload, target)
            backup.unlink(missing_ok=True)
    else:
        if payload.is_dir():
            shutil.copytree(payload, target, symlinks=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(payload, target)


def launch_updater(package: Path, parent_pid: int) -> None:
    target = install_dir()
    meta = {
        "install_dir": str(target),
        "parent_pid": parent_pid,
        "launch": _launch_command(target),
    }
    meta_path = package.with_suffix(package.suffix + ".json")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    if is_frozen():
        cmd = [sys.executable, "--jarvis-apply-update", str(package), str(parent_pid)]
    else:
        stub = Path(__file__).resolve().parents[2] / "packaging" / "updater_stub.py"
        cmd = [sys.executable, str(stub), str(package), str(parent_pid)]

    subprocess.Popen(cmd, close_fds=True)


def _launch_command(target: Path) -> list[str]:
    os_name = normalize_os()
    if os_name == "darwin":
        app = target if target.suffix == ".app" else target.parent
        return ["open", "-n", str(app)]
    if os_name == "windows":
        for name in ("AURA.exe", "JARVIS.exe"):
            candidate = target / name if target.is_dir() else target
            if candidate.exists() or not target.is_dir():
                return [str(candidate)]
        return [str(target / "AURA.exe")]
    for name in ("AURA", "JARVIS"):
        candidate = target / name if target.is_dir() else target
        if not target.is_dir() or candidate.exists():
            return [str(candidate)]
    return [str(target / "AURA")]
