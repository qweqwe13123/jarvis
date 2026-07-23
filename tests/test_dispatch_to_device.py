"""Unit tests for multi-device target resolution, kind inference, app lifecycle."""

from unittest.mock import MagicMock, patch

from actions.app_lifecycle import process_hints_for_app
from actions.dispatch_to_device import (
    _infer_kind,
    _kind_allowed,
    _wants_all_devices,
    dispatch_to_device,
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

DEVICES_SYSTEM_OK = [
    {
        "id": "mac",
        "name": "MacBook",
        "platform": "darwin",
        "online": True,
        "isThisDevice": True,
        "permissions": {
            "allow_remote_control": True,
            "allow_remote_system": True,
        },
    },
    {
        "id": "win",
        "name": "DESKTOP-3N4H07I",
        "platform": "win32",
        "online": True,
        "isThisDevice": False,
        "permissions": {
            "allow_remote_control": True,
            "allow_remote_files": False,
            "allow_remote_system": True,
        },
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
    # System power is allowed to enqueue — target shows JIT prompt.
    assert _kind_allowed("computer_settings", perms, {"action": "shutdown"}) is None
    assert (
        _kind_allowed(
            "computer_settings",
            perms,
            {"action": "shutdown"},
            jit_system=False,
        )
        is not None
    )
    assert _kind_allowed("computer_settings", perms, {"action": "volume"}) is None


def test_yandex_aliases_present():
    assert "yandex" in _APP_ALIASES
    assert "яндекс браузер" in _APP_ALIASES
    assert "yandex" in process_hints_for_app("Yandex Browser")
    # Normalization should resolve to an OS-specific launch name.
    assert _normalize("яндекс")


def _mock_auth_and_devices(devices):
    ua = patch("jarvis_ui.user_account.is_authenticated", return_value=True)
    sync = MagicMock()
    sync.refresh_now.return_value = {"devices": devices}
    ds = patch("jarvis_ui.device_sync.start_device_sync", return_value=sync)
    return ua, ds, sync


def test_remote_shutdown_no_confirm_roundtrip():
    """Mac→Windows shutdown must enqueue immediately (no 'call again with confirmed')."""
    ua, ds, _sync = _mock_auth_and_devices(DEVICES_SYSTEM_OK)
    with ua, ds:
        with patch(
            "jarvis_ui.device_sync.enqueue_job",
            return_value={"job": {"id": "job-1"}},
        ) as enq:
            with patch(
                "jarvis_ui.device_sync.wait_for_job",
                return_value={"status": "done", "result": "Shutting down…"},
            ):
                out = dispatch_to_device(
                    parameters={
                        "platform": "windows",
                        "kind": "computer_settings",
                        "action": "shutdown",
                    }
                )
    assert "call again" not in out.lower()
    assert "confirmed=yes" not in out.lower()
    assert "DESKTOP-3N4H07I" in out or "Done" in out
    enq.assert_called_once()
    _device_id, kind, payload = enq.call_args[0]
    assert _device_id == "win"
    assert kind == "computer_settings"
    assert payload.get("action") == "shutdown"
    assert str(payload.get("confirmed")).lower() in {"yes", "true", "1"}
    assert payload.get("source_device_name") == "MacBook"


def test_remote_shutdown_enqueues_when_system_permission_off():
    """Missing Allow remote system → still enqueues and succeeds (same-account trust)."""
    ua, ds, _sync = _mock_auth_and_devices(DEVICES)
    with ua, ds:
        with patch(
            "jarvis_ui.device_sync.enqueue_job",
            return_value={"job": {"id": "job-jit"}},
        ) as enq:
            with patch(
                "jarvis_ui.device_sync.wait_for_job",
                return_value={"status": "done", "result": "Done: shutdown."},
            ):
                out = dispatch_to_device(
                    parameters={
                        "platform": "windows",
                        "kind": "computer_settings",
                        "action": "shutdown",
                    }
                )
    enq.assert_called_once()
    assert "call again" not in out.lower()
    assert "shutdown" in out.lower() or "Done" in out


def test_remote_shutdown_from_intent_args():
    from core.remote_intent import parse_remote_power_intent

    intent = parse_remote_power_intent("выключи windows компьютер")
    assert intent is not None
    ua, ds, _sync = _mock_auth_and_devices(DEVICES_SYSTEM_OK)
    with ua, ds:
        with patch(
            "jarvis_ui.device_sync.enqueue_job",
            return_value={"job": {"id": "job-2"}},
        ) as enq:
            with patch(
                "jarvis_ui.device_sync.wait_for_job",
                return_value={"status": "done", "result": "ok"},
            ):
                out = dispatch_to_device(parameters=intent.to_dispatch_args())
    assert "call again" not in out.lower()
    enq.assert_called_once()
    assert enq.call_args[0][2].get("confirmed") == "yes"


def test_both_devices_shutdown_fans_out_local_and_remote():
    """platform=all shuts down this device locally + enqueues each remote."""
    ua, ds, _sync = _mock_auth_and_devices(DEVICES_SYSTEM_OK)
    with ua, ds:
        with patch("actions.computer_settings.computer_settings", return_value="Done: shutdown.") as local_cs:
            with patch(
                "jarvis_ui.device_sync.enqueue_job",
                return_value={"job": {"id": "job-all"}},
            ) as enq:
                with patch(
                    "jarvis_ui.device_sync.wait_for_job",
                    return_value={"status": "done", "result": "Done: shutdown."},
                ):
                    out = dispatch_to_device(
                        parameters={
                            "platform": "all",
                            "kind": "computer_settings",
                            "action": "shutdown",
                        }
                    )
    # Local device executed directly; remote device enqueued once.
    local_cs.assert_called_once()
    enq.assert_called_once()
    assert enq.call_args[0][0] == "win"
    assert "MacBook" in out and "DESKTOP-3N4H07I" in out


# --- Target-side execution (same-account trust, no external UI module) ---

_PERMS_SYSTEM_OFF = {
    "allow_remote_control": True,
    "allow_remote_files": False,
    "allow_remote_system": False,
    "allow_kvm_input": False,
}


def test_execute_job_shutdown_runs_even_with_system_off():
    from jarvis_ui.device_sync import execute_job

    job = {
        "kind": "computer_settings",
        "payload": {"action": "shutdown", "confirmed": "yes", "source_device_name": "MacBook"},
    }
    with patch("jarvis_ui.device_sync.get_local_permissions", return_value=_PERMS_SYSTEM_OFF):
        with patch("actions.computer_settings.computer_settings", return_value="Done: shutdown.") as cs:
            ok, text = execute_job(job)
    assert ok is True
    cs.assert_called_once()
    assert cs.call_args.kwargs["parameters"]["confirmed"] == "yes"
    assert cs.call_args.kwargs["parameters"]["action"] == "shutdown"


def test_execute_job_restart_normalizes_reboot():
    from jarvis_ui.device_sync import execute_job

    job = {"kind": "computer_settings", "payload": {"action": "reboot"}}
    with patch("jarvis_ui.device_sync.get_local_permissions", return_value=_PERMS_SYSTEM_OFF):
        with patch("actions.computer_settings.computer_settings", return_value="Done: restart.") as cs:
            ok, _text = execute_job(job)
    assert ok is True
    assert cs.call_args.kwargs["parameters"]["action"] == "restart"
    assert cs.call_args.kwargs["parameters"]["confirmed"] == "yes"
