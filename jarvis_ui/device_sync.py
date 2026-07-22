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
_JOB_POLL_INTERVAL = 5.0
_ONLINE_HINT_S = 90.0

DEFAULT_PERMISSIONS: dict[str, bool] = {
    "allow_remote_control": True,
    "allow_remote_files": False,
    "allow_remote_system": False,
    # Software KVM (built into AURA) — LAN shared keyboard & mouse.
    "allow_kvm_input": False,
}

# Kinds that need allow_remote_control on the target (or this machine when executing).
_CONTROL_KINDS = {
    "open_url",
    "open_app",
    "close_app",
    "close_all_apps",
    "browser_control",
    "computer_control",
    "agent_task",
}
_FILE_KINDS = {"file_controller"}
_SYSTEM_KINDS = {"computer_settings"}
_SYSTEM_DANGEROUS = {
    "shutdown",
    "restart",
    "reboot",
    "sleep",
    "hibernate",
    "lock",
    "logout",
    "log_out",
    "sign_out",
}


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


def get_local_permissions() -> dict[str, bool]:
    data = _load_identity()
    raw = data.get("permissions")
    out = dict(DEFAULT_PERMISSIONS)
    if isinstance(raw, dict):
        for k in DEFAULT_PERMISSIONS:
            if k in raw:
                out[k] = bool(raw[k])
    return out


def set_local_permissions(permissions: dict[str, bool]) -> dict[str, bool]:
    data = _load_identity()
    data["device_key"] = get_device_key()
    merged = get_local_permissions()
    for k in DEFAULT_PERMISSIONS:
        if k in permissions:
            merged[k] = bool(permissions[k])
    data["permissions"] = merged
    _save_identity(data)
    return merged


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
        "permissions": get_local_permissions(),
    }
    # Best-effort LAN hint for KVM peers (backend may ignore unknown fields).
    try:
        from jarvis_ui.kvm.net import local_lan_ip

        lan = local_lan_ip()
        if lan:
            body["lan_ip"] = lan
    except Exception:
        pass
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


