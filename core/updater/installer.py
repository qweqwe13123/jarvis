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


def launch_updater(
    package: Path,
    parent_pid: int,
    *,
    expected_version: str = "",
) -> None:
    """
    Start a detached updater that can replace the running app.

    On macOS we MUST NOT run the replacement from inside AURA.app itself —
    that aborts when the bundle is swapped. Instead we extract to /tmp and
    run an external bash script (ditto + open).
    """
    target = install_dir()
    os_name = normalize_os()
    _ulog(
        f"launch_updater package={package} target={target} "
        f"parent={parent_pid} expected={expected_version or '-'}"
    )
    _mark_in_app_update()

    if os_name == "darwin" and package.suffix.lower() == ".zip":
        _launch_macos_zip_updater(package, target, parent_pid)
        return
    if os_name == "linux" and package.name.lower().endswith(".appimage"):
        _launch_linux_appimage_updater(package, target, parent_pid)
        return
    if os_name == "windows" and package.suffix.lower() == ".zip":
        _launch_windows_zip_updater(
            package, target, parent_pid, expected_version=expected_version
        )
        return
    if os_name == "windows" and package.suffix.lower() == ".exe":
        _launch_windows_exe_updater(
            package, target, parent_pid, expected_version=expected_version
        )
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


def _windows_kill_install_processes_ps(install_var: str = "$dst") -> str:
    """PowerShell snippet: stop AURA + QtWebEngine processes under *install_var*."""
    return f"""
function Stop-AuraInstallProcesses {{
  param([string]$InstallDir)
  $prefix = $InstallDir.TrimEnd('\\')
  if (-not $prefix) {{ return }}
  for ($pass = 0; $pass -lt 3; $pass++) {{
    Get-Process -ErrorAction SilentlyContinue | Where-Object {{
      $_.Path -and ($_.Path -like ($prefix + '*'))
    }} | Stop-Process -Force -ErrorAction SilentlyContinue
    foreach ($name in @('AURA','JARVIS','QtWebEngineProcess')) {{
      Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object {{
        -not $_.Path -or ($_.Path -like ($prefix + '*'))
      }} | Stop-Process -Force -ErrorAction SilentlyContinue
    }}
    Start-Sleep -Milliseconds 600
  }}
}}
Stop-AuraInstallProcesses -InstallDir {install_var}
"""


def _windows_setup_args(install_dir: Path, log_file: Path | None = None) -> list[str]:
    """Inno Setup silent flags; keep the existing install location."""
    # Do NOT embed extra quotes in /DIR= — cmd.exe quoting handles spaces.
    args = [
        "/SP-",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/FORCECLOSEAPPLICATIONS",
        "/NOICONS",
        f"/DIR={install_dir}",
    ]
    if log_file is not None:
        args.append(f"/LOG={log_file}")
    return args


