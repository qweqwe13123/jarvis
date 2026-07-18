"""Global hotkey service for the floating Jarvis overlay."""
from __future__ import annotations

import platform
import tempfile
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget

_DEBUG_LOG = Path(tempfile.gettempdir()) / "aura_hotkey_debug.log"


def default_hotkey() -> str:
    """Primary modifier + A on every OS (⌘A / Ctrl+A)."""
    if platform.system() == "Darwin":
        return "Meta+A"
    return "Ctrl+A"


def hotkey_display(seq: str) -> str:
    """Pretty label for UI (⌘A / Ctrl+A)."""
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


def _parse_combo(seq: str) -> tuple[set[str], str]:
    parts = [p.strip().lower() for p in (seq or "").replace(" ", "").split("+") if p]
    mods: set[str] = set()
    key = ""
    for p in parts:
        if p in ("meta", "cmd", "command"):
            mods.add("meta")
        elif p in ("ctrl", "control"):
            mods.add("ctrl")
        elif p in ("alt", "option"):
            mods.add("alt")
        elif p == "shift":
            mods.add("shift")
        elif p == "space":
            key = "space"
        else:
            key = p
    return mods, key


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


def _dbg(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}\n"
    try:
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"[AURA:hotkey] {msg}")


class _AppKeyFilter(QObject):
    """Catch the hotkey inside Qt; also log Cmd-key presses for diagnosis."""

    matched = pyqtSignal()

    def __init__(self, service: "GlobalHotkeyService"):
        super().__init__(service)
        self._service = service

    def eventFilter(self, obj, event):  # noqa: ANN001
        try:
            if event.type() != QEvent.Type.KeyPress:
                return False
            mods = event.modifiers()
            interesting = (
                Qt.KeyboardModifier.MetaModifier
                | Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
            )
            if mods & interesting:
                try:
                    mods_i = int(mods.value) if hasattr(mods, "value") else int(mods)
                except Exception:
                    mods_i = str(mods)
                _dbg(
                    f"qt KeyPress key={int(event.key())} "
                    f"mods={mods_i} text={event.text()!r} "
                    f"native={event.nativeVirtualKey()}"
                )
            if self._service._qt_event_matches(event):
                _dbg("qt filter MATCH → fire")
                self.matched.emit()
                return True
            return False
        except Exception as e:
            _dbg(f"qt filter error: {e}")
            return False


