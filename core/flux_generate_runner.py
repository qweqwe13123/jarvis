"""Standalone FLUX runner executed via project venv python.

This process isolates heavy imports (torch/diffusers) from the main app.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import torch
from diffusers import FluxPipeline


def _device_and_dtype():
    if torch.backends.mps.is_available():
        return "mps", torch.float16
    if torch.cuda.is_available():
        return "cuda", torch.float16
    return "cpu", torch.float32


def generate(prompt: str, out_path: str, steps: int = 4, guidance: float = 0.0) -> str:
    device, dtype = _device_and_dtype()
    model_id = os.getenv("FLUX_MODEL_ID", "black-forest-labs/FLUX.1-schnell")
    token = os.getenv("HF_TOKEN") or None
    pipe = FluxPipeline.from_pretrained(model_id, torch_dtype=dtype, token=token)
    if device != "cpu":
        pipe = pipe.to(device)
    image = pipe(
        prompt=prompt,
        num_inference_steps=steps,
        guidance_scale=guidance,
        max_sequence_length=256,
    ).images[0]
    p = Path(out_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    image.save(p)
    return str(p)


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: flux_generate_runner.py <prompt> <output_path> [steps] [guidance]"}))
        return 2
    prompt = sys.argv[1]
    out_path = sys.argv[2]
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    guidance = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    try:
        path = generate(prompt, out_path, steps=steps, guidance=guidance)
        print(json.dumps({"ok": True, "path": path}))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
