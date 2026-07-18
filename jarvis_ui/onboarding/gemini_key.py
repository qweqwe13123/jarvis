"""Validate Gemini API keys for onboarding (desktop → Google, no SaaS hop).

Supports:
  • Legacy standard keys — AIza…
  • Auth keys from Google AI Studio (2026+) — AQ.…

Never log the raw key. Live truth is a cheap models.list call.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "invalid", "network", "unknown"]

# Legacy Google API keys (~39 chars).
_LEGACY_KEY_RE = re.compile(r"^AIza[0-9A-Za-z_\-]{20,}$")
# Auth keys issued by Google AI Studio (service-account-backed).
_AUTH_KEY_RE = re.compile(r"^AQ\.[A-Za-z0-9][A-Za-z0-9._-]{8,}$")

_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass(frozen=True)
class VerifyResult:
    status: Status
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def normalize_key(text: str) -> str:
    """Strip whitespace / zero-width junk users paste from browsers."""
    raw = (text or "").strip()
    # Collapse internal whitespace (copy/paste with newlines).
    raw = "".join(raw.split())
    # Common invisible chars from rich text / PDF.
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0"):
        raw = raw.replace(ch, "")
    return raw


def looks_like_gemini_key(key: str) -> bool:
    """Soft format gate — reject obvious garbage before any network call.

    Accepts both AIza… (legacy) and AQ.… (auth). Google remains the source of truth.
    """
    k = normalize_key(key)
    if not k or len(k) > 256:
        return False
    if _LEGACY_KEY_RE.match(k):
        return len(k) >= 30
    if _AUTH_KEY_RE.match(k):
        return True
    return False


def format_error_message() -> str:
    return (
        "This doesn’t look like a Gemini API key. "
        "Paste the key from Google AI Studio."
    )


def verify_gemini_key(key: str, *, timeout: float = 8.0) -> VerifyResult:
    """Live probe against Google Generative Language API.

    Uses models.list — cheap auth check, no chat tokens burned.
    Works for both AIza… and AQ.… keys via x-goog-api-key.
    """
    k = normalize_key(key)
    if not looks_like_gemini_key(k):
        return VerifyResult("invalid", format_error_message())

    # Header auth works for legacy + auth keys; avoids putting the key in the URL.
    url = f"{_MODELS_URL}?{urllib.parse.urlencode({'pageSize': '1'})}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "AURA-Desktop/1.0",
            "x-goog-api-key": k,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536)
            if resp.status != 200:
                return VerifyResult(
                    "unknown",
                    "Google returned an unexpected response. Try again in a moment.",
                )
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                data = {}
            # A valid key returns a models payload (even if empty list).
            if isinstance(data, dict) and ("models" in data or "error" not in data):
                return VerifyResult("ok", "Key verified")
            return VerifyResult(
                "unknown",
                "Google returned an unexpected response. Try again in a moment.",
            )
    except urllib.error.HTTPError as e:
        code = int(getattr(e, "code", 0) or 0)
        detail = _http_error_detail(e)
        if code in (400, 401, 403):
            return VerifyResult(
                "invalid",
                detail
                or "Google rejected this key. Get a new free key in Google AI Studio.",
            )
        if code == 429:
            # Key is accepted but rate-limited — treat as verified for onboarding.
            return VerifyResult("ok", "Key verified")
        return VerifyResult(
            "unknown",
            detail or f"Google returned HTTP {code}. Try again in a moment.",
        )
    except urllib.error.URLError:
        return VerifyResult(
            "network",
            "Couldn’t reach Google. Check your connection and try again.",
        )
    except TimeoutError:
        return VerifyResult(
            "network",
            "Couldn’t reach Google. Check your connection and try again.",
        )
    except Exception:
        return VerifyResult(
            "unknown",
            "Couldn’t verify this key right now. Try again in a moment.",
        )


def _http_error_detail(err: urllib.error.HTTPError) -> str:
    """Parse Google JSON error into a short user-facing line (never include key)."""
    try:
        raw = err.read(4096)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        msg = (
            (data.get("error") or {}).get("message")
            if isinstance(data, dict)
            else None
        )
        if not msg or not isinstance(msg, str):
            return ""
        lower = msg.lower()
        if "api key" in lower or "permission" in lower or "credential" in lower:
            return "Google rejected this key. Get a new free key in Google AI Studio."
        if "billing" in lower or "quota" in lower:
            return (
                "This key is restricted or out of quota. "
                "Check Google AI Studio and try a fresh key."
            )
        # Keep message short; strip anything that might echo the key.
        clean = msg.replace("\n", " ").strip()
        if len(clean) > 160:
            clean = clean[:157] + "…"
        return clean
    except Exception:
        return ""
