"""Build the set of chat models the user can actually use (keys + Ollama)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelOption:
    id: str
    provider: str  # auto | gemini | ollama | groq | ...
    model: str
    title: str
    tier: str  # High | Fast | Medium | Local
    badge: str = ""
    mode: str = "auto"  # live | auto — JCFG mode for general chat


def _cfg() -> dict[str, Any]:
    try:
        from core.app_paths import api_keys_path

        path = api_keys_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _has_key(cfg: dict, name: str) -> bool:
    return len(str(cfg.get(name) or "").strip()) > 5


def _is_chat_ollama(name: str) -> bool:
    low = (name or "").lower()
    skip = ("embed", "nomic-embed", "clip", "whisper", "tts")
    return not any(s in low for s in skip)


def _pretty_gemini(model_id: str) -> str:
    m = (model_id or "").removeprefix("models/").strip()
    mapping = {
        "gemini-flash-latest": "Gemini Flash",
        "gemini-flash-lite-latest": "Gemini Flash Lite",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
        "gemini-2.0-flash": "Gemini 2.0 Flash",
        "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
    }
    if m in mapping:
        return mapping[m]
    # gemini-2.5-flash-something → Gemini 2.5 Flash
    parts = m.replace("_", "-").split("-")
    nice = []
    for p in parts:
        if p.lower() == "gemini":
            nice.append("Gemini")
        elif p.lower() in ("flash", "lite", "pro"):
            nice.append(p.capitalize())
        else:
            nice.append(p)
    return " ".join(nice) if nice else "Gemini"


def available_models() -> list[ModelOption]:
    """Models unlocked by the user's keys / local Ollama (real model names)."""
    cfg = _cfg()
    out: list[ModelOption] = [
        ModelOption(
            id="auto",
            provider="auto",
            model="",
            title="Auto",
            tier="Smart",
            badge="",
            mode="live",
        ),
    ]

    if _has_key(cfg, "gemini_api_key"):
        try:
            from core.gemini_models import primary

            flash_id = primary("fast")
            balanced_id = primary("balanced")
        except Exception:
            flash_id = "gemini-flash-latest"
            balanced_id = "gemini-2.5-flash"

        out.append(
            ModelOption(
                id="gemini-flash",
                provider="gemini",
                model=flash_id,
                title=_pretty_gemini(flash_id),
                tier="Fast",
                badge="",
                mode="auto",
            )
        )
        if balanced_id and balanced_id != flash_id:
            out.append(
                ModelOption(
                    id="gemini-balanced",
                    provider="gemini",
                    model=balanced_id,
                    title=_pretty_gemini(balanced_id),
                    tier="High",
                    badge="",
                    mode="auto",
                )
            )

    if _has_key(cfg, "openai_api_key"):
        out.append(
            ModelOption(
                id="openai-4o-mini",
                provider="openai",
                model="gpt-4o-mini",
                title="GPT-4o mini",
                tier="Fast",
                badge="",
                mode="auto",
            )
        )
        out.append(
            ModelOption(
                id="openai-4o",
                provider="openai",
                model="gpt-4o",
                title="GPT-4o",
                tier="High",
                badge="",
                mode="auto",
            )
        )

    if _has_key(cfg, "openrouter_api_key"):
        out.append(
            ModelOption(
                id="openrouter-auto",
                provider="openrouter",
                model="openrouter/auto",
                title="OpenRouter Auto",
                tier="Medium",
                badge="",
                mode="auto",
            )
        )
        out.append(
            ModelOption(
                id="openrouter-deepseek",
                provider="openrouter",
                model="deepseek/deepseek-chat-v3-0324:free",
                title="DeepSeek V3 (OpenRouter)",
                tier="High",
                badge="",
                mode="auto",
            )
        )

    if _has_key(cfg, "groq_api_key"):
        out.append(
            ModelOption(
                id="groq-llama70",
                provider="groq",
                model="llama-3.3-70b-versatile",
                title="Llama 3.3 70B",
                tier="Fast",
                badge="",
                mode="auto",
            )
        )
        out.append(
            ModelOption(
                id="groq-llama8",
                provider="groq",
                model="llama-3.1-8b-instant",
                title="Llama 3.1 8B",
                tier="Fast",
                badge="",
                mode="auto",
            )
        )

    if _has_key(cfg, "deepseek_api_key"):
        out.append(
            ModelOption(
                id="deepseek-chat",
                provider="deepseek",
                model="deepseek-chat",
                title="DeepSeek Chat",
                tier="High",
                badge="",
                mode="auto",
            )
        )
        out.append(
            ModelOption(
                id="deepseek-reasoner",
                provider="deepseek",
                model="deepseek-reasoner",
                title="DeepSeek Reasoner",
                tier="High",
                badge="",
                mode="auto",
            )
        )

    if _has_key(cfg, "together_api_key"):
        out.append(
            ModelOption(
                id="together-llama70",
                provider="together",
                model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                title="Llama 3.1 70B",
                tier="High",
                badge="",
                mode="auto",
            )
        )

    # Installed Ollama chat models — show the real tag (llama3.2:1b).
    try:
        from jarvis_ui.local_ai.ollama_client import get_ollama_client
        from jarvis_ui.local_ai.prefs import get_ollama_model, load_prefs

        client = get_ollama_client()
        st = client.status()
        preferred = get_ollama_model() or str(load_prefs().get("recommended_model") or "")
        if st.server_up:
            names = [n for n in st.models if _is_chat_ollama(n)]
            if preferred and preferred not in names and _is_chat_ollama(preferred):
                if client.model_installed(preferred):
                    names.insert(0, preferred)
            for name in names[:10]:
                out.append(
                    ModelOption(
                        id=f"ollama:{name}",
                        provider="ollama",
                        model=name,
                        title=name,
                        tier="Local",
                        badge="",
                        mode="auto",
                    )
                )
    except Exception:
        pass

    return out


def find_option(option_id: str, catalog: list[ModelOption] | None = None) -> ModelOption | None:
    catalog = catalog or available_models()
    for opt in catalog:
        if opt.id == option_id:
            return opt
    return catalog[0] if catalog else None


_AUTO_RANK = {
    "gemini-balanced": 95,
    "gemini-flash": 85,
    "openai-4o": 90,
    "openai-4o-mini": 75,
    "deepseek-chat": 80,
    "deepseek-reasoner": 82,
    "groq-llama70": 70,
    "openrouter-deepseek": 72,
    "openrouter-auto": 55,
    "together-llama70": 65,
    "groq-llama8": 50,
}


def resolve_auto_option() -> ModelOption:
    """Pick the best model from keys the user actually has."""
    catalog = available_models()
    concrete = [o for o in catalog if o.id != "auto"]
    if not concrete:
        return catalog[0] if catalog else ModelOption(
            id="auto", provider="auto", model="", title="Auto", tier="Smart", mode="live"
        )

    def score(opt: ModelOption) -> int:
        if opt.provider == "ollama":
            return 40
        return _AUTO_RANK.get(opt.id, 30)

    concrete.sort(key=score, reverse=True)
    return concrete[0]


def effective_option(option_id: str, *, auto_mode: bool = True) -> ModelOption:
    """Resolve what chat should actually use right now."""
    if auto_mode or option_id == "auto":
        # Prefer Live/tools path when Gemini is available (provider=auto, mode=live).
        catalog = available_models()
        if any(o.provider == "gemini" for o in catalog):
            return ModelOption(
                id="auto",
                provider="auto",
                model="",
                title="Auto",
                tier="Smart",
                mode="live",
            )
        return resolve_auto_option()
    return find_option(option_id) or resolve_auto_option()
