from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from core.key_vault import get_provider_key
from core.task_analyzer import analyze_task
from core.usage_manager import reserve_request


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
LOG_PATH = BASE_DIR / "runtime" / "model_router.log"
HEALTH_TTL_SECONDS = 45


@dataclass
class ModelResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    routed_task: str
    fallback_depth: int


class ModelRouterError(RuntimeError):
    pass


class AuthError(ModelRouterError):
    pass


class RateLimitError(ModelRouterError):
    pass


class TimeoutError(ModelRouterError):
    pass


class ProviderUnavailableError(ModelRouterError):
    pass


class EmptyResponseError(ModelRouterError):
    pass


_health_cache: dict[str, tuple[bool, float]] = {}


def _load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _config_value(name: str, default: str = "") -> str:
    cfg = _load_config()
    return str(cfg.get(name, default))


def _key(name: str) -> str:
    env_key = os.getenv(name.upper()) or os.getenv(name)
    if env_key:
        return env_key.strip()
    vault_key = get_provider_key(name)
    if vault_key:
        return vault_key.strip()
    return _config_value(name, "")


def _log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _routes(task_type: str) -> list[tuple[str, str]]:
    task = (task_type or "chat").lower()
    if task == "coding":
        return [
            ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("gemini", "gemini-2.5-flash"),
            ("ollama", "qwen2.5-coder:latest"),
            ("lmstudio", "local-model"),
        ]
    if task in ("analysis", "documents"):
        return [
            ("gemini", "gemini-2.5-flash"),
            ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("ollama", "llama3.1:latest"),
            ("lmstudio", "local-model"),
        ]
    if task in ("translation", "creative", "chat", "search"):
        return [
            ("groq", "llama-3.3-70b-versatile"),
            ("openrouter", "google/gemma-2-9b-it:free"),
            ("gemini", "gemini-2.5-flash"),
            ("ollama", "llama3.1:latest"),
            ("lmstudio", "local-model"),
        ]
    return [
        ("gemini", "gemini-2.5-flash"),
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
        ("ollama", "llama3.1:latest"),
        ("lmstudio", "local-model"),
    ]


def _health_ok(provider: str) -> bool:
    item = _health_cache.get(provider)
    if not item:
        return True
    ok, ts = item
    if time.time() - ts > HEALTH_TTL_SECONDS:
        return True
    return ok


def _mark_health(provider: str, ok: bool) -> None:
    _health_cache[provider] = (ok, time.time())


def _raise_from_http(provider: str, status: int, body: str) -> None:
    if status in (401, 403):
        raise AuthError(f"{provider}: auth error {status}")
    if status == 429:
        raise RateLimitError(f"{provider}: rate limit {status}")
    if status >= 500:
        raise ProviderUnavailableError(f"{provider}: server error {status}")
    raise ModelRouterError(f"{provider}: bad request {status} {body[:180]}")


def _chat_http(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider: str,
    timeout_sec: int,
    temperature: float,
    max_tokens: int,
) -> tuple[str, int]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    except requests.Timeout as e:
        raise TimeoutError(f"{provider}: timeout") from e
    except Exception as e:
        raise ProviderUnavailableError(f"{provider}: transport error {e}") from e
    if resp.status_code >= 400:
        _raise_from_http(provider, resp.status_code, resp.text or "")
    data = resp.json()
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise ModelRouterError(f"{provider}: unexpected response shape") from e
    if not text:
        raise EmptyResponseError(f"{provider}: empty response")
    return text, int((time.time() - start) * 1000)


def _generate_gemini(model: str, prompt: str, timeout_sec: int) -> tuple[str, int]:
    from google import genai

    api_key = _key("gemini_api_key")
    if not api_key:
        raise AuthError("gemini: key missing")
    start = time.time()
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
    except Exception as e:
        raise ProviderUnavailableError(f"gemini: {e}") from e
    text = (response.text or "").strip()
    if not text:
        raise EmptyResponseError("gemini: empty response")
    return text, int((time.time() - start) * 1000)


def _generate_ollama(model: str, prompt: str, timeout_sec: int) -> tuple[str, int]:
    url = os.getenv("OLLAMA_BASE_URL", _config_value("ollama_base_url", "http://localhost:11434/api/generate"))
    start = time.time()
    try:
        resp = requests.post(url, json={"model": model, "prompt": prompt, "stream": False}, timeout=timeout_sec)
    except requests.Timeout as e:
        raise TimeoutError("ollama: timeout") from e
    except Exception as e:
        raise ProviderUnavailableError(f"ollama: {e}") from e
    if resp.status_code >= 400:
        _raise_from_http("ollama", resp.status_code, resp.text or "")
    text = (resp.json().get("response") or "").strip()
    if not text:
        raise EmptyResponseError("ollama: empty response")
    return text, int((time.time() - start) * 1000)


