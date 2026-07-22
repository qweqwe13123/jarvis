"""High-level KVM manager — built into AURA (no external Barrier install)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from jarvis_ui.kvm import prefs as kvm_prefs
from jarvis_ui.kvm.net import local_lan_ip, looks_like_host
from jarvis_ui.kvm.protocol import DEFAULT_PORT
from jarvis_ui.paths import support_dir

_STATE_PATH = support_dir() / "kvm" / "state.json"
_LOG_PATH = support_dir() / "kvm" / "session.log"


class KvmRole(str, Enum):
    SERVER = "server"
    CLIENT = "client"


class KvmEngine(str, Enum):
    AURA = "aura"
    NONE = "none"


class KvmStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    MISSING = "missing"  # unused for native; kept for UI compat


@dataclass
class KvmSnapshot:
    status: KvmStatus
    role: KvmRole
    engine: str
    engine_label: str
    message: str
    peer_host: str
    peer_name: str
    peer_device_id: str
    layout: str
    port: int
    lan_ip: str
    pid: int | None
    download_url: str
    install_hint: str
    server_screen: str
    client_screen: str
    running_since: float | None = None
    connected: bool = False
    remote: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "role": self.role.value,
            "engine": self.engine,
            "engine_label": self.engine_label,
            "message": self.message,
            "peer_host": self.peer_host,
            "peer_name": self.peer_name,
            "peer_device_id": self.peer_device_id,
            "layout": self.layout,
            "port": self.port,
            "lan_ip": self.lan_ip,
            "pid": self.pid,
            "download_url": self.download_url,
            "install_hint": self.install_hint,
            "server_screen": self.server_screen,
            "client_screen": self.client_screen,
            "running_since": self.running_since,
            "connected": self.connected,
            "remote": self.remote,
        }


def _screen_size() -> tuple[int, int]:
    try:
        import pyautogui

        w, h = pyautogui.size()
        return int(w), int(h)
    except Exception:
        return 1920, 1080


def _ensure_dirs() -> None:
    (support_dir() / "kvm").mkdir(parents=True, exist_ok=True)


def _append_log(line: str) -> None:
    try:
        _ensure_dirs()
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")
    except Exception:
        pass


def _write_state(data: dict[str, Any]) -> None:
    _ensure_dirs()
    _STATE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class KvmManager:
    """Owns the in-process AURA KVM server or client."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._status = KvmStatus.STOPPED
        self._message = "Idle — built into AURA"
        self._running_since: float | None = None
        self._role = KvmRole.SERVER
        self._on_change: Callable[[KvmSnapshot], None] | None = None
        self._server = None
        self._client = None

    def set_on_change(self, cb: Callable[[KvmSnapshot], None] | None) -> None:
        self._on_change = cb

    def _emit(self) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(self.snapshot())
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        self._message = msg
        _append_log(msg)
        self._emit()

    def update_prefs(self, **kwargs: Any) -> dict[str, Any]:
        return kvm_prefs.save_prefs(kwargs)

    def snapshot(self) -> KvmSnapshot:
        with self._lock:
            p = kvm_prefs.load_prefs()
            role = KvmRole(str(p.get("role") or "server"))
            if self._status == KvmStatus.RUNNING:
                role = self._role
            connected = False
            remote = False
            if self._server is not None:
                connected = bool(getattr(self._server, "connected", False))
                remote = bool(getattr(self._server, "remote", False))
            if self._client is not None:
                connected = bool(getattr(self._client, "connected", False))
                remote = bool(getattr(self._client, "active", False))
            return KvmSnapshot(
                status=self._status,
                role=role,
                engine=KvmEngine.AURA.value,
                engine_label="AURA (built-in)",
                message=self._message,
                peer_host=str(p.get("peer_host") or ""),
                peer_name=str(p.get("peer_name") or ""),
                peer_device_id=str(p.get("peer_device_id") or ""),
                layout=str(p.get("layout") or "peer_right"),
                port=int(p.get("port") or DEFAULT_PORT),
                lan_ip=local_lan_ip(),
                pid=None,
                download_url="",
                install_hint="",
                server_screen=str(p.get("server_screen") or ""),
                client_screen=str(p.get("client_screen") or ""),
                running_since=self._running_since,
                connected=connected,
                remote=remote,
            )

    def start(
        self,
        *,
        role: KvmRole | str | None = None,
        peer_host: str | None = None,
        peer_name: str | None = None,
        peer_device_id: str | None = None,
        layout: str | None = None,
        server_screen: str | None = None,
        client_screen: str | None = None,
        port: int | None = None,
        invite_peer: bool = True,
    ) -> KvmSnapshot:
        with self._lock:
            return self._start_locked(
                role=role,
                peer_host=peer_host,
                peer_name=peer_name,
                peer_device_id=peer_device_id,
                layout=layout,
                port=port,
                invite_peer=invite_peer,
            )

    def _start_locked(
        self,
        *,
        role: KvmRole | str | None,
        peer_host: str | None,
        peer_name: str | None,
        peer_device_id: str | None,
        layout: str | None,
        port: int | None,
        invite_peer: bool,
    ) -> KvmSnapshot:
        from jarvis_ui.device_sync import get_local_permissions

        perms = get_local_permissions()
        if not perms.get("allow_kvm_input", False):
            self._status = KvmStatus.ERROR
            self._message = "Enable “Allow shared keyboard & mouse (KVM)” first"
            return self.snapshot()

        # Ensure pynput is importable before claiming success.
        try:
            import pynput  # noqa: F401
        except Exception as e:
            self._status = KvmStatus.ERROR
            self._message = f"Input layer unavailable: {e}"
            return self.snapshot()

        p = kvm_prefs.load_prefs()
        role_s = str(role or p.get("role") or "server").lower()
        try:
            role_e = KvmRole(role_s)
        except ValueError:
            role_e = KvmRole.SERVER

        host = (peer_host if peer_host is not None else str(p.get("peer_host") or "")).strip()
        pname = peer_name if peer_name is not None else str(p.get("peer_name") or "")
        pid_dev = (
            peer_device_id
            if peer_device_id is not None
            else str(p.get("peer_device_id") or "")
        )
        lay = layout if layout is not None else str(p.get("layout") or "peer_right")
        # Migrate old Barrier port prefs to native default.
        raw_port = int(port if port is not None else p.get("port") or DEFAULT_PORT)
        port_i = DEFAULT_PORT if raw_port == 24800 else raw_port

        if role_e == KvmRole.CLIENT and not looks_like_host(host):
            self._status = KvmStatus.ERROR
            self._message = "Client needs the server LAN IP / hostname"
            return self.snapshot()

        self._stop_locked(quiet=True)

        kvm_prefs.save_prefs(
            {
                "enabled": True,
                "role": role_e.value,
                "layout": lay,
                "peer_host": host,
                "peer_name": pname,
                "peer_device_id": pid_dev,
                "port": port_i,
            }
        )

        self._status = KvmStatus.STARTING
        self._role = role_e
        self._message = "Starting built-in KVM…"
        self._emit()

        w, h = _screen_size()
        try:
            if role_e == KvmRole.SERVER:
                from jarvis_ui.kvm.native_server import NativeKvmServer

                srv = NativeKvmServer(
                    layout=lay,
                    port=port_i,
                    screen_w=w,
                    screen_h=h,
                    on_log=self._log,
                )
                srv.start()
                self._server = srv
                self._client = None
                self._status = KvmStatus.RUNNING
                self._running_since = time.time()
                self._message = (
                    f"AURA KVM server on :{port_i} — waiting for peer"
                    + (f" · LAN {local_lan_ip()}" if local_lan_ip() else "")
                )
                _write_state(
                    {
                        "role": role_e.value,
                        "engine": "aura",
                        "port": port_i,
                        "started_at": self._running_since,
                    }
                )
                if (
                    invite_peer
                    and pid_dev
                    and bool(kvm_prefs.load_prefs().get("auto_invite", True))
                ):
                    self._try_invite_peer(
                        peer_device_id=pid_dev,
                        layout=lay,
                        port=port_i,
                    )
            else:
                from jarvis_ui.kvm.native_client import NativeKvmClient

                cli = NativeKvmClient(
                    host,
                    port=port_i,
                    layout=lay,
                    screen_w=w,
                    screen_h=h,
                    on_log=self._log,
                )
                cli.start()
                self._client = cli
                self._server = None
                self._status = KvmStatus.RUNNING
                self._running_since = time.time()
                self._message = f"AURA KVM client → {host}:{port_i}"
                _write_state(
                    {
                        "role": role_e.value,
                        "engine": "aura",
                        "port": port_i,
                        "peer_host": host,
                        "started_at": self._running_since,
                    }
                )
        except Exception as e:
            self._server = None
            self._client = None
            self._status = KvmStatus.ERROR
            self._message = str(e)[:200]
            self._running_since = None
            _write_state({})

        snap = self.snapshot()
        self._emit()
        return snap

    def stop(self) -> KvmSnapshot:
        with self._lock:
            return self._stop_locked(quiet=False)

    def _stop_locked(self, *, quiet: bool) -> KvmSnapshot:
        if self._server is not None:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        if self._client is not None:
            try:
                self._client.stop()
            except Exception:
                pass
            self._client = None
        _write_state({})
        kvm_prefs.save_prefs({"enabled": False})
        self._status = KvmStatus.STOPPED
        self._running_since = None
        if not quiet:
            self._message = "Stopped"
        self._emit()
        return self.snapshot()

    def _try_invite_peer(
        self,
        *,
        peer_device_id: str,
        layout: str,
        port: int,
    ) -> None:
        lan = local_lan_ip()
        if not lan:
            self._message += " · invite skipped (no LAN IP)"
            return
        try:
            from jarvis_ui import device_sync as DS

            DS.enqueue_job(
                peer_device_id,
                "kvm_invite",
                {
                    "server_host": lan,
                    "port": port,
                    "layout": layout,
                    "engine": "aura",
                    "server_name": DS.default_device_name(),
                },
            )
            self._message += f" · invited peer ({lan})"
        except Exception as e:
            self._message += f" · invite failed: {str(e)[:60]}"

    def accept_invite(self, payload: dict[str, Any]) -> KvmSnapshot:
        host = str(payload.get("server_host") or "").strip()
        port = int(payload.get("port") or DEFAULT_PORT)
        layout = str(payload.get("layout") or "peer_right")
        server_name = str(payload.get("server_name") or "Peer")
        return self.start(
            role=KvmRole.CLIENT,
            peer_host=host,
            peer_name=server_name,
            peer_device_id="",
            layout=layout,
            port=port,
            invite_peer=False,
        )


_MANAGER: KvmManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_kvm_manager() -> KvmManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = KvmManager()
        return _MANAGER
