"""Extract an HTML document from assistant text — Python port of
F.O.R.G.E `src/lib/extract-html.ts`. Works on partial streams so the live
preview can update on the fly while the model is still writing.
"""
from __future__ import annotations

import re

_CLOSED_RE = re.compile(r"```(?:html)?\s*([\s\S]*?)```", re.IGNORECASE)
_OPEN_RE = re.compile(r"```(?:html)?\s*([\s\S]*)$", re.IGNORECASE)
_RAW_DOC_RE = re.compile(r"<!doctype html|<html[\s>]", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?(?:```|$)")


def extract_html(text: str | None) -> str | None:
    """Return the HTML body of the first code block, even if still streaming."""
    if not text:
        return None

    # Closed ```html ... ``` block.
    closed = _CLOSED_RE.search(text)
    if closed:
        return closed.group(1).strip()

    # Open block (still streaming): only treat as HTML once a doc marker shows.
    open_m = _OPEN_RE.search(text)
    if open_m:
        candidate = open_m.group(1).strip()
        low = candidate.lower()
        if "<!doctype" in low or "<html" in low:
            return candidate

    # Raw document without fences.
    if _RAW_DOC_RE.search(text):
        return text

    return None


def strip_code_blocks(text: str | None) -> str:
    """Remove fenced code blocks so only the chat-facing prose remains."""
    if not text:
        return ""
    return _CODE_BLOCK_RE.sub("", text).strip()