def _generate_lmstudio(model: str, prompt: str, timeout_sec: int, temperature: float, max_tokens: int) -> tuple[str, int]:
    base = os.getenv("LMSTUDIO_BASE_URL", _config_value("lmstudio_base_url", "http://localhost:1234/v1"))
    url = f"{base.rstrip('/')}/chat/completions"
    return _chat_http(url, "", model, prompt, "lmstudio", timeout_sec, temperature, max_tokens)


def generate_text(
    prompt: str,
    task_type: str = "conversation",
    timeout_sec: int = 45,
    temperature: float = 0.4,
    max_tokens: int = 1200,
    preferred_provider: str | None = None,
    preferred_model: str | None = None,
) -> ModelResult:
    profile = analyze_task(prompt)
    routed_task = task_type if task_type and task_type != "conversation" else profile.category
    usage = reserve_request(is_heavy_task=profile.context_size == "large" and profile.quality == "high")
    _log(
        f"USAGE tier={usage.tier} left={usage.requests_left} queue={usage.queued} blocked={usage.blocked_heavy_tasks} "
        f"task={routed_task} quality={profile.quality} speed={profile.speed} ctx={profile.context_size}"
    )

    errors: list[str] = []
    routes = _routes(routed_task)
    if preferred_provider:
        pref_provider = preferred_provider.strip().lower()
        pref_model = (preferred_model or "").strip()
        preferred_route = (pref_provider, pref_model or "auto")
        filtered = []
        if pref_provider == "auto":
            filtered = routes
        else:
            for p, m in routes:
                if p == pref_provider:
                    filtered.append((p, pref_model or m))
            if not filtered:
                filtered = [(pref_provider, pref_model or "auto")]
        routes = filtered + [r for r in routes if r not in filtered]
    for idx, (provider, model) in enumerate(routes):
        if not _health_ok(provider):
            errors.append(f"{provider}/{model}: skipped by health cache")
            continue
        try:
            if provider == "gemini":
                text, latency = _generate_gemini(model, prompt, timeout_sec)
            elif provider == "openai":
                text, latency = _chat_http(
                    "https://api.openai.com/v1/chat/completions",
                    _key("openai_api_key"),
                    model,
                    prompt,
                    provider,
                    timeout_sec,
                    temperature,
                    max_tokens,
                )
            elif provider == "groq":
                text, latency = _chat_http(
                    "https://api.groq.com/openai/v1/chat/completions",
                    _key("groq_api_key"),
                    model,
                    prompt,
                    provider,
                    timeout_sec,
                    temperature,
                    max_tokens,
                )
            elif provider == "deepseek":
                text, latency = _chat_http(
                    "https://api.deepseek.com/chat/completions",
                    _key("deepseek_api_key"),
                    model,
                    prompt,
                    provider,
                    timeout_sec,
                    temperature,
                    max_tokens,
                )
            elif provider == "together":
                text, latency = _chat_http(
                    "https://api.together.xyz/v1/chat/completions",
                    _key("together_api_key"),
                    model,
                    prompt,
                    provider,
                    timeout_sec,
                    temperature,
                    max_tokens,
                )
            elif provider == "openrouter":
                text, latency = _chat_http(
                    "https://openrouter.ai/api/v1/chat/completions",
                    _key("openrouter_api_key"),
                    model,
                    prompt,
                    provider,
                    timeout_sec,
                    temperature,
                    max_tokens,
                )
            elif provider == "ollama":
                text, latency = _generate_ollama(model, prompt, timeout_sec)
            elif provider == "lmstudio":
                text, latency = _generate_lmstudio(model, prompt, timeout_sec, temperature, max_tokens)
            else:
                errors.append(f"{provider}/{model}: unsupported provider")
                continue
            _mark_health(provider, True)
            _log(f"OK provider={provider} model={model} task={routed_task} latency_ms={latency} fallback_depth={idx}")
            return ModelResult(
                text=text,
                provider=provider,
                model=model,
                latency_ms=latency,
                routed_task=routed_task,
                fallback_depth=idx,
            )
        except (AuthError, RateLimitError, TimeoutError, ProviderUnavailableError, EmptyResponseError, ModelRouterError) as e:
            _mark_health(provider, False)
            msg = f"{provider}/{model}: {e}"
            errors.append(msg)
            _log(f"FAIL {msg}")
            continue
        except Exception as e:
            _mark_health(provider, False)
            msg = f"{provider}/{model}: unknown {e}"
            errors.append(msg)
            _log(f"FAIL {msg}")
            continue

    raise ModelRouterError("All model providers failed: " + " | ".join(errors[-6:]))
