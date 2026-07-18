"""Tests for forced update policy (min version / release index)."""

from __future__ import annotations

import os

from core.updater.manifest import force_update_required


def test_min_supported_version_blocks_older():
    required, label = force_update_required(
        {"version": "1.0.15", "min_supported_version": "1.0.13"},
        local_version="1.0.12",
        local_index=12,
    )
    assert required is True
    assert label == "1.0.13"


def test_current_version_allowed():
    required, _ = force_update_required(
        {
            "version": "1.0.15",
            "release_index": 15,
            "min_release_index": 13,
            "min_supported_version": "",
        },
        local_version="1.0.15",
        local_index=15,
    )
    assert required is False


def test_release_index_window_blocks_three_behind():
    # latest=15, min=13 → index 12 is forced
    required, _ = force_update_required(
        {
            "version": "1.0.15",
            "release_index": 15,
            "min_release_index": 13,
        },
        local_version="1.0.12",
        local_index=12,
    )
    assert required is True


def test_simulate_env_forces(monkeypatch):
    monkeypatch.setenv("AURA_SIMULATE_FORCE_UPDATE", "1")
    required, label = force_update_required(
        {"version": "1.0.15"},
        local_version="1.0.15",
        local_index=15,
    )
    assert required is True
    assert label == "1.0.15"
    monkeypatch.delenv("AURA_SIMULATE_FORCE_UPDATE", raising=False)


def test_explicit_min_beats_index():
    required, label = force_update_required(
        {
            "version": "1.0.15",
            "release_index": 15,
            "min_release_index": 10,
            "min_supported_version": "1.0.14",
        },
        local_version="1.0.13",
        local_index=13,
    )
    assert required is True
    assert label == "1.0.14"
