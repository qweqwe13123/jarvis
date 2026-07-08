"""Local image generation utilities backed by FLUX in project venv."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
VENV_PY = BASE_DIR / ".venv" / "bin" / "python"
RUNNER = BASE_DIR / "core" / "flux_generate_runner.py"
OUT_DIR = BASE_DIR / "runtime" / "generated_images"
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class LocalImageError(RuntimeError):
    pass


def _runner_cmd(prompt: str, output_path: Path, steps: int, guidance: float) -> list[str]:
    py = str(VENV_PY if VENV_PY.exists() else "python3")
    return [py, str(RUNNER), prompt, str(output_path), str(steps), str(guidance)]


def generate_flux_image(prompt: str, steps: int = 4, guidance: float = 0.0, timeout_sec: int = 900) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"flux_{stamp}.png"
    cmd = _runner_cmd(prompt, out, steps, guidance)
    env = os.environ.copy()
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    except Exception:
        cfg = {}
    if cfg.get("hf_token") and not env.get("HF_TOKEN"):
        env["HF_TOKEN"] = str(cfg.get("hf_token"))
    configured_model = str(cfg.get("flux_model_id") or env.get("FLUX_MODEL_ID") or "black-forest-labs/FLUX.1-schnell")
    env["FLUX_MODEL_ID"] = configured_model
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, env=env)
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        payload = json.loads(raw.splitlines()[-1] if raw else "{}")
    except Exception:
        payload = {"ok": False, "error": raw or f"runner exit code {proc.returncode}"}
    if proc.returncode != 0 or not payload.get("ok"):
        err = payload.get("error") or "image generation failed"
        if "gated repo" in err.lower() or "restricted" in err.lower() or "401" in err:
            raise LocalImageError(
                "FLUX weights are gated on Hugging Face. Open Settings, add a valid "
                "HuggingFace token (hf_token), and accept the FLUX model license "
                "for black-forest-labs/FLUX.1-schnell."
            )
        raise LocalImageError(err)
    path = payload.get("path")
    if not path or not Path(path).exists():
        raise LocalImageError("image file not created")
    return str(Path(path))


def ensure_flux_available() -> None:
    """Warm up FLUX model download/cache by running a tiny generation."""
    generate_flux_image("Minimal abstract gradient wallpaper", steps=1, guidance=0.0, timeout_sec=1200)
