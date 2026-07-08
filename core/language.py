from __future__ import annotations

import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LANGUAGE_PATH = BASE_DIR / "memory" / "language_state.json"

LANGUAGES = {
    "ru": {"name": "Russian", "greeting": "Йо, на связи. Чё делаем?"},
    "tr": {"name": "Turkish", "greeting": "Yo, buradayım. Ne yapıyoruz?"},
    "az": {"name": "Azerbaijani", "greeting": "Salam, buradayam. Nə edirik?"},
    "en": {"name": "English", "greeting": "Yo, I'm here. What are we doing?"},
}

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_TURKISH_RE = re.compile(r"[çğıöşü]")
_AZERI_HINTS = {"salam", "necəsən", "xahiş", "mənə", "üçün", "göndər", "zəng"}
_TURKISH_HINTS = {"merhaba", "nasılsın", "lütfen", "benim", "için", "gönder", "ara"}


def detect_language(text: str) -> str:
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
        lang = data.get("language", "ru")
        return lang if lang in LANGUAGES else "ru"
    except Exception:
        return "ru"


def save_language(language: str, sample: str = "") -> None:
    if language not in LANGUAGES:
        language = "ru"
    LANGUAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANGUAGE_PATH.write_text(
        json.dumps({"language": language, "sample": sample[:240]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def detect_and_save_language(text: str) -> str:
    lang = detect_language(text)
    save_language(lang, text)
    return lang


def language_instruction() -> str:
    lang = load_language()
    name = LANGUAGES.get(lang, LANGUAGES["ru"])["name"]
    return (
        "[LANGUAGE POLICY]\n"
        f"Current user language: {name} ({lang}). Reply strictly in this language. "
        "All tool summaries, timer confirmations, notifications wording, website-builder reports, "
        "automation reports, agent messages, and UI-facing text must follow this language unless the user explicitly switches language. "
        "If speech recognition is mixed/noisy, infer the user's intended language from the last clear user message.\n"
    )


def phrase(key: str, **kwargs) -> str:
    lang = load_language()
    table = {
        "timer_set_seconds": {
            "ru": "Таймер установлен на {seconds} секунд.",
            "tr": "Zamanlayıcı {seconds} saniyeye ayarlandı.",
            "az": "Taymer {seconds} saniyəyə quruldu.",
            "en": "Timer set for {seconds} seconds.",
        },
        "timer_set_minutes": {
            "ru": "Таймер установлен на {minutes} минут.",
            "tr": "Zamanlayıcı {minutes} dakikaya ayarlandı.",
            "az": "Taymer {minutes} dəqiqəyə quruldu.",
            "en": "Timer set for {minutes} minutes.",
        },
        "reminder_set": {
            "ru": "Напоминание установлено на {time}.",
            "tr": "Hatırlatıcı {time} için ayarlandı.",
            "az": "Xatırlatma {time} üçün quruldu.",
            "en": "Reminder set for {time}.",
        },
    }
    template = table.get(key, {}).get(lang) or table.get(key, {}).get("ru") or key
    return template.format(**kwargs)