class GlobalHotkeyService(QObject):
    """Hotkey → `triggered` on the Qt thread."""

    triggered = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._combo = default_hotkey()
        self._listener = None
        self._fallback: QShortcut | None = None
        self._action: QAction | None = None
        self._host: QWidget | None = parent if isinstance(parent, QWidget) else None
        self._lock = threading.Lock()
        self._app_filter: _AppKeyFilter | None = None
        self._ns_global = None
        self._ns_local = None
        self._last_fire = 0.0
        self._win_hotkey_id = 0xA11A
        self._win_hotkey_thread: threading.Thread | None = None
        self._win_hotkey_stop = threading.Event()
        self._win_thread_id = 0

    @property
    def combo(self) -> str:
        return self._combo

    def set_host(self, host: QWidget) -> None:
        self._host = host

    def start(self, combo: str | None = None) -> None:
        if combo:
            self._combo = combo.strip() or default_hotkey()
        self.stop()
        try:
            _DEBUG_LOG.write_text("", encoding="utf-8")
        except Exception:
            pass

        # Layered capture — OS "Select All" (⌘A / Ctrl+A) steals plain shortcuts.
        self._install_app_filter()
        self._install_action()
        self._install_fallback()

        global_ok = False
        local_ok = False
        if platform.system() == "Darwin":
            local_ok = self._try_nsevent_local()
            global_ok = self._try_nsevent_global()
        else:
            # Windows / Linux: in-app stack + OS global hook.
            local_ok = True  # QAction + filter + shortcut cover focused AURA
            if platform.system() == "Windows":
                global_ok = self._try_win_register_hotkey()
            if not global_ok:
                global_ok = self._try_pynput()

        label = hotkey_display(self._combo)
        if global_ok:
            self.status_changed.emit(f"Global hotkey: {label}")
        else:
            tip = {
                "Darwin": "Enable Accessibility for system-wide use.",
                "Windows": "Allow AURA in antivirus if global Ctrl+A fails.",
                "Linux": "X11 works best; on Wayland use tray or keep AURA focused.",
            }.get(platform.system(), "")
            self.status_changed.emit(f"Hotkey: {label} (in-app). {tip}".strip())
        _dbg(
            f"armed {label} action={self._action is not None} "
            f"shortcut={self._fallback is not None} "
            f"local={local_ok} global={global_ok} os={platform.system()}"
        )
        print(f"[AURA] Overlay hotkey armed: {label} local={local_ok} global={global_ok}")

    def stop(self) -> None:
        self._stop_win_hotkey()
        with self._lock:
            listener = self._listener
            self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        self._stop_nsevent()
        if self._app_filter is not None:
            app = QApplication.instance()
            if app is not None:
                try:
                    app.removeEventFilter(self._app_filter)
                except Exception:
                    pass
            self._app_filter = None
        if self._action is not None and self._host is not None:
            try:
                self._host.removeAction(self._action)
            except Exception:
                pass
            self._action = None
        if self._fallback is not None:
            try:
                self._fallback.setParent(None)
            except Exception:
                pass
            self._fallback = None

    def rebind(self, combo: str) -> None:
        self.start(combo)

    def _fire(self) -> None:
        now = time.monotonic()
        if now - self._last_fire < 0.35:
            return
        self._last_fire = now
        _dbg("FIRE")
        # pyqtSignal.emit is thread-safe. Never create QTimer from the Win32
        # RegisterHotKey thread — that silently drops the toggle on Windows.
        try:
            self.triggered.emit()
        except Exception as e:
            _dbg(f"FIRE emit failed: {e}")

    def _qt_event_matches(self, event) -> bool:  # noqa: ANN001
        want_mods, want_key = _parse_combo(self._combo)
        if not want_key:
            return False
        mods = event.modifiers()
        have: set[str] = set()
        # On macOS Cmd is Meta; also accept Control+Meta oddities by checking Meta/Control carefully.
        if mods & Qt.KeyboardModifier.MetaModifier:
            have.add("meta")
        if mods & Qt.KeyboardModifier.ControlModifier:
            # On some layouts Control appears alone; keep it.
            have.add("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            have.add("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            have.add("shift")
        if have != want_mods:
            return False
        key = int(event.key())
        if want_key == "space":
            return key == int(Qt.Key.Key_Space)
        if len(want_key) == 1:
            # Physical / logical A, or text 'a'/'A' (layout-independent when possible).
            if key == ord(want_key.upper()):
                return True
            text = (event.text() or "").lower()
            if text == want_key.lower():
                return True
            # Russian layout: QWERTY A key often still reports Key_A with Cmd held.
            if want_key == "a" and key in (int(Qt.Key.Key_A), 1040, 1072):  # A / А / а
                return True
            return False
        return False

    def _install_app_filter(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        filt = _AppKeyFilter(self)
        filt.matched.connect(self._fire)
        app.installEventFilter(filt)
        self._app_filter = filt

    def _install_action(self) -> None:
        """QAction on the window beats Select All (⌘A / Ctrl+A) better than QShortcut alone."""
        if self._host is None:
            return
        act = QAction("Toggle Floating Overlay", self._host)
        act.setShortcut(QKeySequence(self._combo))
        act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        try:
            act.setMenuRole(QAction.MenuRole.NoRole)
        except Exception:
            pass
        act.triggered.connect(self._fire)
        self._host.addAction(act)
        self._action = act

    def _install_fallback(self) -> None:
        if self._host is None:
            return
        sc = QShortcut(QKeySequence(self._combo), self._host)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.setAutoRepeat(False)
        sc.activated.connect(self._fire)
        self._fallback = sc

    def _nsevent_matches(self, event) -> bool:
        try:
            from AppKit import (
                NSEventModifierFlagCommand,
                NSEventModifierFlagControl,
                NSEventModifierFlagDeviceIndependentFlagsMask,
                NSEventModifierFlagOption,
                NSEventModifierFlagShift,
            )
        except Exception:
            return False
        want_mods, want_key = _parse_combo(self._combo)
        if not want_key:
            return False
        flags = int(event.modifierFlags()) & int(
            NSEventModifierFlagDeviceIndependentFlagsMask
        )
        have: set[str] = set()
        if flags & NSEventModifierFlagCommand:
            have.add("meta")
        if flags & NSEventModifierFlagControl:
            have.add("ctrl")
        if flags & NSEventModifierFlagOption:
            have.add("alt")
        if flags & NSEventModifierFlagShift:
            have.add("shift")
        if have != want_mods:
            return False
        chars = (event.charactersIgnoringModifiers() or "").lower()
        keycode = int(event.keyCode())
        if want_key == "space":
            return chars == " " or keycode == 49
        if want_key == "a":
            # 0 = kVK_ANSI_A (physical A key, any layout)
            return keycode == 0 or chars in ("a", "ф")
        return chars == want_key

    def _try_nsevent_local(self) -> bool:
        """Local monitor: runs for key events while AURA is active — before Select All."""
        if platform.system() != "Darwin":
            return False
        try:
            from AppKit import NSEvent, NSEventMaskKeyDown
        except Exception:
            return False

        service = self

        def _handler(event):
            try:
                if service._nsevent_matches(event):
                    _dbg("ns LOCAL match → fire + swallow")
                    service._fire()
                    return None  # swallow so Select All / Qt don't also handle it
            except Exception as e:
                _dbg(f"ns LOCAL error: {e}")
            return event

        try:
            self._ns_local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, _handler
            )
            return self._ns_local is not None
        except Exception as e:
            _dbg(f"ns LOCAL install failed: {e}")
            return False

    def _try_nsevent_global(self) -> bool:
        if platform.system() != "Darwin":
            return False
        try:
            from AppKit import NSEvent, NSEventMaskKeyDown
        except Exception:
            return False

        service = self

        def _handler(event):
            try:
                if service._nsevent_matches(event):
                    _dbg("ns GLOBAL match → fire")
                    service._fire()
            except Exception:
                pass

        try:
            self._ns_global = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, _handler
            )
            return self._ns_global is not None
        except Exception as e:
            _dbg(f"ns GLOBAL install failed: {e}")
            return False

    def _stop_nsevent(self) -> None:
        try:
            from AppKit import NSEvent
        except Exception:
            self._ns_global = None
            self._ns_local = None
            return
        for attr in ("_ns_global", "_ns_local"):
            mon = getattr(self, attr)
            if mon is not None:
                try:
                    NSEvent.removeMonitor_(mon)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _try_win_register_hotkey(self) -> bool:
        """Native RegisterHotKey — reliable system-wide Ctrl+A on Windows."""
        if platform.system() != "Windows":
            return False
        mods, key = _parse_combo(self._combo)
        if key != "a" or mods != {"ctrl"}:
            # Keep RegisterHotKey path focused on the product default for now.
            _dbg(f"win RegisterHotKey skip non-default combo mods={mods} key={key}")
            return False
        try:
            import ctypes
            from ctypes import wintypes
        except Exception as e:
            _dbg(f"win ctypes unavailable: {e}")
            return False

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        MOD_CONTROL = 0x0002
        MOD_NOREPEAT = 0x4000
        VK_A = 0x41
        WM_HOTKEY = 0x0312
        WM_QUIT = 0x0012
        hotkey_id = int(self._win_hotkey_id)
        self._win_hotkey_stop.clear()
        ready = threading.Event()
        ok_box = {"ok": False}

        def _loop() -> None:
            self._win_thread_id = int(kernel32.GetCurrentThreadId())
            registered = bool(
                user32.RegisterHotKey(
                    None, hotkey_id, MOD_CONTROL | MOD_NOREPEAT, VK_A
                )
            )
            ok_box["ok"] = registered
            ready.set()
            if not registered:
                _dbg(f"RegisterHotKey failed err={ctypes.GetLastError()}")
                return
            _dbg("RegisterHotKey Ctrl+A armed")
            msg = wintypes.MSG()
            # GetMessageW blocks until a message arrives — more reliable than Peek+sleep
            # for WM_HOTKEY delivery on a dedicated thread.
            while not self._win_hotkey_stop.is_set():
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                    _dbg("win HOTKEY match → fire")
                    self._fire()
                    continue
                if msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
            _dbg("RegisterHotKey released")

        try:
            t = threading.Thread(
                target=_loop, name="AURA-WinHotkey", daemon=True
            )
            t.start()
            if not ready.wait(2.0):
                self._win_hotkey_stop.set()
                _dbg("RegisterHotKey thread timeout")
                return False
            if not ok_box["ok"]:
                return False
            self._win_hotkey_thread = t
            return True
        except Exception as e:
            _dbg(f"RegisterHotKey start failed: {e}")
            return False

    def _stop_win_hotkey(self) -> None:
        if platform.system() != "Windows":
            return
        self._win_hotkey_stop.set()
        tid = int(self._win_thread_id or 0)
        if tid:
            try:
                import ctypes

                ctypes.windll.user32.PostThreadMessageW(tid, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass
        t = self._win_hotkey_thread
        self._win_hotkey_thread = None
        self._win_thread_id = 0
        if t is not None and t.is_alive():
            try:
                t.join(timeout=1.0)
            except Exception:
                pass
        try:
            import ctypes

            ctypes.windll.user32.UnregisterHotKey(None, int(self._win_hotkey_id))
        except Exception:
            pass

    def _try_pynput(self) -> bool:
        """System-wide hotkey on Windows / Linux (X11). Wayland often blocks this."""
        if platform.system() == "Darwin":
            return False
        try:
            from pynput import keyboard
        except Exception as e:
            _dbg(f"pynput import failed: {e}")
            return False
        combo = _to_pynput_combo(self._combo)
        if not combo:
            return False

        def _on_activate():
            _dbg(f"pynput GLOBAL match → fire ({combo})")
            self._fire()

        try:
            listener = keyboard.GlobalHotKeys({combo: _on_activate})
            listener.start()
            self._listener = listener
            _dbg(f"pynput GlobalHotKeys started: {combo}")
            return True
        except Exception as e:
            _dbg(f"pynput GlobalHotKeys failed: {e}")
            self.status_changed.emit(f"Hotkey error: {e}")
            return False
