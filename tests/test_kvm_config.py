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


def _trusted_perms(monkeypatch):
    import jarvis_ui.device_sync as DS
    import jarvis_ui.kvm.permission as P

    monkeypatch.setattr(DS, "get_local_permissions", lambda: {"allow_kvm_input": True})
    monkeypatch.setattr(P, "input_trusted", lambda: True)


def test_start_server_then_stop(monkeypatch):
    from jarvis_ui.kvm import KvmManager, KvmRole

    _trusted_perms(monkeypatch)
    m = KvmManager()
    snap = m.start(role=KvmRole.SERVER, peer_host="", layout="peer_left", invite_peer=False)
    try:
        assert snap.status.value == "running"
        assert snap.role == KvmRole.SERVER
        assert snap.port == 24900
    finally:
        stopped = m.stop()
    assert stopped.status.value == "stopped"


def test_role_enum_is_honored_not_defaulted(monkeypatch):
    """Passing a KvmRole enum must not silently fall back to SERVER."""
    from jarvis_ui.kvm import KvmManager, KvmRole

    _trusted_perms(monkeypatch)
    m = KvmManager()
    # Client with no host is invalid → error, but role stays CLIENT intent.
    snap = m.start(role=KvmRole.CLIENT, peer_host="", invite_peer=False)
    assert snap.status.value == "error"
    assert "LAN IP" in snap.message or "hostname" in snap.message


def test_client_needs_host(monkeypatch):
    from jarvis_ui.kvm import KvmManager, KvmRole

    _trusted_perms(monkeypatch)
    m = KvmManager()
    snap = m.start(role="client", peer_host="", invite_peer=False)
    assert snap.status.value == "error"


def test_blocks_without_input_permission(monkeypatch):
    import jarvis_ui.device_sync as DS
    import jarvis_ui.kvm.permission as P
    from jarvis_ui.kvm import KvmManager, KvmRole

    monkeypatch.setattr(DS, "get_local_permissions", lambda: {"allow_kvm_input": True})
    monkeypatch.setattr(P, "input_trusted", lambda: False)
    m = KvmManager()
    snap = m.start(role=KvmRole.SERVER, invite_peer=False)
    assert snap.status.value == "error"
    assert snap.needs_input_permission is True


def test_blocks_without_kvm_permission(monkeypatch):
    import jarvis_ui.device_sync as DS
    from jarvis_ui.kvm import KvmManager, KvmRole

    monkeypatch.setattr(DS, "get_local_permissions", lambda: {"allow_kvm_input": False})
    m = KvmManager()
    snap = m.start(role=KvmRole.SERVER, invite_peer=False)
    assert snap.status.value == "error"


def test_permission_helper_non_darwin(monkeypatch):
    import jarvis_ui.kvm.permission as P

    monkeypatch.setattr(P, "_OS", "Windows")
    assert P.input_trusted() is True
