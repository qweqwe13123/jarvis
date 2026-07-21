"""Multi-device presence + remote job client for the AURA desktop."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import uuid
import webbrowser
from typing import Any, Callable

from jarvis_ui.paths import support_dir

_DEVICE_PATH = support_dir() / "device_identity.json"
_HEARTBEAT_INTERVAL = 25.0
_ONLINE_HINT_S = 90.0


def _load_identity() -> dict:
    if not _DEVICE_PATH.exists():
        return {}
    try:
        return json.loads(_DEVICE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_identity(data: dict) -> None:
    _DEVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DEVICE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        _DEVICE_PATH.chmod(0o600)
    except Exception:
        pass


def get_device_key() -> str:
    """Stable per-install id (survives updates; lives in Application Support)."""
    data = _load_identity()
    key = str(data.get("device_key") or "").strip()
    if key:
        return key
    key = str(uuid.uuid4())
    data["device_key"] = key
    data["created_at"] = time.time()
    _save_identity(data)
    return key


def default_device_name() -> str:
    data = _load_identity()
    custom = str(data.get("display_name") or "").strip()
    if custom:
        return custom
    host = socket.gethostname().split(".")[0] or "Device"
    if sys.platform == "darwin":
        return f"{host} (Mac)"
    if sys.platform == "win32":
        return f"{host} (Windows)"
    return f"{host} (Linux)"


def set_device_display_name(name: str) -> None:
    data = _load_identity()
    data["device_key"] = get_device_key()
    data["display_name"] = (name or "").strip()[:64]
    _save_identity(data)


def _app_version() -> str:
    try:
        from core.version import VERSION

        return str(VERSION)
    except Exception:
        return ""


def heartbeat() -> dict[str, Any]:
    """Register / refresh this install as online. Requires signed-in account."""
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        raise RuntimeError("Sign in to link this device")
    body = {
        "device_key": get_device_key(),
        "name": default_device_name(),
        "platform": sys.platform,
        "app_version": _app_version(),
    }
    return UA._http_json("POST", "/api/devices/heartbeat", body=body, token=token)


def list_devices() -> list[dict[str, Any]]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        return []
    key = get_device_key()
    data = UA._http_json(
        "GET", f"/api/devices?device_key={key}", token=token
    )
    return list(data.get("devices") or [])


def rename_remote_device(device_id: str, name: str) -> dict[str, Any]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        raise RuntimeError("Sign in required")
    return UA._http_json(
        "PATCH",
        "/api/devices",
        body={"device_id": device_id, "name": name},
        token=token,
    )


def revoke_remote_device(device_id: str) -> dict[str, Any]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        raise RuntimeError("Sign in required")
    return UA._http_json(
        "DELETE", f"/api/devices?device_id={device_id}", token=token
    )


def enqueue_job(
    target_device_id: str,
    kind: str,
    payload: dict | None = None,
) -> dict[str, Any]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        raise RuntimeError("Sign in required")
    return UA._http_json(
        "POST",
        "/api/devices/jobs",
        body={
            "target_device_id": target_device_id,
            "source_device_key": get_device_key(),
            "kind": kind,
            "payload": payload or {},
        },
        token=token,
    )


def poll_jobs() -> list[dict[str, Any]]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        return []
    key = get_device_key()
    data = UA._http_json(
        "GET", f"/api/devices/jobs?device_key={key}&limit=5", token=token
    )
    return list(data.get("jobs") or [])


def finish_job(job_id: str, *, ok: bool, result: str = "", error: str = "") -> None:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        return
    UA._http_json(
        "PATCH",
        f"/api/devices/jobs/{job_id}",
        body={
            "status": "done" if ok else "failed",
            "result": result or None,
            "error": error or None,
        },
        token=token,
    )


def execute_job(job: dict[str, Any]) -> tuple[bool, str]:
    """Run one claimed remote job on this machine."""
    kind = str(job.get("kind") or "")
    payload = job.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        if kind == "open_url":
            url = str(payload.get("url") or "").strip()
            if not url:
                return False, "missing url"
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return True, f"opened {url}"

        if kind == "browser_control":
            from actions.browser_control import browser_control

            action = str(payload.get("action") or "go_to")
            args = dict(payload)
            args["action"] = action
            out = browser_control(args)
            return True, str(out)[:500]

        if kind == "computer_control":
            from actions.computer_control import computer_control

            out = computer_control(dict(payload))
            return True, str(out)[:500]

        return False, f"unknown kind: {kind}"
    except Exception as e:
        return False, str(e)


class DeviceSyncService:
    """Background heartbeat + job poller (daemon thread)."""

    def __init__(self, on_log: Callable[[str], None] | None = None):
        self._on_log = on_log or (lambda _m: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_devices: list[dict] = []
        self._last_error = ""
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="AuraDeviceSync"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "device_key": get_device_key(),
                "name": default_device_name(),
                "platform": sys.platform,
                "devices": list(self._last_devices),
                "error": self._last_error,
            }

    def refresh_now(self) -> dict[str, Any]:
        self._tick()
        return self.snapshot()

    def _log(self, msg: str) -> None:
        try:
            self._on_log(msg)
        except Exception:
            pass

    def _loop(self) -> None:
        # Stagger first beat slightly so UI paints first.
        self._stop.wait(2.0)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                with self._lock:
                    self._last_error = str(e)
            self._stop.wait(_HEARTBEAT_INTERVAL)

    def _tick(self) -> None:
        from jarvis_ui import user_account as UA

        if not UA.is_authenticated():
            with self._lock:
                self._last_devices = []
                self._last_error = "Sign in to link devices"
            return

        try:
            heartbeat()
            devices = list_devices()
            with self._lock:
                self._last_devices = devices
                self._last_error = ""
        except Exception as e:
            with self._lock:
                self._last_error = str(e)
            return

        try:
            jobs = poll_jobs()
        except Exception as e:
            self._log(f"Devices: job poll failed — {e}")
            return

        for job in jobs:
            jid = str(job.get("id") or "")
            ok, detail = execute_job(job)
            try:
                finish_job(jid, ok=ok, result=detail if ok else "", error="" if ok else detail)
            except Exception as e:
                self._log(f"Devices: finish job failed — {e}")
            self._log(
                f"Devices: remote job {job.get('kind')} → "
                f"{'ok' if ok else 'fail'} ({detail[:80]})"
            )


_service: DeviceSyncService | None = None


def get_sync_service() -> DeviceSyncService:
    global _service
    if _service is None:
        _service = DeviceSyncService()
    return _service


def start_device_sync(on_log: Callable[[str], None] | None = None) -> DeviceSyncService:
    svc = get_sync_service()
    if on_log:
        svc._on_log = on_log
    svc.start()
    return svc
