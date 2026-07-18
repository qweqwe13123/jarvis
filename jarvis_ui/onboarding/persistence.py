"""Persist onboarding completion — tied to this installed app bundle.

Policy:
- Download / copy from site DMG → show onboarding (bundle fingerprint changes).
- In-app Update → do NOT re-show onboarding (updater leaves a one-shot marker).
- No usable Gemini key → always show onboarding.
- Flow is always welcome → permissions → API key → main app.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _support_base() -> Path:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "AURA"
        elif sys.platform == "win32":
            base = Path.home() / "AppData" / "Local" / "AURA"
        else:
            base = Path.home() / ".local" / "share" / "AURA"
    else:
        base = Path(__file__).resolve().parents[2] / "runtime"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _state_path() -> Path:
    return _support_base() / "onboarding.json"


def _update_marker_path() -> Path:
    base = _support_base()
    p = base / "runtime" if getattr(sys, "frozen", False) else base
    p.mkdir(parents=True, exist_ok=True)
    return p / "in_app_update.json"


def bundle_fingerprint() -> str:
    """Identity of the currently running install (changes when DMG replaces the app)."""
    try:
        from core.version import VERSION
    except Exception:
        VERSION = "?"

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        try:
            st = exe.stat()
            return f"{VERSION}:{int(st.st_mtime_ns)}:{st.st_size}:{exe}"
        except Exception:
            return f"{VERSION}:{exe}"
    # Dev: fingerprint by VERSION only so reruns don't loop onboarding.
    return f"dev:{VERSION}"


def mark_pending_in_app_update(version: str | None = None) -> None:
    """Called by the updater before replacing the app + relaunch."""
    try:
        from core.version import VERSION as cur
    except Exception:
        cur = "unknown"
    path = _update_marker_path()
    path.write_text(
        json.dumps(
            {
                "pending": True,
                "from_version": version or cur,
                "ts": __import__("time").time(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def consume_in_app_update_marker() -> bool:
    """True once if this launch follows an in-app update."""
    path = _update_marker_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pending = bool(data.get("pending"))
    except Exception:
        pending = True
    try:
        path.unlink()
    except Exception:
        pass
    return pending


def is_onboarding_done() -> bool:
    path = _state_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not bool(data.get("completed")):
            return False
        stored = str(data.get("fingerprint") or "")
        # Legacy / missing fingerprint: treat as incomplete so a site
        # reinstall shows onboarding again.
        if not stored:
            return False
        return stored == bundle_fingerprint()
    except Exception:
        return False


def should_run_onboarding() -> bool:
    """Single gate used at app start."""
    from core.app_paths import has_gemini_setup

    # Broken / fresh machine: never skip past Gemini setup.
    if not has_gemini_setup():
        return True

    # In-app Update: keep the user in the product; bind new fingerprint.
    if consume_in_app_update_marker():
        _refresh_completed_record()
        return False

    # Same installed bundle already completed setup.
    if is_onboarding_done():
        return False

    # New DMG from the site (or replaced .app) → full onboarding again.
    return True


def mark_onboarding_done() -> None:
    _refresh_completed_record()


def _refresh_completed_record() -> None:
    path = _state_path()
    data: dict = {}
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    try:
        from core.version import VERSION
    except Exception:
        VERSION = "?"
    data.update(
        {
            "completed": True,
            "version": VERSION,
            "fingerprint": bundle_fingerprint(),
        }
    )
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def reset_onboarding_for_preview() -> None:
    """Dev helper — force show onboarding again."""
    path = _state_path()
    if path.exists():
        path.unlink()
