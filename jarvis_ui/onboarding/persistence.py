"""Persist onboarding completion so it never shows again."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _state_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path.home() / "Library" / "Application Support" / "AURA"
    else:
        base = Path(__file__).resolve().parents[2] / "runtime"
    base.mkdir(parents=True, exist_ok=True)
    return base / "onboarding.json"


def is_onboarding_done() -> bool:
    path = _state_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("completed"))
    except Exception:
        return False


def mark_onboarding_done() -> None:
    path = _state_path()
    path.write_text(
        json.dumps({"completed": True, "version": 1}, indent=2) + "\n",
        encoding="utf-8",
    )


def reset_onboarding_for_preview() -> None:
    """Dev helper — force show onboarding again."""
    path = _state_path()
    if path.exists():
        path.unlink()
