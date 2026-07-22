"""Tests for cross-device power intent parsing and honesty helpers."""

from __future__ import annotations

from core.remote_intent import (
    parse_remote_power_intent,
    should_redirect_local_power,
    tool_result_ok,
    wants_remote_target,
)


def test_shutdown_windows_from_mac_phrase():
    intent = parse_remote_power_intent("выключи Windows")
    assert intent is not None
    assert intent.action == "shutdown"
    assert intent.platform == "windows"
    assert intent.confirmed is False
    args = intent.to_dispatch_args()
    assert args["platform"] == "windows"
    assert args["kind"] == "computer_settings"
    assert args["action"] == "shutdown"


def test_turn_off_pc_english():
    intent = parse_remote_power_intent("turn off the Windows PC")
    assert intent is not None
    assert intent.platform == "windows"
    assert intent.action == "shutdown"


def test_turn_off_mac_english():
    intent = parse_remote_power_intent("turn off mac")
    assert intent is not None
    assert intent.platform == "mac"
    assert intent.action == "shutdown"


def test_shutdown_mac_from_windows():
    intent = parse_remote_power_intent("выключи макбук")
    assert intent is not None
    assert intent.platform == "mac"
    assert intent.action == "shutdown"


def test_both_devices():
    intent = parse_remote_power_intent("отключи оба компьютера")
    assert intent is not None
    assert intent.all_devices or intent.platform == "all"
    assert intent.to_dispatch_args()["platform"] == "all"


def test_local_only_not_remote():
    assert parse_remote_power_intent("выключи этот компьютер") is None
    assert parse_remote_power_intent("shutdown this mac") is None


def test_plain_local_shutdown_not_stolen():
    # Ambiguous local ask — must stay local (no remote marker).
    assert parse_remote_power_intent("выключи компьютер") is None
    assert parse_remote_power_intent("выключи ноутбук") is None


def test_redirect_when_live_picked_local():
    redir = should_redirect_local_power("shutdown", "выключи windows пожалуйста")
    assert redir is not None
    assert redir.platform == "windows"
    assert redir.action == "shutdown"


def test_no_redirect_for_local_phrase():
    assert should_redirect_local_power("shutdown", "выключи этот компьютер") is None
    assert should_redirect_local_power("volume_up", "сделай громче") is None


def test_wants_remote_target():
    assert wants_remote_target("открой chrome на windows")
    assert not wants_remote_target("открой chrome на этом компьютере")


def test_tool_result_ok_honesty():
    assert tool_result_ok("Shutdown scheduled on Gaming PC.") is True
    assert tool_result_ok("Please confirm by calling again with confirmed=yes.") is False
    assert tool_result_ok("Target blocks remote system power actions") is False
    assert tool_result_ok("Sign in required to control other devices.") is False
    assert tool_result_ok("") is False
