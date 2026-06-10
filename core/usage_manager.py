from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
USAGE_PATH = BASE_DIR / "runtime" / "usage_state.json"
SCHEMA_VERSION = 2


@dataclass
class UsageStatus:
    tier: str
    requests_left: int
    queued: int
    blocked_heavy_tasks: int


def _limits_for_tier(tier: str) -> tuple[int, int]:
    if tier == "enterprise":
        return 20000, 600
    if tier == "team":
        return 5000, 240
    if tier == "pro":
        return 2000, 120
    return 300, 35


def _fresh_state() -> dict:
    now = time.strftime("%Y-%m-%d")
    hour = time.strftime("%Y-%m-%d %H")
    return {
        "schema_version": SCHEMA_VERSION,
        "tier": "free",
        "day": now,
        "hour_window": hour,
        "used_day": 0,
        "used_hour": 0,
        "queued": 0,
        "blocked_heavy_tasks": 0,
    }


def _load() -> dict:
    if not USAGE_PATH.exists():
        return _fresh_state()
    try:
        data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _fresh_state()
    if data.get("schema_version") != SCHEMA_VERSION:
        merged = _fresh_state()
        merged.update({k: v for k, v in data.items() if k in merged})
        return merged
    return data


def _save(state: dict) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = SCHEMA_VERSION
    USAGE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _rotate_windows(state: dict) -> None:
    day = time.strftime("%Y-%m-%d")
    hour = time.strftime("%Y-%m-%d %H")
    if state.get("day") != day:
        state["day"] = day
        state["used_day"] = 0
        state["blocked_heavy_tasks"] = 0
    if state.get("hour_window") != hour:
        state["hour_window"] = hour
        state["used_hour"] = 0


def reserve_request(is_heavy_task: bool = False) -> UsageStatus:
    state = _load()
    _rotate_windows(state)
    tier = str(state.get("tier", "free"))
    day_limit, hour_limit = _limits_for_tier(tier)

    used_day = int(state.get("used_day", 0))
    used_hour = int(state.get("used_hour", 0))

    if tier == "free" and is_heavy_task and used_day >= int(day_limit * 0.5):
        state["blocked_heavy_tasks"] = int(state.get("blocked_heavy_tasks", 0)) + 1
        state["queued"] = int(state.get("queued", 0)) + 1
    elif used_day >= day_limit or used_hour >= hour_limit:
        state["queued"] = int(state.get("queued", 0)) + 1
    else:
        state["used_day"] = used_day + 1
        state["used_hour"] = used_hour + 1

    _save(state)
    left = max(0, day_limit - int(state.get("used_day", 0)))
    return UsageStatus(
        tier=tier,
        requests_left=left,
        queued=int(state.get("queued", 0)),
        blocked_heavy_tasks=int(state.get("blocked_heavy_tasks", 0)),
    )


def usage_stats() -> UsageStatus:
    state = _load()
    _rotate_windows(state)
    _save(state)
    tier = str(state.get("tier", "free"))
    day_limit, _ = _limits_for_tier(tier)
    left = max(0, day_limit - int(state.get("used_day", 0)))
    return UsageStatus(
        tier=tier,
        requests_left=left,
        queued=int(state.get("queued", 0)),
        blocked_heavy_tasks=int(state.get("blocked_heavy_tasks", 0)),
    )
