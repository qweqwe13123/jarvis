"""Unit tests for core.deep_research — pipeline with mocked network/LLM."""
from dataclasses import dataclass

import pytest

import core.deep_research as dr


@dataclass
class FakeResult:
    text: str
    provider: str = "test"
    model: str = "test"
    latency_ms: int = 1
    routed_task: str = "analysis"
    fallback_depth: int = 0


def test_fallback_queries_cover_angles():
    queries = dr._fallback_queries("rust vs go", 4)
    assert len(queries) == 4
    assert queries[0] == "rust vs go"


def test_plan_queries_parses_llm_json(monkeypatch):
    import core.model_router as mr
    monkeypatch.setattr(
        mr, "generate_text",
        lambda *a, **k: FakeResult(text='Sure: ["q1", "q2", "q3"]'),
    )
    assert dr.plan_queries("topic", n=3) == ["q1", "q2", "q3"]


def test_plan_queries_falls_back_on_garbage(monkeypatch):
    import core.model_router as mr
    monkeypatch.setattr(mr, "generate_text", lambda *a, **k: FakeResult(text="no json here"))
    queries = dr.plan_queries("some topic")
    assert queries[0] == "some topic"


def test_gather_sources_dedupes_and_limits(monkeypatch):
    monkeypatch.setattr(dr, "_search", lambda q, max_results=5: [
        {"title": "A", "snippet": "", "url": "https://a.com/x"},
        {"title": "A-dup", "snippet": "", "url": "https://a.com/x"},
        {"title": "B", "snippet": "", "url": "https://b.com/y"},
        {"title": "bad", "snippet": "", "url": "not-a-url"},
    ])
    monkeypatch.setattr(dr, "_fetch_page", lambda url, timeout=12: "words " * 100)
    sources, errors = dr.gather_sources(["q1", "q2"], max_sources=2)
    assert [s.url for s in sources] == ["https://a.com/x", "https://b.com/y"]
    assert errors == []


def test_gather_sources_skips_thin_and_failing_pages(monkeypatch):
    monkeypatch.setattr(dr, "_search", lambda q, max_results=5: [
        {"title": "thin", "snippet": "", "url": "https://thin.com"},
        {"title": "boom", "snippet": "", "url": "https://boom.com"},
        {"title": "good", "snippet": "", "url": "https://good.com"},
    ])

    def fake_fetch(url, timeout=12):
        if "thin" in url:
            return "too short"
        if "boom" in url:
            raise RuntimeError("timeout")
        return "meaningful content " * 50

    monkeypatch.setattr(dr, "_fetch_page", fake_fetch)
    sources, errors = dr.gather_sources(["q"], max_sources=5)
    assert [s.url for s in sources] == ["https://good.com"]
    assert len(errors) == 1


def test_deep_research_full_pipeline(monkeypatch):
    monkeypatch.setattr(dr, "plan_queries", lambda topic, n=4: ["q1"])
    monkeypatch.setattr(dr, "gather_sources", lambda q, max_sources=6, on_progress=None: (
        [dr.Source("T", "https://t.com", "body " * 100)], [],
    ))
    monkeypatch.setattr(dr, "write_report", lambda topic, sources: "## Report [1]")
    progress = []
    report = dr.deep_research("ai agents", on_progress=progress.append)
    assert report.markdown == "## Report [1]"
    assert report.queries == ["q1"]
    assert any("Synthesizing" in p for p in progress)


def test_deep_research_no_sources(monkeypatch):
    monkeypatch.setattr(dr, "plan_queries", lambda topic, n=4: ["q1"])
    monkeypatch.setattr(dr, "gather_sources",
                        lambda q, max_sources=6, on_progress=None: ([], ["err"]))
    report = dr.deep_research("obscure topic")
    assert "No readable web sources" in report.markdown


def test_deep_research_synthesis_failure_falls_back(monkeypatch):
    monkeypatch.setattr(dr, "plan_queries", lambda topic, n=4: ["q1"])
    monkeypatch.setattr(dr, "gather_sources", lambda q, max_sources=6, on_progress=None: (
        [dr.Source("T", "https://t.com", "body " * 100)], [],
    ))

    def boom(topic, sources):
        raise RuntimeError("model down")

    monkeypatch.setattr(dr, "write_report", boom)
    report = dr.deep_research("topic")
    assert "https://t.com" in report.markdown  # raw sources fallback
    assert any("synthesis failed" in e for e in report.errors)


def test_deep_research_rejects_empty_topic():
    with pytest.raises(ValueError):
        dr.deep_research("  ")
