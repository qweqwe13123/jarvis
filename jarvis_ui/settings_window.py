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
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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
        lay.addWidget(_Hint("Hands-free wake via the macOS LaunchAgent."))

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
        lay.addWidget(_Hint("AURA runs on Gemini — chat, voice, and Forge."))

        card = _Card()
        self._model_provider = _ValueLabel("gemini")
        self._model_name = _ValueLabel(_DISPLAY_MODEL)
        self._model_live = _ValueLabel(_live_model_label())
        card.add_row(
            _SettingRow(
                "Forge model",
                "Fixed for Website Builder and agents.",
                trailing=self._model_name,
            )
        )
        card.add_separator()
        card.add_row(
            _SettingRow(
                "Live voice model",
                "Realtime audio session model.",
                trailing=self._model_live,
            )
        )
        lay.addWidget(card)

        keys = _Card()
        btn = _GhostButton("Edit…")
        btn.clicked.connect(self._open_api_keys)
        keys.add_row(
            _SettingRow(
                "Gemini API key",
                "Your BYOK key for chat, voice, and Forge.",
                trailing=btn,
            )
        )
        lay.addWidget(keys)
        return root

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

    def _refresh_clap(self) -> None:
        try:
            from jarvis_ui.wake_bootstrap import is_wake_enabled_pref, is_wake_installed

            on = is_wake_installed() and is_wake_enabled_pref()
        except Exception:
            try:
                from launcher.install_launch_agent import PLIST_PATH

                on = PLIST_PATH.is_file()
            except Exception:
                on = False
        self._clap_toggle.blockSignals(True)
        self._clap_toggle.setChecked(on)
        self._clap_toggle.blockSignals(False)
        self._clap_status.setText(
            "Wake agent is installed and will start at login."
            if on
            else "Wake agent is off. Toggle to install the LaunchAgent."
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
