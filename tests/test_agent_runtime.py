"""Unit tests for core.agent_runtime — tool loop, sessions, parsing."""
import json
from dataclasses import dataclass

import pytest

import core.agent_runtime as rt


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_sessions_dir", lambda: tmp_path)
    return tmp_path


@dataclass
class FakeResult:
    text: str
    provider: str = "test"
    model: str = "test"
    latency_ms: int = 1
    routed_task: str = "analysis"
    fallback_depth: int = 0


def _mock_llm(monkeypatch, replies):
    calls = []

    def fake_generate_text(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return FakeResult(text=replies[min(len(calls) - 1, len(replies) - 1)])

    import core.model_router as mr
    monkeypatch.setattr(mr, "generate_text", fake_generate_text)
    return calls


# ----- toolsets -----------------------------------------------------------
def test_every_sidebar_agent_has_tools():
    for key in ("general", "writer", "researcher", "designer", "automation", "code", "website"):
        assert rt.tools_for(key), f"agent {key} has no tools"


def test_researcher_gets_deep_research():
    names = [t.name for t in rt.tools_for("researcher")]
    assert "deep_research" in names and "web_search" in names


def test_system_prompt_lists_tools():
    prompt = rt.build_system_prompt("researcher")
    assert "deep_research" in prompt
    assert '"tool"' in prompt  # instructs JSON tool-call format


# ----- tool-call parsing ---------------------------------------------------
def test_parse_plain_tool_call():
    out = rt.parse_tool_call('{"tool": "web_search", "args": {"query": "cats"}}', {"web_search"})
    assert out == ("web_search", {"query": "cats"})


def test_parse_fenced_tool_call():
    text = '```json\n{"tool": "web_search", "args": {"query": "x"}}\n```'
    assert rt.parse_tool_call(text, {"web_search"}) == ("web_search", {"query": "x"})


def test_parse_rejects_prose_answer():
    assert rt.parse_tool_call("The answer is 42 because of reasons.", {"web_search"}) is None


def test_parse_rejects_json_embedded_in_long_prose():
    text = "Here is how you'd call it:\n" + "x" * 200 + '\n{"tool": "web_search", "args": {}}'
    assert rt.parse_tool_call(text, {"web_search"}) is None


def test_parse_rejects_unknown_tool():
    assert rt.parse_tool_call('{"tool": "rm_rf", "args": {}}', {"web_search"}) is None


# ----- session memory ------------------------------------------------------
def test_session_persist_and_trim(sessions):
    for i in range(rt.MAX_HISTORY_MESSAGES * 3):
        rt.append_session("writer", "user", f"msg {i}")
    items = rt.load_session("writer")
    assert len(items) == rt.MAX_HISTORY_MESSAGES * 2
    assert items[-1]["content"] == f"msg {rt.MAX_HISTORY_MESSAGES * 3 - 1}"
    rt.clear_session("writer")
    assert rt.load_session("writer") == []


def test_sessions_isolated_per_agent(sessions):
    rt.append_session("writer", "user", "write a poem")
    rt.append_session("researcher", "user", "research llms")
    assert rt.load_session("writer")[0]["content"] == "write a poem"
    assert rt.load_session("researcher")[0]["content"] == "research llms"


# ----- execution loop ------------------------------------------------------
def test_run_agent_direct_answer(sessions, monkeypatch):
    calls = _mock_llm(monkeypatch, ["Just a plain answer."])
    answer = rt.run_agent("writer", "hello")
    assert answer == "Just a plain answer."
    assert len(calls) == 1
    # System prompt must be the writer's, and history persisted.
    assert "copywriter" in calls[0]["system"].lower()
    session = rt.load_session("writer")
    assert [m["role"] for m in session] == ["user", "assistant"]


def test_run_agent_tool_loop(sessions, monkeypatch):
    calls = _mock_llm(monkeypatch, [
        '{"tool": "web_search", "args": {"query": "python 3.14"}}',
        "Final answer using the search results.",
    ])
    monkeypatch.setitem(
        rt._ALL_TOOLS, "web_search",
        rt.Tool("web_search", "d", lambda args: f"RESULTS for {args['query']}"),
    )
    progress = []
    answer = rt.run_agent("researcher", "what's new in python?",
                          on_progress=progress.append)
    assert answer == "Final answer using the search results."
    assert len(calls) == 2
    # Second call must contain the tool observation.
    assert "RESULTS for python 3.14" in calls[1]["prompt"]
    assert progress == ["Using tool: web_search"]


def test_run_agent_stops_at_max_steps(sessions, monkeypatch):
    # Model keeps asking for tools forever — loop must terminate.
    calls = _mock_llm(monkeypatch, ['{"tool": "web_search", "args": {"query": "q"}}'])
    monkeypatch.setitem(
        rt._ALL_TOOLS, "web_search", rt.Tool("web_search", "d", lambda args: "stuff"),
    )
    rt.run_agent("researcher", "loop forever")
    assert len(calls) == rt.MAX_TOOL_STEPS + 1


def test_run_agent_history_included(sessions, monkeypatch):
    rt.append_session("designer", "user", "I like dark themes")
    rt.append_session("designer", "assistant", "Noted: dark themes.")
    calls = _mock_llm(monkeypatch, ["ok"])
    rt.run_agent("designer", "make a palette")
    assert "I like dark themes" in calls[0]["prompt"]


# ----- file tools ----------------------------------------------------------
def test_write_file_relative_goes_to_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_base_dir", lambda: tmp_path)
    msg = rt._tool_write_file({"path": "notes/draft.md", "content": "hello"})
    saved = tmp_path / "runtime" / "agent_files" / "notes" / "draft.md"
    assert saved.read_text() == "hello"
    assert "Saved" in msg


def test_read_file_missing_returns_error(tmp_path):
    out = rt._tool_read_file({"path": str(tmp_path / "nope.txt")})
    assert out.startswith("ERROR")
