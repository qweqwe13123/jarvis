"""Central Gemini model catalog with automatic fallback.

Google does not swap models for you when an id is deprecated or blocked for a
key. AURA owns that: every Gemini call should go through a role chain so a
dead model (404 / not available to new users) silently falls through to the
next healthy one.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

# Roles used across the app.
Role = str  # "fast" | "balanced" | "vision" | "live"

# Prefer stable "latest" aliases — pinned 2.5 ids often 404 for new API keys.
_CHAINS: dict[str, tuple[str, ...]] = {
    "fast": (
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ),
    "balanced": (
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
    ),
    "vision": (
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
    ),
    "live": (
        "models/gemini-2.5-flash-native-audio-preview-12-2025",
        "models/gemini-2.5-flash-native-audio-latest",
        "models/gemini-3.1-flash-live-preview",
    ),
}

# How long a model stays marked unhealthy after a hard failure.
_BAD_TTL_SEC = 15 * 60
_lock = threading.Lock()
_bad_until: dict[str, float] = {}
_last_good: dict[str, str] = {}


@dataclass(frozen=True)
class ModelAttempt:
    role: str
    model: str
    fallback_depth: int


class GeminiModelError(RuntimeError):
    """All models in a role chain failed."""

    def __init__(self, role: str, errors: list[str]):
        self.role = role
        self.errors = errors
        detail = "; ".join(errors[-4:]) if errors else "no attempts"
        super().__init__(f"Gemini role={role!r} exhausted: {detail}")


def primary(role: Role = "balanced") -> str:
    """First preferred model for a role (display / defaults)."""
    chain = models_for(role)
    return chain[0] if chain else "gemini-flash-latest"


def models_for(role: Role = "balanced") -> list[str]:
    """Ordered candidates for a role, last-good first, skipping recent failures."""
    key = (role or "balanced").lower().strip()
    base = list(_CHAINS.get(key) or _CHAINS["balanced"])
    with _lock:
        last = _last_good.get(key)
        now = time.time()
        ordered: list[str] = []
        if last and last in base:
            ordered.append(last)
        for name in base:
            if name not in ordered:
                ordered.append(name)
        healthy = [m for m in ordered if _bad_until.get(m, 0.0) <= now]
        # If everything is marked bad, still try the full chain (TTL may be wrong).
        return healthy or ordered


def mark_good(model: str, role: Role | None = None) -> None:
    with _lock:
        _bad_until.pop(model, None)
        if role:
            _last_good[(role or "").lower()] = model


def mark_bad(model: str, *, ttl_sec: float = _BAD_TTL_SEC) -> None:
    with _lock:
        _bad_until[model] = time.time() + max(30.0, float(ttl_sec))


def clear_health() -> None:
    """Test helper."""
    with _lock:
        _bad_until.clear()
        _last_good.clear()


def is_model_unavailable_error(exc: BaseException | str) -> bool:
    """True when the next model in the chain should be tried."""
    msg = str(exc).lower()
    needles = (
        "404",
        "not_found",
        "not found",
        "no longer available",
        "is not found",
        "unsupported model",
        "unknown model",
        "model is not available",
        "does not exist",
        "invalid model",
        "not supported for",
    )
    return any(n in msg for n in needles)


def is_transient_error(exc: BaseException | str) -> bool:
    msg = str(exc).lower()
    needles = (
        "503",
        "500",
        "overloaded",
        "unavailable",
        "resource exhausted",
        "resource_exhausted",
        "rate limit",
        "quota",
        "too many requests",
        "try again later",
        "deadline exceeded",
        "timeout",
    )
    return any(n in msg for n in needles)


def should_fallback(exc: BaseException | str) -> bool:
    """Fallback on dead models; also hop away from hard quota on a specific model."""
    return is_model_unavailable_error(exc) or is_transient_error(exc)


def call_with_fallback(
    role: Role,
    fn: Callable[[str], T],
    *,
    models: Sequence[str] | None = None,
    retries_per_model: int = 1,
    retry_delay: float = 0.6,
    on_attempt: Callable[[ModelAttempt], None] | None = None,
) -> T:
    """Call ``fn(model_name)`` across the role chain until one succeeds.

    ``fn`` should raise on failure. Non-fallback errors (auth, bad request)
    abort the chain immediately.
    """
    chain = list(models) if models else models_for(role)
    errors: list[str] = []
    role_key = (role or "balanced").lower()

    for depth, model in enumerate(chain):
        if on_attempt is not None:
            on_attempt(ModelAttempt(role=role_key, model=model, fallback_depth=depth))
        for attempt in range(1, max(1, retries_per_model) + 1):
            try:
                result = fn(model)
                mark_good(model, role_key)
                if depth:
                    print(f"[Gemini] ✅ role={role_key} fell back to {model} (depth={depth})")
                return result
            except Exception as e:
                err = f"{model}: {e}"
                errors.append(err)
                if is_model_unavailable_error(e):
                    mark_bad(model)
                    print(f"[Gemini] ⚠️  model unavailable ({model}) — trying next")
                    break
                if is_transient_error(e) and attempt < retries_per_model:
                    time.sleep(retry_delay * attempt)
                    continue
                if is_transient_error(e):
                    # Try another model for quota/overload instead of dying here.
                    mark_bad(model, ttl_sec=120)
                    print(f"[Gemini] ⚠️  transient on {model} — trying next")
                    break
                # Auth / invalid request / etc. — do not burn the whole chain.
                raise

    raise GeminiModelError(role_key, errors)


def generate_content(
    role: Role,
    contents: Any,
    *,
    api_key: str,
    config: Any = None,
    retries_per_model: int = 2,
) -> Any:
    """``google.genai`` Client generate_content with automatic model fallback."""
    from google import genai

    client = genai.Client(api_key=api_key)

    def _once(model: str):
        if config is None:
            return client.models.generate_content(model=model, contents=contents)
        return client.models.generate_content(
            model=model, contents=contents, config=config
        )

    return call_with_fallback(
        role, _once, retries_per_model=retries_per_model
    )


def generate_legacy(
    role: Role,
    prompt: Any,
    *,
    api_key: str,
    system_instruction: str | None = None,
    retries_per_model: int = 2,
) -> Any:
    """``google.generativeai`` GenerativeModel path with automatic fallback."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    def _once(model: str):
        kwargs: dict[str, Any] = {"model_name": model}
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        return genai.GenerativeModel(**kwargs).generate_content(prompt)

    return call_with_fallback(
        role, _once, retries_per_model=retries_per_model
    )


def generative_model(
    role: Role,
    *,
    api_key: str,
    system_instruction: str | None = None,
):
    """Return a GenerativeModel bound to the current best model for ``role``.

    Prefer ``generate_legacy`` / ``call_with_fallback`` for real resilience —
    a single model object cannot hop mid-flight. This helper is for call sites
    that only need a model handle for one shot.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = primary(role)
    # Prefer last-good if present.
    chain = models_for(role)
    if chain:
        model_name = chain[0]
    kwargs: dict[str, Any] = {"model_name": model_name}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    return genai.GenerativeModel(**kwargs)


def live_model_candidates() -> list[str]:
    return models_for("live")
