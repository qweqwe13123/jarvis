"""Focus Guard tool — start/stop distraction watchdog via Live function calls."""
from __future__ import annotations

from core.focus_guard import start_guard, status_text, stop_guard


def focus_guard(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = (params.get("action") or "status").lower().strip()

    if action in ("on", "enable", "start", "watch", "guard"):
        goal = (
            params.get("goal")
            or params.get("task")
            or params.get("note")
            or ""
        ).strip()
        message = (params.get("message") or "").strip()
        language = (params.get("language") or "ru").strip().lower()[:2] or "ru"
        try:
            idle = float(
                params.get("idle_minutes")
                or params.get("minutes")
                or params.get("delay_minutes")
                or 5
            )
        except (TypeError, ValueError):
            idle = 5.0

        state = start_guard(
            goal=goal or "продолжить работу",
            idle_minutes=idle,
            language=language,
            message=message,
        )
        result = (
            f"Focus Guard on. I'll watch for distractions and nudge you after "
            f"{state['idle_minutes']:g} min. Goal: {state['goal']}."
        )
        if language == "ru":
            result = (
                f"Focus Guard включён. Если отвлечёшься примерно на "
                f"{state['idle_minutes']:g} мин — напомню про «{state['goal']}»."
            )
    elif action in ("off", "disable", "stop", "cancel"):
        stop_guard()
        result = "Focus Guard off."
        if (params.get("language") or "").lower().startswith("ru"):
            result = "Focus Guard выключен. Больше не слежу."
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
