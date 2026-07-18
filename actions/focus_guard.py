"""Focus Guard tool — start/stop distraction watchdog via Live function calls."""
from __future__ import annotations

from core.focus_guard import start_guard, status_text, stop_guard


def _parse_one_shot(params: dict) -> bool:
    """Default True. Explicit false/0/no/repeat → keep watching after first nudge."""
    raw = params.get("one_shot")
    if raw is None:
        # Alternate phrasing from the model
        mode = str(params.get("mode") or "").strip().lower()
        if mode in ("repeat", "keep", "loop", "continuous", "каждый", "каждый раз"):
            return False
        return True
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("0", "false", "no", "off", "repeat", "keep", "loop"):
        return False
    return True


def focus_guard(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()
    language = (params.get("language") or "auto").strip().lower()[:16] or "auto"

    if action in ("on", "enable", "start", "watch", "guard"):
        goal = (
            params.get("goal")
            or params.get("task")
            or params.get("note")
            or ""
        ).strip()
        message = (params.get("message") or "").strip()
        try:
            idle = float(
                params.get("idle_minutes")
                or params.get("minutes")
                or params.get("delay_minutes")
                or 5
            )
        except (TypeError, ValueError):
            idle = 5.0
        one_shot = _parse_one_shot(params)

        state = start_guard(
            goal=goal or "stay focused",
            idle_minutes=idle,
            language=language,
            message=message,
            one_shot=one_shot,
        )
        mins = state["idle_minutes"]
        g = state["goal"]
        if one_shot:
            result = (
                f"Focus Guard on. I'll nudge you once after ~{mins:g} min of "
                f"distraction about “{g}”, then turn myself off. "
                f"Say “stop watching” anytime to cancel."
            )
        else:
            result = (
                f"Focus Guard on (repeat). I'll keep nudging after {mins:g} min "
                f"away from “{g}” until you turn it off."
            )
    elif action in ("off", "disable", "stop", "cancel"):
        stop_guard()
        result = "Focus Guard off. I won't watch for distractions anymore."
    elif action == "status":
        result = status_text()
    else:
        result = "Unknown focus_guard action. Use start, stop, or status."

    print(f"[FocusGuard] {result}")
    if player:
        try:
            player.write_log(f"[FocusGuard] {result[:140]}")
        except Exception:
            pass
        try:
            if action in ("on", "enable", "start", "watch", "guard"):
                player.add_activity("Focus Guard", result)
            elif action in ("off", "disable", "stop", "cancel"):
                player.add_activity("Focus Guard", "Off")
        except Exception:
            pass
    return result
