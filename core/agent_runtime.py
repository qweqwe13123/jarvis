"""Local-first agent runtime — every sidebar agent becomes a real agent.

Design (OpenManus / ReAct pattern, implemented natively):
- each agent = system prompt (core.agents) + its own toolset + persistent
  per-agent session memory stored locally in runtime/agent_sessions/;
- execution loop: the model may request a tool via a strict JSON block,
  the runtime executes it locally, feeds the observation back, and loops
  (bounded) until the model produces a final answer.

No cloud state: history lives on disk next to the app, tools are local
functions, LLM calls go through core.model_router (Ollama-capable).
"""
from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.agents import get_agent

ProgressCb = Callable[[str], None]

MAX_TOOL_STEPS = 4
MAX_HISTORY_MESSAGES = 20
MAX_OBSERVATION_CHARS = 7_000

_session_lock = threading.Lock()


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _sessions_dir() -> Path:
    d = _base_dir() / "runtime" / "agent_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[[dict], str]


def _tool_web_search(args: dict) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "ERROR: web_search requires a 'query'."
    try:
        from core.deep_research import _search
        results = _search(query, max_results=6)
    except Exception as e:
        return f"ERROR: search failed: {e}"
    if not results:
        return f"No results for: {query}"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}")
    return "\n".join(lines)


def _tool_fetch_page(args: dict) -> str:
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "ERROR: fetch_page requires a valid http(s) 'url'."
    try:
        from core.deep_research import _fetch_page
        return _fetch_page(url)
    except Exception as e:
        return f"ERROR: could not fetch {url}: {e}"


def _tool_deep_research(args: dict) -> str:
    topic = str(args.get("topic", "") or args.get("query", "")).strip()
    if not topic:
        return "ERROR: deep_research requires a 'topic'."
    try:
        from core.deep_research import deep_research
        report = deep_research(topic, max_sources=int(args.get("max_sources", 5)))
        return report.markdown
    except Exception as e:
        return f"ERROR: deep research failed: {e}"


def _tool_read_file(args: dict) -> str:
    path = Path(str(args.get("path", ""))).expanduser()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:MAX_OBSERVATION_CHARS]
    except Exception as e:
        return f"ERROR: cannot read {path}: {e}"


def _tool_write_file(args: dict) -> str:
    raw = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not raw:
        return "ERROR: write_file requires a 'path'."
    path = Path(raw).expanduser()
    # Relative paths land in a local sandbox folder, never scattered around.
    if not path.is_absolute():
        path = _base_dir() / "runtime" / "agent_files" / path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR: cannot write {path}: {e}"


def _tool_daily_quote(args: dict) -> str:
    from core.daily_quotes import configure_daily_quote
    enabled = args.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in ("false", "0", "off", "no", "disable")
    return configure_daily_quote(
        bool(enabled),
        time_str=str(args.get("time", "09:00")),
        language=str(args.get("language", "en")),
    )


def _tool_set_reminder(args: dict) -> str:
    from actions.reminder import reminder
    return reminder(dict(args))


_ALL_TOOLS: dict[str, Tool] = {
    "web_search": Tool(
        "web_search",
        "Search the web (DuckDuckGo). Args: {\"query\": str}. Returns titles, snippets, URLs.",
        _tool_web_search,
    ),
    "fetch_page": Tool(
        "fetch_page",
        "Download and extract the readable text of a web page. Args: {\"url\": str}.",
        _tool_fetch_page,
    ),
    "deep_research": Tool(
        "deep_research",
        "Full multi-step research: plans queries, crawls several sources, returns a cited "
        "markdown report. Slow (30-90s) — use for substantial research questions only. "
        "Args: {\"topic\": str}.",
        _tool_deep_research,
    ),
    "read_file": Tool(
        "read_file",
        "Read a local text file. Args: {\"path\": str}.",
        _tool_read_file,
    ),
    "write_file": Tool(
        "write_file",
        "Save text to a local file (relative paths go to the app's agent_files folder). "
        "Args: {\"path\": str, \"content\": str}.",
        _tool_write_file,
    ),
    "daily_quote": Tool(
        "daily_quote",
        "Enable/disable the daily motivational quote spoken by JARVIS. "
        "Args: {\"enabled\": bool, \"time\": \"HH:MM\", \"language\": \"en|ru|tr\"}.",
        _tool_daily_quote,
    ),
    "set_reminder": Tool(
        "set_reminder",
        "Set a local reminder/timer. Args: {\"message\": str, \"date\": \"YYYY-MM-DD\", "
        "\"time\": \"HH:MM\"} or {\"message\": str, \"delay_minutes\": int}.",
        _tool_set_reminder,
    ),
}

# Which tools each sidebar agent may use.
AGENT_TOOLSETS: dict[str, list[str]] = {
    "general": ["web_search", "fetch_page"],
    "writer": ["web_search", "fetch_page", "write_file"],
    "researcher": ["web_search", "fetch_page", "deep_research", "write_file"],
    "designer": ["web_search", "fetch_page"],
    "automation": ["web_search", "fetch_page", "read_file", "write_file",
                   "daily_quote", "set_reminder"],
    "code": ["web_search", "fetch_page", "read_file", "write_file"],
    "website": ["web_search", "fetch_page"],
    "maps_prospector": ["web_search"],
}


def tools_for(agent_id: str) -> list[Tool]:
    return [_ALL_TOOLS[n] for n in AGENT_TOOLSETS.get(agent_id, []) if n in _ALL_TOOLS]