def _run_windows_setup(package: Path, target: Path) -> None:
    """Run Inno Setup against the current install dir (sync; used by fallback helper)."""
    install_dir = target if target.is_dir() else target.parent
    log = _log_path().with_name("setup-update.log")
    args = _windows_setup_args(install_dir, log)
    _ulog(f"windows setup sync package={package} dir={install_dir} args={args}")
    try:
        probe = install_dir / ".aura_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        needs_admin = False
    except OSError:
        needs_admin = True
    if "program files" in str(install_dir).lower():
        needs_admin = True

    # cmd /c waits only for setup.exe itself — not the whole process tree
    # (Start-Process -Wait can hang forever if a child stays alive).
    cmdline = subprocess.list2cmdline([str(package), *args])
    if needs_admin:
        ps = (
            f"$p = Start-Process -FilePath 'cmd.exe' "
            f"-ArgumentList @('/c', '{_ps_quote(cmdline)}') "
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
        completed = subprocess.run(["cmd.exe", "/c", cmdline], check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Windows setup failed code={completed.returncode}")
    _ulog("windows setup finished OK")


def _windows_pending_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) / "AURA" if local else Path.home() / "AppData" / "Local" / "AURA"
    pending = base / "updates" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    return pending


def _write_ps1(path: Path, body: str) -> None:
    """PowerShell 5.1 needs a UTF-8 BOM or non-ASCII paths break silently."""
    path.write_bytes(body.encode("utf-8-sig"))


def _spawn_hidden_powershell(script: Path) -> None:
    """Detach updater so it survives AURA exit (job object + no console)."""
    from core.win_subprocess import merge_flags

    # CREATE_BREAKAWAY_FROM_JOB is critical: otherwise the updater dies with the
    # parent when Windows Job Objects are in play (common with packaged apps).
    create_breakaway = 0x01000000
    flags = merge_flags(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        | create_breakaway
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
        stdin=subprocess.DEVNULL,
    )


def _launch_windows_exe_updater(
    package: Path,
    target: Path,
    parent_pid: int,
    *,
    expected_version: str = "",
) -> None:
    """Wait for app exit, run Inno silently into the same dir, verify, relaunch."""
    pending = _windows_pending_dir()
    setup = pending / package.name
    shutil.copy2(package, setup)
    install_dir = target if target.is_dir() else target.parent
    script = pending / f"apply-{os.getpid()}.ps1"
    log = _log_path()
    setup_log = log.with_name("setup-update.log")
    pq = _ps_quote
    expected = (expected_version or "").strip()
    cmdline = subprocess.list2cmdline(
        [str(setup), *_windows_setup_args(install_dir, setup_log)]
    )

    body = f"""$ErrorActionPreference = 'Stop'
$log = '{pq(log)}'
$parent = {int(parent_pid)}
$setup = '{pq(setup)}'
$dst = '{pq(install_dir)}'
$pkg = '{pq(package)}'
$scriptPath = '{pq(script)}'
$expected = '{pq(expected)}'
$cmdline = '{pq(cmdline)}'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Write-AuraLog([string]$msg) {{
  Add-Content -Path $log -Value ("$(Get-Date -Format o) " + $msg)
}}
Write-AuraLog "Windows exe updater start parent=$parent dst=$dst expected=$expected"
for ($i = 0; $i -lt 450; $i++) {{
  try {{ Get-Process -Id $parent -ErrorAction Stop | Out-Null; Start-Sleep -Milliseconds 400 }}
  catch {{ break }}
}}
Start-Sleep -Seconds 2.5
{_windows_kill_install_processes_ps("$dst")}
Start-Sleep -Seconds 1
function Test-AuraWritable([string]$dir) {{
  try {{
    $t = Join-Path $dir '.aura_write_test'
    [IO.File]::WriteAllText($t, 'ok')
    Remove-Item -Force $t -ErrorAction SilentlyContinue
    return $true
  }} catch {{ return $false }}
}}
$elevate = (-not (Test-AuraWritable $dst)) -or ($dst -match '(?i)Program Files')
Write-AuraLog "running setup elevate=$elevate"
$ok = $false
$exitCode = -1
try {{
  if ($elevate) {{
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $cmdline) -Verb RunAs -Wait -PassThru
    $exitCode = $p.ExitCode
  }} else {{
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $cmdline) -Wait -PassThru
    $exitCode = $p.ExitCode
  }}
  Write-AuraLog "setup exit=$exitCode"
  if ($exitCode -ne 0) {{ throw "setup failed exit=$exitCode" }}
  $ok = $true
}} catch {{
  Write-AuraLog "setup FAILED: $_"
  $ok = $false
}}
$exe = Join-Path $dst 'AURA.exe'
if (-not (Test-Path $exe)) {{ $exe = Join-Path $dst 'JARVIS.exe' }}
if ($ok -and (Test-Path $exe)) {{
  try {{
    $ageMin = ((Get-Date) - (Get-Item $exe).LastWriteTime).TotalMinutes
    Write-AuraLog "exe mtime age_min=$ageMin"
    if ($ageMin -gt 20) {{
      Write-AuraLog "exe not freshly written — treating setup as failed"
      $ok = $false
    }}
  }} catch {{
    Write-AuraLog "mtime check skipped: $_"
  }}
}}
if ($ok -and (Test-Path $exe) -and $expected) {{
  try {{
    $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($exe)
    $pv = ([string]$vi.ProductVersion).Trim()
    $fv = ([string]$vi.FileVersion).Trim()
    Write-AuraLog "version check product=$pv file=$fv expected=$expected"
    if (($pv -or $fv) -and ($pv -notlike ($expected + '*')) -and ($fv -notlike ($expected + '*'))) {{
      Write-AuraLog "version mismatch after setup"
      $ok = $false
    }}
  }} catch {{
    Write-AuraLog "version check skipped: $_"
  }}
}}
if ($ok -and (Test-Path $exe)) {{
  Write-AuraLog "launching $exe"
  Start-Process -FilePath $exe -WorkingDirectory $dst
}} else {{
  Write-AuraLog "update aborted; not relaunching stale build"
  try {{
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show(
      "AURA could not finish installing the update.`n`nPlease install the latest build from hiauraai.com/download`n`nLog: $log",
      "AURA Update Failed",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
  }} catch {{
    Write-AuraLog "message box failed: $_"
  }}
}}
Remove-Item -Force $pkg -ErrorAction SilentlyContinue
Remove-Item -Force "$pkg.json" -ErrorAction SilentlyContinue
Remove-Item -Force $setup -ErrorAction SilentlyContinue
Remove-Item -Force $scriptPath -ErrorAction SilentlyContinue
"""
    _write_ps1(script, body)
    _spawn_hidden_powershell(script)
    _ulog(f"spawned Windows exe updater script={script}")


def _launch_windows_zip_updater(
    package: Path,
    target: Path,
    parent_pid: int,
    *,
    expected_version: str = "",
) -> None:
    """Cursor-style: quit app, extract zip externally, robocopy into install dir."""
    pending = _windows_pending_dir()
    staged = pending / package.name
    if staged.resolve() != package.resolve():
        shutil.copy2(package, staged)
    pkg = staged
    work = pending / f"work-{os.getpid()}"
    script = pending / f"apply-zip-{os.getpid()}.ps1"
    log = _log_path()
    pq = _ps_quote
    expected = (expected_version or "").strip()
    body = f"""$ErrorActionPreference = 'Stop'
$log = '{pq(log)}'
$parent = {int(parent_pid)}
$pkg = '{pq(pkg)}'
$dst = '{pq(target)}'
$work = '{pq(work)}'
$scriptPath = '{pq(script)}'
$expected = '{pq(expected)}'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Write-AuraLog([string]$msg) {{
  Add-Content -Path $log -Value ("$(Get-Date -Format o) " + $msg)
}}
Write-AuraLog "Windows zip updater start pkg=$pkg dst=$dst expected=$expected"
for ($i = 0; $i -lt 450; $i++) {{
  try {{ Get-Process -Id $parent -ErrorAction Stop | Out-Null; Start-Sleep -Milliseconds 400 }}
  catch {{ break }}
}}
Start-Sleep -Seconds 2.5
{_windows_kill_install_processes_ps("$dst")}
Start-Sleep -Seconds 1
$ok = $false
try {{
  if (Test-Path $work) {{ Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }}
  $extract = Join-Path $work 'extract'
  New-Item -ItemType Directory -Force -Path $extract | Out-Null
  Write-AuraLog "extracting zip"
  $usedTar = $false
  try {{
    & tar -xf $pkg -C $extract 2>$null
    if ($LASTEXITCODE -eq 0) {{ $usedTar = $true }}
  }} catch {{}}
  if (-not $usedTar) {{
    Expand-Archive -Path $pkg -DestinationPath $extract -Force
  }}
  $src = $extract
  if (-not (Test-Path (Join-Path $extract 'AURA.exe')) -and -not (Test-Path (Join-Path $extract 'JARVIS.exe')) {{
    $child = Get-ChildItem -Path $extract -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($child) {{ $src = $child.FullName }}
  }}
  if (-not (Test-Path (Join-Path $src 'AURA.exe')) -and -not (Test-Path (Join-Path $src 'JARVIS.exe')) {{
    throw "update zip missing AURA.exe under $src"
  }}
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  Write-AuraLog "robocopy from $src to $dst"
  & robocopy $src $dst /E /R:2 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np
  if ($LASTEXITCODE -ge 8) {{ throw "robocopy failed exit=$LASTEXITCODE" }}
  Write-AuraLog "robocopy OK exit=$LASTEXITCODE"
  $ok = $true
}} catch {{
  Write-AuraLog "zip apply failed, trying elevated copy: $_"
  try {{
    $inner = @"
`$ErrorActionPreference = 'Stop'
`$pkg = '{pq(pkg)}'
`$dst = '{pq(target)}'
`$work = '{pq(work)}'
`$extract = Join-Path `$work 'extract'
if (Test-Path `$work) {{ Remove-Item -Recurse -Force `$work -ErrorAction SilentlyContinue }}
New-Item -ItemType Directory -Force -Path `$extract | Out-Null
try {{ & tar -xf `$pkg -C `$extract }} catch {{ Expand-Archive -Path `$pkg -DestinationPath `$extract -Force }}
`$src = `$extract
if (-not (Test-Path (Join-Path `$extract 'AURA.exe'))) {{
  `$child = Get-ChildItem -Path `$extract -Directory | Select-Object -First 1
  if (`$child) {{ `$src = `$child.FullName }}
}}
New-Item -ItemType Directory -Force -Path `$dst | Out-Null
& robocopy `$src `$dst /E /R:2 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np
if (`$LASTEXITCODE -ge 8) {{ exit `$LASTEXITCODE }}
exit 0
"@
    $tmp = Join-Path $env:TEMP ('aura-elevate-' + [guid]::NewGuid().ToString() + '.ps1')
    [IO.File]::WriteAllText($tmp, $inner, (New-Object System.Text.UTF8Encoding $true))
    try {{
      $p = Start-Process -FilePath powershell -ArgumentList @(
        '-NoProfile','-ExecutionPolicy','Bypass','-File',$tmp
      ) -Verb RunAs -Wait -PassThru
      if ($p.ExitCode -ne 0) {{ throw "elevated robocopy failed exit=$($p.ExitCode)" }}
      Write-AuraLog "elevated robocopy OK"
      $ok = $true
    }} finally {{
      Remove-Item -Force $tmp -ErrorAction SilentlyContinue
    }}
  }} catch {{
    Write-AuraLog "elevated apply FAILED: $_"
    $ok = $false
  }}
}}
$exe = Join-Path $dst 'AURA.exe'
if (-not (Test-Path $exe)) {{ $exe = Join-Path $dst 'JARVIS.exe' }}
if ($ok -and (Test-Path $exe)) {{
  try {{
    $ageMin = ((Get-Date) - (Get-Item $exe).LastWriteTime).TotalMinutes
    Write-AuraLog "exe mtime age_min=$ageMin"
    if ($ageMin -gt 30) {{
      Write-AuraLog "exe not freshly written — treating update as failed"
      $ok = $false
    }}
  }} catch {{
    Write-AuraLog "mtime check skipped: $_"
  }}
}}
if ($ok -and (Test-Path $exe) -and $expected) {{
  try {{
    $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($exe)
    $pv = ([string]$vi.ProductVersion).Trim()
    $fv = ([string]$vi.FileVersion).Trim()
    Write-AuraLog "version check product=$pv file=$fv expected=$expected"
    # PyInstaller builds may omit version metadata — only fail on explicit mismatch.
    if ($pv -and ($pv -notlike ($expected + '*')) -and ($fv -and ($fv -notlike ($expected + '*')))) {{
      Write-AuraLog "version mismatch after update (non-fatal if metadata empty)"
    }}
  }} catch {{
    Write-AuraLog "version check skipped: $_"
  }}
}}
if ($ok -and (Test-Path $exe)) {{
  Write-AuraLog "launching $exe"
  Start-Process -FilePath $exe -WorkingDirectory $dst
}} else {{
  Write-AuraLog "zip update aborted; not relaunching stale build"
  try {{
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show(
      "AURA could not finish installing the update.`n`nPlease install the latest build from hiauraai.com/download`n`nLog: $log",
      "AURA Update Failed",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
  }} catch {{}}
}}
Remove-Item -Force $pkg -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
Remove-Item -Force $scriptPath -ErrorAction SilentlyContinue
"""
    _write_ps1(script, body)
    _spawn_hidden_powershell(script)
    _ulog(f"spawned Windows zip updater script={script} pkg={pkg}")



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
