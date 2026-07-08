"""Unit tests for core.model_router routing tables and key resolution."""
import pytest

import core.model_router as mr


KNOWN_PROVIDERS = {"gemini", "openrouter", "groq", "deepseek", "together",
                   "ollama", "lmstudio", "openai"}


@pytest.mark.parametrize("task", ["coding", "analysis", "documents", "chat",
                                  "translation", "creative", "search", "unknown", ""])
def test_routes_nonempty_and_known_providers(task):
    routes = mr._routes(task)
    assert routes, f"no routes for task={task!r}"
    for provider, model in routes:
        assert provider in KNOWN_PROVIDERS
        assert isinstance(model, str) and model


def test_routes_local_fallback_present():
    # Every route list must end with a local option so the app can work
    # fully offline (ollama/lmstudio).
    for task in ("coding", "chat", "analysis", "other"):
        providers = [p for p, _ in mr._routes(task)]
        assert "ollama" in providers or "lmstudio" in providers


def test_key_env_precedence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-123")
    assert mr._key("gemini_api_key") == "env-key-123"


def test_key_falls_back_to_config(monkeypatch, tmp_path):
    monkeypatch.delenv("SOME_FAKE_KEY", raising=False)
    cfg = tmp_path / "api_keys.json"
    cfg.write_text('{"some_fake_key": "cfg-value"}', encoding="utf-8")
    monkeypatch.setattr(mr, "CONFIG_PATH", cfg)
    monkeypatch.setattr(mr, "get_provider_key", lambda name: "")
    assert mr._key("some_fake_key") == "cfg-value"


def test_health_cache_ttl(monkeypatch):
    mr._health_cache.clear()
    mr._health_cache["groq"] = (False, mr.time.time())
    assert mr._health_ok("groq") is False
    # Expired entries are treated as healthy again.
    mr._health_cache["groq"] = (False, mr.time.time() - mr.HEALTH_TTL_SECONDS - 1)
    assert mr._health_ok("groq") is True
    mr._health_cache.clear()


def test_error_hierarchy():
    for exc in (mr.AuthError, mr.RateLimitError, mr.TimeoutError,
                mr.ProviderUnavailableError, mr.EmptyResponseError):
        assert issubclass(exc, mr.ModelRouterError)