# --------------------------------------------------------------------------
# Per-agent session memory (local JSON)
# --------------------------------------------------------------------------
def _session_path(agent_id: str) -> Path:
    safe = re.sub(r"[^a-z0-9_]", "_", agent_id.lower())
    return _sessions_dir() / f"{safe}.json"


def load_session(agent_id: str) -> list[dict]:
    try:
        data = json.loads(_session_path(agent_id).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_session(agent_id: str, role: str, content: str) -> None:
    with _session_lock:
        items = load_session(agent_id)
        items.append({"role": role, "content": content})
        items = items[-MAX_HISTORY_MESSAGES * 2:]
        try:
            _session_path(agent_id).write_text(
                json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:
            pass


def clear_session(agent_id: str) -> None:
    with _session_lock:
        try:
            _session_path(agent_id).unlink(missing_ok=True)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Prompt building + tool-call parsing
# --------------------------------------------------------------------------
def build_system_prompt(agent_id: str) -> str:
    agent = get_agent(agent_id)
    tools = tools_for(agent_id)
    if not tools:
        return agent.system_prompt
    tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    return (
        f"{agent.system_prompt}\n\n"
        "TOOLS AVAILABLE:\n"
        f"{tool_lines}\n\n"
        "TOOL PROTOCOL (strict):\n"
        "- To call a tool, your ENTIRE reply must be one JSON object, nothing else:\n"
        '  {"tool": "web_search", "args": {"query": "latest stable python version"}}\n'
        "- You will then receive an OBSERVATION with the tool result and can call "
        "another tool or write the final answer as normal prose (no JSON).\n"
        "- You MUST call a tool before answering anything that depends on current "
        "information: versions, prices, news, dates, statistics, or the user "
        "explicitly asking to search/research/read a file. Your training data is "
        "stale — do not answer such questions from memory.\n"
        "- Never fabricate tool output or invent URLs."
    )


def parse_tool_call(text: str, allowed: set[str]) -> tuple[str, dict] | None:
    """Return (tool_name, args) if the reply is a tool invocation, else None.

    Strict on purpose: the whole reply (minus an optional code fence) must be
    the JSON object. A JSON example embedded in a prose answer never triggers
    tool execution.
    """
    stripped = (text or "").strip()
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL).strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("tool", "")).strip()
    if name not in allowed:
        return None
    args = data.get("args") or {}
    return (name, args) if isinstance(args, dict) else (name, {})


_FRESH_INFO_MARKERS = (
    "latest", "current", "today", "right now", "this year", "news", "price",
    "cost", "version", "release", "2025", "2026", "search", "look up",
    "check the web", "google",
    # ru
    "последн", "актуальн", "сейчас", "сегодня", "новост", "цена", "верси",
    "найди", "поищи", "загугли",
    # tr
    "güncel", "son sürüm", "bugün", "haber", "fiyat", "ara",
)


def needs_fresh_info(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _FRESH_INFO_MARKERS)


def _render_history(history: list[dict], user_text: str) -> str:
    parts = []
    for msg in history[-MAX_HISTORY_MESSAGES:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        parts.append(f"{role}: {msg.get('content', '')}")
    parts.append(f"User: {user_text}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Execution loop
# --------------------------------------------------------------------------
def run_agent(
    agent_id: str,
    user_text: str,
    preferred_provider: str = "auto",
    preferred_model: str = "",
    on_progress: ProgressCb | None = None,
    remember: bool = True,
) -> str:
    """Run one agent turn: history + tool loop + final answer. Blocking."""
    from core.model_router import generate_text

    agent = get_agent(agent_id)
    system = build_system_prompt(agent.id)
    allowed = {t.name for t in tools_for(agent.id)}
    history = load_session(agent.id) if remember else []
    prompt = _render_history(history, user_text)

    task_type = "coding" if agent.id in ("code", "website", "automation") else "analysis"
    observations: list[str] = []
    answer = ""

    # Deterministic grounding: when the question clearly needs fresh external
    # info, run a web search up-front and feed results in as the first
    # observation. Small local models (Ollama) often ignore the JSON tool
    # protocol, so this keeps them grounded too.
    if "web_search" in allowed and needs_fresh_info(user_text):
        if on_progress:
            on_progress("Searching the web")
        pre = _ALL_TOOLS["web_search"].fn({"query": user_text})
        if pre and not pre.startswith("ERROR"):
            observations.append(
                f"OBSERVATION from web_search (auto, current results for the user's "
                f"question):\n{pre[:MAX_OBSERVATION_CHARS]}"
            )

    for step in range(MAX_TOOL_STEPS + 1):
        full_prompt = prompt
        if observations:
            full_prompt += "\n\n" + "\n\n".join(observations) + (
                "\n\nNow either call another tool (JSON only) or give the final answer."
            )
        result = generate_text(
            full_prompt,
            system=system,
            task_type=task_type,
            preferred_provider=preferred_provider,
            preferred_model=preferred_model,
            max_tokens=2000,
            timeout_sec=90,
        )
        answer = result.text.strip()

        call = parse_tool_call(answer, allowed) if step < MAX_TOOL_STEPS else None
        if not call:
            break
        name, args = call
        if on_progress:
            on_progress(f"Using tool: {name}")
        tool = _ALL_TOOLS[name]
        try:
            output = tool.fn(args)
        except Exception as e:
            output = f"ERROR: tool {name} crashed: {e}"
        observations.append(
            f"OBSERVATION from {name}({json.dumps(args, ensure_ascii=False)[:200]}):\n"
            f"{str(output)[:MAX_OBSERVATION_CHARS]}"
        )

    if remember:
        append_session(agent.id, "user", user_text)
        append_session(agent.id, "assistant", answer)
    return answer
