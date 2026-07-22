"""Cursor-style model picker for the chat bar (Auto ▾ + popover)."""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T
from jarvis_ui.model_catalog import ModelOption, available_models, find_option
from jarvis_ui.paths import support_dir

_PREFS = support_dir() / "model_picker_prefs.json"

# Soft AURA navy — Cursor-like, not loud cyan blocks.
_POP_BG = "#0d1520"
_POP_BORDER = "rgba(0, 209, 255, 0.14)"
_ROW_HOVER = "rgba(255, 255, 255, 0.05)"
_ROW_ACTIVE = "rgba(0, 209, 255, 0.10)"
_TOGGLE_ON = "#3d8bfd"
_TOGGLE_OFF = "#2a3544"
_MUTED = "#7a93a8"
_MUTED_SOFT = "#5a7388"


def _load_prefs() -> dict:
    defaults = {"option_id": "auto", "auto_mode": True}
    if not _PREFS.exists():
        return dict(defaults)
    try:
        data = json.loads(_PREFS.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update({k: data[k] for k in defaults if k in data})
    except Exception:
        pass
    return defaults


def _save_prefs(patch: dict) -> dict:
    data = _load_prefs()
    data.update(patch)
    _PREFS.parent.mkdir(parents=True, exist_ok=True)
    _PREFS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


class _MiniToggle(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, on: bool = False, parent=None):
        super().__init__(parent)
        self._on = bool(on)
        self.setFixedSize(34, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, on: bool) -> None:
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on = not self._on
            self.update()
            self.toggled.emit(self._on)
        super().mousePressEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_TOGGLE_ON if self._on else _TOGGLE_OFF))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        d = h - 4
        x = w - d - 2 if self._on else 2
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(x, 2, d, d)


class _ModelRow(QFrame):
    """Cursor-style row:  Title  Tier   (quiet text, no chunky badges)."""

    clicked = pyqtSignal(str)

    def __init__(self, opt: ModelOption, selected: bool, parent=None):
        super().__init__(parent)
        self._id = opt.id
        self._selected = bool(selected)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_bg()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)

        title = QLabel(opt.title)
        title.setFont(QFont(T.CHAT_FONT, 12))
        title.setStyleSheet(
            f"color: {T.WHITE}; background: transparent; border: none; padding: 0;"
        )
        lay.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)

        # Quiet secondary label — like Cursor's "High" / "Fast" / "Medium"
        if opt.badge and opt.badge.upper() == "NEW":
            new = QLabel("NEW")
            new.setFont(QFont(T.CHAT_FONT, 9, QFont.Weight.DemiBold))
            new.setStyleSheet(
                f"color: {_TOGGLE_ON}; background: transparent; border: none; padding: 0;"
            )
            lay.addWidget(new, 0, Qt.AlignmentFlag.AlignVCenter)

        if opt.tier:
            meta = QLabel(opt.tier)
            meta.setFont(QFont(T.CHAT_FONT, 12))
            meta.setStyleSheet(
                f"color: {_MUTED}; background: transparent; border: none; padding: 0;"
            )
            lay.addWidget(meta, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)

    def _apply_bg(self) -> None:
        bg = _ROW_ACTIVE if self._selected else "transparent"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: none; border-radius: 6px; }}"
        )

    def enterEvent(self, e):
        if not self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: {_ROW_HOVER}; border: none; border-radius: 6px; }}"
            )
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._apply_bg()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(e)


