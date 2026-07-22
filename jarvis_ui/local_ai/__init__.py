"""Free local AI (Ollama) — hardware-aware setup for AURA chat & agents.

Voice / Live always stays on Gemini.
"""

from __future__ import annotations

from jarvis_ui.local_ai.prefs import (
    get_ollama_model,
    is_ollama_chat_enabled,
    load_prefs as load_local_ai_prefs,
    save_prefs as save_local_ai_prefs,
)
from jarvis_ui.local_ai.recommend import recommend_model
from jarvis_ui.local_ai.hardware import probe_hardware
from jarvis_ui.local_ai.ollama_client import OllamaClient, get_ollama_client

__all__ = [
    "OllamaClient",
    "get_ollama_client",
    "get_ollama_model",
    "is_ollama_chat_enabled",
    "load_local_ai_prefs",
    "save_local_ai_prefs",
    "probe_hardware",
    "recommend_model",
]
