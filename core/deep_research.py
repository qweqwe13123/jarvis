"""Local-first Deep Research pipeline (GPT Researcher pattern, MIT-inspired).

Multi-step: plan sub-queries -> web search (DuckDuckGo, no API key) ->
crawl & extract sources (requests + BeautifulSoup) -> synthesize a cited
markdown report through core.model_router (so it works with local Ollama,
BYOK Gemini/Groq/OpenRouter — whatever the user has configured).

Everything runs on-device; only outbound calls are the web pages themselves
and the user's chosen LLM provider. No server-side state.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

ProgressCb = Callable[[str], None]

MAX_PAGE_CHARS = 6_000
MIN_PAGE_CHARS = 300


@dataclass
class Source:
    title: str
    url: str
    text: str


@dataclass
class ResearchReport:
    topic: str
    queries: list[str]
    sources: list[Source]
    markdown: str = ""
    errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Step 1 — plan sub-queries
# --------------------------------------------------------------------------
def plan_queries(topic: str, n: int = 4) -> list[str]:
    """Ask the LLM for diverse search queries; fall back to heuristics."""
    from core.model_router import generate_text, ModelRouterError

    prompt = (
        f"You are a research planner. The user wants a deep research report on:\n"
        f"\"{topic}\"\n\n"
        f"Return a JSON array of {n} diverse, specific web search queries "
        f"(different angles: facts, comparisons, recent developments, criticism). "
        f"Return ONLY the JSON array, no prose."
    )
    try:
        result = generate_text(prompt, task_type="analysis", max_tokens=300, temperature=0.5)
        match = re.search(r"\[.*\]", result.text, re.DOTALL)
        if match:
            queries = json.loads(match.group(0))
            queries = [str(q).strip() for q in queries if str(q).strip()]
            if queries:
                return queries[:n]
    except (ModelRouterError, ValueError, json.JSONDecodeError):
        pass
    return _fallback_queries(topic, n)


def _fallback_queries(topic: str, n: int = 4) -> list[str]:
    base = topic.strip()
    variants = [
        base,
        f"{base} overview 2026",
        f"{base} pros and cons",
        f"{base} latest news analysis",
    ]
    return variants[:n]


# --------------------------------------------------------------------------
# Step 2 — search & crawl
# --------------------------------------------------------------------------
def _search(query: str, max_results: int = 5) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    out = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            out.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
    return out


def _fetch_page(url: str, timeout: int = 12) -> str:
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    return text[:MAX_PAGE_CHARS]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def gather_sources(
    queries: list[str],
    max_sources: int = 6,
    on_progress: ProgressCb | None = None,
) -> tuple[list[Source], list[str]]:
    """Search every query, crawl unique result pages until max_sources."""
    sources: list[Source] = []
    errors: list[str] = []
    seen_urls: set[str] = set()

    for query in queries:
        if len(sources) >= max_sources:
            break
        if on_progress:
            on_progress(f"Searching: {query}")
        try:
            results = _search(query)
        except Exception as e:
            errors.append(f"search failed for {query!r}: {e}")
            continue
        for item in results:
            if len(sources) >= max_sources:
                break
            url = item.get("url", "")
            if not url.startswith(("http://", "https://")) or url in seen_urls:
                continue
            seen_urls.add(url)
            if on_progress:
                on_progress(f"Reading: {_domain(url)}")
            try:
                text = _fetch_page(url)
            except Exception as e:
                errors.append(f"fetch failed {url}: {e}")
                continue
            if len(text) < MIN_PAGE_CHARS:
                continue
            sources.append(Source(title=item.get("title") or _domain(url), url=url, text=text))

    return sources, errors


# --------------------------------------------------------------------------
# Step 3 — synthesize cited report
# --------------------------------------------------------------------------
def write_report(topic: str, sources: list[Source]) -> str:
    from core.model_router import generate_text

    source_block = "\n\n".join(
        f"[{i}] {s.title}\nURL: {s.url}\nCONTENT: {s.text}"
        for i, s in enumerate(sources, 1)
    )
    prompt = f"""You are a meticulous research analyst. Write a deep research report on:

"{topic}"

Rules:
- Use ONLY the numbered sources below. Cite claims inline as [1], [2] etc.
- Structure: TL;DR (2-3 sentences), Key findings (bulleted, cited), Analysis,
  Caveats & open questions, then a "Sources" section listing [n] Title — URL.
- Write in the same language as the topic. Markdown formatting.
- Never invent facts or sources.

{source_block}
"""
    result = generate_text(prompt, task_type="analysis", max_tokens=2000, temperature=0.3, timeout_sec=90)
    return result.text.strip()


def _sources_only_markdown(topic: str, sources: list[Source]) -> str:
    lines = [f"## Research notes: {topic}", "", "Could not synthesize a full report; raw sources:", ""]
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. [{s.title}]({s.url})")
        lines.append(f"   {s.text[:280]}…")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------
def deep_research(
    topic: str,
    max_sources: int = 6,
    on_progress: ProgressCb | None = None,
) -> ResearchReport:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("empty research topic")

    if on_progress:
        on_progress("Planning research queries")
    queries = plan_queries(topic)

    sources, errors = gather_sources(queries, max_sources=max_sources, on_progress=on_progress)
    report = ResearchReport(topic=topic, queries=queries, sources=sources, errors=errors)

    if not sources:
        report.markdown = (
            f"## {topic}\n\nNo readable web sources found "
            f"({len(errors)} fetch errors). Try rephrasing the topic."
        )
        return report

    if on_progress:
        on_progress(f"Synthesizing report from {len(sources)} sources")
    try:
        report.markdown = write_report(topic, sources)
    except Exception as e:
        report.errors.append(f"synthesis failed: {e}")
        report.markdown = _sources_only_markdown(topic, sources)
    return report
