#web_search.py
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
from core.app_paths import api_keys_path as _api_keys_path
API_CONFIG_PATH = _api_keys_path()


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_search(query: str) -> str:
    from google.genai import types as gtypes

    from core.gemini_models import generate_content as gemini_generate_content

    response = gemini_generate_content(
        "fast",
        query,
        api_key=_get_api_key(),
        config=gtypes.GenerateContentConfig(
            tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())]
        ),
    )

    text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text

    text = text.strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title",  ""),
                "snippet": r.get("body",   ""),
                "url":     r.get("href",   ""),
            })
    return results


def _extract_page_text(url: str, timeout: int = 12) -> str:
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
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    return text[:10_000]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _deep_research(query: str, max_sources: int = 5) -> str:
    results = _ddg_search(query, max_results=max(max_sources + 2, 8))
    sources: list[dict] = []

    for item in results:
        url = item.get("url", "")
        if not url.startswith(("http://", "https://")):
            continue
        try:
            text = _extract_page_text(url)
        except Exception as e:
            print(f"[WebSearch] ⚠️ Could not fetch {url}: {e}")
            continue
        if len(text) < 400:
            continue
        sources.append({
            "title": item.get("title", "") or _domain(url),
            "url": url,
            "text": text,
        })
        if len(sources) >= max_sources:
            break

    if not sources:
        return _format_ddg(query, results)

    from core.gemini_models import generate_content as gemini_generate_content
    source_block = "\n\n".join(
        f"SOURCE {i}\nTitle: {s['title']}\nURL: {s['url']}\nText: {s['text']}"
        for i, s in enumerate(sources, 1)
    )
    prompt = f"""You are a careful research assistant.

Question:
{query}

Use the sources below. Produce a concise but useful deep research brief in the user's language.
Include:
- direct answer
- key findings
- caveats/uncertainty
- source list with URLs

Do not invent facts not supported by the sources.

{source_block}
"""
    response = gemini_generate_content("balanced", prompt, api_key=_get_api_key())
    text = (response.text or "").strip()
    if not text:
        return _format_ddg(query, results)
    return text


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()

def _compare(items: list[str], aspect: str) -> str:
    query = (
        f"Compare {', '.join(items)} in terms of {aspect}. "
        "Give specific facts and data."
    )
    try:
        return _gemini_search(query)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Gemini compare failed: {e} — falling back to DDG")

    # DDG fallback: fetch results per item and merge
    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=3)
        except Exception:
            all_results[item] = []

    lines = [f"Comparison — {aspect.upper()}", "─" * 40]
    for item in items:
        lines.append(f"\n▸ {item}")
        for r in all_results.get(item, [])[:2]:
            if r.get("snippet"):
                lines.append(f"  • {r['snippet']}")
    return "\n".join(lines)

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"
    max_sources = int(params.get("max_sources", 5))

    if not query and not items:
        return "Please provide a search query, sir."

    if items and mode != "compare":
        mode = "compare"

    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 Query: {query!r}  Mode: {mode}")

    try:
        if mode in ("deep", "deep_research", "research"):
            print("[WebSearch] 🧠 Deep research mode...")
            result = _deep_research(query, max_sources=max_sources)
            print("[WebSearch] ✅ Deep research done.")
            return result

        if mode == "compare" and items:
            print(f"[WebSearch] 📊 Comparing: {items}")
            result = _compare(items, aspect)
            print("[WebSearch] ✅ Compare done.")
            return result

        print("[WebSearch] 🌐 Trying Gemini...")
        try:
            result = _gemini_search(query)
            print("[WebSearch] ✅ Gemini OK.")
            return result
        except Exception as e:
            print(f"[WebSearch] ⚠️ Gemini failed ({e}) — trying DDG...")
            results = _ddg_search(query)
            result  = _format_ddg(query, results)
            print(f"[WebSearch] ✅ DDG: {len(results)} result(s).")
            return result

    except Exception as e:
        print(f"[WebSearch] ❌ All backends failed: {e}")
        return f"Search failed, sir: {e}"
