"""Double-clap wake listener for AURA.

Opens / focuses AURA when it hears two short hand claps — not music beats
or keyboard taps. Detection uses onset + crest factor + bright spectrum +
fast decay, then requires exactly two events (a third cancels the pair).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd


BASE_DIR = Path(__file__).resolve().parent.parent
MAIN = BASE_DIR / "main.py"
_VENV_PYTHON = (
    BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else BASE_DIR / ".venv" / "bin" / "python"
)
LOCAL_APP_PATH = BASE_DIR / "dist" / "AURA.app"
APPLICATIONS_APP_PATH = Path("/Applications/AURA.app")
_LEGACY_APPS = (
    BASE_DIR / "dist" / "JARVIS.app",
    Path("/Applications/JARVIS.app"),
)

_WAKE_FLAGS = ("--wake-listener", "--aura-wake")


def _wake_support_dir() -> Path:
    try:
        from core.app_paths import support_dir

        return support_dir() / "wake"
    except Exception:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "AURA" / "wake"
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Local" / "AURA" / "wake"
        return Path.home() / ".local" / "share" / "AURA" / "wake"


def _log_path() -> Path:
    # Keep the legacy macOS path so existing installs keep one continuous log.
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "mark_xxxix_wake.log"
    return _wake_support_dir() / "logs" / "aura_wake.log"


LOG = _log_path()


def _log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message}\n")


def _is_wake_cmdline(cmdline: str) -> bool:
    low = (cmdline or "").lower()
    return any(flag in low for flag in _WAKE_FLAGS)


def _subprocess_kwargs() -> dict:
    kw: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # Avoid flashing a console when the wake agent launches/focuses AURA.
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if creation:
            kw["creationflags"] = creation
    return kw


def _app_running_darwin() -> bool:
    try:
        for pattern in ("AURA.app/Contents/MacOS/AURA", "main.py"):
            result = subprocess.run(
                ["pgrep", "-fl", pattern],
                capture_output=True,
                text=True,
                timeout=2,
            )
            out = result.stdout or ""
            if not out.strip():
                continue
            if _is_wake_cmdline(out) and "AURA.app" not in pattern:
                continue
            # UI binary lines may also list the wake child — require a non-wake hit.
            lines = [ln for ln in out.splitlines() if ln.strip()]
            ui_lines = [ln for ln in lines if not _is_wake_cmdline(ln)]
            if ui_lines:
                return True
        return False
    except Exception:
        return False


def _win_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)


def _app_running_win() -> bool:
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='AURA.exe'\" | "
            "Where-Object { $_.CommandLine -notmatch '--wake-listener|--aura-wake' } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        kw: dict = {"capture_output": True, "text": True, "timeout": 6}
        flag = _win_no_window_flag()
        if flag:
            kw["creationflags"] = flag
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            **kw,
        )
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def _app_running_linux() -> bool:
    try:
        result = subprocess.run(
            ["ps", "-eo", "args="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in (result.stdout or "").splitlines():
            low = line.lower()
            if _is_wake_cmdline(line) or "wake_listener" in low:
                continue
            if "aura.appimage" in low:
                return True
            if "main.py" in low:
                return True
            # Frozen binary named AURA / aura without wake flags.
            parts = low.strip().split()
            if parts and Path(parts[0]).name in {"aura", "AURA".lower()}:
                return True
        return False
    except Exception:
        return False


def _app_running() -> bool:
    if sys.platform == "darwin":
        return _app_running_darwin()
    if sys.platform == "win32":
        return _app_running_win()
    return _app_running_linux()


def _bring_to_front_darwin() -> None:
    for app_name in ("AURA", "JARVIS"):
        try:
            subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            return
        except Exception:
            continue


def _bring_to_front_win() -> None:
    # Prefer the main window of AURA.exe; fall back to AppActivate by title.
    ps = (
        "$p = Get-Process -Name AURA -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1; "
        "if ($p) { "
        "  (New-Object -ComObject WScript.Shell).AppActivate($p.Id) | Out-Null "
        "} else { "
        "  (New-Object -ComObject WScript.Shell).AppActivate('AURA') | Out-Null "
        "}"
    )
    try:
        kw: dict = {"timeout": 6}
        kw.update(_subprocess_kwargs())
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            **kw,
        )
    except Exception:
        pass


def _bring_to_front_linux() -> None:
    for cmd in (
        ["wmctrl", "-a", "AURA"],
        ["xdotool", "search", "--name", "AURA", "windowactivate"],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                return
        except Exception:
            continue


def _bring_to_front() -> None:
    if sys.platform == "darwin":
        _bring_to_front_darwin()
    elif sys.platform == "win32":
        _bring_to_front_win()
    else:
        _bring_to_front_linux()


def _frozen_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def _windows_install_exe() -> Path | None:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    candidate = Path(local) / "Programs" / "AURA" / "AURA.exe"
    return candidate if candidate.is_file() else None


def _linux_install_candidates() -> list[Path]:
    home = Path.home()
    out: list[Path] = []
    for p in (
        home / ".local" / "bin" / "AURA",
        home / ".local" / "bin" / "aura",
        Path("/usr/local/bin/AURA"),
        Path("/usr/bin/AURA"),
    ):
        out.append(p)
    # Common AppImage drop locations.
    for folder in (home / "Applications", home / "Downloads", home / "Desktop"):
        if not folder.is_dir():
            continue
        try:
            out.extend(sorted(folder.glob("AURA*.AppImage")))
        except Exception:
            pass
    return out


def _launch_aura() -> None:
    if _app_running():
        _log("AURA is already running — bringing to front.")
        _bring_to_front()
        return

    frozen = _frozen_exe()
    if frozen is not None and frozen.is_file():
        # Wake child is the same binary — start a UI process without wake flags.
        subprocess.Popen([str(frozen)], **_subprocess_kwargs())
        _log(f"Launched AURA via frozen binary {frozen}.")
        return

    if sys.platform == "darwin":
        candidates = [
            (APPLICATIONS_APP_PATH, "/Applications"),
            (LOCAL_APP_PATH, "local dist"),
        ]
        candidates.extend((p, str(p)) for p in _LEGACY_APPS)
        for app_path, label in candidates:
            if app_path.exists():
                subprocess.Popen(
                    ["open", "-n", str(app_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _log(f"Launched AURA.app from {label}.")
                return

    if sys.platform == "win32":
        win_exe = _windows_install_exe()
        if win_exe is not None:
            subprocess.Popen([str(win_exe)], **_subprocess_kwargs())
            _log(f"Launched AURA.exe from {win_exe.parent}.")
            return

    if sys.platform.startswith("linux"):
        for path in _linux_install_candidates():
            if path.is_file() and os.access(path, os.X_OK):
                subprocess.Popen([str(path)], **_subprocess_kwargs())
                _log(f"Launched AURA from {path}.")
                return

    python = _VENV_PYTHON if _VENV_PYTHON.exists() else Path(sys.executable)
    subprocess.Popen(
        [str(python), str(MAIN)],
        cwd=str(BASE_DIR),
        **_subprocess_kwargs(),
    )
    _log("Launched AURA via python fallback.")


def _default_input_device() -> int | None:
    try:
        default = sd.default.device
        if isinstance(default, (list, tuple)):
            return int(default[0]) if default[0] is not None else None
        return int(default) if default is not None else None
    except Exception:
        return None


def _pick_input_device() -> int | None:
    """Prefer a real built-in / array mic over headphones and virtual devices."""
    try:
        devices = sd.query_devices()
    except Exception:
        return None

    if sys.platform == "darwin":
        preferred = (
            "macbook pro microphone",
            "macbook air microphone",
            "built-in microphone",
            "macbook microphone",
        )
    elif sys.platform == "win32":
        preferred = (
            "microphone array",
            "built-in",
            "internal microphone",
            "microphone (",
            "mic in",
        )
    else:
        preferred = (
            "built-in",
            "internal",
            "laptop",
            "microphone",
            "default",
        )

    skip_bits = (
        "monitor",
        "null",
        "dummy",
        "loopback",
        "stereo mix",
        "what u hear",
        "cable",
        "vb-audio",
    )
    for i, d in enumerate(devices):
        if int(d.get("max_input_channels") or 0) <= 0:
            continue
        name = str(d.get("name") or "").lower()
        if any(s in name for s in skip_bits):
            continue
        if any(p in name for p in preferred):
            _log(f"Using preferred mic: {d.get('name')}")
            return i
    return _default_input_device()


def _band_energy(mag: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> float:
    mask = (freqs >= lo) & (freqs < hi)
    if not np.any(mask):
        return 0.0
    chunk = mag[mask]
    return float(np.sum(chunk * chunk))


def _clap_features(
    samples: np.ndarray,
    sample_rate: int,
    baseline_rms: float,
) -> dict[str, float] | None:
    """Return clap-like features for one audio block, or None if silent."""
    if samples.size < 64:
        return None
    x = samples.astype(np.float32).reshape(-1)
    peak = float(np.max(np.abs(x)))
    if peak < 0.012:
        return None

    rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
    crest = peak / rms

    # Recent-energy onset: clap jumps hard above the quiet baseline.
    onset = rms / max(baseline_rms, 1e-4)

    n = x.size
    window = np.hanning(n).astype(np.float32)
    spec = np.fft.rfft(x * window)
    mag = np.abs(spec).astype(np.float32)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    low = _band_energy(mag, freqs, 60.0, 400.0)
    mid = _band_energy(mag, freqs, 400.0, 2000.0)
    high = _band_energy(mag, freqs, 2000.0, min(8000.0, sample_rate * 0.45))
    total = low + mid + high + 1e-12
    bright = (mid + high) / total
    high_ratio = high / total

    # Spectral flatness (geometric/arithmetic mean) — claps are noisy, music is tonal.
    power = (mag * mag) + 1e-12
    log_mean = float(np.mean(np.log(power)))
    arith_mean = float(np.mean(power))
    flatness = float(np.exp(log_mean) / (arith_mean + 1e-12))

    # Score blends brightness + impulsive onset. Pure loudness alone is not enough.
    score = peak * (0.35 + 0.65 * bright) * min(crest / 4.0, 1.35) * min(onset / 6.0, 1.4)

    return {
        "score": score,
        "rms": rms,
        "peak": peak,
        "crest": crest,
        "onset": onset,
        "bright": bright,
        "high_ratio": high_ratio,
        "flatness": flatness,
    }


def _is_clap_candidate(f: dict[str, float], threshold: float) -> bool:
    """Clap gate — impulsive + bright; rejects soft keys and bass-heavy music."""
    if f["score"] < threshold:
        return False
    # Hand claps: sharp spike, bright spectrum, strong onset vs quiet baseline.
    if f["crest"] < 2.8:
        return False
    if f["bright"] < 0.48:
        return False
    if f["high_ratio"] < 0.14:
        return False
    if f["onset"] < 3.0:
        return False
    if f["flatness"] < 0.015:
        return False
    # Absolute floor so tiny desk taps / soft keys rarely pass.
    if f["peak"] < 0.05:
        return False
    return True


def listen_for_double_clap(
    threshold: float,
    min_gap: float,
    max_gap: float,
    cooldown: float,
    sample_rate: int,
    block_ms: int,
) -> None:
    blocksize = max(256, int(sample_rate * block_ms / 1000))
    device = _pick_input_device()

    clap_times: list[float] = []
    last_trigger = 0.0
    last_clap = 0.0
    pending_confirm_until = 0.0
    baseline = 0.004
    recent_rms: deque[float] = deque(maxlen=24)
    # Ignore re-triggers while the clap ring/echo settles.
    refractory_until = 0.0
    last_health = 0.0
    max_peak_30s = 0.0
    max_peak_reset = time.monotonic()
    sustained_blocks = 0

    _log(
        "Wake listener started "
        f"(clap-filter, threshold={threshold}, min_gap={min_gap}, "
        f"max_gap={max_gap}, cooldown={cooldown})."
    )

    with sd.InputStream(
        device=device,
        channels=1,
        samplerate=sample_rate,
        dtype="float32",
        blocksize=blocksize,
    ) as stream:
        while True:
            indata, _overflowed = stream.read(blocksize)
            now = time.monotonic()
            samples = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)

            rms_now = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)) + 1e-12)
            peak_now = float(np.max(np.abs(samples)))
            recent_rms.append(rms_now)
            # Quiet baseline from lower half of recent blocks (ignores spikes).
            if recent_rms:
                arr = np.array(recent_rms, dtype=np.float32)
                baseline = float(max(np.percentile(arr, 35), 1e-4))

            if now - max_peak_reset >= 30.0:
                max_peak_30s = 0.0
                max_peak_reset = now
            max_peak_30s = max(max_peak_30s, peak_now)

            if now - last_health >= 30.0:
                _log(
                    f"Audio health: peak={peak_now:.3f} rms={rms_now:.3f} "
                    f"max30s={max_peak_30s:.3f}"
                )
                last_health = now

            # Drop a lone first clap that aged out of the pair window.
            if clap_times and len(clap_times) == 1 and now - clap_times[0] > max_gap:
                _log("First clap expired — clap again twice, closer together.")
                clap_times.clear()
                pending_confirm_until = 0.0

            # Confirm double-clap after a short quiet gap (a 3rd hit cancels).
            if pending_confirm_until and now >= pending_confirm_until:
                if len(clap_times) == 2 and now - last_trigger >= cooldown:
                    last_trigger = now
                    clap_times.clear()
                    pending_confirm_until = 0.0
                    _log("Double clap confirmed — launching AURA.")
                    _launch_aura()
                elif len(clap_times) == 2 and now - last_trigger < cooldown:
                    _log("Double clap ignored — cooldown active.")
                    clap_times.clear()
                    pending_confirm_until = 0.0
                else:
                    pending_confirm_until = 0.0

            feats = _clap_features(samples, sample_rate, baseline)
            if feats is None:
                sustained_blocks = 0
                continue

            # Music/speech linger: many low-crest loud blocks after a hit.
            # Do NOT cancel on the clap's own short ring (first ~150ms).
            if clap_times and now - last_clap > 0.16:
                if feats["rms"] > baseline * 10.0 and feats["crest"] < 2.2:
                    sustained_blocks += 1
                else:
                    sustained_blocks = 0
                if sustained_blocks >= 5:
                    _log("Rejected sustained sound after candidate (likely music).")
                    clap_times.clear()
                    pending_confirm_until = 0.0
                    sustained_blocks = 0
                    continue
            else:
                sustained_blocks = 0

            if now < refractory_until:
                continue
            # Already have a double-clap waiting to confirm — ignore echo/ring.
            if pending_confirm_until and len(clap_times) >= 2:
                continue
            if not _is_clap_candidate(feats, threshold):
                continue
            if now - last_clap < min_gap:
                continue

            last_clap = now
            # Longer refractory after loud claps so room echo isn't clap #3.
            refractory_until = now + 0.22
            prev_n = len(clap_times)
            clap_times = [t for t in clap_times if now - t <= max_gap]
            if prev_n and not clap_times:
                _log("Previous clap aged out of window before this one.")
            clap_times.append(now)
            gap = (clap_times[-1] - clap_times[-2]) if len(clap_times) >= 2 else 0.0
            _log(
                "Clap candidate "
                f"score={feats['score']:.3f} peak={feats['peak']:.3f} "
                f"crest={feats['crest']:.2f} bright={feats['bright']:.2f} "
                f"onset={feats['onset']:.1f} flat={feats['flatness']:.3f} "
                f"count={len(clap_times)} gap={gap:.2f}s."
            )

            if len(clap_times) > 2:
                # Keep the first pair; extra hits are almost always echo, not music.
                clap_times = clap_times[:2]
                pending_confirm_until = now + 0.12
                continue

            if len(clap_times) == 2:
                # Confirm quickly; ignore further impulses until then.
                pending_confirm_until = now + 0.14


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA double-clap wake listener.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(os.getenv("MARK_WAKE_THRESHOLD", "0.08")),
    )
    # Natural double-clap is often ~0.2–2s apart (not a drum roll).
    parser.add_argument("--min-gap", type=float, default=0.12)
    parser.add_argument("--max-gap", type=float, default=2.40)
    parser.add_argument("--cooldown", type=float, default=8.0)
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--block-ms", type=int, default=30)
    parser.add_argument("--restart-delay", type=float, default=3.0)
    args = parser.parse_args()

    while True:
        try:
            listen_for_double_clap(
                threshold=args.threshold,
                min_gap=args.min_gap,
                max_gap=args.max_gap,
                cooldown=args.cooldown,
                sample_rate=args.sample_rate,
                block_ms=args.block_ms,
            )
        except KeyboardInterrupt:
            _log("Wake listener stopped by keyboard interrupt.")
            return
        except Exception as e:
            _log(
                f"Wake listener crashed: {e}. "
                f"Restarting audio stream in {args.restart_delay:.1f}s."
            )
            time.sleep(args.restart_delay)


if __name__ == "__main__":
    main()
