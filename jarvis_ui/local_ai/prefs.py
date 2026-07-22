"""Persist Local AI (Ollama) preferences."""

from __future__ import annotations

import json
import time
from typing import Any

from jarvis_ui.paths import support_dir

_PREFS_PATH = support_dir() / "local_ai_prefs.json"

DEFAULTS: dict[str, Any] = {
    # When True, text chat / agents / Forge prefer Ollama. Voice stays Gemini.
    "use_ollama_for_chat": False,
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "",
    "recommended_model": "",
    "recommended_label": "",
    "last_probe_ram_gb": 0,
}


def load_prefs() -> dict[str, Any]:
    out = dict(DEFAULTS)
    if not _PREFS_PATH.exists():
        return out
    try:
        raw = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    for k, default in DEFAULTS.items():
        if k not in raw:
            continue
        val = raw[k]
        if isinstance(default, bool):
            out[k] = bool(val)
        elif isinstance(default, int):
            try:
                out[k] = int(val)
            except Exception:
                out[k] = default
        else:
            out[k] = str(val) if val is not None else default
    return out


def save_prefs(patch: dict[str, Any]) -> dict[str, Any]:
    data = load_prefs()
    for k, v in patch.items():
        if k in DEFAULTS:
            data[k] = v
    data["updated_at"] = time.time()
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        _PREFS_PATH.chmod(0o600)
    except Exception:
        pass
    # Keep api_keys.json in sync for model_router.
    _sync_api_keys(data)
    return data


def _sync_api_keys(data: dict[str, Any]) -> None:
    try:
        from core.app_paths import api_keys_path
        import json as _json

        path = api_keys_path()
        cfg: dict[str, Any] = {}
        if path.exists():
            try:
                cfg = _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        base = str(data.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
        # Router expects /api/generate endpoint.
        if not base.endswith("/api/generate"):
            generate_url = base + "/api/generate"
        else:
            generate_url = base
            base = base[: -len("/api/generate")] or "http://localhost:11434"
        cfg["ollama_base_url"] = generate_url
        cfg["ollama_model"] = str(data.get("ollama_model") or "")
        cfg["primary_chat_provider"] = (
            "ollama" if data.get("use_ollama_for_chat") else "gemini"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    except Exception:
        pass


def is_ollama_chat_enabled() -> bool:
    return bool(load_prefs().get("use_ollama_for_chat"))


def get_ollama_model() -> str:
    return str(load_prefs().get("ollama_model") or "").strip()
