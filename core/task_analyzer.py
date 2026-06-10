from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskProfile:
    category: str
    quality: str
    speed: str
    context_size: str


def analyze_task(text: str) -> TaskProfile:
    t = (text or "").lower()
    if any(k in t for k in ("code", "debug", "python", "react", "api", "backend", "frontend", "bug")):
        return TaskProfile(category="coding", quality="high", speed="medium", context_size="large")
    if any(k in t for k in ("analy", "compare", "investigate", "deep research", "исслед", "сравни")):
        return TaskProfile(category="analysis", quality="high", speed="medium", context_size="large")
    if any(k in t for k in ("translate", "переведи", "translation")):
        return TaskProfile(category="translation", quality="medium", speed="high", context_size="medium")
    if any(k in t for k in ("doc", "pdf", "report", "документ", "файл")):
        return TaskProfile(category="documents", quality="high", speed="medium", context_size="large")
    if any(k in t for k in ("story", "creative", "идея", "название", "пост")):
        return TaskProfile(category="creative", quality="high", speed="medium", context_size="medium")
    if any(k in t for k in ("search", "найди", "поиск", "google", "website", "сайт")):
        return TaskProfile(category="search", quality="medium", speed="high", context_size="medium")
    return TaskProfile(category="chat", quality="medium", speed="high", context_size="small")
