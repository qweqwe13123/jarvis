"""Reminder scheduling — persistence only.

Reminders are NEVER spoken through a system TTS voice (``say`` / SAPI / espeak)
or any third-party engine. They are persisted to ``runtime/reminders/reminders.json``
and fired by the in-app :class:`core.reminder_engine.ReminderEngine`, which routes
every announcement through the live JARVIS voice session so timers, alarms,
scheduled tasks and automation events always sound exactly like a normal
conversation with the same voice, tone and personality.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from core.language import detect_language, phrase


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _scripts_dir() -> Path:
    d = _base_dir() / "runtime" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store_path() -> Path:
    return _scripts_dir() / "reminders.json"


def _load_reminders() -> list[dict]:
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_reminders(items: list[dict]) -> None:
    try:
        _store_path().write_text(
            json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _is_duplicate(message: str, target_dt: datetime) -> bool:
    target_key = target_dt.isoformat(timespec="minutes")[:16]
    for item in _load_reminders():
        if item.get("status") != "pending":
            continue
        if item.get("message") == message and (item.get("target") or "")[:16] == target_key:
            return True
    return False


def _record_reminder(item: dict) -> None:
    items = _load_reminders()
    items.append(item)
    _save_reminders(items[-500:])


def _sanitise(text: str, max_len: int = 200) -> str:
    return (
        (text or "")
        .replace("\\", "")
        .replace('"', "")
        .replace("'", "")
        .replace("\n", " ")
        .replace("\r", "")
        .strip()
    )[:max_len]


def _spoken_message(message: str, language: str) -> str:
    """Reminder payload — Live adds natural phrasing in the user's language."""
    clean = _sanitise(message, 160) or message or "your reminder"
    return clean


def reminder(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """Register a reminder. Firing + speech is handled by the in-app engine."""
    date_str = (parameters.get("date") or "").strip()
    time_str = (parameters.get("time") or "").strip()
    message = (parameters.get("message") or "Reminder").strip()
    delay_seconds_raw = parameters.get("delay_seconds")
    delay_minutes_raw = parameters.get("delay_minutes")

    delay_seconds = None
    try:
        if delay_seconds_raw not in (None, ""):
            delay_seconds = int(float(delay_seconds_raw))
        elif delay_minutes_raw not in (None, ""):
            delay_seconds = int(float(delay_minutes_raw) * 60)
    except Exception:
        return "I couldn't parse the reminder delay."

    if delay_seconds is not None:
        if delay_seconds <= 0:
            return "The reminder delay must be in the future."
        target_dt = datetime.now() + timedelta(seconds=delay_seconds)
    else:
        if not date_str or not time_str:
            return "I need either a relative delay or both a date and a time to set a reminder."
        try:
            target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return "I couldn't parse that date or time. Please use YYYY-MM-DD and HH:MM."

    if target_dt <= datetime.now():
        return "That time has already passed — I can't set a reminder in the past."

    safe_msg = _sanitise(message)
    lang_hint = (parameters.get("language") or parameters.get("source_language") or "").strip().lower()
    reminder_lang = lang_hint or detect_language(message)

    if _is_duplicate(safe_msg, target_dt):
        return phrase("reminder_set", time=target_dt.strftime("%Y-%m-%d %H:%M"))

    task_name = f"JARVISReminder_{target_dt.strftime('%Y%m%d_%H%M%S')}_{abs(hash(safe_msg)) % 10000}"

    _record_reminder({
        "id": task_name,
        "message": safe_msg,
        "spoken": _spoken_message(safe_msg, reminder_lang),
        "language": reminder_lang,
        "kind": "reminder",
        "target": target_dt.isoformat(timespec="seconds"),
        "status": "pending",
        "created": datetime.now().isoformat(timespec="seconds"),
    })

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(
                f"[Reminder] scheduled {target_dt.strftime('%Y-%m-%d %H:%M:%S')} "
                f"[{reminder_lang}] — {safe_msg[:40]}"
            )
        except Exception:
            pass

    if delay_seconds is not None:
        if delay_seconds < 60:
            return phrase("timer_set_seconds", seconds=delay_seconds)
        minutes = round(delay_seconds / 60, 1)
        return phrase("timer_set_minutes", minutes=f"{minutes:g}")

    friendly_time = target_dt.strftime("%B %d at %I:%M %p")
    return phrase("reminder_set", time=friendly_time)
