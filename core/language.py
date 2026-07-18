from __future__ import annotations

import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LANGUAGE_PATH = BASE_DIR / "memory" / "language_state.json"

# Default startup vibe — Live speaks it in the user's language via prompt.
DEFAULT_GREETING_HINT = "Yo, I'm here. What are we doing?"

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_TURKISH_RE = re.compile(r"[çğıöşü]")
_AZERI_HINTS = {"salam", "necəsən", "xahiş", "mənə", "üçün", "göndər", "zəng"}
_TURKISH_HINTS = {"merhaba", "nasılsın", "lütfen", "benim", "için", "gönder", "ara"}


def detect_language(text: str) -> str:
    """Best-effort hint for reminders/notifications — not a hard language lock."""
    low = (text or "").lower()
    if _CYRILLIC_RE.search(low):
        return "ru"
    tokens = set(re.findall(r"[\wçğıöşüəıİ]+", low))
    if tokens & _AZERI_HINTS or "ə" in low:
        return "az"
    if _TURKISH_RE.search(low) or tokens & _TURKISH_HINTS:
        return "tr"
    return "en"


def load_language() -> str:
    try:
        data = json.loads(LANGUAGE_PATH.read_text(encoding="utf-8"))
        lang = (data.get("language") or "auto").strip().lower()
        return lang or "auto"
    except Exception:
        return "auto"


def save_language(language: str, sample: str = "") -> None:
    lang = (language or "auto").strip().lower()[:16] or "auto"
    LANGUAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANGUAGE_PATH.write_text(
        json.dumps({"language": lang, "sample": sample[:240]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def detect_and_save_language(text: str) -> str:
    lang = detect_language(text)
    save_language(lang, text)
    return lang


def language_instruction() -> str:
    lang_hint = load_language()
    hint = ""
    if lang_hint and lang_hint != "auto":
        hint = f"Last detected user language hint: {lang_hint}. "
    return (
        "[LANGUAGE POLICY]\n"
        f"{hint}"
        "Always reply in the same language the user is speaking right now. "
        "You support all languages — match their language, slang, and energy naturally. "
        "If they switch language mid-conversation, switch with them. "
        "If speech recognition is noisy or mixed, infer intent from the last clear user message. "
        "Tool summaries, timer confirmations, reminders, and notifications must follow the user's language.\n"
    )


def phrase(key: str, **kwargs) -> str:
    """English fallback for system tool replies — Live rephrases in the user's language."""
    table = {
        "timer_set_seconds": "Timer set for {seconds} seconds.",
        "timer_set_minutes": "Timer set for {minutes} minutes.",
        "reminder_set": "Reminder set for {time}.",
    }
    template = table.get(key, key)
    return template.format(**kwargs)
