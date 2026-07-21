"""Unit tests for multi-device target resolution."""

from actions.dispatch_to_device import resolve_target_device


DEVICES = [
    {
        "id": "1",
        "name": "Office Mac",
        "platform": "darwin",
        "online": True,
        "isThisDevice": True,
    },
    {
        "id": "2",
        "name": "Gaming PC",
        "platform": "win32",
        "online": True,
        "isThisDevice": False,
    },
    {
        "id": "3",
        "name": "Old Laptop",
        "platform": "win32",
        "online": False,
        "isThisDevice": False,
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