def patch_remote_permissions(device_id: str, permissions: dict[str, bool]) -> dict[str, Any]:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token:
        raise RuntimeError("Sign in required")
    return UA._http_json(
        "PATCH",
        "/api/devices",
        body={"device_id": device_id, "permissions": permissions},
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


def get_job_status(job_id: str) -> dict[str, Any] | None:
    from jarvis_ui import user_account as UA

    token = UA.get_access_token()
    if not token or not job_id:
        return None
    data = UA._http_json("GET", f"/api/devices/jobs/{job_id}", token=token)
    job = data.get("job")
    return job if isinstance(job, dict) else None


def wait_for_job(
    job_id: str,
    *,
    timeout_s: float = 45.0,
    poll_s: float = 2.0,
) -> dict[str, Any]:
    """Block until job is done/failed or timeout. Returns last known job dict."""
    deadline = time.time() + max(3.0, timeout_s)
    last: dict[str, Any] = {"id": job_id, "status": "queued"}
    while time.time() < deadline:
        try:
            cur = get_job_status(job_id)
            if cur:
                last = cur
                st = str(cur.get("status") or "")
                if st in {"done", "failed", "cancelled"}:
                    return cur
        except Exception:
            pass
        time.sleep(poll_s)
    return last


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


def _permission_denied(kind: str, need: str) -> tuple[bool, str]:
    return (
        False,
        f"Remote '{kind}' blocked on this device — enable {need} in Devices settings.",
    )


def _result_is_failure(text: str) -> bool:
    low = (text or "").lower()
    needles = (
        "please confirm",
        "could not",
        "failed",
        "unknown action",
        "missing ",
        "blocked",
        "not found",
        "no application",
        "sign in required",
        "needs app_name",
        "needs a url",
        "needs a goal",
        "unavailable",
    )
    return any(n in low for n in needles)


def execute_job(job: dict[str, Any]) -> tuple[bool, str]:
    """Run one claimed remote job on this machine (respects local permissions)."""
    kind = str(job.get("kind") or "").strip().lower()
    payload = job.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    perms = get_local_permissions()

    try:
        if kind == "kvm_invite":
            if not perms.get("allow_kvm_input", False):
                return _permission_denied(kind, "Allow shared keyboard & mouse (KVM)")
            from jarvis_ui.kvm import get_kvm_manager

            snap = get_kvm_manager().accept_invite(payload)
            if snap.status.value == "running":
                return True, f"KVM client connected to {snap.peer_host}:{snap.port}"
            return False, snap.message or "KVM invite failed"

        if kind == "kvm_stop":
            if not perms.get("allow_kvm_input", False):
                return _permission_denied(kind, "Allow shared keyboard & mouse (KVM)")
            from jarvis_ui.kvm import get_kvm_manager

            get_kvm_manager().stop()
            return True, "KVM stopped"

        if kind in _CONTROL_KINDS and not perms.get("allow_remote_control", True):
            return _permission_denied(kind, "Allow remote control")

        if kind in _FILE_KINDS and not perms.get("allow_remote_files", False):
            return _permission_denied(kind, "Allow remote files")

        if kind in _SYSTEM_KINDS:
            action = str(payload.get("action") or "").strip().lower()
            if action in _SYSTEM_DANGEROUS and not perms.get("allow_remote_system", False):
                return _permission_denied(kind, "Allow remote system (shutdown/lock)")
            if not perms.get("allow_remote_control", True) and action not in _SYSTEM_DANGEROUS:
                # Soft settings (volume etc.) still need remote control.
                return _permission_denied(kind, "Allow remote control")

        if kind == "open_url":
            url = str(payload.get("url") or "").strip()
            if not url:
                return False, "missing url"
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return True, f"opened {url}"

        if kind == "open_app":
            from actions.open_app import open_app

            app_name = str(payload.get("app_name") or payload.get("name") or "").strip()
            if not app_name:
                return False, "missing app_name"
            out = open_app(parameters={"app_name": app_name})
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "close_app":
            from actions.computer_settings import computer_settings

            app_name = str(payload.get("app_name") or payload.get("name") or "").strip()
            out = computer_settings(
                parameters={
                    "action": "close_app",
                    "app_name": app_name,
                    "confirmed": payload.get("confirmed"),
                }
            )
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "close_all_apps":
            from actions.computer_settings import computer_settings

            out = computer_settings(
                parameters={
                    "action": "close_all_apps",
                    "confirmed": payload.get("confirmed") or "yes",
                }
            )
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "browser_control":
            from actions.browser_control import browser_control

            action = str(payload.get("action") or "go_to")
            args = dict(payload)
            args["action"] = action
            out = browser_control(parameters=args)
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "computer_control":
            from actions.computer_control import computer_control

            out = computer_control(parameters=dict(payload))
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "computer_settings":
            from actions.computer_settings import computer_settings

            out = computer_settings(parameters=dict(payload))
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "file_controller":
            from actions.file_controller import file_controller

            action = str(payload.get("action") or "").strip().lower()
            if action in {"delete", "remove", "rm"} and not perms.get(
                "allow_remote_files", False
            ):
                return _permission_denied(kind, "Allow remote files")
            out = file_controller(parameters=dict(payload))
            text = str(out)[:500]
            return (not _result_is_failure(text), text)

        if kind == "agent_task":
            from agent.task_queue import TaskPriority, get_queue

            goal = str(payload.get("goal") or payload.get("description") or "").strip()
            if not goal:
                return False, "missing goal"
            # Soft constraints so a remote agent cannot outrun the Devices toggles.
            constraints: list[str] = []
            if not perms.get("allow_remote_files", False):
                constraints.append(
                    "Do not use file tools; do not read, write, move, or delete files."
                )
            if not perms.get("allow_remote_system", False):
                constraints.append(
                    "Do not shut down, restart, sleep, lock, or log out this computer."
                )
            if constraints:
                goal = goal + "\n\nREMOTE PERMISSION CONSTRAINTS:\n- " + "\n- ".join(
                    constraints
                )
            priority_map = {
                "low": TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high": TaskPriority.HIGH,
            }
            pri = priority_map.get(
                str(payload.get("priority") or "normal").lower(),
                TaskPriority.NORMAL,
            )
            task_id = get_queue().submit(goal=goal, priority=pri, speak=None)
            return True, f"Remote agent task started (ID: {task_id}): {goal[:160]}"

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
        self._last_job_msg = ""
        self._lock = threading.Lock()
        self._last_heartbeat_at = 0.0

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
                "permissions": get_local_permissions(),
                "devices": list(self._last_devices),
                "error": self._last_error,
                "last_job": self._last_job_msg,
            }

    def refresh_now(self) -> dict[str, Any]:
        self._tick(force_heartbeat=True)
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
                self._tick(force_heartbeat=False)
            except Exception as e:
                with self._lock:
                    self._last_error = str(e)
            self._stop.wait(_JOB_POLL_INTERVAL)

    def _tick(self, *, force_heartbeat: bool) -> None:
        from jarvis_ui import user_account as UA

        if not UA.is_authenticated():
            with self._lock:
                self._last_devices = []
                self._last_error = "Sign in to link devices"
            return

        now = time.time()
        need_hb = force_heartbeat or (now - self._last_heartbeat_at) >= _HEARTBEAT_INTERVAL
        if need_hb:
            try:
                heartbeat()
                devices = list_devices()
                with self._lock:
                    self._last_devices = devices
                    self._last_error = ""
                self._last_heartbeat_at = now
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
            kind = str(job.get("kind") or "")
            self._log(f"Devices: running remote job {kind}…")
            ok, detail = execute_job(job)
            try:
                finish_job(jid, ok=ok, result=detail if ok else "", error="" if ok else detail)
            except Exception as e:
                self._log(f"Devices: finish job failed — {e}")
            msg = (
                f"Devices: remote job {kind} → "
                f"{'ok' if ok else 'fail'} ({detail[:80]})"
            )
            with self._lock:
                self._last_job_msg = msg
            self._log(msg)


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
