"""Daily motivational quotes — fully local, offline-capable.

A curated multilingual quote bank plus a helper that (un)registers a
repeating daily reminder in the local reminder store. The ReminderEngine
fires it through the live JARVIS voice like any other reminder; a fresh
quote is chosen at fire time.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

QUOTE_REMINDER_ID = "daily_quote"

QUOTES: dict[str, list[str]] = {
    "en": [
        "Discipline is choosing between what you want now and what you want most.",
        "Small daily improvements are the key to staggering long-term results.",
        "The best time to plant a tree was 20 years ago. The second best time is now.",
        "You don't have to be great to start, but you have to start to be great.",
        "Action is the foundational key to all success.",
        "Success is the sum of small efforts repeated day in and day out.",
        "Don't watch the clock; do what it does. Keep going.",
        "Hard choices, easy life. Easy choices, hard life.",
        "Motivation gets you going, habit keeps you growing.",
        "The obstacle is the way.",
        "Focus on being productive instead of busy.",
        "A year from now you may wish you had started today.",
    ],
    "ru": [
        "Дисциплина — это выбор между тем, что хочешь сейчас, и тем, что хочешь больше всего.",
        "Маленькие ежедневные улучшения дают ошеломляющий результат в долгую.",
        "Лучшее время посадить дерево было 20 лет назад. Второе лучшее — сейчас.",
        "Не обязательно быть великим, чтобы начать. Но нужно начать, чтобы стать великим.",
        "Действие — основа любого успеха.",
        "Успех — это сумма маленьких усилий, повторяемых изо дня в день.",
        "Не смотри на часы — делай, как они: продолжай идти.",
        "Сложные решения — лёгкая жизнь. Лёгкие решения — сложная жизнь.",
        "Мотивация запускает, привычка не даёт остановиться.",
        "Препятствие — это и есть путь.",
        "Через год ты пожалеешь, что не начал сегодня.",
    ],
    "tr": [
        "Disiplin, şimdi istediğinle en çok istediğin arasında seçim yapmaktır.",
        "Küçük günlük gelişmeler, uzun vadede muazzam sonuçların anahtarıdır.",
        "Bir ağaç dikmek için en iyi zaman 20 yıl önceydi. İkinci en iyi zaman şimdi.",
        "Başlamak için harika olmak zorunda değilsin, harika olmak için başlamak zorundasın.",
        "Başarı, her gün tekrarlanan küçük çabaların toplamıdır.",
    ],
}


def get_quote(language: str = "en") -> str:
    bank = QUOTES.get(language) or QUOTES["en"]
    return random.choice(bank)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _store_path() -> Path:
    d = _base_dir() / "runtime" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d / "reminders.json"


def _load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def next_occurrence(hour: int, minute: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def configure_daily_quote(
    enabled: bool,
    time_str: str = "09:00",
    language: str = "en",
    store_path: Path | None = None,
) -> str:
    """Enable/disable the repeating daily quote in the local reminder store."""
    path = store_path or _store_path()
    items = [i for i in _load(path) if i.get("id") != QUOTE_REMINDER_ID]

    if enabled:
        try:
            hour, minute = (int(p) for p in time_str.split(":", 1))
            assert 0 <= hour < 24 and 0 <= minute < 60
        except Exception:
            return "Invalid time — use HH:MM (e.g. 09:00)."
        target = next_occurrence(hour, minute)
        items.append({
            "id": QUOTE_REMINDER_ID,
            "kind": "quote",
            "message": "Daily motivational quote",
            "language": language if language in QUOTES else "en",
            "target": target.isoformat(timespec="seconds"),
            "repeat": "daily",
            "status": "pending",
            "created": datetime.now().isoformat(timespec="seconds"),
        })
        result = f"Daily quote enabled at {time_str}."
    else:
        result = "Daily quote disabled."

    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
