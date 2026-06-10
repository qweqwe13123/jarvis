from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_PATH = BASE_DIR / "memory" / "vector_memory.jsonl"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wа-яёçğıöşüə]+", (text or "").lower(), re.IGNORECASE)


def _vector(text: str) -> Counter:
    return Counter(_tokens(text))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def remember_vector(text: str, kind: str = "note", meta: dict | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return "empty"
    VECTOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "id": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
        "kind": kind,
        "text": text[:2000],
        "meta": meta or {},
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    with VECTOR_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item["id"]


def search_memory(query: str, limit: int = 5) -> list[dict]:
    if not VECTOR_PATH.exists():
        return []
    qv = _vector(query)
    scored = []
    for line in VECTOR_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        score = _cosine(qv, _vector(item.get("text", "")))
        if score > 0:
            item["score"] = round(score, 4)
            scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def format_vector_context(query: str, limit: int = 5) -> str:
    found = search_memory(query, limit)
    if not found:
        return ""
    lines = ["[RELEVANT VECTOR MEMORY]"]
    for item in found:
        lines.append(f"- ({item.get('kind')}, score={item.get('score')}) {item.get('text', '')[:500]}")
    return "\n".join(lines) + "\n"
