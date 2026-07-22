"""Unit tests for Ollama pull progress helpers + model catalog."""

from __future__ import annotations

from jarvis_ui.local_ai.ollama_client import (
    PullProgress,
    format_bytes,
    friendly_pull_status,
)
from jarvis_ui.model_catalog import ModelOption, available_models, find_option


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert "KB" in format_bytes(2048)
    assert format_bytes(420 * 1024 * 1024) == "420 MB"
    assert "GB" in format_bytes(int(1.3 * 1024 * 1024 * 1024))


def test_friendly_pull_status():
    assert "info" in friendly_pull_status("pulling manifest").lower() or "Fetch" in friendly_pull_status(
        "pulling manifest"
    )
    assert "Verif" in friendly_pull_status("verifying sha256 digest")
    assert friendly_pull_status("success") == "Finished"


def test_pull_progress_dataclass():
    p = PullProgress(status="downloading", completed=100, total=200, fraction=0.5)
    assert p.completed == 100
    assert p.total == 200
    assert p.fraction == 0.5


def test_catalog_has_auto_no_live_voice():
    models = available_models()
    titles = [m.title for m in models]
    assert "Auto" in titles
    assert "Live Voice" not in titles
    assert all(isinstance(m, ModelOption) for m in models)


def test_find_option_auto():
    opt = find_option("auto")
    assert opt is not None
    assert opt.id == "auto"
