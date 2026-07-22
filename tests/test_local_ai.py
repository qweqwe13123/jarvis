"""Tests for Local AI (Ollama) recommendation helpers."""

from __future__ import annotations

from jarvis_ui.local_ai.hardware import HardwareProfile
from jarvis_ui.local_ai.recommend import catalog_for_hardware, recommend_model


def _hw(**kwargs) -> HardwareProfile:
    base = dict(
        os_name="macOS",
        arch="arm64",
        ram_gb=16.0,
        disk_free_gb=40.0,
        apple_silicon=True,
        has_nvidia=False,
        cpu_cores=8,
        summary="macOS · Apple Silicon · 16 GB",
    )
    base.update(kwargs)
    return HardwareProfile(**base)


def test_recommend_low_ram():
    rec = recommend_model(_hw(ram_gb=6.0, apple_silicon=False))
    assert rec.tier == "light"
    assert "1b" in rec.model_id or rec.size_gb <= 2.0


def test_recommend_mid_ram():
    rec = recommend_model(_hw(ram_gb=16.0, apple_silicon=True))
    assert rec.model_id
    assert rec.size_gb > 0
    assert rec.label


def test_recommend_coding_prefers_coder():
    rec = recommend_model(_hw(ram_gb=24.0), prefer_coding=True)
    assert "coder" in rec.model_id or rec.tier == "coding"


def test_catalog_unique():
    cats = catalog_for_hardware(_hw(ram_gb=16.0))
    ids = [c.model_id for c in cats]
    assert len(ids) == len(set(ids))
    assert len(cats) >= 1


def test_disk_gate():
    rec = recommend_model(_hw(ram_gb=32.0, disk_free_gb=1.0))
    assert rec.ok_for_disk is False
