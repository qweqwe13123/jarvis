from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd


BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = BASE_DIR / ".venv" / "bin" / "python"
MAIN = BASE_DIR / "main.py"
LOCAL_APP_PATH = BASE_DIR / "dist" / "JARVIS.app"
APPLICATIONS_APP_PATH = Path("/Applications/JARVIS.app")
LOG = Path.home() / "Library" / "Logs" / "mark_xxxix_wake.log"


def _log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message}\n")


def _jarvis_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "main.py"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return "main.py" in result.stdout
    except Exception:
        return False


def _launch_jarvis() -> None:
    if _jarvis_running():
        _log("Jarvis is already running.")
        try:
            subprocess.run(
                ["osascript", "-e", 'tell application "Python" to activate'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
        except Exception:
            pass
        return

    for app_path, label in (
        (LOCAL_APP_PATH, "local dist"),
        (APPLICATIONS_APP_PATH, "/Applications"),
    ):
        if app_path.exists():
            subprocess.Popen(["open", "-n", str(app_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _log(f"Launched Jarvis.app from {label}.")
            return

    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    subprocess.Popen(
        [str(python), str(MAIN)],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _log("Launched Jarvis via python fallback.")


def _audio_level(indata: np.ndarray) -> tuple[float, float, float]:
    if indata.size == 0:
        return 0.0, 0.0, 0.0
    samples = indata.astype(np.float32)
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    # Claps are short transients: peak catches them better than RMS alone.
    score = max(rms, peak * 0.28)
    return score, rms, peak


def listen_for_double_clap(
    threshold: float,
    min_gap: float,
    max_gap: float,
    cooldown: float,
    sample_rate: int,
    block_ms: int,
) -> None:
    blocksize = max(256, int(sample_rate * block_ms / 1000))
    clap_times: list[float] = []
    last_trigger = 0.0
    last_clap = 0.0

    _log(
        "Wake listener started "
        f"(threshold={threshold}, min_gap={min_gap}, max_gap={max_gap}, cooldown={cooldown})."
    )

    with sd.InputStream(
        channels=1,
        samplerate=sample_rate,
        dtype="float32",
        blocksize=blocksize,
    ) as stream:
        while True:
            indata, _overflowed = stream.read(blocksize)
            now = time.monotonic()
            level, rms, peak = _audio_level(indata)

            if level < threshold or now - last_clap < min_gap:
                continue

            last_clap = now
            clap_times = [t for t in clap_times if now - t <= max_gap]
            clap_times.append(now)
            _log(
                f"Clap detected, score={level:.3f}, rms={rms:.3f}, "
                f"peak={peak:.3f}, count={len(clap_times)}."
            )

            if len(clap_times) >= 2 and now - last_trigger >= cooldown:
                last_trigger = now
                clap_times.clear()
                _launch_jarvis()


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS double-clap wake listener.")
    parser.add_argument("--threshold", type=float, default=float(os.getenv("MARK_WAKE_THRESHOLD", "0.12")))
    parser.add_argument("--min-gap", type=float, default=0.08)
    parser.add_argument("--max-gap", type=float, default=2.8)
    parser.add_argument("--cooldown", type=float, default=8.0)
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--block-ms", type=int, default=45)
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
            _log(f"Wake listener crashed: {e}. Restarting audio stream in {args.restart_delay:.1f}s.")
            time.sleep(args.restart_delay)


if __name__ == "__main__":
    main()
