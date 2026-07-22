"""Persist local KVM preferences under Application Support."""

from __future__ import annotations

import json
import time
from typing import Any

from jarvis_ui.paths import support_dir

_PREFS_PATH = support_dir() / "kvm_prefs.json"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "role": "server",  # server | client
    "layout": "peer_right",
    "peer_device_id": "",
    "peer_name": "",
    "peer_host": "",  # LAN IP / hostname of the other machine
    "server_screen": "",
    "client_screen": "",
    "port": 24900,
    "auto_invite": True,
}


def load_prefs() -> dict[str, Any]:
    out = dict(DEFAULTS)
    if not _PREFS_PATH.exists():
        return out
    try:
        raw = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    for k, default in DEFAULTS.items():
        if k not in raw:
            continue
        val = raw[k]
        if isinstance(default, bool):
            out[k] = bool(val)
        elif isinstance(default, int):
            try:
                out[k] = int(val)
            except Exception:
                out[k] = default
        else:
            out[k] = str(val) if val is not None else default
    return out


def save_prefs(patch: dict[str, Any]) -> dict[str, Any]:
    data = load_prefs()
    for k, v in patch.items():
        if k in DEFAULTS:
            data[k] = v
    data["updated_at"] = time.time()
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        _PREFS_PATH.chmod(0o600)
    except Exception:
        pass
    return data
