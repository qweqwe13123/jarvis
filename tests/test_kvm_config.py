"""Unit tests for KVM helpers (no external apps required)."""

from __future__ import annotations

from jarvis_ui.kvm.config import build_server_config, sanitize_screen_name
from jarvis_ui.kvm.net import looks_like_host
from jarvis_ui.kvm.protocol import decode_lines, encode


def test_sanitize_screen_name():
    assert sanitize_screen_name("My MacBook Pro") == "My-MacBook-Pro"
    assert sanitize_screen_name("!!!") == "screen"
    assert sanitize_screen_name("pc@home#1") == "pchome1"


def test_build_server_config_peer_right():
    text = build_server_config(
        server_name="Aura-Mac",
        client_name="Aura-PC",
        layout="peer_right",
    )
    assert "section: screens" in text
    assert "Aura-Mac:" in text
    assert "Aura-PC:" in text
    assert "right = Aura-PC" in text
    assert "left = Aura-Mac" in text
    assert "clipboardSharing = true" in text


def test_looks_like_host():
    assert looks_like_host("192.168.1.10")
    assert looks_like_host("macbook.local")
    assert looks_like_host("192.168.1.10:24800")
    assert not looks_like_host("")
    assert not looks_like_host("http://x")


def test_protocol_roundtrip():
    raw = encode({"type": "hello", "w": 100})
    msgs, rest = decode_lines(bytearray(raw))
    assert rest == bytearray()
    assert len(msgs) == 1
    assert msgs[0]["type"] == "hello"
    assert msgs[0]["w"] == 100


def test_manager_snapshot_native():
    from jarvis_ui.kvm import get_kvm_manager

    snap = get_kvm_manager().snapshot()
    assert snap.engine == "aura"
    assert snap.engine_label.startswith("AURA")
