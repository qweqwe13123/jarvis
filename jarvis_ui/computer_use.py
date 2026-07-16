"""Computer Use — light settings-style guide for the floating overlay (all OS)."""
from __future__ import annotations

import platform

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from jarvis_ui.global_hotkey import default_hotkey, hotkey_display
from memory import workspace_manager as ws


# Screenshot-matched light settings palette
_PAGE = "#F8F7F2"
_CARD = "#FFFFFF"
_TITLE = "#111111"
_BODY = "#6B7280"
_ROW_TITLE = "#1F2937"
_DIVIDER = "#EDECE8"
_PILL_BG = "#F3F2ED"
_PILL_TEXT = "#374151"
_PILL_ACTIVE_BG = "#FFFFFF"
_ACCENT = "#111111"


def _serif(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    # Prefer elegant system serifs (matches screenshot headers).
    for family in ("New York", "Iowan Old Style", "Palatino Linotype", "Palatino", "Georgia", "Times New Roman"):
        f = QFont(family, size, weight)
        if QFont(family).exactMatch() or family in ("Georgia", "Times New Roman"):
            f.setStyleHint(QFont.StyleHint.Serif)
            return f
    f = QFont("Georgia", size, weight)
    f.setStyleHint(QFont.StyleHint.Serif)
    return f


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI", size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    return f


class _KeyPill(QLabel):
    """Single keycap / shortcut chip."""

    def __init__(self, text: str, active: bool = False, parent=None):
        super().__init__(text, parent)
        self.setFont(_sans(12, QFont.Weight.Medium))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(30)
        pad = max(10, 8 + len(text) * 3)
        self.setMinimumWidth(28 + len(text) * 7)
        if active:
            self.setStyleSheet(
                f"background: {_PILL_ACTIVE_BG}; color: {_TITLE}; border: 1px solid {_DIVIDER}; "
                f"border-radius: 8px; padding: 0 {pad}px;"
            )
        else:
            self.setStyleSheet(
                f"background: {_PILL_BG}; color: {_PILL_TEXT}; border: 1px solid transparent; "
                f"border-radius: 8px; padding: 0 {pad}px;"
            )


class _KeyGroup(QFrame):
    """Grouped shortcut pills in one rounded tray (like the screenshot)."""

    def __init__(self, keys: list[str], highlight_first: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("KeyGroup")
        self.setStyleSheet(
            f"QFrame#KeyGroup {{ background: {_PILL_BG}; border: none; border-radius: 12px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        for i, k in enumerate(keys):
            lay.addWidget(_KeyPill(k, active=(highlight_first and i == 0)))


class _SettingRow(QFrame):
    """Left: title + description. Right: control widget. Optional bottom divider."""

    def __init__(
        self,
        title: str,
        description: str,
        right: QWidget,
        *,
        show_divider: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(22, 18, 22, 18)
        row.setSpacing(16)

        text = QVBoxLayout()
        text.setSpacing(4)
        text.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setFont(_sans(14, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {_ROW_TITLE}; background: transparent;")
        text.addWidget(t)
        d = QLabel(description)
        d.setWordWrap(True)
        d.setFont(_sans(12))
        d.setStyleSheet(f"color: {_BODY}; background: transparent;")
        d.setMaximumWidth(420)
        text.addWidget(d)
        row.addLayout(text, stretch=1)
        row.addWidget(right, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        outer.addLayout(row)

        if show_divider:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {_DIVIDER}; border: none; margin-left: 22px; margin-right: 22px;")
            outer.addWidget(line)


class _SettingsCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setStyleSheet(
            f"QFrame#SettingsCard {{ background: {_CARD}; border: none; border-radius: 20px; }}"
        )
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 4, 0, 4)
        self._lay.setSpacing(0)

    def add_row(self, row: _SettingRow):
        self._lay.addWidget(row)


class ComputerUseView(QWidget):
    """Light settings page explaining how to open the floating bar on every OS."""

    hotkey_changed = pyqtSignal(str)
    open_overlay = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ComputerUseView")
        self.setStyleSheet(f"QWidget#ComputerUseView {{ background: {_PAGE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_PAGE}; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}"
            f"QScrollBar::handle:vertical {{ background: #D6D3CB; border-radius: 4px; min-height: 32px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        page = QWidget()
        page.setStyleSheet(f"background: {_PAGE};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 36, 48, 56)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        inner = QWidget()
        inner.setMaximumWidth(760)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)

        # —— page intro ——
        page_title = QLabel("Computer Use")
        page_title.setFont(_serif(32, QFont.Weight.Normal))
        page_title.setStyleSheet(f"color: {_TITLE}; background: transparent;")
        il.addWidget(page_title)
        page_sub = QLabel(
            "Summon the floating AURA bar from anywhere — over any app, on any screen."
        )
        page_sub.setWordWrap(True)
        page_sub.setFont(_sans(13))
        page_sub.setStyleSheet(f"color: {_BODY}; background: transparent; margin-top: 6px;")
        il.addWidget(page_sub)
        il.addSpacing(28)

        # —— Floating bar ——
        il.addWidget(self._section_header(
            "Floating bar",
            "Summon and position the AURA bar from anywhere.",
        ))
        il.addSpacing(12)
        float_card = _SettingsCard()
        current = platform.system()
        float_card.add_row(_SettingRow(
            "macOS",
            "Press ⌘ Space anytime — even when AURA is minimized or another app is focused. "
            "Press again (or Esc) to hide. If Spotlight uses ⌘ Space, change it or pick a custom hotkey below.",
            _KeyGroup(["⌘", "Space"]),
            show_divider=True,
        ))
        float_card.add_row(_SettingRow(
            "Windows",
            "Press Alt + Space to show or hide the floating bar over any window. "
            "Works from the system tray while AURA runs in the background.",
            _KeyGroup(["Alt", "Space"]),
            show_divider=True,
        ))
        float_card.add_row(_SettingRow(
            "Linux",
            "Press Alt + Space (X11). On Wayland some desktops block global shortcuts — "
            "use the custom hotkey below or open from the system tray.",
            _KeyGroup(["Alt", "Space"]),
            show_divider=True,
        ))
        # Highlight current OS row visually via a small badge on the right of description — 
        # add a "This device" pill next to the matching OS.
        yours = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux",
        }.get(current, "Linux")
        float_card.add_row(_SettingRow(
            "Show or hide the bar",
            f"You’re on {yours}. The shortcut above for your system is active by default. "
            "Bring the floating bar forward, or tuck it out of the way.",
            _KeyGroup(self._current_key_parts()),
            show_divider=False,
        ))
        il.addWidget(float_card)
        il.addSpacing(32)

        # —— Custom hotkey ——
        il.addWidget(self._section_header(
            "Custom shortcut",
            "Override the default hotkey. Saved on this device and applied immediately.",
        ))
        il.addSpacing(12)
        custom = _SettingsCard()
        editor = QWidget()
        el = QHBoxLayout(editor)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(8)
        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText(default_hotkey())
        self._hotkey_edit.setFixedHeight(34)
        self._hotkey_edit.setMinimumWidth(160)
        self._hotkey_edit.setFont(_sans(12))
        self._hotkey_edit.setStyleSheet(
            f"QLineEdit {{ background: {_PILL_BG}; color: {_TITLE}; border: 1px solid {_DIVIDER}; "
            f"border-radius: 10px; padding: 0 12px; }}"
            f"QLineEdit:focus {{ border: 1px solid #C4C0B6; background: {_CARD}; }}"
        )
        el.addWidget(self._hotkey_edit)
        save = QPushButton("Save")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setFixedSize(72, 34)
        save.setFont(_sans(12, QFont.Weight.DemiBold))
        save.setStyleSheet(
            f"QPushButton {{ background: {_TITLE}; color: {_CARD}; border: none; "
            f"border-radius: 10px; }}"
            "QPushButton:hover { background: #333; }"
        )
        save.clicked.connect(self._save_hotkey)
        el.addWidget(save)
        custom.add_row(_SettingRow(
            "Change hotkey",
            "Examples: Meta+Space · Alt+Space · Ctrl+Space · Ctrl+Shift+J",
            editor,
            show_divider=False,
        ))
        il.addWidget(custom)
        il.addSpacing(32)

        # —— Permissions ——
        il.addWidget(self._section_header(
            "Permissions",
            "One-time setup so the global shortcut works while other apps are focused.",
        ))
        il.addSpacing(12)
        perm = _SettingsCard()
        perm.add_row(_SettingRow(
            "macOS",
            "System Settings → Privacy & Security → Accessibility — enable AURA "
            "(or Terminal / Python). Also allow Input Monitoring if asked, then restart AURA.",
            _KeyGroup(["Settings"], highlight_first=True),
            show_divider=True,
        ))
        perm.add_row(_SettingRow(
            "Windows",
            "Usually no extra setup. If the shortcut fails, check antivirus isn’t blocking "
            "AURA and try Alt+Space or a custom combo.",
            _KeyGroup(["Alt", "Space"]),
            show_divider=True,
        ))
        perm.add_row(_SettingRow(
            "Linux",
            "Best on X11. Under Wayland, grant input permissions in your desktop settings "
            "or rely on the tray menu / custom in-app shortcut.",
            _KeyGroup(["X11"], highlight_first=True),
            show_divider=False,
        ))
        il.addWidget(perm)
        il.addSpacing(32)

        # —— Tray ——
        il.addWidget(self._section_header(
            "Menu bar & tray",
            "Closing the main window does not quit AURA.",
        ))
        il.addSpacing(12)
        tray = _SettingsCard()
        tray.add_row(_SettingRow(
            "Background menu",
            "macOS: menu bar icon · Windows / Linux: system tray. "
            "Open AURA · Settings · Check for updates · Quit.",
            _KeyGroup(["Open AURA"], highlight_first=True),
            show_divider=False,
        ))
        il.addWidget(tray)
        il.addSpacing(28)

        try_btn = QPushButton("Try floating overlay now")
        try_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        try_btn.setFixedHeight(44)
        try_btn.setFont(_sans(13, QFont.Weight.DemiBold))
        try_btn.setStyleSheet(
            f"QPushButton {{ background: {_TITLE}; color: {_CARD}; border: none; "
            f"border-radius: 14px; padding: 0 22px; }}"
            "QPushButton:hover { background: #333; }"
        )
        try_btn.clicked.connect(self.open_overlay.emit)
        il.addWidget(try_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(_sans(12))
        self._status.setStyleSheet(f"color: {_BODY}; background: transparent; margin-top: 10px;")
        il.addWidget(self._status)

        lay.addWidget(inner)
        scroll.setWidget(page)
        root.addWidget(scroll)

        saved = ws.get_settings().get("overlay_hotkey") or default_hotkey()
        self._hotkey_edit.setText(saved)

    def set_hotkey_status(self, text: str) -> None:
        self._status.setText(text)

    @staticmethod
    def _section_header(title: str, subtitle: str) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(6)
        h = QLabel(title)
        h.setFont(_serif(26))
        h.setStyleSheet(f"color: {_TITLE}; background: transparent;")
        lay.addWidget(h)
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setFont(_sans(13))
        s.setStyleSheet(f"color: {_BODY}; background: transparent;")
        lay.addWidget(s)
        return wrap

    def _current_key_parts(self) -> list[str]:
        combo = ws.get_settings().get("overlay_hotkey") or default_hotkey()
        # Split into pill labels for the active OS display.
        parts = [p for p in combo.replace(" ", "").split("+") if p]
        out = []
        for p in parts:
            pl = p.lower()
            if pl in ("meta", "cmd", "command"):
                out.append("⌘" if platform.system() == "Darwin" else "Win")
            elif pl in ("alt", "option"):
                out.append("⌥" if platform.system() == "Darwin" else "Alt")
            elif pl in ("ctrl", "control"):
                out.append("⌃" if platform.system() == "Darwin" else "Ctrl")
            elif pl == "shift":
                out.append("⇧" if platform.system() == "Darwin" else "Shift")
            elif pl == "space":
                out.append("Space")
            else:
                out.append(p.upper() if len(p) == 1 else p)
        return out or ["Alt", "Space"]

    def _save_hotkey(self):
        combo = self._hotkey_edit.text().strip() or default_hotkey()
        ws.save_settings({"overlay_hotkey": combo})
        self.hotkey_changed.emit(combo)
        self._status.setText(f"Hotkey updated to {hotkey_display(combo)}")
