"""Native KVM server — capture local input at screen edge, forward to peer."""

from __future__ import annotations

import socket
import threading
from typing import Any, Callable

from jarvis_ui.kvm.protocol import DEFAULT_PORT, PROTOCOL_VERSION, decode_lines, encode

LogFn = Callable[[str], None]


def _key_name(key) -> str:
    try:
        from pynput.keyboard import Key

        if isinstance(key, Key):
            return f"<{key.name}>"
    except Exception:
        pass
    try:
        if hasattr(key, "char") and key.char:
            return key.char
    except Exception:
        pass
    return str(key)


class NativeKvmServer:
    """
    Listens on LAN. When the cursor hits the edge toward the peer, subsequent
    mouse/keyboard events are forwarded to the connected client.
    Hotkey Ctrl+Shift+Alt+Q returns control to this machine.
    """

    def __init__(
        self,
        *,
        layout: str = "peer_right",
        port: int = DEFAULT_PORT,
        screen_w: int = 1920,
        screen_h: int = 1080,
        on_log: LogFn | None = None,
    ):
        self.layout = layout
        self.port = int(port)
        self.screen_w = max(1, int(screen_w))
        self.screen_h = max(1, int(screen_h))
        self._log = on_log or (lambda _m: None)

        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._client: socket.socket | None = None
        self._client_lock = threading.Lock()
        self._listeners: list[Any] = []

        self.remote = False
        self.connected = False
        self.peer_w = 1920
        self.peer_h = 1080

    def start(self) -> None:
        self._stop.clear()
        # Bind the port first so a failure (port in use) surfaces immediately,
        # then attach input hooks (raises if the OS input layer is unavailable).
        self._bind_or_raise()
        self._start_input_hooks()
        threading.Thread(
            target=self._accept_loop, daemon=True, name="AuraKvmAccept"
        ).start()
        self._log(f"KVM server listening on :{self.port}")

    def _bind_or_raise(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", self.port))
            s.listen(1)
            s.settimeout(1.0)
        except OSError as e:
            raise RuntimeError(
                f"Can't listen on port {self.port} ({e.strerror or e}). "
                "Is another KVM already running?"
            ) from e
        self._sock = s

    def stop(self) -> None:
        self._stop.set()
        self.remote = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        with self._client_lock:
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass
            self._client = None
            self.connected = False
        for lst in self._listeners:
            try:
                lst.stop()
            except Exception:
                pass
        self._listeners.clear()

    def _accept_loop(self) -> None:
        s = self._sock
        if s is None:
            self._log("KVM accept aborted: socket not bound")
            return

        while not self._stop.is_set():
            try:
                conn, addr = s.accept()
            except socket.timeout:
                continue
            except Exception:
                if self._stop.is_set():
                    break
                continue
            self._log(f"KVM peer connected from {addr[0]}")
            with self._client_lock:
                old = self._client
                self._client = conn
                self.connected = True
            if old:
                try:
                    old.close()
                except Exception:
                    pass
            self._send(
                {
                    "v": PROTOCOL_VERSION,
                    "type": "hello",
                    "role": "server",
                    "w": self.screen_w,
                    "h": self.screen_h,
                    "layout": self.layout,
                }
            )
            threading.Thread(
                target=self._recv_loop,
                args=(conn,),
                daemon=True,
                name="AuraKvmRecv",
            ).start()

    def _recv_loop(self, conn: socket.socket) -> None:
        buf = bytearray()
        conn.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data = conn.recv(65536)
            except socket.timeout:
                continue
            except Exception:
                break
            if not data:
                break
            buf.extend(data)
            msgs, buf = decode_lines(buf)
            for msg in msgs:
                t = str(msg.get("type") or "")
                if t == "hello":
                    self.peer_w = int(msg.get("w") or self.peer_w)
                    self.peer_h = int(msg.get("h") or self.peer_h)
                elif t == "return":
                    self.remote = False
                    self._log("Control returned to this computer")
        with self._client_lock:
            if self._client is conn:
                self._client = None
                self.connected = False
                self.remote = False
        try:
            conn.close()
        except Exception:
            pass
        self._log("KVM peer disconnected")

    def _send(self, msg: dict[str, Any]) -> bool:
        raw = encode(msg)
        with self._client_lock:
            c = self._client
            if not c:
                return False
            try:
                c.sendall(raw)
                return True
            except Exception:
                try:
                    c.close()
                except Exception:
                    pass
                self._client = None
                self.connected = False
                self.remote = False
                return False

    def _start_input_hooks(self) -> None:
        try:
            from pynput import keyboard, mouse
            from pynput.keyboard import Key
        except Exception as e:
            raise RuntimeError(f"input layer unavailable: {e}") from e

        mods: set[str] = set()
        edge = 2

        def on_move(x, y):
            if self._stop.is_set():
                return False
            if not self.connected:
                return
            if self.remote:
                if self.layout == "peer_right":
                    nx = max(0.0, min(1.0, (float(x) - (self.screen_w - 80)) / 80.0))
                    ny = max(0.0, min(1.0, float(y) / float(self.screen_h)))
                elif self.layout == "peer_left":
                    nx = max(0.0, min(1.0, 1.0 - float(x) / 80.0))
                    ny = max(0.0, min(1.0, float(y) / float(self.screen_h)))
                elif self.layout == "peer_below":
                    nx = max(0.0, min(1.0, float(x) / float(self.screen_w)))
                    ny = max(
                        0.0, min(1.0, (float(y) - (self.screen_h - 80)) / 80.0)
                    )
                else:
                    nx = max(0.0, min(1.0, float(x) / float(self.screen_w)))
                    ny = max(0.0, min(1.0, 1.0 - float(y) / 80.0))
                self._send({"type": "mouse_abs", "nx": nx, "ny": ny})
                return

            hit = False
            entry_nx = entry_ny = 0.5
            if self.layout == "peer_right" and x >= self.screen_w - edge:
                hit, entry_nx, entry_ny = (
                    True,
                    0.02,
                    max(0.0, min(1.0, y / self.screen_h)),
                )
            elif self.layout == "peer_left" and x <= edge:
                hit, entry_nx, entry_ny = (
                    True,
                    0.98,
                    max(0.0, min(1.0, y / self.screen_h)),
                )
            elif self.layout == "peer_below" and y >= self.screen_h - edge:
                hit, entry_nx, entry_ny = (
                    True,
                    max(0.0, min(1.0, x / self.screen_w)),
                    0.02,
                )
            elif self.layout == "peer_above" and y <= edge:
                hit, entry_nx, entry_ny = (
                    True,
                    max(0.0, min(1.0, x / self.screen_w)),
                    0.98,
                )
            if hit:
                self.remote = True
                self._send({"type": "enter", "nx": entry_nx, "ny": entry_ny})
                self._log("Controlling peer — Ctrl+Shift+Alt+Q to return")

        def on_click(_x, _y, button, pressed):
            if self._stop.is_set():
                return False
            if not self.remote or not self.connected:
                return
            self._send(
                {
                    "type": "mouse_button",
                    "button": str(button).split(".")[-1],
                    "pressed": bool(pressed),
                }
            )

        def on_scroll(_x, _y, dx, dy):
            if self._stop.is_set():
                return False
            if not self.remote or not self.connected:
                return
            self._send({"type": "mouse_scroll", "dx": int(dx), "dy": int(dy)})

        def _mod_name(key) -> str | None:
            mapping = {
                Key.ctrl: "ctrl",
                Key.ctrl_l: "ctrl",
                Key.ctrl_r: "ctrl",
                Key.alt: "alt",
                Key.alt_l: "alt",
                Key.alt_r: "alt",
                Key.alt_gr: "alt",
                Key.shift: "shift",
                Key.shift_l: "shift",
                Key.shift_r: "shift",
                Key.cmd: "cmd",
                Key.cmd_l: "cmd",
                Key.cmd_r: "cmd",
            }
            return mapping.get(key)

        def on_press(key):
            if self._stop.is_set():
                return False
            m = _mod_name(key)
            if m:
                mods.add(m)
            try:
                ch = getattr(key, "char", None)
            except Exception:
                ch = None
            if (
                ch
                and ch.lower() == "q"
                and "ctrl" in mods
                and "shift" in mods
                and "alt" in mods
            ):
                if self.remote:
                    self.remote = False
                    self._send({"type": "leave"})
                    self._log("Returned control (hotkey)")
                return
            if not self.remote or not self.connected:
                return
            self._send({"type": "key", "key": _key_name(key), "pressed": True})

        def on_release(key):
            if self._stop.is_set():
                return False
            m = _mod_name(key)
            if m:
                mods.discard(m)
            if not self.remote or not self.connected:
                return
            self._send({"type": "key", "key": _key_name(key), "pressed": False})

        ml = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        kl = keyboard.Listener(on_press=on_press, on_release=on_release)
        ml.start()
        kl.start()
        self._listeners = [ml, kl]
