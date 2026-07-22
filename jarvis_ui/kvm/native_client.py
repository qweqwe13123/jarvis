"""Native KVM client — receive events from server and inject locally."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any, Callable

from jarvis_ui.kvm.protocol import DEFAULT_PORT, PROTOCOL_VERSION, decode_lines, encode

LogFn = Callable[[str], None]


class NativeKvmClient:
    """Connects to an AURA KVM server and injects mouse/keyboard via pynput."""

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        layout: str = "peer_right",
        screen_w: int = 1920,
        screen_h: int = 1080,
        on_log: LogFn | None = None,
    ):
        self.host = (host or "").strip()
        self.port = int(port)
        self.layout = layout
        self.screen_w = max(1, int(screen_w))
        self.screen_h = max(1, int(screen_h))
        self._log = on_log or (lambda _m: None)

        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self.active = False  # server is controlling us
        self.connected = False
        self._mouse = None
        self._keyboard = None

    def start(self) -> None:
        self._stop.clear()
        try:
            from pynput.keyboard import Controller as KeyCtrl
            from pynput.mouse import Button, Controller as MouseCtrl

            self._mouse = MouseCtrl()
            self._keyboard = KeyCtrl()
            self._Button = Button
        except Exception as e:
            raise RuntimeError(f"pynput unavailable: {e}") from e

        threading.Thread(
            target=self._run, daemon=True, name="AuraKvmClient"
        ).start()

    def stop(self) -> None:
        self._stop.set()
        self.active = False
        self.connected = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._connect_once()
            except Exception as e:
                if self._stop.is_set():
                    break
                self._log(f"KVM reconnect in 2s — {e}")
                self.connected = False
                self.active = False
                time.sleep(2.0)

    def _connect_once(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8.0)
        s.connect((self.host, self.port))
        s.settimeout(1.0)
        self._sock = s
        self.connected = True
        self._log(f"KVM connected to {self.host}:{self.port}")
        self._send(
            {
                "v": PROTOCOL_VERSION,
                "type": "hello",
                "role": "client",
                "w": self.screen_w,
                "h": self.screen_h,
            }
        )
        buf = bytearray()
        while not self._stop.is_set():
            try:
                data = s.recv(65536)
            except socket.timeout:
                continue
            except Exception:
                break
            if not data:
                break
            buf.extend(data)
            msgs, buf = decode_lines(buf)
            for msg in msgs:
                self._handle(msg)
        self.connected = False
        self.active = False
        try:
            s.close()
        except Exception:
            pass
        if self._sock is s:
            self._sock = None
        raise ConnectionError("disconnected")

    def _send(self, msg: dict[str, Any]) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendall(encode(msg))
        except Exception:
            pass

    def _handle(self, msg: dict[str, Any]) -> None:
        t = str(msg.get("type") or "")
        if t == "hello":
            return
        if t == "enter":
            self.active = True
            self._move_norm(float(msg.get("nx") or 0.5), float(msg.get("ny") or 0.5))
            self._log("Peer is controlling this computer")
            return
        if t == "leave":
            self.active = False
            self._log("Peer released control")
            return
        if not self.active:
            return
        if t == "mouse_abs":
            self._move_norm(float(msg.get("nx") or 0), float(msg.get("ny") or 0))
            # Edge return toward server
            nx = float(msg.get("nx") or 0)
            ny = float(msg.get("ny") or 0)
            if self.layout == "peer_right" and nx <= 0.002:
                self._return_control()
            elif self.layout == "peer_left" and nx >= 0.998:
                self._return_control()
            elif self.layout == "peer_below" and ny <= 0.002:
                self._return_control()
            elif self.layout == "peer_above" and ny >= 0.998:
                self._return_control()
        elif t == "mouse_button":
            self._click(str(msg.get("button") or "left"), bool(msg.get("pressed")))
        elif t == "mouse_scroll":
            try:
                self._mouse.scroll(int(msg.get("dx") or 0), int(msg.get("dy") or 0))
            except Exception:
                pass
        elif t == "key":
            self._key(str(msg.get("key") or ""), bool(msg.get("pressed")))

    def _return_control(self) -> None:
        if not self.active:
            return
        self.active = False
        self._send({"type": "return"})
        self._log("Returned control to server (edge)")

    def _move_norm(self, nx: float, ny: float) -> None:
        x = int(max(0.0, min(1.0, nx)) * (self.screen_w - 1))
        y = int(max(0.0, min(1.0, ny)) * (self.screen_h - 1))
        try:
            self._mouse.position = (x, y)
        except Exception:
            pass

    def _click(self, button: str, pressed: bool) -> None:
        btn = self._Button.left
        b = button.lower()
        if "right" in b:
            btn = self._Button.right
        elif "middle" in b:
            btn = self._Button.middle
        try:
            if pressed:
                self._mouse.press(btn)
            else:
                self._mouse.release(btn)
        except Exception:
            pass

    def _key(self, name: str, pressed: bool) -> None:
        if not name:
            return
        try:
            from pynput.keyboard import Key

            key_obj: Any
            if name.startswith("<") and name.endswith(">"):
                attr = name[1:-1]
                key_obj = getattr(Key, attr, None)
                if key_obj is None:
                    return
            else:
                key_obj = name
            if pressed:
                self._keyboard.press(key_obj)
            else:
                self._keyboard.release(key_obj)
        except Exception:
            pass
