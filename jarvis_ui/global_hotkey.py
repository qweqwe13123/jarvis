"""Global hotkey service for the floating Jarvis overlay."""
from __future__ import annotations

import platform
import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget


def default_hotkey() -> str:
    if platform.system() == "Darwin":
        return "Meta+Space"
    return "Alt+Space"


def hotkey_display(seq: str) -> str:
    """Pretty label for UI (⌘Space / Alt+Space)."""
    s = (seq or default_hotkey()).strip()
    parts = [p for p in s.replace(" ", "").split("+") if p]
    if platform.system() == "Darwin":
        mapping = {
            "meta": "⌘", "cmd": "⌘", "command": "⌘",
            "alt": "⌥", "option": "⌥",
            "ctrl": "⌃", "control": "⌃",
            "shift": "⇧",
            "space": "Space",
        }
        pretty = [mapping.get(p.lower(), p.upper() if len(p) == 1 else p) for p in parts]
        if len(pretty) == 2 and pretty[0] in ("⌘", "⌥", "⌃", "⇧"):
            return f"{pretty[0]}{pretty[1]}"
        return "+".join(pretty)
    labels = []
    for p in parts:
        pl = p.lower()
        if pl in ("meta", "cmd", "command"):
            labels.append("Win")
        elif pl in ("ctrl", "control"):
            labels.append("Ctrl")
        elif pl in ("alt", "option"):
            labels.append("Alt")
        elif pl == "shift":
            labels.append("Shift")
        elif pl == "space":
            labels.append("Space")
        else:
            labels.append(p.upper() if len(p) == 1 else p.capitalize())
    return "+".join(labels)


def _to_pynput_combo(seq: str) -> str:
    parts = [p.strip().lower() for p in (seq or "").replace(" ", "").split("+") if p]
    mapped = []
    for p in parts:
        if p in ("meta", "cmd", "command"):
            mapped.append("<cmd>")
        elif p in ("ctrl", "control"):
            mapped.append("<ctrl>")
        elif p in ("alt", "option"):
            mapped.append("<alt>")
        elif p == "shift":
            mapped.append("<shift>")
        elif p == "space":
            mapped.append("<space>")
        else:
            mapped.append(p)
    return "+".join(mapped)


class GlobalHotkeyService(QObject):
    """System-wide hotkey → `triggered` on the Qt thread."""

    triggered = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._combo = default_hotkey()
        self._listener = None
        self._fallback: QShortcut | None = None
        self._host: QWidget | None = parent if isinstance(parent, QWidget) else None
        self._lock = threading.Lock()

    @property
    def combo(self) -> str:
        return self._combo

    def set_host(self, host: QWidget) -> None:
        self._host = host

    def start(self, combo: str | None = None) -> None:
        if combo:
            self._combo = combo.strip() or default_hotkey()
        self.stop()
        if self._try_pynput():
            self.status_changed.emit(f"Global hotkey: {hotkey_display(self._combo)}")
            return
        self._install_fallback()
        self.status_changed.emit(
            f"In-app hotkey: {hotkey_display(self._combo)} "
            "(enable Accessibility for a system-wide shortcut)"
        )

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        if self._fallback is not None:
            try:
                self._fallback.setParent(None)
            except Exception:
                pass
            self._fallback = None

    def rebind(self, combo: str) -> None:
        self.start(combo)

    def _try_pynput(self) -> bool:
        # pynput's Darwin keyboard path calls TSMGetInputSourceProperty off the
        # main queue and can SIGTRAP the whole process (dispatch_assert_queue).
        # Keep global hotkeys for non-macOS; macOS uses in-app QShortcut fallback.
        if platform.system() == "Darwin":
            return False
        try:
            from pynput import keyboard
        except Exception:
            return False
        combo = _to_pynput_combo(self._combo)
        if not combo:
            return False

        def _on_activate():
            self.triggered.emit()

        try:
            listener = keyboard.GlobalHotKeys({combo: _on_activate})
            listener.start()
            self._listener = listener
            return True
        except Exception as e:
            self.status_changed.emit(f"Hotkey error: {e}")
            return False

    def _install_fallback(self) -> None:
        if self._host is None:
            return
        sc = QShortcut(QKeySequence(self._combo), self._host)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(self.triggered.emit)
        self._fallback = sc
