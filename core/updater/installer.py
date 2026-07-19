from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from core.platform_detect import is_frozen, normalize_os


def _log_path() -> Path:
    if normalize_os() == "darwin":
        root = Path.home() / "Library" / "Logs" / "AURA"
    elif normalize_os() == "windows":
        root = Path.home() / "AppData" / "Local" / "AURA" / "logs"
    else:
        root = Path.home() / ".local" / "state" / "AURA" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "updater.log"


def _ulog(message: str) -> None:
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def appimage_path() -> Path | None:
    """When running inside an AppImage, return the mounted AppImage file path."""
    raw = (os.environ.get("APPIMAGE") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def install_dir() -> Path:
    ai = appimage_path()
    if ai is not None:
        return ai

    if is_frozen():
        exe = Path(sys.executable).resolve()
        if normalize_os() == "darwin" and exe.parent.name == "MacOS":
            return exe.parent.parent.parent  # AURA.app
        if normalize_os() == "windows":
            return exe.parent
        return exe.parent
    return Path(__file__).resolve().parents[2]


def apply_update(package: Path, parent_pid: int | None = None) -> int:
    """Standalone updater entry (non-macOS / fallback). Prefer launch_updater scripts."""
    _ulog(f"apply_update package={package} pid={parent_pid}")
    meta_path = Path(str(package) + ".json")
    if not meta_path.exists():
        meta_path = package.with_suffix(package.suffix + ".json")
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing update metadata: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    target = Path(meta["install_dir"])
    launch = meta.get("launch")
    wait_pid = int(meta.get("parent_pid") or parent_pid or 0)

    if wait_pid > 0:
        _wait_for_pid(wait_pid, timeout=180)

    staging = Path(tempfile.mkdtemp(prefix="aura-update-"))
    try:
        name_l = package.name.lower()
        if name_l.endswith(".appimage"):
            _install_appimage(package, target)
        elif package.suffix.lower() == ".zip":
            _install_zip(package, target, staging)
        elif package.suffix.lower() == ".dmg":
            if normalize_os() == "darwin":
                subprocess.Popen(["open", str(package)])
                return 0
            raise ValueError(f"Unsupported update package: {package.name}")
        elif package.suffix.lower() == ".exe" and normalize_os() == "windows":
            _run_windows_setup(package, target)
        else:
            raise ValueError(f"Unsupported update package: {package.name}")

        if launch:
            _ulog(f"relaunch {launch}")
            subprocess.Popen(
                launch,
                cwd=str(target if target.is_dir() else target.parent),
                start_new_session=True,
            )
    except Exception as exc:
        _ulog(f"apply_update FAILED: {exc}")
        # Best-effort relaunch of whatever is still on disk.
        try:
            if launch:
                subprocess.Popen(launch, start_new_session=True)
        except Exception:
            pass
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        package.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    return 0


def _wait_for_pid(pid: int, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            # Give the OS a moment to release bundle file locks.
            time.sleep(0.8)
            return
        time.sleep(0.35)


def _install_appimage(package: Path, target: Path) -> None:
    """Replace the running AppImage file atomically and keep it executable."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".new")
    backup = target.with_name(target.name + ".bak")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(package, tmp)
    os.chmod(
        tmp,
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH,
    )
    if target.exists():
        if backup.exists():
            backup.unlink(missing_ok=True)
        shutil.move(str(target), str(backup))
    shutil.move(str(tmp), str(target))
    backup.unlink(missing_ok=True)


def _extract_zip(package: Path, staging: Path) -> None:
    """Extract update ZIP into staging.

    On macOS, Python zipfile breaks Frameworks symlinks + execute bits +
    codesign/staple — that yields \"AURA can't be opened\" after Update.
    Always prefer ``ditto -x -k`` (same as packaging / Cursor-style).
    """
    staging.mkdir(parents=True, exist_ok=True)
    if normalize_os() == "darwin" and shutil.which("ditto"):
        subprocess.check_call(
            ["ditto", "-x", "-k", str(package), str(staging)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    with zipfile.ZipFile(package, "r") as zf:
        zf.extractall(staging)


def _find_app_in_dir(root: Path) -> Path | None:
    """Locate AURA.app (or a single .app) under an extracted update tree."""
    if not root.is_dir():
        return None
    nested = root / "AURA.app"
    if nested.is_dir():
        return nested
    apps = [p for p in root.iterdir() if p.suffix == ".app" and p.is_dir()]
    if len(apps) == 1:
        return apps[0]
    # ditto may place the .app one level deeper depending on zip layout.
    for child in root.iterdir():
        if child.is_dir() and child.name not in {".DS_Store"}:
            found = _find_app_in_dir(child)
            if found is not None:
                return found
    return None


def _extract_app_payload(package: Path, staging: Path) -> Path:
    """Unzip and return the AURA.app (or onedir) payload path."""
    _extract_zip(package, staging)

    found = _find_app_in_dir(staging)
    if found is not None:
        return found

    children = [p for p in staging.iterdir() if p.name not in {".DS_Store"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return staging


def _install_zip(package: Path, target: Path, staging: Path) -> None:
    payload = _extract_app_payload(package, staging)

    backup = target.parent / f"{target.name}.backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
        if backup.is_file():
            backup.unlink(missing_ok=True)

    if target.exists():
        if normalize_os() == "darwin" and target.suffix == ".app":
            shutil.move(str(target), str(backup))
            shutil.copytree(payload, target, symlinks=True)
            shutil.rmtree(backup, ignore_errors=True)
        elif target.is_dir():
            shutil.move(str(target), str(backup))
            shutil.copytree(payload, target, symlinks=True)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(target), str(backup))
            src = payload / target.name if payload.is_dir() and (payload / target.name).exists() else payload
            if src.is_dir():
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
            if backup.is_dir():
                shutil.rmtree(backup, ignore_errors=True)
            else:
                backup.unlink(missing_ok=True)
    else:
        if payload.is_dir():
            shutil.copytree(payload, target, symlinks=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(payload, target)


def _mark_in_app_update() -> None:
    """Tell the next launch this was an Update, not a fresh site DMG install."""
    try:
        from core.app_paths import support_dir
        from core.version import VERSION

        path = support_dir() / "runtime" / "in_app_update.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"pending": True, "from_version": VERSION, "ts": time.time()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _ulog("marked pending in-app update (skip onboarding on relaunch)")
    except Exception as e:
        _ulog(f"could not mark in-app update: {e}")


def launch_updater(package: Path, parent_pid: int) -> None:
    """
    Start a detached updater that can replace the running app.

    On macOS we MUST NOT run the replacement from inside AURA.app itself —
    that aborts when the bundle is swapped. Instead we extract to /tmp and
    run an external bash script (ditto + open).
    """
    target = install_dir()
    os_name = normalize_os()
    _ulog(f"launch_updater package={package} target={target} parent={parent_pid}")
    _mark_in_app_update()

    if os_name == "darwin" and package.suffix.lower() == ".zip":
        _launch_macos_zip_updater(package, target, parent_pid)
        return
    if os_name == "linux" and package.name.lower().endswith(".appimage"):
        _launch_linux_appimage_updater(package, target, parent_pid)
        return
    if os_name == "windows" and package.suffix.lower() == ".exe":
        _launch_windows_exe_updater(package, target, parent_pid)
        return
    if os_name == "windows" and package.suffix.lower() == ".zip":
        _launch_windows_zip_updater(package, target, parent_pid)
        return

    # Fallback: in-process helper (dev / odd packages)
    meta = {
        "install_dir": str(target),
        "parent_pid": parent_pid,
        "launch": _launch_command(target),
    }
    meta_path = Path(str(package) + ".json")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    if is_frozen():
        cmd = [sys.executable, "--jarvis-apply-update", str(package), str(parent_pid)]
    else:
        stub = Path(__file__).resolve().parents[2] / "packaging" / "updater_stub.py"
        cmd = [sys.executable, str(stub), str(package), str(parent_pid)]

    kwargs: dict = {"close_fds": True}
    if os_name != "windows":
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    _ulog(f"spawned fallback updater: {cmd}")


def _shell_quote(p: Path | str) -> str:
    """Escape a path for use inside single-quoted shell / PowerShell strings."""
    return str(p).replace("'", "'\"'\"'")


def _ps_quote(p: Path | str) -> str:
    return str(p).replace("'", "''")


def _launch_macos_zip_updater(package: Path, target: Path, parent_pid: int) -> None:
    """Cursor-style: extract with ditto, replace .app with ditto, then open.

    Never use Python zipfile for the .app — it strips codesign and +x bits.
    """
    work = Path(tempfile.mkdtemp(prefix="aura-mac-update-"))
    # Extract into work/extract so apply.sh can also re-extract if needed.
    extract_dir = work / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(package, extract_dir)
    payload = _find_app_in_dir(extract_dir)
    if payload is None or not (payload / "Contents" / "MacOS").exists():
        raise RuntimeError(f"Update zip does not contain a macOS app bundle: {extract_dir}")

    # Fail fast before quitting the running app if codesign is already broken.
    try:
        subprocess.check_call(
            ["codesign", "--verify", "--deep", "--strict", str(payload)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _ulog(f"update payload codesign OK: {payload}")
    except Exception as exc:
        _ulog(f"update payload codesign FAILED: {exc}")
        raise RuntimeError(
            "Update package is damaged (codesign). "
            "Please download the DMG from hiauraai.com/download instead."
        ) from exc

    log = _log_path()
    script = work / "apply.sh"
    q = _shell_quote

    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"LOG='{q(log)}'\n"
        f"PARENT={int(parent_pid)}\n"
        f"SRC='{q(payload)}'\n"
        f"DST='{q(target)}'\n"
        f"PKG='{q(package)}'\n"
        f"WORK='{q(work)}'\n"
        "BAK=\"${DST}.backup\"\n"
        "mkdir -p \"$(dirname \"$LOG\")\"\n"
        "echo \"$(date '+%F %T') macOS updater start parent=$PARENT\" >>\"$LOG\"\n"
        "restore_bak() {\n"
        "  if [ ! -d \"$DST\" ] && [ -d \"$BAK\" ]; then\n"
        "    mv \"$BAK\" \"$DST\" || true\n"
        "    echo \"$(date '+%F %T') restored backup after failure\" >>\"$LOG\"\n"
        "  fi\n"
        "}\n"
        "_on_err() {\n"
        "  st=$?\n"
        "  echo \"$(date '+%F %T') FAILED status=$st\" >>\"$LOG\"\n"
        "  restore_bak\n"
        "}\n"
        "trap _on_err ERR\n"
        "for i in $(seq 1 300); do\n"
        "  if ! kill -0 \"$PARENT\" 2>/dev/null; then break; fi\n"
        "  sleep 0.4\n"
        "done\n"
        "sleep 1.2\n"
        "rm -rf \"$BAK\"\n"
        "if [ -d \"$DST\" ]; then\n"
        "  mv \"$DST\" \"$BAK\" || true\n"
        "fi\n"
        # ditto preserves symlinks + codesign + stapler ticket (required).\n"
        "ditto \"$SRC\" \"$DST\"\n"
        "xattr -dr com.apple.quarantine \"$DST\" 2>/dev/null || true\n"
        # Ensure main binary is executable even if something stripped mode bits.\n"
        "chmod +x \"$DST/Contents/MacOS/\"* 2>/dev/null || true\n"
        "if ! codesign --verify --deep --strict \"$DST\" >/dev/null 2>&1; then\n"
        "  echo \"$(date '+%F %T') codesign verify FAILED after ditto\" >>\"$LOG\"\n"
        "  rm -rf \"$DST\"\n"
        "  restore_bak\n"
        "  exit 1\n"
        "fi\n"
        "rm -rf \"$BAK\"\n"
        "rm -f \"$PKG\" \"${PKG}.json\"\n"
        "echo \"$(date '+%F %T') opening $DST\" >>\"$LOG\"\n"
        "if open -n \"$DST\"; then\n"
        "  echo \"$(date '+%F %T') macOS updater done\" >>\"$LOG\"\n"
        "else\n"
        "  echo \"$(date '+%F %T') open failed; app replaced at $DST\" >>\"$LOG\"\n"
        "fi\n"
        "rm -rf \"$WORK\"\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    subprocess.Popen(
        ["/bin/bash", str(script)],
        start_new_session=True,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _ulog(f"spawned macOS bash updater script={script}")


def _launch_linux_appimage_updater(package: Path, target: Path, parent_pid: int) -> None:
    work = Path(tempfile.mkdtemp(prefix="aura-appimage-update-"))
    script = work / "apply.sh"
    log = _log_path()
    q = _shell_quote

    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"LOG='{q(log)}'\n"
        f"PARENT={int(parent_pid)}\n"
        f"SRC='{q(package)}'\n"
        f"DST='{q(target)}'\n"
        "mkdir -p \"$(dirname \"$LOG\")\"\n"
        "echo \"$(date '+%F %T') AppImage updater start\" >>\"$LOG\"\n"
        "for i in $(seq 1 300); do\n"
        "  if ! kill -0 \"$PARENT\" 2>/dev/null; then break; fi\n"
        "  sleep 0.4\n"
        "done\n"
        "sleep 1\n"
        "TMP=\"${DST}.new\"\n"
        "cp \"$SRC\" \"$TMP\"\n"
        "chmod +x \"$TMP\"\n"
        "mv \"$TMP\" \"$DST\"\n"
        "rm -f \"$SRC\" \"${SRC}.json\"\n"
        "echo \"$(date '+%F %T') launching $DST\" >>\"$LOG\"\n"
        "\"$DST\" &\n"
        f"rm -rf '{q(work)}'\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    subprocess.Popen(
        ["/bin/bash", str(script)],
        start_new_session=True,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _ulog(f"spawned Linux AppImage updater script={script}")


def _windows_setup_args(install_dir: Path, log_file: Path | None = None) -> list[str]:
    """Inno Setup silent flags; keep the existing install location."""
    # Quoted DIR/LOG so paths with spaces survive Start-Process -ArgumentList.
    args = [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/FORCECLOSEAPPLICATIONS",
        f'/DIR="{install_dir}"',
    ]
    if log_file is not None:
        args.append(f'/LOG="{log_file}"')
    return args


def _run_windows_setup(package: Path, target: Path) -> None:
    """Run Inno Setup against the current install dir (sync; used by fallback helper)."""
    install_dir = target if target.is_dir() else target.parent
    log = _log_path().with_name("setup-update.log")
    args = _windows_setup_args(install_dir, log)
    _ulog(f"windows setup sync package={package} dir={install_dir} args={args}")
    # Prefer non-elevated first (DefaultDirName is LocalAppData). Elevate when needed.
    try:
        probe = install_dir / ".aura_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        needs_admin = False
    except OSError:
        needs_admin = True
    if "program files" in str(install_dir).lower():
        needs_admin = True

    if needs_admin:
        arg_lit = ", ".join(f"'{_ps_quote(a)}'" for a in args)
        ps = (
            f"$p = Start-Process -FilePath '{_ps_quote(package)}' "
            f"-ArgumentList @({arg_lit}) "
            f"-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            check=False,
        )
        if completed.returncode not in (0, None):
            raise RuntimeError(f"Windows setup failed (elevated) code={completed.returncode}")
    else:
        completed = subprocess.run([str(package), *args], check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Windows setup failed code={completed.returncode}")
    _ulog("windows setup finished OK")

def _spawn_hidden_powershell(script: Path) -> None:
    from core.win_subprocess import merge_flags

    flags = merge_flags(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        close_fds=True,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _launch_windows_exe_updater(package: Path, target: Path, parent_pid: int) -> None:
    """Wait for app exit, run Inno Setup silently into the same dir, relaunch."""
    work = Path(tempfile.mkdtemp(prefix="aura-win-setup-"))
    setup = work / package.name
    shutil.copy2(package, setup)
    install_dir = target if target.is_dir() else target.parent
    script = work / "apply.ps1"
    log = _log_path()
    setup_log = log.with_name("setup-update.log")
    pq = _ps_quote
    # Argument list as a PowerShell string array literal.
    arg_items = ", ".join(
        f"'{_ps_quote(a)}'" for a in _windows_setup_args(install_dir, setup_log)
    )
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$log = '{pq(log)}'\n"
        f"$parent = {int(parent_pid)}\n"
        f"$setup = '{pq(setup)}'\n"
        f"$dst = '{pq(install_dir)}'\n"
        f"$pkg = '{pq(package)}'\n"
        f"$work = '{pq(work)}'\n"
        f"$setupArgs = @({arg_items})\n"
        "New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null\n"
        "Add-Content $log \"$(Get-Date -Format o) Windows exe updater start\"\n"
        "for ($i=0; $i -lt 300; $i++) {\n"
        "  try { Get-Process -Id $parent -ErrorAction Stop | Out-Null; Start-Sleep -Milliseconds 400 }\n"
        "  catch { break }\n"
        "}\n"
        "Start-Sleep -Seconds 1.2\n"
        "# Extra settle: release file locks from the just-exited process.\n"
        "Get-Process -Name 'AURA','JARVIS' -ErrorAction SilentlyContinue |\n"
        "  Where-Object { $_.Id -ne $parent } |\n"
        "  Stop-Process -Force -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Seconds 0.8\n"
        "function Test-AuraWritable([string]$dir) {\n"
        "  try {\n"
        "    $t = Join-Path $dir '.aura_write_test'\n"
        "    [IO.File]::WriteAllText($t, 'ok')\n"
        "    Remove-Item -Force $t -ErrorAction SilentlyContinue\n"
        "    return $true\n"
        "  } catch { return $false }\n"
        "}\n"
        "$elevate = (-not (Test-AuraWritable $dst)) -or ($dst -match '(?i)Program Files')\n"
        "Add-Content $log \"$(Get-Date -Format o) running setup elevate=$elevate dir=$dst\"\n"
        "try {\n"
        "  if ($elevate) {\n"
        "    $p = Start-Process -FilePath $setup -ArgumentList $setupArgs -Verb RunAs -Wait -PassThru\n"
        "  } else {\n"
        "    $p = Start-Process -FilePath $setup -ArgumentList $setupArgs -Wait -PassThru\n"
        "  }\n"
        "  Add-Content $log \"$(Get-Date -Format o) setup exit=$($p.ExitCode)\"\n"
        "  if ($p.ExitCode -ne 0) { throw \"setup failed exit=$($p.ExitCode)\" }\n"
        "} catch {\n"
        "  Add-Content $log \"$(Get-Date -Format o) setup FAILED: $_\"\n"
        "}\n"
        "$exe = Join-Path $dst 'AURA.exe'\n"
        "if (-not (Test-Path $exe)) { $exe = Join-Path $dst 'JARVIS.exe' }\n"
        "if (Test-Path $exe) {\n"
        "  Add-Content $log \"$(Get-Date -Format o) launching $exe\"\n"
        "  Start-Process -FilePath $exe\n"
        "} else {\n"
        "  Add-Content $log \"$(Get-Date -Format o) AURA.exe missing after setup\"\n"
        "}\n"
        "Remove-Item -Force $pkg -ErrorAction SilentlyContinue\n"
        "Remove-Item -Force \"$pkg.json\" -ErrorAction SilentlyContinue\n"
        "Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    _spawn_hidden_powershell(script)
    _ulog(f"spawned Windows exe updater script={script}")


def _launch_windows_zip_updater(package: Path, target: Path, parent_pid: int) -> None:
    """Portable/ZIP fallback: overwrite in place; elevate when the install dir is locked down."""
    work = Path(tempfile.mkdtemp(prefix="aura-win-update-"))
    payload = _extract_app_payload(package, work)
    script = work / "apply.ps1"
    log = _log_path()
    pq = _ps_quote
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$log = '{pq(log)}'\n"
        f"$parent = {int(parent_pid)}\n"
        f"$src = '{pq(payload)}'\n"
        f"$dst = '{pq(target)}'\n"
        f"$pkg = '{pq(package)}'\n"
        f"$work = '{pq(work)}'\n"
        "New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null\n"
        "Add-Content $log \"$(Get-Date -Format o) Windows zip updater start\"\n"
        "for ($i=0; $i -lt 300; $i++) {\n"
        "  try { Get-Process -Id $parent -ErrorAction Stop | Out-Null; Start-Sleep -Milliseconds 400 }\n"
        "  catch { break }\n"
        "}\n"
        "Start-Sleep -Seconds 1.2\n"
        "Get-Process -Name 'AURA','JARVIS' -ErrorAction SilentlyContinue |\n"
        "  Stop-Process -Force -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Seconds 0.8\n"
        "function Invoke-AuraCopy {\n"
        "  New-Item -ItemType Directory -Force -Path $dst | Out-Null\n"
        "  Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force\n"
        "}\n"
        "try {\n"
        "  Invoke-AuraCopy\n"
        "  Add-Content $log \"$(Get-Date -Format o) zip copy OK\"\n"
        "} catch {\n"
        "  Add-Content $log \"$(Get-Date -Format o) zip copy failed, elevating: $_\"\n"
        "  $inner = @'\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"$src = '{pq(payload)}'\n"
        f"$dst = '{pq(target)}'\n"
        "New-Item -ItemType Directory -Force -Path $dst | Out-Null\n"
        "Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force\n"
        "'@\n"
        "  $tmp = Join-Path $env:TEMP ('aura-elevate-' + [guid]::NewGuid().ToString() + '.ps1')\n"
        "  Set-Content -Path $tmp -Value $inner -Encoding UTF8\n"
        "  $p = Start-Process -FilePath powershell -ArgumentList @(\n"
        "    '-NoProfile','-ExecutionPolicy','Bypass','-File',$tmp\n"
        "  ) -Verb RunAs -Wait -PassThru\n"
        "  Remove-Item -Force $tmp -ErrorAction SilentlyContinue\n"
        "  if ($p.ExitCode -ne 0) { throw \"elevated zip copy failed exit=$($p.ExitCode)\" }\n"
        "  Add-Content $log \"$(Get-Date -Format o) elevated zip copy OK\"\n"
        "}\n"
        "Remove-Item -Force $pkg -ErrorAction SilentlyContinue\n"
        "Remove-Item -Force \"$pkg.json\" -ErrorAction SilentlyContinue\n"
        "$exe = Join-Path $dst 'AURA.exe'\n"
        "if (-not (Test-Path $exe)) { $exe = Join-Path $dst 'JARVIS.exe' }\n"
        "if (Test-Path $exe) {\n"
        "  Add-Content $log \"$(Get-Date -Format o) launching $exe\"\n"
        "  Start-Process -FilePath $exe\n"
        "} else {\n"
        "  Add-Content $log \"$(Get-Date -Format o) AURA.exe missing after zip update\"\n"
        "}\n"
        "Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    _spawn_hidden_powershell(script)
    _ulog(f"spawned Windows PowerShell zip updater script={script}")


def _launch_command(target: Path) -> list[str]:
    os_name = normalize_os()
    if os_name == "darwin":
        app = target if target.suffix == ".app" else target.parent
        return ["open", "-n", str(app)]
    if os_name == "windows":
        if target.is_file() and target.suffix.lower() == ".exe":
            return [str(target)]
        for name in ("AURA.exe", "JARVIS.exe"):
            candidate = target / name if target.is_dir() else target
            if candidate.exists():
                return [str(candidate)]
        return [str(target / "AURA.exe")]
    if target.is_file():
        return [str(target)]
    for name in ("AURA", "JARVIS"):
        candidate = target / name
        if candidate.exists():
            return [str(candidate)]
    return [str(target / "AURA")]
