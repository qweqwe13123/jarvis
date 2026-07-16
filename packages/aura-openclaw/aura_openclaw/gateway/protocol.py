"""OpenClaw Gateway protocol v4 — frame helpers (subset)."""
from __future__ import annotations

import json
import uuid
from typing import Any


def new_id() -> str:
    return uuid.uuid4().hex


def req(method: str, params: dict[str, Any] | None = None, req_id: str | None = None) -> str:
    return json.dumps({
        "type": "req",
        "id": req_id or new_id(),
        "method": method,
        "params": params or {},
    })


def res(req_id: str, ok: bool, payload: dict | None = None, error: str | None = None) -> str:
    body: dict[str, Any] = {"type": "res", "id": req_id, "ok": ok}
    if ok:
        body["payload"] = payload or {}
    else:
        body["error"] = {"message": error or "error"}
    return json.dumps(body)


def event(name: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps({
        "type": "event",
        "event": name,
        "payload": payload or {},
    })


def parse_frame(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("invalid gateway frame")
    return data