class ModelPickerPopup(QFrame):
    """Popover: search + Auto toggle + available models."""

    selection_changed = pyqtSignal(str)  # option id
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(300)
        self.setStyleSheet(
            f"QFrame#ModelPickerPopup {{ background: {_POP_BG}; "
            f"border: 1px solid {_POP_BORDER}; border-radius: 10px; }}"
        )
        self.setObjectName("ModelPickerPopup")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search models")
        self._search.setFixedHeight(30)
        self._search.setFont(QFont(T.CHAT_FONT, 12))
        self._search.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {T.WHITE}; "
            f"border: none; border-radius: 6px; padding: 0 10px; }}"
            f"QLineEdit:focus {{ background: rgba(255,255,255,0.04); }}"
            f"QLineEdit::placeholder {{ color: {_MUTED_SOFT}; }}"
        )
        self._search.textChanged.connect(self._rebuild_list)
        root.addWidget(self._search)

        prefs = _load_prefs()

        auto_row = QWidget()
        auto_row.setFixedHeight(30)
        hl = QHBoxLayout(auto_row)
        hl.setContentsMargins(12, 0, 10, 0)
        lab = QLabel("Auto")
        lab.setFont(QFont(T.CHAT_FONT, 12))
        lab.setStyleSheet(f"color: {T.WHITE}; background: transparent;")
        hl.addWidget(lab)
        hl.addStretch(1)
        self._auto_tog = _MiniToggle(bool(prefs.get("auto_mode", True)))
        hl.addWidget(self._auto_tog)
        root.addWidget(auto_row)
        self._auto_tog.toggled.connect(self._on_auto_toggled)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.08); border: none;")
        root.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; margin: 2px; }"
            f"QScrollBar::handle:vertical {{ background: {_MUTED_SOFT}; border-radius: 2px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(1)
        self._scroll.setWidget(self._list_host)
        self._scroll.setMinimumHeight(200)
        self._scroll.setMaximumHeight(280)
        root.addWidget(self._scroll)

        self._selected_id = str(prefs.get("option_id") or "auto")
        self._catalog: list[ModelOption] = []
        self._rebuild_list()

    def _on_auto_toggled(self, on: bool) -> None:
        _save_prefs({"auto_mode": bool(on)})
        if on:
            self._select("auto")

    def _rebuild_list(self, *_args) -> None:
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        q = self._search.text().strip().lower()
        self._catalog = available_models()
        shown = 0
        for opt in self._catalog:
            # Auto lives in the toggle — don't duplicate it in the list.
            if opt.id == "auto":
                continue
            hay = f"{opt.title} {opt.provider} {opt.id} {opt.tier}".lower()
            if q and q not in hay:
                continue
            row = _ModelRow(opt, selected=(opt.id == self._selected_id))
            row.clicked.connect(self._select)
            self._list_lay.addWidget(row)
            shown += 1
        if shown == 0:
            empty = QLabel("No models yet — add an API key in Settings → Models")
            empty.setWordWrap(True)
            empty.setFont(QFont(T.CHAT_FONT, 11))
            empty.setStyleSheet(f"color: {_MUTED}; padding: 14px 12px;")
            self._list_lay.addWidget(empty)
        self._list_lay.addStretch(1)

    def _select(self, option_id: str) -> None:
        self._selected_id = option_id
        if option_id != "auto":
            self._auto_tog.blockSignals(True)
            self._auto_tog.setChecked(False)
            self._auto_tog.blockSignals(False)
            _save_prefs({"auto_mode": False, "option_id": option_id})
        else:
            self._auto_tog.blockSignals(True)
            self._auto_tog.setChecked(True)
            self._auto_tog.blockSignals(False)
            _save_prefs({"auto_mode": True, "option_id": "auto"})
        self.selection_changed.emit(option_id)
        self._rebuild_list()
        QTimer.singleShot(80, self.close)

    def show_at(self, global_pos: QPoint) -> None:
        self._rebuild_list()
        self.adjustSize()
        x = global_pos.x()
        y = global_pos.y() - self.sizeHint().height() - 8
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            x = min(x, screen.right() - self.width() - 8)
            x = max(screen.left() + 8, x)
            y = max(screen.top() + 8, y)
        self.move(x, y)
        self.show()
        self._search.setFocus()

    def hideEvent(self, e):
        self.closed.emit()
        super().hideEvent(e)


class AutoModelButton(QPushButton):
    """Chat-bar trigger: 'Auto ▾' or selected model name."""

    selection_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        self.setMinimumWidth(64)
        self.setFont(QFont(T.CHAT_FONT, 12))
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_MUTED}; "
            f"border: none; border-radius: 6px; padding: 0 6px; text-align: left; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.06); color: {T.WHITE}; }}"
        )
        self._popup: ModelPickerPopup | None = None
        self._option_id = str(_load_prefs().get("option_id") or "auto")
        self.clicked.connect(self._toggle_popup)
        self._refresh_label()

    def current_option_id(self) -> str:
        prefs = _load_prefs()
        if prefs.get("auto_mode", True):
            return "auto"
        return str(prefs.get("option_id") or "auto")

    def current_option(self) -> ModelOption:
        return find_option(self.current_option_id()) or ModelOption(
            id="auto",
            provider="auto",
            model="",
            title="Auto",
            tier="Smart",
            mode="live",
        )

    def _refresh_label(self) -> None:
        opt = self.current_option()
        label = "Auto" if opt.id == "auto" else opt.title
        if len(label) > 16:
            label = label[:14] + "…"
        self.setText(f"{label}  ▾")
        tip = opt.title if opt.id == "auto" else f"{opt.title} · {opt.tier}"
        self.setToolTip(tip)

    def _toggle_popup(self) -> None:
        if self._popup and self._popup.isVisible():
            self._popup.close()
            return
        self._popup = ModelPickerPopup(self.window())
        self._popup.selection_changed.connect(self._on_selected)
        g = self.mapToGlobal(QPoint(0, 0))
        self._popup.show_at(g)

    def _on_selected(self, option_id: str) -> None:
        self._option_id = option_id
        self._refresh_label()
        self.selection_changed.emit(option_id)

    def refresh(self) -> None:
        self._refresh_label()
