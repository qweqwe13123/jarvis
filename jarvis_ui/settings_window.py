"""Cursor-style in-window Settings page for A.U.R.A.

Embeds as a QWidget inside the main window (not a separate OS dialog).
"""

from __future__ import annotations

import sys
import webbrowser
from typing import Any, Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T
from jarvis_ui.components import _LineIcon
from core.version import APP_NAME, VERSION

# Settings chrome — Cursor-like charcoal nested inside AURA navy.
_BG = "#12181f"
_SIDEBAR = "#0d1218"
_CARD = "#171e27"
_CARD_BORDER = "#243040"
_NAV_ACTIVE = "rgba(255,255,255,0.08)"
_NAV_HOVER = "rgba(255,255,255,0.05)"
_TEXT = "#e6eef6"
_TEXT_MED = "#9aafc0"
_TEXT_DIM = "#6b8294"
_ACCENT = T.CYAN
_TOGGLE_ON = "#3d8bfd"
_TOGGLE_OFF = "#3a4554"
_SEARCH_BG = "#1a222c"
_SIDEBAR_W = 220
_FONT = T.SB_FONT

try:
    from core.gemini_models import primary as _gemini_primary

    _LIVE_MODEL_FALLBACK = _gemini_primary("live").removeprefix("models/")
    _DISPLAY_MODEL = _gemini_primary("balanced")
except Exception:
    _LIVE_MODEL_FALLBACK = "gemini-2.5-flash-native-audio-preview-12-2025"
    _DISPLAY_MODEL = "gemini-flash-latest"


# ── Primitives ──────────────────────────────────────────────────────────────


class _PillToggle(QWidget):
    """iOS / Cursor-style pill switch."""

    toggled = pyqtSignal(bool)

    def __init__(self, on: bool = False, parent=None):
        super().__init__(parent)
        self._on = bool(on)
        self.setFixedSize(40, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:  # noqa: N802 — Qt naming
        return self._on

    def setChecked(self, on: bool) -> None:  # noqa: N802
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._on = not self._on
            self.update()
            self.toggled.emit(self._on)
        super().mousePressEvent(e)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track = QColor(_TOGGLE_ON if self._on else _TOGGLE_OFF)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        knob_d = h - 4
        x = w - knob_d - 2 if self._on else 2
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(x, 2, knob_d, knob_d)


class _GhostButton(QPushButton):
    def __init__(self, text: str, *, primary: bool = False, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        if primary:
            self.setStyleSheet(
                f"QPushButton {{ background: rgba(0,209,255,0.12); color: {_ACCENT}; "
                f"border: 1px solid rgba(0,209,255,0.28); border-radius: 7px; "
                f"padding: 0 14px; font-family: '{_FONT}'; font-size: 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: rgba(0,209,255,0.20); }}"
                f"QPushButton:disabled {{ color: {_TEXT_DIM}; border-color: {_CARD_BORDER}; "
                f"background: transparent; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: {_SEARCH_BG}; color: {_TEXT}; "
                f"border: 1px solid {_CARD_BORDER}; border-radius: 7px; "
                f"padding: 0 14px; font-family: '{_FONT}'; font-size: 12px; }}"
                f"QPushButton:hover {{ background: #222b36; border-color: {_TEXT_DIM}; }}"
                f"QPushButton:disabled {{ color: {_TEXT_DIM}; }}"
            )


class _IconButton(QPushButton):
    """Compact header control (back / close)."""

    def __init__(self, icon: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 8px; }}"
            f"QPushButton:hover {{ background: {_NAV_HOVER}; }}"
            f"QPushButton:pressed {{ background: {_NAV_ACTIVE}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._icon = _LineIcon(icon, _TEXT_MED, 16)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignCenter)

    def enterEvent(self, e):  # noqa: N802
        self._icon.set_color(_TEXT)
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._icon.set_color(_TEXT_MED)
        super().leaveEvent(e)


class _CloseGlyph(QWidget):
    """Explicit ✕ — readable even if macOS traffic lights are wrong."""

    def __init__(self, color: str = _TEXT_MED, size: int = 14, parent=None):
        super().__init__(parent)
        self._color = color
        self._sz = size
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        if color != self._color:
            self._color = color
            self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PyQt6.QtGui import QPen

        pen = QPen(QColor(self._color))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = 2.5
        p.drawLine(int(m), int(m), int(self._sz - m), int(self._sz - m))
        p.drawLine(int(self._sz - m), int(m), int(m), int(self._sz - m))


class _CloseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Close")
        self.setAccessibleName("Close")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 8px; }}"
            f"QPushButton:hover {{ background: rgba(255,68,102,0.14); }}"
            f"QPushButton:pressed {{ background: rgba(255,68,102,0.22); }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._glyph = _CloseGlyph(_TEXT_MED, 14)
        lay.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignCenter)

    def enterEvent(self, e):  # noqa: N802
        self._glyph.set_color(T.RED)
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._glyph.set_color(_TEXT_MED)
        super().leaveEvent(e)


class _NavItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, key: str, label: str, icon: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._active = False
        self._hover = False
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)
        self._icon = _LineIcon(icon, _TEXT_DIM, 15)
        self._label = QLabel(label)
        self._label.setFont(QFont(_FONT, 12))
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._label, 1, Qt.AlignmentFlag.AlignVCenter)
        self._apply()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._apply()

    def _apply(self) -> None:
        if self._active:
            bg = _NAV_ACTIVE
            fg = _TEXT
        elif self._hover:
            bg = _NAV_HOVER
            fg = _TEXT
        else:
            bg = "transparent"
            fg = _TEXT_MED
        self.setStyleSheet(f"QFrame {{ background: {bg}; border: none; border-radius: 8px; }}")
        self._label.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self._icon.set_color(fg if self._active else _TEXT_DIM)

    def enterEvent(self, e):  # noqa: N802
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(e)


class _SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont(_FONT, 20, QFont.Weight.DemiBold))
        self.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")


class _Hint(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setFont(QFont(_FONT, 11))
        self.setStyleSheet(f"color: {_TEXT_DIM}; background: transparent; border: none;")


class _Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setStyleSheet(
            f"QFrame#SettingsCard {{ background: {_CARD}; border: 1px solid {_CARD_BORDER}; "
            f"border-radius: 10px; }}"
        )
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

    def add_row(self, row: QWidget) -> None:
        self._lay.addWidget(row)

    def add_separator(self) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {_CARD_BORDER}; border: none; margin: 0 14px;")
        self._lay.addWidget(line)


class _SettingRow(QFrame):
    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        trailing: QWidget | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setFont(QFont(_FONT, 13, QFont.Weight.Medium))
        t.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        text_col.addWidget(t)
        if description:
            d = QLabel(description)
            d.setWordWrap(True)
            d.setFont(QFont(_FONT, 11))
            d.setStyleSheet(f"color: {_TEXT_DIM}; background: transparent; border: none;")
            text_col.addWidget(d)
        lay.addLayout(text_col, stretch=1)
        if trailing is not None:
            lay.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)


class _ValueLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setFont(QFont(_FONT, 12))
        self.setStyleSheet(f"color: {_TEXT_MED}; background: transparent; border: none;")
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


# Nested well + recessed input — Cursor API Keys look, AURA palette.
_WELL = "#1a222c"
_INPUT_BG = "#0d1218"
_LINK = "#3d8bfd"


