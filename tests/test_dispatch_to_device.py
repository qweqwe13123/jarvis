"""Unit tests for multi-device target resolution, kind inference, app lifecycle."""

from actions.app_lifecycle import process_hints_for_app
from actions.dispatch_to_device import (
    _infer_kind,
    _kind_allowed,
    _wants_all_devices,
    resolve_all_targets,
    resolve_target_device,
)
from actions.open_app import _APP_ALIASES, _normalize


DEVICES = [
    {
        "id": "1",
        "name": "Office Mac",
        "platform": "darwin",
        "online": True,
        "isThisDevice": True,
        "permissions": {"allow_remote_control": True, "allow_remote_system": True},
    },
    {
        "id": "2",
        "name": "Gaming PC",
        "platform": "win32",
        "online": True,
        "isThisDevice": False,
        "permissions": {
            "allow_remote_control": True,
            "allow_remote_files": False,
            "allow_remote_system": False,
        },
    },
    {
        "id": "3",
        "name": "Old Laptop",
        "platform": "win32",
        "online": False,
        "isThisDevice": False,
        "permissions": {"allow_remote_control": False},
    },
]


def test_resolve_prefers_online_windows():
    t = resolve_target_device(DEVICES, platform="windows")
    assert t is not None
    assert t["id"] == "2"


def test_resolve_by_partial_name():
    t = resolve_target_device(DEVICES, device_name="gaming")
    assert t is not None
    assert t["id"] == "2"


def test_resolve_by_id():
    t = resolve_target_device(DEVICES, device_id="3")
    assert t is not None
    assert t["id"] == "3"


def test_resolve_mac_this_device():
    t = resolve_target_device(DEVICES, platform="mac")
    assert t is not None
    assert t["id"] == "1"


def test_resolve_empty():
    assert resolve_target_device([], platform="windows") is None


def test_resolve_all_targets():
    ids = [d["id"] for d in resolve_all_targets(DEVICES)]
    assert "1" in ids and "2" in ids


def test_wants_all_devices():
    assert _wants_all_devices({"platform": "all"})
    assert _wants_all_devices({"platform": "оба"})
    assert _wants_all_devices({"all_devices": True})
    assert not _wants_all_devices({"platform": "windows"})


def test_infer_kinds():
    assert _infer_kind({}, "https://x.com") == "open_url"
    assert _infer_kind({"app_name": "Chrome"}, "") == "open_app"
    assert _infer_kind({"goal": "clean desktop"}, "") == "agent_task"
    assert _infer_kind({"action": "delete", "path": "x"}, "") == "file_controller"
    assert _infer_kind({"action": "close_app", "app_name": "Yandex"}, "") == "close_app"
    assert _infer_kind({"action": "close_all_apps"}, "") == "close_all_apps"
    assert _infer_kind({"action": "shutdown"}, "") == "computer_settings"


def test_kind_allowed_blocks_files_and_system():
    perms = {
        "allow_remote_control": True,
        "allow_remote_files": False,
        "allow_remote_system": False,
    }
    assert _kind_allowed("open_url", perms, {}) is None
    assert _kind_allowed("close_app", perms, {"app_name": "Chrome"}) is None
    assert _kind_allowed("file_controller", perms, {"action": "list"}) is not None
    assert _kind_allowed("computer_settings", perms, {"action": "shutdown"}) is not None
    assert _kind_allowed("computer_settings", perms, {"action": "volume"}) is None


def test_yandex_aliases_present():
    assert "yandex" in _APP_ALIASES
    assert "яндекс браузер" in _APP_ALIASES
    assert "yandex" in process_hints_for_app("Yandex Browser")
    # Normalization should resolve to an OS-specific launch name.
    assert _normalize("яндекс")
