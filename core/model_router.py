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


def _gemini_role_for_task(task: str) -> str:
    if task == "coding":
        return "balanced"
    if task in ("analysis", "documents"):
        return "balanced"
    return "fast"


def _routes(task_type: str) -> list[tuple[str, str]]:
    from core.gemini_models import primary

    task = (task_type or "chat").lower()
    gemini_model = primary(_gemini_role_for_task(task))
    if task == "coding":
        return [
            ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("gemini", gemini_model),
            ("ollama", "qwen2.5-coder:latest"),
            ("lmstudio", "local-model"),
        ]
    if task in ("analysis", "documents"):
        return [
            ("gemini", gemini_model),
            ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ("groq", "llama-3.3-70b-versatile"),
            ("ollama", "llama3.1:latest"),
            ("lmstudio", "local-model"),
        ]
    if task in ("translation", "creative", "chat", "search"):
        return [
            ("ollama", "qwen3:8b"),
            ("groq", "llama-3.3-70b-versatile"),
            ("openrouter", "google/gemma-2-9b-it:free"),
            ("gemini", gemini_model),
            ("ollama", "llama3.1:latest"),
            ("lmstudio", "local-model"),
        ]
    return [
        ("gemini", gemini_model),
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


def _build_messages(prompt: str, system: str | None) -> list[dict]:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _chat_http(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider: str,
    timeout_sec: int,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
) -> tuple[str, int]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": _build_messages(prompt, system),
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


def _generate_gemini(
    model: str,
    prompt: str,
    timeout_sec: int,
    system: str | None = None,
    *,
    role: str = "balanced",
) -> tuple[str, int]:
    from google.genai import types

    from core.gemini_models import (
        GeminiModelError,
        call_with_fallback,
        models_for,
    )

    api_key = _key("gemini_api_key")
    if not api_key:
        raise AuthError("gemini: key missing")

    from google import genai

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    # Prefer the requested model, then the full role chain.
    chain = [model] + [m for m in models_for(role) if m != model]
    start = time.time()
    try:
        def _once(name: str):
            if config is None:
                return client.models.generate_content(model=name, contents=prompt)
            return client.models.generate_content(
                model=name, contents=prompt, config=config
            )

        response = call_with_fallback(role, _once, models=chain, retries_per_model=2)
    except GeminiModelError as e:
        raise ProviderUnavailableError(f"gemini: {e}") from e
    except Exception as e:
        raise ProviderUnavailableError(f"gemini: {e}") from e
    text = (response.text or "").strip()
    if not text:
        raise EmptyResponseError("gemini: empty response")
    return text, int((time.time() - start) * 1000)


def _generate_ollama(model: str, prompt: str, timeout_sec: int) -> tuple[str, int]:
    url = os.getenv("OLLAMA_BASE_URL", _config_value("ollama_base_url", "http://localhost:11434/api/generate"))
    if not (model or "").strip() or (model or "").strip().lower() in ("auto", "latest"):
        model = _config_value("ollama_model", "") or "llama3.2:3b"
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
    system: str | None = None,
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
        if pref_provider == "ollama" and (
            not pref_model or pref_model.lower() in ("auto", "latest")
        ):
            pref_model = _config_value("ollama_model", "") or "llama3.2:3b"
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
                text, latency = _generate_gemini(
                    model,
                    prompt,
                    timeout_sec,
                    system,
                    role=_gemini_role_for_task(routed_task),
                )
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
                    system,
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
                    system,
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
                    system,
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
                    system,
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
                    system,
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


# --------------------------------------------------------------------------- #
# Streaming — used by the Website Builder for a live, on-the-fly HTML preview. #
# --------------------------------------------------------------------------- #

_OPENAI_COMPATIBLE_URLS = {
    "openai": ("https://api.openai.com/v1/chat/completions", "openai_api_key"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "groq_api_key"),
    "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek_api_key"),
    "together": ("https://api.together.xyz/v1/chat/completions", "together_api_key"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter_api_key"),
}


def _stream_gemini(model: str, prompt: str, system: str | None, max_tokens: int):
    from google import genai
    from google.genai import types

    api_key = _key("gemini_api_key")
    if not api_key:
        raise AuthError("gemini: key missing")
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    try:
        stream = client.models.generate_content_stream(model=model, contents=prompt, config=config)
        for chunk in stream:
            piece = getattr(chunk, "text", None)
            if piece:
                yield piece
    except Exception as e:
        raise ProviderUnavailableError(f"gemini: {e}") from e


def _stream_openai_compatible(url: str, api_key: str, model: str, prompt: str,
                              provider: str, system: str | None, timeout_sec: int,
                              temperature: float, max_tokens: int):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": _build_messages(prompt, system),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec, stream=True)
    except requests.Timeout as e:
        raise TimeoutError(f"{provider}: timeout") from e
    except Exception as e:
        raise ProviderUnavailableError(f"{provider}: transport error {e}") from e
    if resp.status_code >= 400:
        _raise_from_http(provider, resp.status_code, resp.text or "")
    got_any = False
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        data = raw[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = obj["choices"][0]["delta"].get("content")
        except Exception:
            continue
        if delta:
            got_any = True
            yield delta
    if not got_any:
        raise EmptyResponseError(f"{provider}: empty stream")


def stream_text(
    prompt: str,
    system: str | None = None,
    task_type: str = "coding",
    timeout_sec: int = 120,
    temperature: float = 0.6,
    max_tokens: int = 8192,
    preferred_provider: str | None = None,
    preferred_model: str | None = None,
):
    """Yield text deltas from the first healthy provider that streams.

    Falls back to a single non-streamed generation (yielded as one delta) if
    every streaming provider fails, so callers always get *something*.
    """
    reserve_request(is_heavy_task=False)

    routes = _routes(task_type)
    if preferred_provider:
        pref = preferred_provider.strip().lower()
        if pref != "auto":
            routes = [(p, (preferred_model or m)) for p, m in routes if p == pref] + \
                     [(p, m) for p, m in routes if p != pref]

    errors: list[str] = []
    for provider, model in routes:
        if not _health_ok(provider):
            continue
        try:
            if provider == "gemini":
                yield from _stream_gemini(model, prompt, system, max_tokens)
            elif provider in _OPENAI_COMPATIBLE_URLS:
                url, key_name = _OPENAI_COMPATIBLE_URLS[provider]
                yield from _stream_openai_compatible(
                    url, _key(key_name), model, prompt, provider, system,
                    timeout_sec, temperature, max_tokens,
                )
            else:
                continue
            _mark_health(provider, True)
            _log(f"STREAM OK provider={provider} model={model} task={task_type}")
            return
        except (AuthError, RateLimitError, TimeoutError, ProviderUnavailableError,
                EmptyResponseError, ModelRouterError) as e:
            _mark_health(provider, False)
            errors.append(f"{provider}/{model}: {e}")
            _log(f"STREAM FAIL {provider}/{model}: {e}")
            continue
        except Exception as e:
            _mark_health(provider, False)
            errors.append(f"{provider}/{model}: unknown {e}")
            _log(f"STREAM FAIL {provider}/{model}: unknown {e}")
            continue

    # Last resort: non-streamed generation.
    result = generate_text(
        prompt,
        task_type=task_type,
        timeout_sec=timeout_sec,
        temperature=temperature,
        max_tokens=max_tokens,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
        system=system,
    )
    yield result.text