class _KeyInput(QLineEdit):
    """Password-style key field recessed inside a well."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setFixedHeight(34)
        self.setFont(QFont(_FONT, 12))
        self.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {_INPUT_BG}; color: {_TEXT};"
            f"  border: 1px solid {_CARD_BORDER}; border-radius: 6px;"
            f"  padding: 0 10px; font-family: '{_FONT}'; font-size: 12px;"
            f"  selection-background-color: {_TOGGLE_ON};"
            f"}}"
            f"QLineEdit:focus {{ border: 1px solid {_ACCENT}; }}"
            f"QLineEdit::placeholder {{ color: {_TEXT_DIM}; }}"
        )


class _ApiKeyBlock(QWidget):
    """Title + description + nested input well (Cursor-style)."""

    def __init__(
        self,
        title: str,
        description: str,
        placeholder: str,
        *,
        parent=None,
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        t = QLabel(title)
        t.setFont(QFont(_FONT, 13, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        lay.addWidget(t)
        lay.addSpacing(4)

        d = QLabel(description)
        d.setWordWrap(True)
        d.setFont(QFont(_FONT, 11))
        d.setTextFormat(Qt.TextFormat.RichText)
        d.setOpenExternalLinks(True)
        d.setStyleSheet(
            f"color: {_TEXT_DIM}; background: transparent; border: none;"
            f"a {{ color: {_LINK}; text-decoration: none; }}"
            f"a:hover {{ text-decoration: underline; }}"
        )
        lay.addWidget(d)
        lay.addSpacing(10)

        well = QFrame()
        well.setObjectName("ApiKeyWell")
        well.setStyleSheet(
            f"QFrame#ApiKeyWell {{"
            f"  background: {_WELL}; border: 1px solid {_CARD_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
        well_l = QVBoxLayout(well)
        well_l.setContentsMargins(10, 10, 10, 10)
        well_l.setSpacing(0)
        self.input = _KeyInput(placeholder)
        well_l.addWidget(self.input)
        lay.addWidget(well)

    def text(self) -> str:
        return self.input.text()

    def setText(self, value: str) -> None:  # noqa: N802
        self.input.setText(value)


class _ToggleKeyBlock(QWidget):
    """Toggle row; when on, shows a nested multi-field well (Azure/AWS Cursor style)."""

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        fields: list[tuple[str, str]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._fields: dict[str, _KeyInput] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setFont(QFont(_FONT, 13, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        text_col.addWidget(t)
        if description:
            d = QLabel(description)
            d.setWordWrap(True)
            d.setFont(QFont(_FONT, 11))
            d.setStyleSheet(
                f"color: {_TEXT_DIM}; background: transparent; border: none;"
            )
            text_col.addWidget(d)
        head.addLayout(text_col, stretch=1)
        self.toggle = _PillToggle(False)
        head.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)

        self._well = QFrame()
        self._well.setObjectName("ApiKeyWell")
        self._well.setStyleSheet(
            f"QFrame#ApiKeyWell {{"
            f"  background: {_WELL}; border: 1px solid {_CARD_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
        well_l = QVBoxLayout(self._well)
        well_l.setContentsMargins(12, 8, 12, 8)
        well_l.setSpacing(0)
        for i, (label, placeholder) in enumerate(fields or []):
            if i:
                sep = QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet(
                    f"background: {_CARD_BORDER}; border: none; margin: 0;"
                )
                well_l.addWidget(sep)
            row = QHBoxLayout()
            row.setContentsMargins(0, 8, 0, 8)
            row.setSpacing(12)
            lbl = QLabel(label)
            lbl.setFont(QFont(_FONT, 12))
            lbl.setStyleSheet(
                f"color: {_TEXT_MED}; background: transparent; border: none;"
            )
            lbl.setMinimumWidth(110)
            row.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            inp = _KeyInput(placeholder)
            inp.setEchoMode(QLineEdit.EchoMode.Normal)
            row.addWidget(inp, 1)
            well_l.addLayout(row)
            self._fields[label] = inp
        self._well_wrap = QWidget()
        wrap_l = QVBoxLayout(self._well_wrap)
        wrap_l.setContentsMargins(0, 10, 0, 0)
        wrap_l.setSpacing(0)
        wrap_l.addWidget(self._well)
        self._well_wrap.setVisible(False)
        lay.addWidget(self._well_wrap)
        self.toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, on: bool) -> None:
        self._well_wrap.setVisible(bool(on))

    def field(self, label: str) -> str:
        w = self._fields.get(label)
        return w.text() if w is not None else ""

    def set_field(self, label: str, value: str) -> None:
        w = self._fields.get(label)
        if w is not None:
            w.setText(value)

    def is_on(self) -> bool:
        return self.toggle.isChecked()

    def set_on(self, on: bool) -> None:
        self.toggle.setChecked(bool(on))
        self._well_wrap.setVisible(bool(on))


# ── Page builders ───────────────────────────────────────────────────────────


def _scroll_page(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setStyleSheet(
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}"
        f"QScrollBar::handle:vertical {{ background: {_CARD_BORDER}; border-radius: 4px; min-height: 28px; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
    )
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(28, 8, 28, 28)
    lay.setSpacing(0)
    lay.addWidget(inner)
    lay.addStretch(1)
    area.setWidget(wrap)
    return area


def _page_root() -> tuple[QWidget, QVBoxLayout]:
    root = QWidget()
    root.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(root)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(16)
    return root, lay


def _live_model_label() -> str:
    # Prefer the already-loaded runtime module; never import main (heavy side effects).
    mod = sys.modules.get("main")
    raw = ""
    if mod is not None:
        raw = str(getattr(mod, "LIVE_MODEL", "") or "").strip()
    if raw.startswith("models/"):
        raw = raw[len("models/") :]
    return raw or _LIVE_MODEL_FALLBACK


class SettingsWindow(QWidget):
    """In-window two-pane settings — General, Account, Voice, Plan, Models, Updates, Docs."""

    closed = pyqtSignal()

    NAV: list[tuple[str, str, str]] = [
        ("general", "General", "settings"),
        ("account", "Account", "user"),
        ("voice", "Voice & Wake", "clap"),
        ("plan", "Plan & Usage", "credit"),
        ("models", "Models", "cube"),
        ("updates", "Updates", "download"),
        ("docs", "Docs & Support", "book"),
    ]

    def __init__(self, parent=None, *, updater: Any | None = None):
        super().__init__(parent)
        self._updater = updater
        self._nav_items: dict[str, _NavItem] = {}
        self._page_keys: list[str] = []
        self._current = "general"

        self.setObjectName("AuraSettingsPage")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            f"QWidget#AuraSettingsPage {{ background: {_BG}; color: {_TEXT}; }}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), stretch=1)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close_page)

        self._select("general")

    def set_updater(self, updater: Any | None) -> None:
        self._updater = updater

    def open_page(self, section: str = "general") -> None:
        """Show this page: select section, refresh live data."""
        self._select(section if section in self._nav_items else "general")
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, self._refresh_dynamic)

    def close_page(self) -> None:
        self.closed.emit()

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setFixedWidth(_SIDEBAR_W)
        side.setStyleSheet(
            f"QFrame {{ background: {_SIDEBAR}; border: none; "
            f"border-right: 1px solid {_CARD_BORDER}; }}"
        )
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(4)

        # Cursor-like: Back sits above the first nav item (where Search used to).
        back = QPushButton("←  Back")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setFixedHeight(32)
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 8px; "
            f"color: {_TEXT_MED}; font-family: '{_FONT}'; font-size: 13px; "
            f"text-align: left; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: {_NAV_HOVER}; color: {_TEXT}; }}"
            f"QPushButton:pressed {{ background: {_NAV_ACTIVE}; }}"
        )
        back.clicked.connect(self.close_page)
        lay.addWidget(back)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background: {_CARD_BORDER}; border: none; margin: 6px 4px 8px 4px;"
        )
        lay.addWidget(sep)

        for key, label, icon in self.NAV:
            item = _NavItem(key, label, icon)
            item.clicked.connect(self._on_nav)
            self._nav_items[key] = item
            lay.addWidget(item)

        lay.addStretch(1)
        return side

    def _build_content(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {_BG};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top-right Close only — Back lives in the sidebar.
        top = QFrame()
        top.setFixedHeight(44)
        top.setStyleSheet(f"QFrame {{ background: {_BG}; border: none; }}")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(16, 8, 16, 0)
        top_lay.setSpacing(0)
        top_lay.addStretch(1)
        close_btn = _CloseButton()
        close_btn.clicked.connect(self.close_page)
        top_lay.addWidget(close_btn)
        lay.addWidget(top)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        builders: list[tuple[str, Callable[[], QWidget]]] = [
            ("general", self._page_general),
            ("account", self._page_account),
            ("voice", self._page_voice),
            ("plan", self._page_plan),
            ("models", self._page_models),
            ("updates", self._page_updates),
            ("docs", self._page_docs),
        ]
        for key, builder in builders:
            self._page_keys.append(key)
            self._stack.addWidget(_scroll_page(builder()))
        lay.addWidget(self._stack, stretch=1)
        return panel

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_page()
            return
        super().keyPressEvent(event)

    # ── Navigation ──────────────────────────────────────────────────────────

    def _on_nav(self, key: str) -> None:
        self._select(key)

    def _select(self, key: str) -> None:
        if key not in self._nav_items:
            return
        self._current = key
        for k, item in self._nav_items.items():
            item.set_active(k == key)
        if key in self._page_keys:
            self._stack.setCurrentIndex(self._page_keys.index(key))
        self._refresh_dynamic()

    # ── Pages ───────────────────────────────────────────────────────────────

    def _page_general(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("General"))
        lay.addWidget(_Hint("App identity and developer API keys."))

        card = _Card()
        self._version_value = _ValueLabel(f"v{VERSION}")
        card.add_row(
            _SettingRow(
                "Version",
                f"You are running {APP_NAME}.",
                trailing=self._version_value,
            )
        )
        card.add_separator()

        api_btn = _GhostButton("Edit…")
        api_btn.clicked.connect(self._open_api_keys)
        card.add_row(
            _SettingRow(
                "Gemini API key",
                "Powers chat, voice, and Forge.",
                trailing=api_btn,
            )
        )
        lay.addWidget(card)
        return root

    def _page_account(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Account"))
        lay.addWidget(_Hint("Signed-in profile, plan, and session."))

        card = _Card()
        self._acct_name = _ValueLabel("—")
        self._acct_email = _ValueLabel("—")
        self._acct_plan = _ValueLabel("—")
        card.add_row(_SettingRow("Name", trailing=self._acct_name))
        card.add_separator()
        card.add_row(_SettingRow("Email", trailing=self._acct_email))
        card.add_separator()
        card.add_row(_SettingRow("Plan", trailing=self._acct_plan))
        lay.addWidget(card)

        actions = _Card()
        manage = _GhostButton("Manage Account", primary=True)
        manage.clicked.connect(self._manage_account)
        actions.add_row(
            _SettingRow(
                "Manage on the web",
                "Open your AURA account at hiauraai.com.",
                trailing=manage,
            )
        )
        actions.add_separator()
        self._sign_btn = _GhostButton("Log Out")
        self._sign_btn.clicked.connect(self._toggle_auth)
        actions.add_row(
            _SettingRow(
                "Session",
                "Sign out on this device. Cloud billing is unchanged.",
                trailing=self._sign_btn,
            )
        )
        lay.addWidget(actions)
        return root

    def _page_voice(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Voice & Wake"))
        lay.addWidget(_Hint("Hands-free wake: two claps open or focus AURA in the background."))

        card = _Card()
        self._clap_toggle = _PillToggle(False)
        self._clap_toggle.toggled.connect(self._on_clap_toggled)
        row = _SettingRow(
            "Double-clap wake",
            "Two short hand claps open or focus AURA in the background.",
            trailing=self._clap_toggle,
        )
        card.add_row(row)
        lay.addWidget(card)
        self._clap_status = _Hint("")
        lay.addWidget(self._clap_status)
        return root

    def _page_plan(self) -> QWidget:
        """Cursor-style billing: Free vs Pro $20/mo, no usage meters."""
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Plan & Usage"))
        lay.addWidget(_Hint("Keep your subscription in sync with hiauraai.com."))

        card = _Card()
        hero = QWidget()
        hero.setStyleSheet("background: transparent; border: none;")
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(18, 18, 18, 18)
        hero_l.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)
        self._plan_title = QLabel("Free Plan")
        self._plan_title.setFont(QFont(_FONT, 15, QFont.Weight.DemiBold))
        self._plan_title.setStyleSheet(
            f"color: {_TEXT}; background: transparent; border: none;"
        )
        title_row.addWidget(self._plan_title, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        self._plan_badge = QLabel("")
        self._plan_badge.setFont(QFont(_FONT, 10, QFont.Weight.DemiBold))
        self._plan_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._plan_badge.setFixedHeight(22)
        self._plan_badge.hide()
        title_row.addWidget(self._plan_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        hero_l.addLayout(title_row)

        self._plan_desc = QLabel("Upgrade for unlimited desktop access.")
        self._plan_desc.setWordWrap(True)
        self._plan_desc.setFont(QFont(_FONT, 12))
        self._plan_desc.setStyleSheet(
            f"color: {_TEXT_MED}; background: transparent; border: none;"
        )
        hero_l.addWidget(self._plan_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 8, 0, 0)
        self._plan_primary = _GhostButton("Subscribe — $20 / month", primary=True)
        self._plan_primary.clicked.connect(self._plan_primary_action)
        btn_row.addWidget(self._plan_primary, 0, Qt.AlignmentFlag.AlignLeft)
        btn_row.addStretch(1)
        hero_l.addLayout(btn_row)

        card.add_row(hero)
        lay.addWidget(card)
        return root

    def _page_models(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Models"))
        lay.addWidget(
            _Hint(
                "Voice stays on Gemini. Chat & agents can use free AI on this computer."
            )
        )

        card = _Card()
        self._model_provider = _ValueLabel("gemini")
        self._model_name = _ValueLabel(_DISPLAY_MODEL)
        self._model_live = _ValueLabel(_live_model_label())
        card.add_row(
            _SettingRow(
                "Forge model",
                "Fixed for Website Builder when using Gemini.",
                trailing=self._model_name,
            )
        )
        card.add_separator()
        card.add_row(
            _SettingRow(
                "Live voice model",
                "Realtime audio — always Gemini.",
                trailing=self._model_live,
            )
        )
        lay.addWidget(card)

        # Free Local AI (Ollama) — hardware-aware, one-click setup.
        lay.addSpacing(4)
        lay.addWidget(self._build_local_ai_card())

        # Cursor-style API Keys — below models card, AURA theme (not gray).
        lay.addSpacing(8)
        keys_hdr = QLabel("API Keys")
        keys_hdr.setFont(QFont(_FONT, 16, QFont.Weight.DemiBold))
        keys_hdr.setStyleSheet(
            f"color: {_TEXT}; background: transparent; border: none;"
        )
        lay.addWidget(keys_hdr)
        lay.addWidget(
            _Hint("Bring your own keys. Stored locally in config/api_keys.json.")
        )

        self._key_gemini = _ApiKeyBlock(
            "Google API Key",
            'Gemini powers voice and cloud chat. Get '
            '<a href="https://aistudio.google.com/apikey">your Google AI key</a>.',
            "Enter your Google / Gemini API Key",
        )
        lay.addWidget(self._key_gemini)

        self._key_openai = _ApiKeyBlock(
            "OpenAI API Key",
            'Optional router / compatible models. Get '
            '<a href="https://platform.openai.com/api-keys">your OpenAI key</a>.',
            "Enter your OpenAI API Key",
        )
        lay.addWidget(self._key_openai)

        self._openai_base = _ToggleKeyBlock(
            "Override OpenAI Base URL",
            "Use a custom OpenAI-compatible endpoint.",
            fields=[("Base URL", "https://api.openai.com/v1")],
        )
        lay.addWidget(self._openai_base)

        self._key_openrouter = _ApiKeyBlock(
            "OpenRouter API Key",
            'Multi-provider routing. Get '
            '<a href="https://openrouter.ai/keys">your OpenRouter key</a>.',
            "Enter your OpenRouter API Key",
        )
        lay.addWidget(self._key_openrouter)

        self._key_groq = _ApiKeyBlock(
            "Groq API Key",
            'Fast inference. Get '
            '<a href="https://console.groq.com/keys">your Groq key</a>.',
            "Enter your Groq API Key",
        )
        lay.addWidget(self._key_groq)

        self._key_deepseek = _ApiKeyBlock(
            "DeepSeek API Key",
            'Get <a href="https://platform.deepseek.com/api_keys">your DeepSeek key</a>.',
            "Enter your DeepSeek API Key",
        )
        lay.addWidget(self._key_deepseek)

        self._key_together = _ApiKeyBlock(
            "Together API Key",
            'Get <a href="https://api.together.xyz/settings/api-keys">your Together key</a>.',
            "Enter your Together API Key",
        )
        lay.addWidget(self._key_together)

        self._local_models = _ToggleKeyBlock(
            "Advanced local endpoints",
            "Custom Ollama / LM Studio URLs (optional).",
            fields=[
                ("Ollama URL", "http://localhost:11434/api/generate"),
                ("LM Studio URL", "http://localhost:1234/v1"),
            ],
        )
        lay.addWidget(self._local_models)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 4, 0, 0)
        save_row.addStretch(1)
        save_btn = _GhostButton("Save API Keys", primary=True)
        save_btn.clicked.connect(self._save_api_keys_inline)
        save_row.addWidget(save_btn, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(save_row)

        self._load_api_keys_inline()
        QTimer.singleShot(80, self._refresh_local_ai_card)
        return root

    # ── Local AI (Ollama) ───────────────────────────────────────────────────

    def _build_local_ai_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("LocalAiCard")
        card.setStyleSheet(
            f"QFrame#LocalAiCard {{ background: {_CARD}; border: 1px solid {_CARD_BORDER}; "
            f"border-radius: 10px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        t = QLabel("Free AI on this computer")
        t.setFont(QFont(_FONT, 14, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        titles.addWidget(t)
        self._local_ai_hint = QLabel(
            "Download once · chat free forever · voice still uses Gemini"
        )
        self._local_ai_hint.setWordWrap(True)
        self._local_ai_hint.setFont(QFont(_FONT, 11))
        self._local_ai_hint.setStyleSheet(
            f"color: {_TEXT_DIM}; background: transparent; border: none;"
        )
        titles.addWidget(self._local_ai_hint)
        head.addLayout(titles, stretch=1)
        self._local_ai_toggle = _PillToggle(False)
        self._local_ai_toggle.setToolTip("Use local AI for chat & agents")
        self._local_ai_toggle.toggled.connect(self._on_local_ai_toggled)
        head.addWidget(self._local_ai_toggle, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        # Soft hardware chip
        self._local_ai_hw = QLabel("Checking your computer…")
        self._local_ai_hw.setWordWrap(True)
        self._local_ai_hw.setFont(QFont(_FONT, 11))
        self._local_ai_hw.setStyleSheet(
            f"color: {_TEXT_MED}; background: {_SEARCH_BG}; border: 1px solid {_CARD_BORDER}; "
            f"border-radius: 8px; padding: 8px 10px;"
        )
        lay.addWidget(self._local_ai_hw)

        rec_row = QHBoxLayout()
        rec_row.setSpacing(10)
        rl = QLabel("Best for you")
        rl.setFont(QFont(_FONT, 12))
        rl.setStyleSheet(f"color: {_TEXT_MED}; background: transparent; border: none;")
        rl.setMinimumWidth(90)
        rec_row.addWidget(rl)
        self._local_ai_model = QComboBox()
        self._local_ai_model.setFixedHeight(32)
        self._local_ai_model.setFont(QFont(_FONT, 12))
        self._local_ai_model.setStyleSheet(
            f"QComboBox {{ background: {_SEARCH_BG}; color: {_TEXT}; "
            f"border: 1px solid {_CARD_BORDER}; border-radius: 8px; padding: 0 10px; }}"
            f"QComboBox:hover {{ border-color: {_TEXT_DIM}; }}"
            f"QComboBox QAbstractItemView {{ background: {_CARD}; color: {_TEXT}; "
            f"selection-background-color: {_CARD_BORDER}; }}"
        )
        self._local_ai_model.currentIndexChanged.connect(self._on_local_ai_model_changed)
        rec_row.addWidget(self._local_ai_model, stretch=1)
        lay.addLayout(rec_row)

        self._local_ai_rec_blurb = QLabel("")
        self._local_ai_rec_blurb.setWordWrap(True)
        self._local_ai_rec_blurb.setFont(QFont(_FONT, 11))
        self._local_ai_rec_blurb.setStyleSheet(
            f"color: {_TEXT_DIM}; background: transparent; border: none;"
        )
        lay.addWidget(self._local_ai_rec_blurb)

        self._local_ai_status = QLabel("Status: —")
        self._local_ai_status.setWordWrap(True)
        self._local_ai_status.setFont(QFont(_FONT, 12, QFont.Weight.Medium))
        self._local_ai_status.setStyleSheet(
            f"color: {_TEXT}; background: transparent; border: none;"
        )
        lay.addWidget(self._local_ai_status)

        # Download panel — Cursor-like nested well with real MB progress.
        self._local_ai_dl = QFrame()
        self._local_ai_dl.setObjectName("LocalAiDownload")
        self._local_ai_dl.setVisible(False)
        self._local_ai_dl.setStyleSheet(
            f"QFrame#LocalAiDownload {{ background: {_SEARCH_BG}; "
            f"border: 1px solid {_CARD_BORDER}; border-radius: 10px; }}"
        )
        dl = QVBoxLayout(self._local_ai_dl)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.setSpacing(8)

        dl_top = QHBoxLayout()
        dl_top.setSpacing(8)
        self._local_ai_dl_title = QLabel("Downloading…")
        self._local_ai_dl_title.setFont(QFont(_FONT, 12, QFont.Weight.DemiBold))
        self._local_ai_dl_title.setStyleSheet(
            f"color: {_TEXT}; background: transparent; border: none;"
        )
        dl_top.addWidget(self._local_ai_dl_title, stretch=1)
        self._local_ai_dl_pct = QLabel("")
        self._local_ai_dl_pct.setFont(QFont(_FONT, 12, QFont.Weight.DemiBold))
        self._local_ai_dl_pct.setStyleSheet(
            f"color: {_ACCENT}; background: transparent; border: none;"
        )
        dl_top.addWidget(self._local_ai_dl_pct)
        dl.addLayout(dl_top)

        self._local_ai_progress = QProgressBar()
        self._local_ai_progress.setFixedHeight(10)
        self._local_ai_progress.setTextVisible(False)
        self._local_ai_progress.setRange(0, 100)
        self._local_ai_progress.setValue(0)
        self._local_ai_progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(0,0,0,0.35); border: none; "
            f"border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 5px; }}"
        )
        dl.addWidget(self._local_ai_progress)

        self._local_ai_dl_detail = QLabel("")
        self._local_ai_dl_detail.setWordWrap(True)
        self._local_ai_dl_detail.setFont(QFont(_FONT, 11))
        self._local_ai_dl_detail.setStyleSheet(
            f"color: {_TEXT_MED}; background: transparent; border: none;"
        )
        dl.addWidget(self._local_ai_dl_detail)
        lay.addWidget(self._local_ai_dl)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._local_ai_primary = _GhostButton("Set up free AI", primary=True)
        self._local_ai_primary.clicked.connect(self._on_local_ai_primary)
        actions.addWidget(self._local_ai_primary)
        self._local_ai_secondary = _GhostButton("Install Ollama…")
        self._local_ai_secondary.clicked.connect(self._on_local_ai_install)
        actions.addWidget(self._local_ai_secondary)
        self._local_ai_refresh = _GhostButton("Refresh")
        self._local_ai_refresh.clicked.connect(self._refresh_local_ai_card)
        actions.addWidget(self._local_ai_refresh)
        actions.addStretch(1)
        lay.addLayout(actions)

        self._local_ai_busy = False
        self._local_ai_recs: list = []
        self._local_ai_last_pull_bytes = 0
        return card

    def _refresh_local_ai_card(self) -> None:
        if not hasattr(self, "_local_ai_hw"):
            return
        if self._local_ai_busy:
            return
        if hasattr(self, "_local_ai_dl"):
            self._local_ai_dl.setVisible(False)
        try:
            from jarvis_ui.local_ai.hardware import probe_hardware
            from jarvis_ui.local_ai.ollama_client import get_ollama_client
            from jarvis_ui.local_ai.prefs import load_prefs, save_prefs
            from jarvis_ui.local_ai.recommend import catalog_for_hardware, recommend_model
        except Exception as e:
            self._local_ai_status.setText(f"Status: error — {e}")
            return

        hw = probe_hardware()
        self._local_ai_hw.setText(f"Your computer: {hw.summary}")
        prefs = load_prefs()
        recs = catalog_for_hardware(hw)
        self._local_ai_recs = recs
        primary = recommend_model(hw)

        self._local_ai_model.blockSignals(True)
        self._local_ai_model.clear()
        saved = str(prefs.get("ollama_model") or "")
        select_idx = 0
        for i, rec in enumerate(recs):
            label = f"{rec.label}  ·  {rec.model_id}  ·  ~{rec.size_gb:.1f} GB"
            self._local_ai_model.addItem(label, rec.model_id)
            if saved and saved == rec.model_id:
                select_idx = i
            elif not saved and rec.model_id == primary.model_id:
                select_idx = i
        self._local_ai_model.setCurrentIndex(select_idx)
        self._local_ai_model.blockSignals(False)

        cur = self._local_ai_model.currentData()
        cur_rec = next((r for r in recs if r.model_id == cur), primary)
        self._local_ai_rec_blurb.setText(
            f"{cur_rec.blurb} · download once, then free unlimited chat"
        )

        save_prefs(
            {
                "recommended_model": primary.model_id,
                "recommended_label": primary.label,
                "last_probe_ram_gb": int(hw.ram_gb),
                "ollama_model": str(cur or primary.model_id),
            }
        )

        client = get_ollama_client(str(prefs.get("ollama_base_url") or ""))
        st = client.status()
        model_ok = bool(cur) and client.model_installed(str(cur))
        enabled = bool(prefs.get("use_ollama_for_chat")) and st.server_up and model_ok

        self._local_ai_toggle.blockSignals(True)
        self._local_ai_toggle.setChecked(enabled and bool(prefs.get("use_ollama_for_chat")))
        # Keep pref if user enabled but model not ready yet — don't force off silently
        if prefs.get("use_ollama_for_chat") and not (st.server_up and model_ok):
            self._local_ai_toggle.setChecked(False)
        elif prefs.get("use_ollama_for_chat"):
            self._local_ai_toggle.setChecked(True)
        self._local_ai_toggle.blockSignals(False)

        if not st.server_up:
            color = "#fbbf24"
            self._local_ai_status.setText(f"Status: {st.message}")
            self._local_ai_primary.setText("Download recommended model")
            self._local_ai_primary.setEnabled(False)
            self._local_ai_secondary.setText("Install Ollama…")
            self._local_ai_secondary.setVisible(True)
            self._local_ai_toggle.setEnabled(False)
        elif not model_ok:
            color = "#fbbf24"
            need = f"~{cur_rec.size_gb:.1f} GB"
            if not cur_rec.ok_for_disk:
                self._local_ai_status.setText(
                    f"Status: need {need} free disk space for {cur}"
                )
                self._local_ai_primary.setEnabled(False)
            else:
                self._local_ai_status.setText(
                    f"Status: Ollama ready — download {cur} ({need}, one time)"
                )
                self._local_ai_primary.setEnabled(True)
            self._local_ai_primary.setText("Download && turn on")
            self._local_ai_secondary.setText("Open Ollama")
            self._local_ai_secondary.setVisible(True)
            self._local_ai_toggle.setEnabled(False)
        else:
            color = "#34d399"
            self._local_ai_status.setText(
                f"Status: ready · {cur} downloaded · toggle to use for chat"
            )
            self._local_ai_primary.setText("Test reply")
            self._local_ai_primary.setEnabled(True)
            self._local_ai_secondary.setText("Open Ollama")
            self._local_ai_secondary.setVisible(True)
            self._local_ai_toggle.setEnabled(True)

        self._local_ai_status.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        if prefs.get("use_ollama_for_chat") and st.server_up and model_ok:
            self._model_provider.setText("ollama")
        else:
            self._model_provider.setText("gemini")

    def _on_local_ai_model_changed(self, *_args) -> None:
        if self._local_ai_busy:
            return
        mid = str(self._local_ai_model.currentData() or "")
        if not mid:
            return
        from jarvis_ui.local_ai.prefs import save_prefs

        save_prefs({"ollama_model": mid})
        rec = next((r for r in self._local_ai_recs if r.model_id == mid), None)
        if rec:
            self._local_ai_rec_blurb.setText(
                f"{rec.blurb} · download once, then free unlimited chat"
            )
        self._refresh_local_ai_card()

    def _on_local_ai_toggled(self, on: bool) -> None:
        if self._local_ai_busy:
            return
        from jarvis_ui.local_ai.ollama_client import get_ollama_client
        from jarvis_ui.local_ai.prefs import save_prefs

        mid = str(self._local_ai_model.currentData() or "")
        client = get_ollama_client()
        st = client.status()
        if on and not (st.server_up and mid and client.model_installed(mid)):
            self._local_ai_toggle.blockSignals(True)
            self._local_ai_toggle.setChecked(False)
            self._local_ai_toggle.blockSignals(False)
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Free AI",
                "Download the recommended model first, then turn this on.",
            )
            return
        save_prefs(
            {
                "use_ollama_for_chat": bool(on),
                "ollama_model": mid,
            }
        )
        self._model_provider.setText("ollama" if on else "gemini")
        self._local_ai_status.setText(
            "Status: using free AI on this computer for chat"
            if on
            else "Status: chat uses Gemini / cloud — local AI off"
        )

    def _on_local_ai_install(self) -> None:
        from jarvis_ui.local_ai.ollama_client import get_ollama_client

        client = get_ollama_client()
        st = client.status()
        if st.server_up or st.binary_found:
            client.try_start_app()
            QTimer.singleShot(1500, self._refresh_local_ai_card)
            return
        client.open_install_page()
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "Install Ollama",
            "1. Install Ollama from the page that opened\n"
            "2. Open the Ollama app once\n"
            "3. Come back here and press Refresh\n"
            "4. Tap Download & turn on",
        )

    def _on_local_ai_primary(self) -> None:
        from jarvis_ui.local_ai.ollama_client import get_ollama_client
        from jarvis_ui.local_ai.prefs import save_prefs

        client = get_ollama_client()
        st = client.status()
        mid = str(self._local_ai_model.currentData() or "")
        if not st.server_up:
            client.try_start_app()
            self._local_ai_status.setText("Status: starting Ollama…")
            QTimer.singleShot(2000, self._refresh_local_ai_card)
            return

        if mid and client.model_installed(mid):
            self._local_ai_busy = True
            self._local_ai_primary.setEnabled(False)
            self._local_ai_status.setText("Status: testing…")

            def _work():
                ok, msg = client.test_generate(mid)
                QTimer.singleShot(0, lambda: self._on_local_ai_test_done(ok, msg))

            import threading

            threading.Thread(target=_work, daemon=True).start()
            return

        # Download model
        if not mid:
            return
        rec = next((r for r in self._local_ai_recs if r.model_id == mid), None)
        if rec and not rec.ok_for_disk:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Free AI",
                f"Need about {rec.size_gb:.0f} GB free disk space for this model.",
            )
            return

        self._local_ai_busy = True
        self._local_ai_primary.setEnabled(False)
        self._local_ai_model.setEnabled(False)
        self._local_ai_last_pull_bytes = 0
        est = f"~{rec.size_gb:.1f} GB" if rec else ""
        self._local_ai_status.setText(f"Status: downloading {mid}…")
        self._local_ai_status.setStyleSheet(
            "color: #fbbf24; background: transparent; border: none;"
        )
        self._local_ai_dl.setVisible(True)
        self._local_ai_dl_title.setText(f"Downloading {mid}")
        self._local_ai_dl_pct.setText("…")
        self._local_ai_dl_detail.setText(
            f"Starting download{f' · about {est} total' if est else ''}…"
        )
        self._local_ai_progress.setRange(0, 0)  # indeterminate until totals arrive
        self._local_ai_progress.setValue(0)

        def _on_prog(prog) -> None:
            QTimer.singleShot(0, lambda p=prog: self._on_local_ai_pull_progress(p, mid))

        def _work():
            ok, msg = client.pull(mid, on_progress=_on_prog)
            if not ok:
                ok, msg = client.pull_via_cli(mid, on_progress=_on_prog)
            QTimer.singleShot(0, lambda: self._on_local_ai_pull_done(ok, msg, mid))

        import threading

        threading.Thread(target=_work, daemon=True).start()

    def _on_local_ai_pull_progress(self, prog, model_id: str) -> None:
        from jarvis_ui.local_ai.ollama_client import format_bytes, friendly_pull_status

        if not hasattr(self, "_local_ai_dl"):
            return
        phase = friendly_pull_status(getattr(prog, "status", "") or "")
        completed = int(getattr(prog, "completed", 0) or 0)
        total = int(getattr(prog, "total", 0) or 0)
        frac = float(getattr(prog, "fraction", -1.0))

        self._local_ai_dl.setVisible(True)
        self._local_ai_dl_title.setText(f"{phase}  ·  {model_id}")

        if total > 0 and frac >= 0:
            pct = int(max(0.0, min(1.0, frac)) * 100)
            left = max(0, total - completed)
            self._local_ai_progress.setRange(0, 100)
            self._local_ai_progress.setValue(pct)
            self._local_ai_dl_pct.setText(f"{pct}%")
            self._local_ai_dl_detail.setText(
                f"{format_bytes(completed)} of {format_bytes(total)}"
                f"  ·  {format_bytes(left)} left"
            )
            self._local_ai_last_pull_bytes = total
            self._local_ai_status.setText(
                f"Status: {phase.lower()} — {format_bytes(left)} remaining"
            )
        else:
            self._local_ai_progress.setRange(0, 0)
            self._local_ai_dl_pct.setText("")
            self._local_ai_dl_detail.setText(
                "Connecting to Ollama and preparing layers…"
            )
            self._local_ai_status.setText(f"Status: {phase.lower()}…")

    def _on_local_ai_test_done(self, ok: bool, msg: str) -> None:
        self._local_ai_busy = False
        self._local_ai_primary.setEnabled(True)
        self._local_ai_model.setEnabled(True)
        if ok:
            self._local_ai_status.setText(f"Status: works — “{msg[:80]}”")
            self._local_ai_status.setStyleSheet(
                "color: #34d399; background: transparent; border: none;"
            )
        else:
            self._local_ai_status.setText(f"Status: test failed — {msg}")
            self._local_ai_status.setStyleSheet(
                "color: #f87171; background: transparent; border: none;"
            )
        self._refresh_local_ai_card()

    def _on_local_ai_pull_done(self, ok: bool, msg: str, model_id: str) -> None:
        from jarvis_ui.local_ai.ollama_client import format_bytes
        from jarvis_ui.local_ai.prefs import save_prefs

        self._local_ai_busy = False
        self._local_ai_primary.setEnabled(True)
        self._local_ai_model.setEnabled(True)

        if ok:
            size = self._local_ai_last_pull_bytes
            size_txt = f" ({format_bytes(size)})" if size else ""
            save_prefs(
                {
                    "ollama_model": model_id,
                    "use_ollama_for_chat": True,
                }
            )
            self._local_ai_progress.setRange(0, 100)
            self._local_ai_progress.setValue(100)
            self._local_ai_dl.setVisible(True)
            self._local_ai_dl_title.setText(f"Downloaded {model_id}")
            self._local_ai_dl_pct.setText("100%")
            self._local_ai_dl_detail.setText(
                f"Saved on this computer{size_txt}. Free local chat is ready."
            )
            self._local_ai_status.setText(
                f"Status: downloaded {model_id}{size_txt} — local AI is on"
            )
            self._local_ai_status.setStyleSheet(
                "color: #34d399; background: transparent; border: none;"
            )
            self._model_provider.setText("ollama")
            # Keep the success panel visible briefly, then refresh the card.
            QTimer.singleShot(2200, self._hide_local_ai_download_then_refresh)
        else:
            self._local_ai_dl.setVisible(True)
            self._local_ai_dl_title.setText("Download failed")
            self._local_ai_dl_pct.setText("")
            self._local_ai_dl_detail.setText(msg or "Something went wrong.")
            self._local_ai_progress.setRange(0, 100)
            self._local_ai_progress.setValue(0)
            self._local_ai_status.setText(f"Status: download failed — {msg}")
            self._local_ai_status.setStyleSheet(
                "color: #f87171; background: transparent; border: none;"
            )
            self._local_ai_busy = False

    def _hide_local_ai_download_then_refresh(self) -> None:
        if hasattr(self, "_local_ai_dl"):
            self._local_ai_dl.setVisible(False)
        self._refresh_local_ai_card()

    def _page_updates(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Updates"))
        lay.addWidget(_Hint("Keep AURA current with the stable release channel."))

        card = _Card()
        self._upd_installed = _ValueLabel(f"v{VERSION}")
        self._upd_latest = _ValueLabel("—")
        self._upd_status = _ValueLabel("—")
        card.add_row(_SettingRow("Installed version", trailing=self._upd_installed))
        card.add_separator()
        card.add_row(_SettingRow("Latest available", trailing=self._upd_latest))
        card.add_separator()
        card.add_row(_SettingRow("Status", trailing=self._upd_status))
        lay.addWidget(card)

        actions = _Card()
        check = _GhostButton("Check for Updates")
        check.clicked.connect(self._check_updates)
        update_btn = _GhostButton("Update", primary=True)
        update_btn.clicked.connect(self._open_update_ui)
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(8)
        row_l.addWidget(check)
        row_l.addWidget(update_btn)
        actions.add_row(
            _SettingRow(
                "Release channel",
                "Stable updates from hiauraai.com.",
                trailing=row_w,
            )
        )
        lay.addWidget(actions)
        return root

    def _page_docs(self) -> QWidget:
        root, lay = _page_root()
        lay.addWidget(_SectionHeader("Docs & Support"))
        lay.addWidget(_Hint("Legal docs, billing help, and contact."))

        card = _Card()
        privacy = _GhostButton("Open", primary=True)
        privacy.clicked.connect(
            lambda: webbrowser.open("https://www.hiauraai.com/privacy")
        )
        card.add_row(
            _SettingRow(
                "Privacy Policy",
                "How A.U.R.A handles your data on hiauraai.com.",
                trailing=privacy,
            )
        )
        card.add_separator()
        terms = _GhostButton("Open")
        terms.clicked.connect(
            lambda: webbrowser.open("https://www.hiauraai.com/terms")
        )
        card.add_row(
            _SettingRow(
                "Terms of Use",
                "Terms of Service for using A.U.R.A.",
                trailing=terms,
            )
        )
        card.add_separator()
        support = _GhostButton("Support")
        support.clicked.connect(self._open_support)
        card.add_row(
            _SettingRow(
                "Help & Support",
                "Contact and account assistance.",
                trailing=support,
            )
        )
        card.add_separator()
        site = _GhostButton("Website")
        site.clicked.connect(lambda: webbrowser.open("https://www.hiauraai.com"))
        card.add_row(
            _SettingRow(
                "hiauraai.com",
                "Product home and marketing site.",
                trailing=site,
            )
        )
        lay.addWidget(card)
        return root

    # ── Dynamic refresh ─────────────────────────────────────────────────────

    def _refresh_dynamic(self) -> None:
        self._refresh_account()
        self._refresh_plan()
        self._refresh_models()
        self._refresh_clap()
        self._refresh_updates()

    def _host_window(self):
        """Walk parents to the main window (stack reparents this page)."""
        w = self.parent()
        while w is not None:
            if hasattr(w, "_nav") and hasattr(w, "_updater_ref"):
                return w
            if hasattr(w, "_nav") and hasattr(w, "_open_settings"):
                return w
            w = w.parent() if hasattr(w, "parent") else None
        top = self.window()
        return top if top is not None and top is not self else None

    def _refresh_parent_account_ui(self) -> None:
        host = self._host_window()
        nav = getattr(host, "_nav", None) if host is not None else None
        if nav is not None and hasattr(nav, "refresh_user_account"):
            try:
                nav.refresh_user_account()
            except Exception:
                pass

    def _refresh_account(self) -> None:
        try:
            from jarvis_ui import user_account as UA

            authed = UA.is_authenticated()
            if authed:
                self._acct_name.setText(UA.get_display_name() or "—")
                self._acct_email.setText(UA.get_email() or "—")
                self._acct_plan.setText(UA.get_subtitle() or UA.get_plan().title())
                self._sign_btn.setText("Log Out")
            else:
                self._acct_name.setText("Not signed in")
                self._acct_email.setText("—")
                self._acct_plan.setText("Free")
                self._sign_btn.setText("Sign In")
        except Exception:
            pass

    def _refresh_plan(self) -> None:
        """Cursor-style plan card: Pro $20/mo unlimited, or Free + subscribe."""
        if not hasattr(self, "_plan_title"):
            return
        try:
            from jarvis_ui import user_account as UA

            paid = UA.is_authenticated() and UA.has_active_subscription()
            if paid:
                plan = UA.get_plan().replace("_", " ").title() or "Pro"
                self._plan_title.setText(f"{plan} Plan")
                self._plan_desc.setText("$20 / month · Unlimited AURA access")
                self._plan_badge.setText("  Active  ")
                self._plan_badge.setStyleSheet(
                    f"QLabel {{ color: {_ACCENT}; background: rgba(0,209,255,0.12); "
                    f"border: 1px solid rgba(0,209,255,0.28); border-radius: 11px; "
                    f"padding: 0 8px; }}"
                )
                self._plan_badge.show()
                self._plan_primary.setText("Manage billing")
            else:
                self._plan_title.setText("Free Plan")
                self._plan_desc.setText(
                    "Upgrade for unlimited desktop access — $20 / month."
                )
                self._plan_badge.hide()
                self._plan_primary.setText("Subscribe — $20 / month")
        except Exception:
            self._plan_title.setText("Free Plan")
            self._plan_desc.setText("Upgrade for unlimited desktop access — $20 / month.")
            self._plan_badge.hide()
            self._plan_primary.setText("Subscribe — $20 / month")

    def _refresh_models(self) -> None:
        self._model_provider.setText("gemini")
        self._model_name.setText(_DISPLAY_MODEL)
        self._model_live.setText(_live_model_label())
        if hasattr(self, "_key_gemini"):
            self._load_api_keys_inline()
        if hasattr(self, "_local_ai_hw"):
            self._refresh_local_ai_card()

    def _refresh_clap(self) -> None:
        try:
            from jarvis_ui.wake_bootstrap import is_wake_enabled_pref, is_wake_installed

            on = is_wake_installed() and is_wake_enabled_pref()
        except Exception:
            on = False
        self._clap_toggle.blockSignals(True)
        self._clap_toggle.setChecked(on)
        self._clap_toggle.blockSignals(False)
        self._clap_status.setText(
            "Wake agent is installed and will start at login."
            if on
            else "Wake agent is off. Toggle to install the double-clap listener."
        )

    def _refresh_updates(self) -> None:
        self._upd_installed.setText(f"v{VERSION}")
        updater = self._resolve_updater()
        if updater is None:
            self._upd_latest.setText("—")
            self._upd_status.setText("Updater unavailable")
            return
        try:
            state = updater.service.state
            if state.error:
                self._upd_latest.setText("—")
                self._upd_status.setText(str(state.error)[:80])
            elif state.downloading:
                self._upd_status.setText("Downloading…")
                if state.release:
                    self._upd_latest.setText(f"v{state.release.version}")
            elif state.release:
                self._upd_latest.setText(f"v{state.release.version}")
                self._upd_status.setText("Update available")
            else:
                self._upd_latest.setText(f"v{VERSION}")
                self._upd_status.setText("Up to date")
        except Exception as e:
            self._upd_status.setText(str(e)[:80])

    def _resolve_updater(self) -> Any | None:
        if self._updater is not None:
            return self._updater
        host = self._host_window()
        if host is not None:
            return getattr(host, "_updater_ref", None)
        return None

    # ── Actions ─────────────────────────────────────────────────────────────

    def _on_clap_toggled(self, on: bool) -> None:
        try:
            from jarvis_ui.wake_bootstrap import set_wake_enabled

            set_wake_enabled(bool(on))
            self._clap_status.setText(
                "Wake agent installed." if on else "Wake agent removed."
            )
        except Exception as e:
            self._clap_status.setText(f"Could not update wake agent: {e}")
            QTimer.singleShot(0, self._refresh_clap)

    def _open_api_keys(self) -> None:
        host = self._host_window() or self
        try:
            from ui import ApiSettingsDialog

            dlg = ApiSettingsDialog(host)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                dlg.save()
                self._refresh_models()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "API Keys", str(e))

    def _api_keys_cfg_path(self):
        from core.app_paths import api_keys_path

        return api_keys_path()

    def _read_api_keys_cfg(self) -> dict:
        import json

        path = self._api_keys_cfg_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_api_keys_inline(self) -> None:
        if not hasattr(self, "_key_gemini"):
            return
        cfg = self._read_api_keys_cfg()
        self._key_gemini.setText(str(cfg.get("gemini_api_key", "") or ""))
        self._key_openai.setText(str(cfg.get("openai_api_key", "") or ""))
        self._key_openrouter.setText(str(cfg.get("openrouter_api_key", "") or ""))
        self._key_groq.setText(str(cfg.get("groq_api_key", "") or ""))
        self._key_deepseek.setText(str(cfg.get("deepseek_api_key", "") or ""))
        self._key_together.setText(str(cfg.get("together_api_key", "") or ""))

        openai_base = str(cfg.get("openai_base_url", "") or "").strip()
        self._openai_base.set_on(bool(openai_base))
        self._openai_base.set_field(
            "Base URL", openai_base or "https://api.openai.com/v1"
        )

        ollama = str(cfg.get("ollama_base_url", "") or "").strip()
        lmstudio = str(cfg.get("lmstudio_base_url", "") or "").strip()
        defaults = (
            "http://localhost:11434/api/generate",
            "http://localhost:1234/v1",
        )
        local_on = bool(
            (ollama and ollama != defaults[0])
            or (lmstudio and lmstudio != defaults[1])
        )
        self._local_models.set_on(local_on)
        self._local_models.set_field("Ollama URL", ollama or defaults[0])
        self._local_models.set_field("LM Studio URL", lmstudio or defaults[1])

    def _save_api_keys_inline(self) -> None:
        import json
        import platform

        from PyQt6.QtWidgets import QMessageBox

        if not hasattr(self, "_key_gemini"):
            return
        path = self._api_keys_cfg_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = self._read_api_keys_cfg()

        cfg["gemini_api_key"] = self._key_gemini.text().strip()
        cfg["openai_api_key"] = self._key_openai.text().strip()
        cfg["openrouter_api_key"] = self._key_openrouter.text().strip()
        cfg["groq_api_key"] = self._key_groq.text().strip()
        cfg["deepseek_api_key"] = self._key_deepseek.text().strip()
        cfg["together_api_key"] = self._key_together.text().strip()

        if self._openai_base.is_on():
            base = self._openai_base.field("Base URL").strip()
            if base:
                cfg["openai_base_url"] = base
            else:
                cfg.pop("openai_base_url", None)
        else:
            cfg.pop("openai_base_url", None)

        if self._local_models.is_on():
            cfg["ollama_base_url"] = (
                self._local_models.field("Ollama URL").strip()
                or "http://localhost:11434/api/generate"
            )
            cfg["lmstudio_base_url"] = (
                self._local_models.field("LM Studio URL").strip()
                or "http://localhost:1234/v1"
            )
        else:
            cfg.setdefault(
                "ollama_base_url", "http://localhost:11434/api/generate"
            )
            cfg.setdefault("lmstudio_base_url", "http://localhost:1234/v1")

        cfg.setdefault(
            "os_system",
            {"Darwin": "mac", "Windows": "windows"}.get(platform.system(), "linux"),
        )
        cfg.setdefault("camera_index", 0)

        try:
            path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
            QMessageBox.information(self, "API Keys", "API keys saved.")
        except Exception as e:
            QMessageBox.warning(self, "API Keys", f"Could not save keys: {e}")

    def _manage_account(self) -> None:
        try:
            from jarvis_ui import user_account as UA

            UA.open_account()
        except Exception:
            webbrowser.open("https://www.hiauraai.com/account")

    def _toggle_auth(self) -> None:
        try:
            from jarvis_ui import user_account as UA
            from jarvis_ui.auth_async import sign_out_async, start_sign_in_worker

            if UA.is_authenticated():
                def _done() -> None:
                    self._refresh_account()
                    self._refresh_plan()
                    self._refresh_parent_account_ui()

                sign_out_async(on_done=_done)
                return

            self._sign_btn.setText("Signing in…")
            worker = start_sign_in_worker(self, timeout=180.0, replace_running=True)
            if worker is None:
                return

            def _ok() -> None:
                if getattr(self, "_sign_in_worker", None) is worker:
                    self._sign_in_worker = None
                self._refresh_account()
                self._refresh_plan()
                self._refresh_parent_account_ui()

            def _err(msg: str) -> None:
                if getattr(self, "_sign_in_worker", None) is worker:
                    self._sign_in_worker = None
                self._refresh_account()
                if msg and "cancelled" not in msg.lower():
                    from PyQt6.QtWidgets import QMessageBox

                    QMessageBox.warning(self, "Account", msg)

            worker.succeeded.connect(_ok)
            worker.failed.connect(_err)
            worker.start()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Account", str(e))

    def _open_pricing(self) -> None:
        try:
            from jarvis_ui import user_account as UA

            UA.open_pricing()
        except Exception:
            webbrowser.open("https://www.hiauraai.com/pricing")

    def _plan_primary_action(self) -> None:
        """Subscribe ($20) or open Stripe/account billing portal."""
        try:
            from jarvis_ui import user_account as UA

            if UA.is_authenticated() and UA.has_active_subscription():
                UA.open_billing_portal()
            else:
                UA.start_checkout("pro")
        except Exception:
            webbrowser.open("https://www.hiauraai.com/pricing?plan=pro")

    def _open_support(self) -> None:
        try:
            from jarvis_ui import user_account as UA

            UA.open_support()
        except Exception:
            webbrowser.open("https://www.hiauraai.com/support")

    def _check_updates(self) -> None:
        updater = self._resolve_updater()
        if updater is None:
            self._upd_status.setText("Updater unavailable")
            return
        try:
            updater.check_now()
            self._upd_status.setText("Checking…")
            QTimer.singleShot(1200, self._refresh_updates)
        except Exception as e:
            self._upd_status.setText(str(e)[:80])

    def _open_update_ui(self) -> None:
        """Open the update card so the user can install (Update now)."""
        updater = self._resolve_updater()
        if updater is None:
            self._upd_status.setText("Updater unavailable")
            return
        try:
            svc = getattr(updater, "_service", None)
            release = getattr(getattr(svc, "state", None), "release", None) if svc else None
            if release is None and svc is not None:
                # No cached release yet — check, then open when found.
                self._upd_status.setText("Checking…")
                updater.check_now()

                def _open_when_ready(attempt: int = 0) -> None:
                    try:
                        st = svc.state
                        self._refresh_updates()
                        if st.release:
                            updater.open_update_ui()
                        elif attempt < 8:
                            QTimer.singleShot(400, lambda: _open_when_ready(attempt + 1))
                        else:
                            self._upd_status.setText("Up to date")
                    except Exception:
                        pass

                QTimer.singleShot(500, lambda: _open_when_ready(0))
            else:
                updater.open_update_ui()
                QTimer.singleShot(400, self._refresh_updates)
        except Exception as e:
            self._upd_status.setText(str(e)[:80])


def open_settings(parent=None, *, updater: Any | None = None) -> SettingsWindow:
    """Create a settings page widget (caller embeds it in the main window stack)."""
    page = SettingsWindow(parent, updater=updater)
    page.open_page()
    return page
