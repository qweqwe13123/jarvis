"""Lightweight markdown → HTML for JARVIS console and chat cards."""
from __future__ import annotations

import html
import re

_CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADER = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_UL = re.compile(r"^[\-\*•]\s+(.+)$", re.MULTILINE)
_OL = re.compile(r"^\d+\.\s+(.+)$", re.MULTILINE)
_TABLE_ROW = re.compile(r"^\|(.+)\|$", re.MULTILINE)
_HR = re.compile(r"^---+$", re.MULTILINE)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _INLINE_CODE.sub(r'<code style="background:#001a24;color:#00d4ff;padding:2px 5px;border-radius:3px;font-family:monospace;">\1</code>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(r'<a href="\2" style="color:#00d4ff;">\1</a>', text)
    return text


def _render_table(block: str) -> str:
    rows = [r.strip() for r in block.strip().split("\n") if r.strip().startswith("|")]
    if len(rows) < 2:
        return f"<p>{_inline(block)}</p>"
    html_rows = []
    for i, row in enumerate(rows):
        if re.match(r"^\|[\s\-:|]+\|$", row):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        tag = "th" if i == 0 else "td"
        style = (
            'style="padding:6px 10px;border:1px solid #0d3347;color:#8ffcff;"'
            if tag == "td"
            else 'style="padding:6px 10px;border:1px solid #0d3347;color:#00d4ff;font-weight:bold;"'
        )
        html_rows.append(
            "<tr>" + "".join(f"<{tag} {style}>{_inline(c)}</{tag}>" for c in cells) + "</tr>"
        )
    return (
        '<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:12px;">'
        + "".join(html_rows)
        + "</table>"
    )


def markdown_to_html(text: str) -> str:
    if not text:
        return ""
    src = text.strip()

    parts: list[str] = []
    last = 0
    for m in _CODE_BLOCK.finditer(src):
        before = src[last:m.start()]
        if before.strip():
            parts.append(_render_blocks(before))
        lang = m.group(1) or "code"
        code = html.escape(m.group(2).strip())
        parts.append(
            f'<pre style="background:#000d14;border:1px solid #0d3347;border-radius:6px;'
            f'padding:10px;margin:8px 0;overflow-x:auto;font-family:monospace;font-size:11px;'
            f'color:#d8f8ff;"><span style="color:#3a8a9a;font-size:10px;">{lang}</span>\n{code}</pre>'
        )
        last = m.end()
    tail = src[last:]
    if tail.strip():
        parts.append(_render_blocks(tail))
    return "".join(parts) if parts else _render_blocks(src)


def _render_blocks(text: str) -> str:
    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.strip().startswith("|"):
            block_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block_lines.append(lines[i])
                i += 1
            out.append(_render_table("\n".join(block_lines)))
            continue
        hm = _HEADER.match(line)
        if hm:
            level = len(hm.group(1))
            sizes = {1: 18, 2: 16, 3: 14, 4: 13}
            out.append(
                f'<h{level} style="color:#d8f8ff;margin:10px 0 6px;font-size:{sizes.get(level,13)}px;">'
                f"{_inline(hm.group(2))}</h{level}>"
            )
            i += 1
            continue
        if _HR.match(line.strip()):
            out.append('<hr style="border:none;border-top:1px solid #0d3347;margin:10px 0;">')
            i += 1
            continue
        if _UL.match(line):
            items = []
            while i < len(lines) and _UL.match(lines[i]):
                items.append(f"<li style='margin:4px 0;'>{_inline(_UL.match(lines[i]).group(1))}</li>")
                i += 1
            out.append(f"<ul style='margin:6px 0;padding-left:18px;color:#8ffcff;'>{''.join(items)}</ul>")
            continue
        if _OL.match(line):
            items = []
            while i < len(lines) and _OL.match(lines[i]):
                items.append(f"<li style='margin:4px 0;'>{_inline(_OL.match(lines[i]).group(1))}</li>")
                i += 1
            out.append(f"<ol style='margin:6px 0;padding-left:18px;color:#8ffcff;'>{''.join(items)}</ol>")
            continue
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("|"):
            if _HEADER.match(lines[i]) or _UL.match(lines[i]) or _OL.match(lines[i]):
                break
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            out.append(
                f'<p style="margin:6px 0;line-height:1.5;color:#8ffcff;">'
                f"{_inline(' '.join(para_lines))}</p>"
            )
    return "".join(out)
