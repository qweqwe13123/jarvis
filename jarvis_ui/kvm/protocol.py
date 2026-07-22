"""AURA native KVM wire protocol (LAN TCP, JSON lines).

Everything runs inside the AURA process — no Barrier / Input Leap install.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1
DEFAULT_PORT = 24900  # distinct from Barrier's 24800
RECV_BUF = 65536


def encode(msg: dict[str, Any]) -> bytes:
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def decode_lines(buffer: bytearray) -> tuple[list[dict[str, Any]], bytearray]:
    """Split buffer into complete JSON objects; return (messages, remainder)."""
    out: list[dict[str, Any]] = []
    while True:
        nl = buffer.find(b"\n")
        if nl < 0:
            break
        line = bytes(buffer[:nl]).decode("utf-8", errors="replace").strip()
        del buffer[: nl + 1]
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out, buffer
