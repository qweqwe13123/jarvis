"""One free desktop preview turn, then Pro gate (Cursor-style).

After onboarding the user may use chat or voice once. The first successful
assistant reply that follows a user turn marks the preview as used; further
use requires an active Pro subscription.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from jarvis_ui.paths import support_dir

_LOCK = threading.Lock()
_STATE_PATH = support_dir() / "preview_access.json"

# In-process: waiting for the assistant reply that will consume the preview.
_pending_user_turn = False


def _default() -> dict[str, Any]:
    return {
        "free_preview_used": False,
        "consumed_at": None,
        "version": 1,
    }


def _load() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return _default()
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default()
        out = _default()
        out.update(data)
        return out
    except Exception:
        return _default()


def _save(data: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def is_pro() -> bool:
    try:
        from jarvis_ui.user_account import has_active_subscription

        return bool(has_active_subscription())
    except Exception:
        return False


def free_preview_used() -> bool:
    with _LOCK:
        return bool(_load().get("free_preview_used"))


def can_start_turn() -> bool:
    """True if the user may send chat / speak a new request."""
    if is_pro():
        return True
    with _LOCK:
        return not bool(_load().get("free_preview_used"))


def note_user_turn() -> bool:
    """Mark that a user started a turn. Returns False if blocked (show Pro gate)."""
    global _pending_user_turn
    if is_pro():
        _pending_user_turn = True
        return True
    with _LOCK:
        data = _load()
        if data.get("free_preview_used"):
            _pending_user_turn = False
            return False
        _pending_user_turn = True
        return True


def note_assistant_success(text: str = "") -> bool:
    """
    Call when Jarvis delivers a real reply after a user turn.

    Returns True if the free preview was just consumed (caller should show gate).
    """
    global _pending_user_turn
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        return False
    low = cleaned.lower()
    if low.startswith(("err:", "sys:", "error", "agent error")):
        return False

    if is_pro():
        _pending_user_turn = False
        return False

    with _LOCK:
        if not _pending_user_turn:
            return False
        _pending_user_turn = False
        data = _load()
        if data.get("free_preview_used"):
            return True  # already consumed — still nudge gate
        import time

        data["free_preview_used"] = True
        data["consumed_at"] = time.time()
        _save(data)
        return True


def reset_preview_for_tests() -> None:
    """Dev helper — restore one free turn."""
    global _pending_user_turn
    with _LOCK:
        _pending_user_turn = False
        _save(_default())
