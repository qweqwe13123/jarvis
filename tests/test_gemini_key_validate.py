"""Unit tests for onboarding Gemini key format + verify mapping."""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

from jarvis_ui.onboarding.gemini_key import (
    format_error_message,
    looks_like_gemini_key,
    normalize_key,
    verify_gemini_key,
)


def test_normalize_strips_whitespace_and_zwsp():
    assert normalize_key("  AIza\u200bSyAb Cd\nEf  ") == "AIzaSyAbCdEf"
    assert normalize_key("  AQ.Ab8RN6J7g5P.Seg  ") == "AQ.Ab8RN6J7g5P.Seg"


def test_looks_like_rejects_garbage():
    assert not looks_like_gemini_key("")
    assert not looks_like_gemini_key("hello")
    assert not looks_like_gemini_key("sk-openai-style-key-123456789012345")
    assert not looks_like_gemini_key("AIzaShort")
    assert not looks_like_gemini_key("AQ.")
    assert not looks_like_gemini_key("AQ.short")


def test_looks_like_accepts_legacy_aiza():
    key = "AIza" + ("SyA" + "x" * 32)
    assert looks_like_gemini_key(key)


def test_looks_like_accepts_auth_key_aq():
    assert looks_like_gemini_key("AQ.Ab8RN6J7g5P.SegmentExtra")
    assert looks_like_gemini_key("AQ.Ab8RN6J7g5P_extra-key1")
    # Typical AI Studio auth key shape
    assert looks_like_gemini_key("AQ." + ("Ab8RN6J7g5P" * 2))


def test_verify_format_fail_no_network():
    r = verify_gemini_key("hello world")
    assert r.status == "invalid"
    assert "google ai studio" in r.message.lower() or "look" in r.message.lower()
    assert "AIza" not in format_error_message()  # neutral copy


def test_verify_ok_models_list_legacy():
    key = "AIza" + ("SyA" + "x" * 32)
    payload = json.dumps({"models": [{"name": "models/gemini-2.0-flash"}]}).encode()

    class _Resp:
        status = 200

        def read(self, _n=-1):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()) as mocked:
        r = verify_gemini_key(key)
        req = mocked.call_args[0][0]
        assert req.get_header("X-goog-api-key") == key
    assert r.ok
    assert r.status == "ok"


def test_verify_ok_models_list_auth_key():
    key = "AQ.Ab8RN6J7g5P.TestSegmentExtra"
    payload = json.dumps({"models": [{"name": "models/gemini-2.0-flash"}]}).encode()

    class _Resp:
        status = 200

        def read(self, _n=-1):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()):
        r = verify_gemini_key(key)
    assert r.ok
    assert r.status == "ok"


def test_verify_invalid_http_403():
    key = "AIza" + ("SyA" + "x" * 32)
    body = json.dumps(
        {"error": {"message": "API key not valid. Please pass a valid API key."}}
    ).encode()
    err = urllib.error.HTTPError(
        url="https://example",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=BytesIO(body),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        r = verify_gemini_key(key)
    assert r.status == "invalid"
    assert "rejected" in r.message.lower() or "key" in r.message.lower()


def test_verify_network_error():
    key = "AQ.Ab8RN6J7g5P.TestSegmentExtra"
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("timed out"),
    ):
        r = verify_gemini_key(key)
    assert r.status == "network"
