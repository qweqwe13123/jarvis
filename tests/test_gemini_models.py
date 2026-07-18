"""Unit tests for core.gemini_models fallback catalog."""
import pytest

import core.gemini_models as gm


@pytest.fixture(autouse=True)
def _clean_health():
    gm.clear_health()
    yield
    gm.clear_health()


@pytest.mark.parametrize("role", ["fast", "balanced", "vision", "live"])
def test_models_for_nonempty_unique_ordered(role):
    models = gm.models_for(role)
    assert models
    assert len(models) == len(set(models))
    assert models == list(dict.fromkeys(models))


@pytest.mark.parametrize(
    "msg",
    [
        "404 model not found",
        "Model is no longer available to new users",
        "NOT_FOUND: unsupported model",
        "unknown model id",
    ],
)
def test_is_model_unavailable_error(msg):
    assert gm.is_model_unavailable_error(msg)


def test_is_model_unavailable_error_rejects_generic():
    assert not gm.is_model_unavailable_error("connection reset by peer")


def test_call_with_fallback_skips_bad_model():
    calls: list[str] = []

    def fn(model: str) -> str:
        calls.append(model)
        if model == "bad-model":
            raise RuntimeError("404 model not found")
        return f"ok:{model}"

    result = gm.call_with_fallback("fast", fn, models=["bad-model", "good-model"])
    assert result == "ok:good-model"
    assert calls == ["bad-model", "good-model"]


def test_mark_bad_excludes_model_until_ttl(monkeypatch):
    role = "balanced"
    chain = list(gm.models_for(role))
    assert chain

    bad = chain[0]
    gm.mark_bad(bad, ttl_sec=60)

    healthy = gm.models_for(role)
    assert bad not in healthy
    assert healthy

    # After TTL expires the model re-enters the chain.
    real_time = gm.time.time
    monkeypatch.setattr(gm.time, "time", lambda: real_time() + 120)
    restored = gm.models_for(role)
    assert bad in restored


def test_mark_good_promotes_last_good():
    role = "fast"
    chain = gm.models_for(role)
    preferred = chain[-1]
    gm.mark_good(preferred, role)

    ordered = gm.models_for(role)
    assert ordered[0] == preferred


def test_primary_matches_first_of_models_for():
    for role in ("fast", "balanced", "vision", "live"):
        assert gm.primary(role) == gm.models_for(role)[0]
