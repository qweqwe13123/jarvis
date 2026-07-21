"""JARVIS workspace UI components — screenshot-matched design."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QUrl, QRectF, QPointF, QPoint, QSize
from PyQt6.QtGui import (
    QFont, QFontMetrics, QDesktopServices, QPainter, QPen, QColor, QPolygonF, QPainterPath, QBrush,
    QCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QGridLayout, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QTextBrowser,
    QTextEdit, QToolButton, QVBoxLayout, QWidget, QMenu,
)

from jarvis_ui.markdown_utils import markdown_to_html
from jarvis_ui import theme as T
from jarvis_ui import user_account as UA
from jarvis_ui.avatar import AvatarCircle
from jarvis_ui.dashboard_hud import DashboardHeroView

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE = True
except Exception:
    QWebEngineView = None
    _WEB_ENGINE = False

WORKFLOW_STEPS = [
    "Thinking",
    "Searching",
    "Writing code",
    "Generating files",
    "Finished",
]


def _lbl(text: str, size: int = 8, color: str = T.TEXT_MED, bold: bool = False) -> QLabel:
    w = QLabel(text)
    w.setFont(QFont(T.FONT_UI, size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    w.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return w


class ActivityPill(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._name = text
        self.setFixedHeight(38)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._label = QLabel(text)
        self._label.setFont(QFont(T.FONT_UI, 9))
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        lay.addStretch()
        self.set_state("idle")

    def set_state(self, state: str):
        if state == "active":
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(0, 209, 255, 0.10);
                    border: 1px solid rgba(0, 209, 255, 0.22);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.WHITE}; background: transparent; border: none;")
        elif state == "done":
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(0, 255, 148, 0.08);
                    border: 1px solid rgba(0, 255, 148, 0.18);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.GREEN}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.GREEN}; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(12, 24, 36, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.04);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")


class JarvisConsole(QWidget):
    """Right panel: LIVE ACTIVITY pills + response stream."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pills: list[ActivityPill] = []
        self._entries: list[dict] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        hdr = _lbl("LIVE ACTIVITY", 7, T.CYAN, True)
        lay.addWidget(hdr)

        for step in WORKFLOW_STEPS:
            pill = ActivityPill(step)
            lay.addWidget(pill)
            self._pills.append(pill)

        lay.addSpacing(4)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {T.BG}; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}
        """)
        self._output_host = QWidget()
        self._output_lay = QVBoxLayout(self._output_host)
        self._output_lay.setContentsMargins(0, 0, 0, 0)
        self._output_lay.setSpacing(8)
        self._output_lay.addStretch()
        self._scroll.setWidget(self._output_host)
        lay.addWidget(self._scroll, stretch=1)

    def reset_workflow(self):
        for pill in self._pills:
            pill.set_state("idle")

    def set_workflow_step(self, step_name: str):
        aliases = {
            "Reading Files": "Searching",
            "Analyzing Code": "Writing code",
            "Creating Files": "Generating files",
            "Editing Files": "Generating files",
        }
        step_name = aliases.get(step_name, step_name)
        try:
            idx = WORKFLOW_STEPS.index(step_name)
        except ValueError:
            return
        for i, pill in enumerate(self._pills):
            if i < idx:
                pill.set_state("done")
            elif i == idx:
                pill.set_state("active")
            else:
                pill.set_state("idle")

    def add_response(self, title: str, content: str, role: str = "assistant"):
        self._entries.insert(0, {"title": title, "content": content, "role": role})
        self._rebuild_output()

    def clear(self):
        self._entries = []
        self._rebuild_output()

    def load_conversation(self, messages: list[dict]):
        self._entries = []
        for m in messages:
            role = m.get("role", "assistant")
            title = "You" if role == "user" else "AURA"
            self._entries.insert(0, {"title": title, "content": m.get("content", ""), "role": role})
        self._rebuild_output()

    def _rebuild_output(self):
        while self._output_lay.count() > 1:
            item = self._output_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for entry in reversed(self._entries):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {T.BG_CARD};
                    border: 1px solid {T.BORDER_HI};
                    border-radius: 12px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            hdr = QLabel(entry.get("title", "AURA"))
            hdr.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
            hdr.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
            cl.addWidget(hdr)
            body = QLabel()
            body.setWordWrap(True)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setOpenExternalLinks(True)
            body.setText(markdown_to_html(entry.get("content", "")))
            body.setStyleSheet("background: transparent; border: none;")
            cl.addWidget(body)
            self._output_lay.insertWidget(0, card)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(0))


class ChatPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(24, 8, 24, 8)
        self._lay.setSpacing(10)
        self._lay.addStretch()
        self.setWidget(self._host)
        self.hide()

    def clear_messages(self):
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.hide()

    def load_messages(self, messages: list[dict]):
        self.clear_messages()
        if not messages:
            self.hide()
            return
        self.show()
        for msg in messages:
            self.add_message(msg.get("role", "user"), msg.get("content", ""), scroll=False)
        self._scroll_bottom()

    def add_message(self, role: str, content: str, scroll: bool = True):
        self.show()
        is_user = role == "user"
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {T.BG_CARD if is_user else '#0a1a28'};
                border: 1px solid {T.BORDER if is_user else T.BORDER_HI};
                border-radius: 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        tag = QLabel("YOU" if is_user else "AURA")
        tag.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {T.WHITE if is_user else T.CYAN}; background: transparent; border: none;")
        cl.addWidget(tag)
        body = QLabel()
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setText(markdown_to_html(content))
        body.setStyleSheet(f"color: {T.TEXT}; background: transparent; border: none;")
        cl.addWidget(body)
        self._lay.insertWidget(self._lay.count() - 1, card)
        if scroll:
            self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(30, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))


class _SideRow(QFrame):
    """A selectable list row with hover-revealed rename/delete actions."""

    def __init__(self, title: str, subtitle: str, item_id: str, active: bool,
                 icon: str, on_select, on_rename, on_delete, can_delete=True,
                 on_pin=None, pinned: bool = False, parent=None):
        super().__init__(parent)
        self._id = item_id
        self._active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40 if subtitle else 32)
        self._apply_style(active)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 6, 2)
        lay.setSpacing(8)

        if icon:
            ic = QLabel(icon)
            ic.setFont(QFont(T.FONT_UI, 9))
            ic.setStyleSheet(f"color: {T.CYAN if active else T.TEXT_DIM}; background: transparent; border: none;")
            ic.setFixedWidth(16)
            lay.addWidget(ic)

        textcol = QVBoxLayout()
        textcol.setSpacing(0)
        name = QLabel(title)
        name.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium if active else QFont.Weight.Normal))
        name.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE if active else T.SB_TEXT}; background: transparent; border: none;"
        )
        textcol.addWidget(name)
        lay.addLayout(textcol, stretch=1)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(QFont(T.SB_FONT, 10))
            sub.setStyleSheet(f"color: {T.SB_TEXT_MUTED}; background: transparent; border: none;")
            sub.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(sub)

        self._actions = QWidget()
        self._actions.setStyleSheet("background: transparent; border: none;")
        al = QHBoxLayout(self._actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(2)
        edit = self._mini_btn("✎", T.CYAN)
        edit.clicked.connect(lambda: on_rename(item_id))
        al.addWidget(edit)
        if on_pin:
            pin = self._mini_btn("★" if pinned else "☆", T.GREEN)
            pin.clicked.connect(lambda: on_pin(item_id))
            al.addWidget(pin)
        if can_delete:
            dele = self._mini_btn("✕", T.RED)
            dele.clicked.connect(lambda: on_delete(item_id))
            al.addWidget(dele)
        self._actions.setVisible(False)
        lay.addWidget(self._actions)

        self._on_select = on_select

    def _mini_btn(self, glyph: str, color: str) -> QPushButton:
        b = QPushButton(glyph)
        b.setFixedSize(20, 20)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(T.FONT_UI, 8))
        b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {T.TEXT_DIM}; border: none; border-radius: 5px; }}
            QPushButton:hover {{ color: {color}; background: rgba(255,255,255,0.06); }}
        """)
        return b

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                _SideRow {{
                    background: {T.SB_ACCENT_SOFT};
                    border: none;
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                _SideRow {{ background: transparent; border: none; border-radius: 6px; }}
                _SideRow:hover {{ background: {T.SB_HOVER}; }}
            """)

    def enterEvent(self, e):
        self._actions.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._actions.setVisible(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_select:
            self._on_select(self._id)
        super().mousePressEvent(e)


class _ElidedLabel(QLabel):
    """Single-line label that always truncates with … when text is too wide.

    sizeHint must stay small — otherwise QScrollArea grows wider than the
    sidebar viewport and right-side chat actions get clipped off-screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def sizeHint(self):  # noqa: N802
        return QSize(40, super().sizeHint().height())

    def minimumSizeHint(self):  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def set_full_text(self, text: str):
        self._full = text or ""
        self._reflow()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reflow()

    def _reflow(self):
        w = max(1, self.width())
        fm = QFontMetrics(self.font())
        self.setText(fm.elidedText(self._full, Qt.TextElideMode.ElideRight, w))
        self.setToolTip(self._full if fm.horizontalAdvance(self._full) > w else "")


class _ChatIconBtn(QFrame):
    """Compact icon button for chat-row actions (trash / more)."""

    clicked = pyqtSignal()

    def __init__(self, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatIconBtn")
        self._hover = False
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._icon = _LineIcon(icon_name, T.SB_TEXT, 14)
        lay.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self._apply()

    def set_icon_color(self, color: str) -> None:
        self._icon.set_color(color)

    def _apply(self):
        bg = "rgba(255,255,255,0.10)" if self._hover else "transparent"
        self.setStyleSheet(
            f"QFrame#ChatIconBtn {{ background: {bg}; border: none; border-radius: 6px; }}"
        )
        if not self._hover:
            # Keep explicit color from parent when not hovering the icon itself.
            pass
        else:
            self._icon.set_color(T.SB_TEXT_ACTIVE)

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class _ChatSidebarRow(QFrame):
    """Chat row with rename/delete drawn in paintEvent (no fragile child buttons)."""

    _BTN = 20
    _GAP = 0
    _ACTIONS_W = _BTN + _GAP + _BTN + 4  # trash + more + padding

    def __init__(self, title: str, chat_id: str, active: bool, pinned: bool,
                 on_select, on_delete, on_rename=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatSidebarRow")
        self._id = chat_id
        self._full_title = (title or "New chat").strip() or "New chat"
        self._active = bool(active)
        self._hover = False
        self._on_select = on_select
        self._on_delete = on_delete
        self._on_rename = on_rename
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, self._ACTIONS_W, 0)
        lay.setSpacing(8)

        self._icon = _LineIcon("chat", T.SB_TEXT_MUTED, 16)
        self._icon.setFixedSize(16, 16)
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._icon)

        self._title = _ElidedLabel()
        self._title.setFont(
            QFont(T.SB_FONT, 13, QFont.Weight.Medium if active else QFont.Weight.Normal)
        )
        self._title.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE if active else T.SB_TEXT}; "
            "background: transparent; border: none;"
        )
        self._title.set_full_text(self._full_title)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._title, stretch=1)
        self._sync_icon()

    def _sync_icon(self) -> None:
        self._icon.set_color(T.CYAN if self._active else T.SB_TEXT_MUTED)
        weight = QFont.Weight.Medium if self._active else QFont.Weight.Normal
        self._title.setFont(QFont(T.SB_FONT, 13, weight))
        self._title.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE if self._active else T.SB_TEXT}; "
            "background: transparent; border: none;"
        )

    def _delete_rect(self) -> QRectF:
        """Trash — left of the action pair (matches reference)."""
        y = (self.height() - self._BTN) / 2
        x = self.width() - 6 - self._BTN - self._GAP - self._BTN
        return QRectF(x, y, self._BTN, self._BTN)

    def _more_rect(self) -> QRectF:
        """Vertical ⋮ menu — far right."""
        y = (self.height() - self._BTN) / 2
        x = self.width() - 6 - self._BTN
        return QRectF(x, y, self._BTN, self._BTN)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._active:
            bg = QColor(0, 209, 255, 31)
        elif self._hover:
            bg = QColor(0, 209, 255, 15)
        else:
            bg = QColor(0, 0, 0, 0)
        if bg.alpha():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        # Muted line icons like the reference: trash + vertical kebab.
        icon_color = QColor(T.SB_TEXT_MUTED)
        pen = QPen(icon_color)
        pen.setWidthF(1.55)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Trash (slightly smaller glyph than the ⋮)
        trash = self._delete_rect()
        s = min(trash.width(), trash.height()) / 24.0 * 0.82
        ox = trash.x() + (trash.width() - 24 * s) / 2
        oy = trash.y() + (trash.height() - 24 * s) / 2
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.drawLine(QPointF(ox + 8 * s, oy + 6 * s), QPointF(ox + 16 * s, oy + 6 * s))
        p.drawLine(QPointF(ox + 10 * s, oy + 6 * s), QPointF(ox + 10.5 * s, oy + 4.2 * s))
        p.drawLine(QPointF(ox + 13.5 * s, oy + 6 * s), QPointF(ox + 14 * s, oy + 4.2 * s))
        p.drawLine(QPointF(ox + 10.5 * s, oy + 4.2 * s), QPointF(ox + 13.5 * s, oy + 4.2 * s))
        p.drawRoundedRect(QRectF(ox + 7 * s, oy + 7 * s, 10 * s, 12 * s), 1.4 * s, 1.4 * s)
        p.drawLine(QPointF(ox + 10 * s, oy + 10 * s), QPointF(ox + 10 * s, oy + 16 * s))
        p.drawLine(QPointF(ox + 12 * s, oy + 10 * s), QPointF(ox + 12 * s, oy + 16 * s))
        p.drawLine(QPointF(ox + 14 * s, oy + 10 * s), QPointF(ox + 14 * s, oy + 16 * s))

        # Vertical ellipsis (⋮)
        more = self._more_rect()
        s = min(more.width(), more.height()) / 24.0
        ox = more.x() + (more.width() - 24 * s) / 2
        oy = more.y() + (more.height() - 24 * s) / 2
        p.setBrush(icon_color)
        p.setPen(Qt.PenStyle.NoPen)
        for cy in (7.0, 12.0, 17.0):
            p.drawEllipse(QRectF(ox + 10.5 * s, oy + (cy - 1.5) * s, 3.0 * s, 3.0 * s))
        p.end()

    def _set_hover(self, hover: bool) -> None:
        if self._hover == hover:
            return
        self._hover = hover
        self.update()

    def _menu_stylesheet(self) -> str:
        return (
            f"QMenu {{ background: {T.BG_CARD}; color: {T.CHAT_TEXT}; "
            f"border: 1px solid {T.BORDER}; padding: 4px 0; border-radius: 8px; }}"
            "QMenu::item { padding: 8px 16px; }"
            "QMenu::item:selected { background: rgba(255,255,255,0.08); }"
        )

    def _run_chat_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())
        rename_act = menu.addAction("Rename")
        delete_act = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen is rename_act and self._on_rename:
            self._on_rename(self._id)
        elif chosen is delete_act and self._on_delete:
            self._on_delete(self._id)

    def _open_context_menu(self, pos: QPoint) -> None:
        self._run_chat_menu(self.mapToGlobal(pos))

    def event(self, e):  # noqa: N802
        et = e.type()
        if et == QEvent.Type.HoverEnter:
            self._set_hover(True)
        elif et == QEvent.Type.HoverLeave:
            self._set_hover(False)
        return super().event(e)

    def enterEvent(self, e):
        self._set_hover(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            return
        self._set_hover(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        pos = e.position()
        if self._delete_rect().contains(pos):
            if self._on_delete:
                self._on_delete(self._id)
            e.accept()
            return
        if self._more_rect().contains(pos):
            # Open menu under the ⋮ hit target.
            r = self._more_rect()
            self._run_chat_menu(
                self.mapToGlobal(QPoint(int(r.left()), int(r.bottom())))
            )
            e.accept()
            return
        if self._on_select:
            self._on_select(self._id)
        e.accept()


def _spaced_font(family: str, size: int, px: float, bold: bool = False) -> QFont:
    f = QFont(family, size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
    return f


class _LineIcon(QWidget):
    """Crisp single-colour line icons painted to match the screenshot."""

    def __init__(self, name: str, color: str = T.TEXT_DIM, size: int = 22, parent=None):
        super().__init__(parent)
        self._name = name
        self._color = color
        self._sz = size
        self.setFixedSize(size, size)

    def set_color(self, color: str):
        if color != self._color:
            self._color = color
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._sz / 24.0
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.7 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        def P(x, y):
            return QPointF(x * s, y * s)

        def R(x, y, w, h):
            return QRectF(x * s, y * s, w * s, h * s)

        def poly(*pts):
            p.drawPolyline(QPolygonF([P(x, y) for x, y in pts]))

        n = self._name
        if n == "chat":
            p.drawRoundedRect(R(3, 4, 18, 13), 4 * s, 4 * s)
            poly((8, 17), (8, 21), (13, 17))
            p.drawLine(P(7, 9), P(17, 9))
            p.drawLine(P(7, 12), P(14, 12))
        elif n == "globe":
            p.drawEllipse(R(4, 4, 16, 16))
            p.drawEllipse(R(9, 4, 6, 16))
            p.drawLine(P(4, 12), P(20, 12))
        elif n == "code":
            poly((9, 7), (4, 12), (9, 17))
            poly((15, 7), (20, 12), (15, 17))
            p.drawLine(P(13, 6), P(11, 18))
        elif n == "automation":
            p.drawRoundedRect(R(3, 4, 6, 6), 1.5 * s, 1.5 * s)
            p.drawRoundedRect(R(3, 14, 6, 6), 1.5 * s, 1.5 * s)
            p.drawRoundedRect(R(15, 9, 6, 6), 1.5 * s, 1.5 * s)
            p.drawLine(P(9, 7), P(15, 11.5))
            p.drawLine(P(9, 17), P(15, 12.5))
        elif n == "writer":
            poly((15, 4), (20, 9), (9, 20), (4, 20), (4, 15), (15, 4))
            p.drawLine(P(13, 6), P(18, 11))
        elif n == "researcher":
            p.drawLine(P(9, 4), P(14, 9))
            p.drawLine(P(11.5, 6.5), P(7, 11))
            p.drawEllipse(R(4.5, 10.5, 5.5, 5.5))
            p.drawLine(P(5, 20), P(19, 20))
            p.drawLine(P(12, 16), P(16, 20))
        elif n == "designer":
            p.drawEllipse(R(3, 3, 18, 18))
            p.drawEllipse(R(13, 13, 5, 5))
            for dx, dy in [(7, 7), (11, 5.5), (15.5, 7.5), (7.5, 12)]:
                p.drawEllipse(R(dx, dy, 1.7, 1.7))
        elif n == "maps":
            p.drawArc(R(5, 4, 14, 14), 0, 360 * 16)
            poly((7, 15), (12, 21), (17, 15))
            p.drawEllipse(R(9.5, 8.5, 5, 5))
        elif n == "settings":
            p.drawEllipse(R(6, 6, 12, 12))
            p.drawEllipse(R(10, 10, 4, 4))
            for x1, y1, x2, y2 in [
                (12, 2.8, 12, 5.2), (12, 18.8, 12, 21.2),
                (2.8, 12, 5.2, 12), (18.8, 12, 21.2, 12),
                (5.1, 5.1, 6.9, 6.9), (17.1, 17.1, 18.9, 18.9),
                (5.1, 18.9, 6.9, 17.1), (17.1, 6.9, 18.9, 5.1),
            ]:
                p.drawLine(P(x1, y1), P(x2, y2))
        elif n == "grid":
            for ox, oy in ((4, 4), (13, 4), (4, 13), (13, 13)):
                p.drawRoundedRect(R(ox, oy, 7, 7), 1.5 * s, 1.5 * s)
        elif n == "plug":
            p.drawRoundedRect(R(8, 3, 8, 7), 1.5 * s, 1.5 * s)
            p.drawLine(P(12, 10), P(12, 14))
            p.drawLine(P(8, 14), P(16, 14))
        elif n == "puzzle":
            poly((6, 8), (10, 8), (10, 6), (14, 6), (14, 10), (18, 10), (18, 14), (14, 14), (14, 18), (10, 18), (10, 14), (6, 14))
        elif n == "mic":
            p.drawRoundedRect(R(9, 4, 6, 10), 3 * s, 3 * s)
            p.drawArc(R(6, 10, 12, 8), 0, -180 * 16)
            p.drawLine(P(12, 18), P(12, 21))
            p.drawLine(P(8, 21), P(16, 21))
        elif n == "monitor":
            p.drawRoundedRect(R(3, 5, 18, 11), 2 * s, 2 * s)
            p.drawLine(P(9, 16), P(15, 16))
            p.drawLine(P(12, 16), P(12, 19))
            p.drawLine(P(8, 19), P(16, 19))
        elif n == "clock":
            p.drawEllipse(R(4, 4, 16, 16))
            p.drawLine(P(12, 12), P(12, 8))
            p.drawLine(P(12, 12), P(16, 12))
        elif n == "plus":
            p.drawLine(P(12, 6), P(12, 18))
            p.drawLine(P(6, 12), P(18, 12))
        elif n == "subscription":
            p.drawRoundedRect(R(5, 5, 14, 14), 2 * s, 2 * s)
            p.drawLine(P(12, 8), P(12, 16))
            p.drawLine(P(8, 12), P(16, 12))
        elif n == "gift":
            p.drawRoundedRect(R(5, 10, 14, 10), 2 * s, 2 * s)
            p.drawLine(P(5, 14), P(19, 14))
            p.drawLine(P(12, 10), P(12, 20))
            # Bow
            p.drawArc(R(6.5, 5.5, 5.5, 5.5), 20 * 16, 200 * 16)
            p.drawArc(R(12, 5.5, 5.5, 5.5), -40 * 16, 200 * 16)
            p.drawLine(P(12, 7.5), P(12, 10))
        elif n == "close":
            p.drawLine(P(7, 7), P(17, 17))
            p.drawLine(P(17, 7), P(7, 17))
        elif n == "user":
            p.drawEllipse(R(8, 4, 8, 8))
            p.drawArc(R(5, 13, 14, 9), 0, -180 * 16)
        elif n == "keyboard":
            # Modern outline keyboard (Cursor / Lucide style).
            p.drawRoundedRect(R(2.5, 6.5, 19, 12), 2.2 * s, 2.2 * s)
            for x in (5.2, 8.4, 11.6, 14.8, 18.0):
                p.drawRoundedRect(R(x - 1.0, 9.0, 2.0, 2.0), 0.4 * s, 0.4 * s)
            for x in (6.8, 10.0, 13.2, 16.4):
                p.drawRoundedRect(R(x - 1.0, 12.2, 2.0, 2.0), 0.4 * s, 0.4 * s)
            p.drawRoundedRect(R(7.0, 15.4, 10.0, 1.8), 0.5 * s, 0.5 * s)
        elif n == "help":
            # Help circle with a proper question mark (not a “C”).
            p.drawEllipse(R(3.5, 3.5, 17, 17))
            path = QPainterPath()
            path.moveTo(P(9.2, 9.2))
            path.cubicTo(P(9.2, 7.0), P(10.6, 6.0), P(12.0, 6.0))
            path.cubicTo(P(13.6, 6.0), P(15.0, 7.1), P(15.0, 8.8))
            path.cubicTo(P(15.0, 10.2), P(14.0, 11.0), P(12.6, 11.6))
            path.lineTo(P(12.0, 12.0))
            path.lineTo(P(12.0, 14.0))
            p.drawPath(path)
            p.setBrush(QColor(self._color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(R(11.0, 16.2, 2.0, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
        elif n == "logout":
            p.drawRoundedRect(R(4, 5, 10, 14), 2 * s, 2 * s)
            p.drawLine(P(14, 12), P(20, 12))
            p.drawLine(P(17, 9), P(20, 12))
            p.drawLine(P(17, 15), P(20, 12))
        elif n == "login":
            p.drawRoundedRect(R(10, 5, 10, 14), 2 * s, 2 * s)
            p.drawLine(P(4, 12), P(10, 12))
            p.drawLine(P(7, 9), P(4, 12))
            p.drawLine(P(7, 15), P(4, 12))
        elif n == "plus_user":
            p.drawEllipse(R(6, 4, 8, 8))
            p.drawArc(R(3, 13, 14, 9), 0, -180 * 16)
            p.drawLine(P(17, 8), P(17, 14))
            p.drawLine(P(14, 11), P(20, 11))
        elif n == "trash":
            p.drawLine(P(8, 6), P(16, 6))
            p.drawLine(P(10, 6), P(10.5, 4))
            p.drawLine(P(13.5, 6), P(14, 4))
            p.drawLine(P(10.5, 4), P(13.5, 4))
            p.drawRoundedRect(R(7, 7, 10, 12), 1.5 * s, 1.5 * s)
            p.drawLine(P(10, 10), P(10, 16))
            p.drawLine(P(12, 10), P(12, 16))
            p.drawLine(P(14, 10), P(14, 16))
        elif n == "more":
            # Vertical kebab (⋮)
            for cy in (7, 12, 17):
                p.setBrush(QColor(self._color))
                p.drawEllipse(R(10.5, cy - 1.5, 3, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
        elif n == "more_h":
            # Horizontal ellipsis (⋯)
            for cx in (7, 12, 17):
                p.setBrush(QColor(self._color))
                p.drawEllipse(R(cx - 1.5, 10.5, 3, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
        elif n == "shield":
            # Premium security shield + check (sidebar Permissions).
            path = QPainterPath()
            path.moveTo(12, 2.8)
            path.cubicTo(16.8, 3.4, 19.4, 5.2, 19.4, 7.6)
            path.lineTo(19.4, 12.8)
            path.cubicTo(19.4, 17.2, 15.8, 19.8, 12, 21.2)
            path.cubicTo(8.2, 19.8, 4.6, 17.2, 4.6, 12.8)
            path.lineTo(4.6, 7.6)
            path.cubicTo(4.6, 5.2, 7.2, 3.4, 12, 2.8)
            path.closeSubpath()
            p.drawPath(path)
            pen2 = QPen(QColor(self._color), max(1.6, 1.7 * s))
            pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen2.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen2)
            p.drawLine(P(8.6, 12.2), P(11.0, 14.6))
            p.drawLine(P(11.0, 14.6), P(15.8, 9.4))
        elif n == "search":
            p.drawEllipse(R(4, 4, 12, 12))
            p.drawLine(P(13.5, 13.5), P(20, 20))
        elif n == "back":
            poly((14, 5), (7, 12), (14, 19))
            p.drawLine(P(7.5, 12), P(19, 12))
        elif n == "book":
            p.drawRoundedRect(R(5, 3.5, 14, 17), 1.5 * s, 1.5 * s)
            p.drawLine(P(12, 3.5), P(12, 20.5))
            p.drawLine(P(7.5, 8), P(10.5, 8))
            p.drawLine(P(7.5, 11), P(10.5, 11))
            p.drawLine(P(13.5, 8), P(16.5, 8))
            p.drawLine(P(13.5, 11), P(16.5, 11))
        elif n == "cube":
            poly((12, 3), (20, 7.5), (20, 16.5), (12, 21), (4, 16.5), (4, 7.5), (12, 3))
            p.drawLine(P(12, 3), P(12, 12))
            p.drawLine(P(4, 7.5), P(12, 12))
            p.drawLine(P(20, 7.5), P(12, 12))
        elif n == "credit":
            p.drawRoundedRect(R(3, 6, 18, 12), 2 * s, 2 * s)
            p.drawLine(P(3, 10.5), P(21, 10.5))
            p.drawLine(P(6, 14.5), P(11, 14.5))
        elif n == "appearance":
            p.drawEllipse(R(3.5, 3.5, 17, 17))
            path = QPainterPath()
            path.moveTo(P(12, 3.5))
            path.arcTo(R(3.5, 3.5, 17, 17), 90, 180)
            path.closeSubpath()
            p.setBrush(QColor(self._color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
        elif n == "external":
            p.drawRoundedRect(R(4, 8, 12, 12), 1.5 * s, 1.5 * s)
            p.drawLine(P(12, 4), P(20, 4))
            p.drawLine(P(20, 4), P(20, 12))
            p.drawLine(P(11, 13), P(20, 4))
        elif n == "download":
            p.drawLine(P(12, 4), P(12, 15))
            poly((7, 11), (12, 16.5), (17, 11))
            p.drawLine(P(5, 19), P(19, 19))
        elif n == "clap":
            # Sound / wake waves
            p.drawEllipse(R(9.5, 9.5, 5, 5))
            p.drawArc(R(6, 6, 12, 12), 40 * 16, 100 * 16)
            p.drawArc(R(6, 6, 12, 12), 220 * 16, 100 * 16)
            p.drawArc(R(3.5, 3.5, 17, 17), 40 * 16, 100 * 16)
            p.drawArc(R(3.5, 3.5, 17, 17), 220 * 16, 100 * 16)


class _SidebarShieldBadge(QWidget):
    """Soft cyan plate + shield mark for the Permissions sidebar row."""

    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self._d = int(size)
        self._hot = False
        self.setFixedSize(self._d, self._d)

    def set_hot(self, hot: bool) -> None:
        if self._hot != hot:
            self._hot = hot
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        d = float(self._d)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Plate
        alpha_fill = 48 if self._hot else 28
        alpha_ring = 110 if self._hot else 70
        p.setPen(QPen(QColor(0, 209, 255, alpha_ring), 1.1))
        p.setBrush(QColor(0, 209, 255, alpha_fill))
        p.drawRoundedRect(QRectF(0.5, 0.5, d - 1.0, d - 1.0), 6.0, 6.0)

        # Shield
        s = d / 22.0
        path = QPainterPath()
        path.moveTo(11 * s, 3.2 * s)
        path.cubicTo(15.2 * s, 3.7 * s, 17.6 * s, 5.2 * s, 17.6 * s, 7.2 * s)
        path.lineTo(17.6 * s, 11.4 * s)
        path.cubicTo(17.6 * s, 15.0 * s, 14.4 * s, 17.2 * s, 11 * s, 18.4 * s)
        path.cubicTo(7.6 * s, 17.2 * s, 4.4 * s, 15.0 * s, 4.4 * s, 11.4 * s)
        path.lineTo(4.4 * s, 7.2 * s)
        path.cubicTo(4.4 * s, 5.2 * s, 6.8 * s, 3.7 * s, 11 * s, 3.2 * s)
        path.closeSubpath()
        cyan = QColor(T.SB_ACCENT if self._hot else T.SB_TEXT_MUTED)
        if not self._hot:
            cyan = QColor(0, 209, 255, 200)
        p.setPen(QPen(cyan, max(1.3, 1.35 * s)))
        p.setBrush(QColor(0, 209, 255, 22 if self._hot else 14))
        p.drawPath(path)

        # Check
        pen = QPen(cyan, max(1.4, 1.45 * s))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(7.8 * s, 10.8 * s), QPointF(9.8 * s, 12.8 * s))
        p.drawLine(QPointF(9.8 * s, 12.8 * s), QPointF(14.2 * s, 8.4 * s))
        p.end()


_SUPPORT_EMAIL = "aura.companydev@gmail.com"
_WELCOME_PREVIEW = (
    "Thank you for choosing AURA and becoming one of our first users. "
    "Tap to read a note from our team."
)


def _welcome_card_state_path() -> Path:
    try:
        from jarvis_ui.onboarding.persistence import _support_base

        return _support_base() / "welcome_card.json"
    except Exception:
        return Path(__file__).resolve().parents[1] / "runtime" / "welcome_card.json"


def is_welcome_card_dismissed() -> bool:
    path = _welcome_card_state_path()
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("dismissed"))
    except Exception:
        return False


def mark_welcome_card_dismissed() -> None:
    path = _welcome_card_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"dismissed": True}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


class _ImportantMark(QWidget):
    """Attention badge — soft amber plate + exclamation."""

    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self._d = int(size)
        self.setFixedSize(self._d, self._d)

    def paintEvent(self, _e) -> None:  # noqa: N802
        d = float(self._d)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(QPen(QColor(255, 184, 48, 160), 1.1))
        p.setBrush(QColor(255, 184, 48, 42))
        p.drawRoundedRect(QRectF(0.5, 0.5, d - 1.0, d - 1.0), 6.0, 6.0)

        # Triangle
        s = d / 22.0
        tri = QPainterPath()
        tri.moveTo(11 * s, 4.2 * s)
        tri.lineTo(18.2 * s, 17.2 * s)
        tri.lineTo(3.8 * s, 17.2 * s)
        tri.closeSubpath()
        amber = QColor(255, 196, 72)
        p.setPen(QPen(amber, max(1.2, 1.25 * s)))
        p.setBrush(QColor(255, 184, 48, 36))
        p.drawPath(tri)

        # Exclamation
        pen = QPen(amber, max(1.5, 1.55 * s))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(11 * s, 8.2 * s), QPointF(11 * s, 13.2 * s))
        p.setBrush(amber)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(10.1 * s, 14.6 * s, 1.8 * s, 1.8 * s))
        p.end()


class WelcomeFoundersDialog(QDialog):
    """Full early-user welcome note from the AURA team."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to AURA")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(540)
        self.setStyleSheet(
            f"QDialog {{ background: {T.BG}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(_ImportantMark(28), 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        badge = QLabel("FOR NEW USERS")
        badge.setFont(QFont(T.SB_FONT, 10, QFont.Weight.DemiBold))
        badge.setStyleSheet(
            "color: #ffc448; background: rgba(255, 184, 48, 0.12);"
            "border: 1px solid rgba(255, 184, 48, 0.35); border-radius: 8px;"
            "padding: 3px 8px;"
        )
        titles.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        title = QLabel("Welcome!")
        title.setFont(QFont(T.CHAT_FONT, 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.WHITE}; background: transparent;")
        titles.addWidget(title)
        head.addLayout(titles, stretch=1)
        root.addLayout(head)

        body = QLabel(
            "Thank you for choosing <b>AURA</b> and becoming one of our first users. "
            "We're truly glad you decided to try our app — your support helps us grow every day."
            "<br/><br/>"
            "We're a young team working hard to make the product as convenient, fast, and useful "
            "as possible. We continuously add new features, refine the design, and fix issues as "
            "we find them."
            "<br/><br/>"
            "If you notice a bug, crash, or anything that doesn't work as expected, please reach "
            "out by email:"
            f"<br/><br/><a href=\"mailto:{_SUPPORT_EMAIL}\" style=\"color:#00d1ff;\">"
            f"{_SUPPORT_EMAIL}</a>"
            "<br/><br/>"
            "Describe the issue in as much detail as you can, and our team will do our best to "
            "investigate and fix it quickly."
            "<br/><br/>"
            "Thank you for helping us make <b>AURA</b> better!"
            "<br/><br/>"
            "— The AURA Team"
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setOpenExternalLinks(True)
        body.setFont(QFont(T.CHAT_FONT, 13))
        body.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; line-height: 1.45;")
        root.addWidget(body)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        mail = QPushButton("Email support")
        mail.setCursor(Qt.CursorShape.PointingHandCursor)
        mail.setFixedHeight(36)
        mail.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {T.CYAN}; "
            f"border: 1px solid rgba(0, 209, 255, 0.35); border-radius: 10px; padding: 0 16px; "
            f"font-family: '{T.SB_FONT}'; font-size: 12px; font-weight: 600; }}"
            "QPushButton:hover { background: rgba(0, 209, 255, 0.08); }"
        )
        mail.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"mailto:{_SUPPORT_EMAIL}"))
        )
        actions.addWidget(mail)
        actions.addStretch()
        close = QPushButton("Got it")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedHeight(36)
        close.setDefault(True)
        close.setStyleSheet(
            f"QPushButton {{ background: {T.CYAN}; color: #041018; border: none; "
            f"border-radius: 10px; padding: 0 18px; font-family: '{T.SB_FONT}'; "
            "font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background: #33daff; }"
        )
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        root.addLayout(actions)


class _SidebarWelcomeCard(QFrame):
    """Compact early-user row — same size as Permissions."""

    clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarWelcomeCard")
        self._hover = False
        self.setFixedHeight(T.SB_ROW_H + 2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_WELCOME_PREVIEW)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        self._mark = _ImportantMark(22)
        lay.addWidget(self._mark, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel("Welcome!")
        self._label.setFont(QFont(T.SB_FONT, T.SB_FONT_SIZE, QFont.Weight.Medium))
        lay.addWidget(self._label, stretch=1)

        self._close = QFrame(self)
        self._close.setObjectName("SidebarWelcomeClose")
        self._close.setFixedSize(18, 18)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.setToolTip("Dismiss")
        close_lay = QHBoxLayout(self._close)
        close_lay.setContentsMargins(0, 0, 0, 0)
        self._close_icon = _LineIcon("close", T.SB_TEXT_MUTED, size=11)
        close_lay.addWidget(self._close_icon, 0, Qt.AlignmentFlag.AlignCenter)
        self._close.mousePressEvent = self._on_close_press  # type: ignore[method-assign]
        lay.addWidget(self._close, 0, Qt.AlignmentFlag.AlignVCenter)

        self._chev = QLabel("›")
        self._chev.setFont(QFont(T.SB_FONT, 16, QFont.Weight.Light))
        lay.addWidget(self._chev, 0, Qt.AlignmentFlag.AlignVCenter)
        self._apply()

    def _apply(self) -> None:
        bg = "rgba(255, 184, 48, 0.14)" if self._hover else "rgba(255, 184, 48, 0.08)"
        border = "rgba(255, 184, 48, 0.42)" if self._hover else "rgba(255, 184, 48, 0.26)"
        self.setStyleSheet(
            f"""
            QFrame#SidebarWelcomeCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QFrame#SidebarWelcomeClose {{
                background: transparent;
                border: none;
                border-radius: 5px;
            }}
            """
        )
        fg = T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT
        self._label.setStyleSheet(
            f"color: {fg}; background: transparent; border: none;"
        )
        self._chev.setStyleSheet(
            f"color: {'#ffc448' if self._hover else T.SB_TEXT_MUTED}; "
            "background: transparent; border: none;"
        )
        self._close_icon.set_color(T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT_MUTED)

    def _on_close_press(self, e) -> None:  # noqa: ANN001
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()
            mark_welcome_card_dismissed()
            self.hide()
            self.dismissed.emit()
            return
        QFrame.mousePressEvent(self._close, e)

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._close.geometry().contains(e.position().toPoint()):
                return
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class _SidebarPermissionsRow(QFrame):
    """Dedicated Permissions entry above the profile chip."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarPermissionsRow")
        self._hover = False
        self.setFixedHeight(T.SB_ROW_H + 2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        self._badge = _SidebarShieldBadge(22)
        lay.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel("Permissions")
        self._label.setFont(QFont(T.SB_FONT, T.SB_FONT_SIZE, QFont.Weight.Medium))
        lay.addWidget(self._label, stretch=1)

        self._chev = QLabel("›")
        self._chev.setFont(QFont(T.SB_FONT, 16, QFont.Weight.Light))
        lay.addWidget(self._chev, 0, Qt.AlignmentFlag.AlignVCenter)
        self._apply()

    def _apply(self) -> None:
        bg = "rgba(0, 209, 255, 0.08)" if self._hover else "rgba(0, 209, 255, 0.04)"
        border = "rgba(0, 209, 255, 0.28)" if self._hover else "rgba(0, 209, 255, 0.14)"
        self.setStyleSheet(
            f"""
            QFrame#SidebarPermissionsRow {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            """
        )
        self._badge.set_hot(self._hover)
        fg = T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT
        self._label.setStyleSheet(
            f"color: {fg}; background: transparent; border: none;"
        )
        self._chev.setStyleSheet(
            f"color: {T.SB_ACCENT if self._hover else T.SB_TEXT_MUTED}; "
            "background: transparent; border: none;"
        )

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class _SidebarLogo(QWidget):
    """Compact AURA mark + wordmark at the top of the sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._pix = None
        try:
            from pathlib import Path

            from PyQt6.QtGui import QPixmap

            roots = []
            try:
                from jarvis_ui.paths import resource_dir

                roots.append(Path(resource_dir()))
            except Exception:
                pass
            roots.append(Path(__file__).resolve().parents[1])
            for root in roots:
                for name in ("aura_logo.png", "aura_logo_onboarding.png"):
                    path = root / "assets" / name
                    if path.is_file():
                        pix = QPixmap(str(path))
                        if not pix.isNull():
                            self._pix = pix.scaled(
                                22,
                                22,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            break
                if self._pix is not None:
                    break
        except Exception:
            self._pix = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = 4
        if self._pix is not None:
            p.drawPixmap(x, (self.height() - self._pix.height()) // 2, self._pix)
            x += self._pix.width() + 8
        p.setPen(QPen(QColor(T.SB_TEXT_ACTIVE)))
        p.setFont(QFont(T.SB_FONT, 14, QFont.Weight.DemiBold))
        p.drawText(x, 20, "AURA")


class _SidebarNewSessionBtn(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)
        lay.addWidget(_LineIcon("plus", T.SB_TEXT_MUTED, 15))
        lbl = QLabel("New chat")
        lbl.setFont(QFont(T.SB_FONT, T.SB_FONT_SIZE))
        lbl.setStyleSheet(f"color: {T.SB_TEXT}; background: transparent;")
        lay.addWidget(lbl)
        lay.addStretch()
        self._apply()

    def _apply(self):
        bg = T.SB_HOVER if self._hover else "transparent"
        self.setStyleSheet(
            f"_SidebarNewSessionBtn {{ background: {bg}; border: none; border-radius: 8px; }}"
        )

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class _SidebarMoreBtn(QFrame):
    """'⋯ More' under Automations — no filled gray background."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarMoreBtn")
        self._hover = False
        self.setFixedHeight(T.SB_ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)
        self._icon = _LineIcon("more_h", T.SB_TEXT_MUTED, T.SB_ICON)
        lay.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._lbl = QLabel("More")
        self._lbl.setFont(QFont(T.SB_FONT, T.SB_FONT_SIZE))
        self._lbl.setStyleSheet(f"color: {T.SB_TEXT}; background: transparent; border: none;")
        lay.addWidget(self._lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch()
        self._apply()

    def _apply(self):
        # Transparent by default — only a soft hover like other nav rows.
        bg = T.SB_HOVER if self._hover else "transparent"
        self.setStyleSheet(
            f"QFrame#SidebarMoreBtn {{ background: {bg}; border: none; border-radius: 8px; }}"
        )
        self._icon.set_color(T.SB_TEXT if self._hover else T.SB_TEXT_MUTED)
        self._lbl.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT}; "
            "background: transparent; border: none;"
        )

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class _SidebarNavRow(QFrame):
    """Linear-style sidebar row using SB_* theme tokens."""

    clicked = pyqtSignal(str)

    def __init__(
        self,
        key: str,
        label: str,
        icon_name: str,
        active: bool = False,
        trailing: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._key = key
        self._active = active
        self._hover = False
        self.setFixedHeight(T.SB_ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        self._icon = _LineIcon(icon_name, T.SB_TEXT_MUTED, T.SB_ICON)
        lay.addWidget(self._icon)

        self._label = QLabel(label)
        self._label.setFont(QFont(T.SB_FONT, T.SB_FONT_SIZE))
        lay.addWidget(self._label, stretch=1)

        self._trail = None
        if trailing:
            self._trail = QLabel(trailing)
            self._trail.setFont(QFont(T.SB_FONT, 10))
            lay.addWidget(self._trail)

        self._apply()

    def set_active(self, active: bool):
        if active != self._active:
            self._active = active
            self._apply()

    def _apply(self):
        if self._active:
            bg, icon_c, fg = T.SB_ACCENT_SOFT, T.SB_ACCENT, T.SB_TEXT_ACTIVE
        elif self._hover:
            bg, icon_c, fg = T.SB_HOVER, T.SB_TEXT, T.SB_TEXT
        else:
            bg, icon_c, fg = "transparent", T.SB_TEXT_MUTED, T.SB_TEXT
        self.setStyleSheet(
            f"_SidebarNavRow {{ background: {bg}; border: none; border-radius: 6px; }}"
        )
        self._icon.set_color(icon_c)
        self._label.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        if self._trail is not None:
            self._trail.setStyleSheet(f"color: {T.SB_TEXT_MUTED}; background: transparent;")

    def enterEvent(self, e):
        if not self._active:
            self._hover = True
            self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(e)


class _ProfileMenuItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, action: str, label: str, icon_name: str, *, danger: bool = False, parent=None):
        super().__init__(parent)
        self._action = action
        self._hover = False
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(10)
        icon_color = T.RED if danger else T.SB_TEXT_MUTED
        self._icon = _LineIcon(icon_name, icon_color, 16)
        lay.addWidget(self._icon)
        self._label = QLabel(label)
        self._label.setFont(QFont(T.SB_FONT, 12))
        lay.addWidget(self._label, stretch=1)
        self._danger = danger
        self._apply()

    def _apply(self) -> None:
        if self._danger:
            fg, icon = T.RED, T.RED
            hover_bg = "rgba(255, 68, 102, 0.10)"
        else:
            fg = T.SB_TEXT
            icon = T.SB_ACCENT if self._hover else T.SB_TEXT_MUTED
            hover_bg = T.SB_HOVER
        bg = hover_bg if self._hover else "transparent"
        self.setStyleSheet(f"_ProfileMenuItem {{ background: {bg}; border-radius: 8px; }}")
        self._icon.set_color(icon)
        self._label.setStyleSheet(f"color: {fg}; background: transparent; border: none;")

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._action)
        super().mousePressEvent(e)


class ProfileMenuPopover(QWidget):
    action_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(228)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        self._card = QFrame()
        self._card.setObjectName("profileMenuCard")
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(8, 8, 8, 8)
        card_lay.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 8)
        self._avatar = AvatarCircle(32)
        header.addWidget(self._avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        self._name = QLabel("Sign in")
        self._name.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium))
        self._subtitle = QLabel("")
        self._subtitle.setFont(QFont(T.SB_FONT, 10))
        col.addWidget(self._name)
        col.addWidget(self._subtitle)
        header.addLayout(col, stretch=1)
        card_lay.addLayout(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {T.BORDER}; border: none;")
        card_lay.addWidget(sep)

        self._items_host = QVBoxLayout()
        self._items_host.setContentsMargins(0, 4, 0, 4)
        self._items_host.setSpacing(1)
        card_lay.addLayout(self._items_host)
        outer.addWidget(self._card)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 110))
        self._card.setGraphicsEffect(shadow)
        self._style_card()
        self.refresh()

    def _style_card(self) -> None:
        self._card.setStyleSheet(
            f"QFrame#profileMenuCard {{ background: {T.BG_CARD}; "
            f"border: 1px solid {T.BORDER_HI}; border-radius: 14px; }}"
        )
        self._name.setStyleSheet(f"color: {T.SB_TEXT_ACTIVE}; background: transparent; border: none;")
        self._subtitle.setStyleSheet(f"color: {T.SB_TEXT_MUTED}; background: transparent; border: none;")

    def _clear_items(self) -> None:
        while self._items_host.count():
            item = self._items_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_item(self, action: str, label: str, icon: str, *, danger: bool = False) -> None:
        row = _ProfileMenuItem(action, label, icon, danger=danger)
        row.clicked.connect(self._on_item)
        self._items_host.addWidget(row)

    def _add_separator(self) -> None:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {T.BORDER}; border: none; margin: 4px 8px;")
        self._items_host.addWidget(sep)

    def _on_item(self, action: str) -> None:
        self.hide()
        self.action_selected.emit(action)

    def refresh(self, *, authenticated: bool | None = None) -> None:
        authed = UA.is_authenticated() if authenticated is None else authenticated
        if authed:
            name = UA.get_display_name() or "User"
            subtitle = UA.get_subtitle(authenticated=True)
            self._name.setText(name)
            self._subtitle.setText(subtitle)
            self._subtitle.setVisible(bool(subtitle))
            self._avatar.set_profile(
                initial=name[:1],
                url=UA.get_avatar_url(),
                authenticated=True,
            )
        else:
            # Cursor-style guest chip in the menu header.
            self._name.setText("Sign in")
            self._subtitle.setText("")
            self._subtitle.setVisible(False)
            self._avatar.set_profile(initial="", url="", authenticated=False)
        self._clear_items()
        if authed:
            for action, label, icon in (
                ("profile", "Profile", "user"),
                ("settings", "Settings", "settings"),
                ("permissions", "Permissions", "shield"),
                ("subscription", "Subscription", "subscription"),
                ("referral", "Referral Program", "gift"),
                ("shortcuts", "Keyboard Shortcuts", "keyboard"),
                ("help", "Help & Support", "help"),
            ):
                self._add_item(action, label, icon)
            self._add_separator()
            self._add_item("sign_out", "Sign Out", "logout", danger=True)
        else:
            self._add_item("sign_in", "Sign In", "login")
            self._add_item("create_account", "Create Account", "plus_user")
        self.adjustSize()

    def popup_above(self, anchor: QWidget, *, authenticated: bool | None = None) -> None:
        self.refresh(authenticated=authenticated)
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, 0))
        x = pos.x() + max(0, (anchor.width() - self.width()) // 2)
        y = pos.y() - self.height() - 6
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


class _SidebarSettingsBtn(QFrame):
    """Cursor-style outline gear next to the profile chip."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Settings")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._icon = _LineIcon("settings", T.SB_TEXT_MUTED, size=18)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignCenter)
        self._apply()

    def _apply(self) -> None:
        bg = "rgba(255,255,255,0.06)" if self._hover else "transparent"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: none; border-radius: 6px; }}"
        )
        self._icon.set_color(T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT_MUTED)

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class _SidebarReferralCard(QFrame):
    """Cursor-style promo chip above the account row — gift + copy + dismiss (session only)."""

    clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarReferralCard")
        self._hover = False
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open referral program")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(8)

        self._gift = _LineIcon("gift", T.SB_TEXT_ACTIVE, size=16)
        lay.addWidget(self._gift, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel("Refer friends, earn up…")
        self._label.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium))
        self._label.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE}; background: transparent; border: none;"
        )
        lay.addWidget(self._label, stretch=1)

        self._close = QFrame(self)
        self._close.setObjectName("SidebarReferralClose")
        self._close.setFixedSize(22, 22)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.setToolTip("Dismiss")
        close_lay = QHBoxLayout(self._close)
        close_lay.setContentsMargins(0, 0, 0, 0)
        self._close_icon = _LineIcon("close", T.SB_TEXT_MUTED, size=12)
        close_lay.addWidget(self._close_icon, 0, Qt.AlignmentFlag.AlignCenter)
        self._close.mousePressEvent = self._on_close_press  # type: ignore[method-assign]
        lay.addWidget(self._close, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply()

    def _apply(self) -> None:
        bg = "rgba(0, 209, 255, 0.12)" if self._hover else "rgba(0, 209, 255, 0.07)"
        border = "rgba(0, 209, 255, 0.32)" if self._hover else "rgba(0, 209, 255, 0.18)"
        self.setStyleSheet(
            f"""
            QFrame#SidebarReferralCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QFrame#SidebarReferralClose {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            """
        )
        self._gift.set_color(T.CYAN if self._hover else T.SB_TEXT)
        self._label.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT}; "
            "background: transparent; border: none;"
        )
        self._close_icon.set_color(T.SB_TEXT_ACTIVE if self._hover else T.SB_TEXT_MUTED)

    def _on_close_press(self, e) -> None:  # noqa: ANN001
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()
            # Session-only: hide until next app launch (do not persist).
            self.hide()
            self.dismissed.emit()
            return
        QFrame.mousePressEvent(self._close, e)

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Dismiss control handles its own clicks.
            if self._close.geometry().contains(e.position().toPoint()):
                return
            self.clicked.emit()
        super().mousePressEvent(e)


class _SidebarProfileFooter(QFrame):
    """Bottom-left account chip — Cursor-style avatar / plan / Update / settings."""

    menu_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self._update_available = False
        self.setObjectName("SidebarProfileFooter")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 4, 6)
        lay.setSpacing(8)

        self._identity = QFrame(self)
        self._identity.setObjectName("SidebarProfileIdentity")
        self._identity.setCursor(Qt.CursorShape.PointingHandCursor)
        id_lay = QHBoxLayout(self._identity)
        id_lay.setContentsMargins(0, 0, 0, 0)
        id_lay.setSpacing(10)

        self._avatar = AvatarCircle(28)
        id_lay.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(1)
        info.setContentsMargins(0, 0, 0, 0)
        self._name = QLabel("Sign in")
        self._name.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium))
        self._plan = QLabel("")
        self._plan.setFont(QFont(T.SB_FONT, 10))
        info.addWidget(self._name)
        info.addWidget(self._plan)
        id_lay.addLayout(info, stretch=1)
        lay.addWidget(self._identity, stretch=1)

        # Cursor-like soft periwinkle Update pill (hidden until a release is ready).
        self._update_btn = QPushButton("Update")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setFixedHeight(24)
        self._update_btn.setVisible(False)
        self._update_btn.setStyleSheet(
            "QPushButton {"
            "  background: #b7c9e8;"
            "  color: #1a1f2a;"
            "  border: none;"
            "  border-radius: 12px;"
            "  padding: 0 12px;"
            f"  font-family: '{T.SB_FONT}';"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #c5d4f0; }"
            "QPushButton:pressed { background: #a8bbdf; }"
            "QPushButton:disabled { background: #6b7a94; color: #1a1f2a; }"
        )
        self._update_btn.clicked.connect(self.update_requested.emit)
        lay.addWidget(self._update_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._settings_btn = _SidebarSettingsBtn(self)
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        lay.addWidget(self._settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._identity.mousePressEvent = self._identity_click  # type: ignore[method-assign]
        self.refresh_account()

    def _identity_click(self, e) -> None:  # noqa: ANN001
        if e.button() == Qt.MouseButton.LeftButton:
            self.menu_requested.emit()
        QFrame.mousePressEvent(self._identity, e)

    def set_update_available(self, available: bool, *, downloading: bool = False) -> None:
        self._update_available = bool(available)
        self._update_btn.setVisible(self._update_available or downloading)
        if downloading:
            self._update_btn.setText("Updating…")
            self._update_btn.setEnabled(False)
        else:
            self._update_btn.setText("Update")
            self._update_btn.setEnabled(True)

    def refresh_account(self) -> None:
        authed = UA.is_authenticated()
        if authed:
            name = UA.get_display_name() or "User"
            subtitle = UA.get_subtitle(authenticated=True)
            self._name.setText(name)
            self._plan.setText(subtitle)
            self._plan.setVisible(bool(subtitle))
            self._avatar.set_profile(
                initial=name[:1],
                url=UA.get_avatar_url(),
                authenticated=True,
            )
        else:
            self._name.setText("Sign in")
            self._plan.setText("")
            self._plan.setVisible(False)
            self._avatar.set_profile(initial="", url="", authenticated=False)
        self._apply(authenticated=authed)

    def _apply(self, *, authenticated: bool | None = None) -> None:
        authed = UA.is_authenticated() if authenticated is None else authenticated
        bg = T.SB_HOVER if self._hover else "transparent"
        self.setStyleSheet(
            f"QFrame#SidebarProfileFooter {{ background: {bg}; border: none; border-radius: 8px; }}"
            "QFrame#SidebarProfileIdentity { background: transparent; border: none; }"
        )
        self._name.setStyleSheet(
            f"color: {T.SB_TEXT_ACTIVE}; background: transparent; border: none;"
        )
        self._plan.setStyleSheet(
            f"color: {T.SB_TEXT_MUTED}; background: transparent; border: none;"
        )

    def enterEvent(self, e):
        self._hover = True
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._apply()
        super().leaveEvent(e)


class _BracketButton(QFrame):
    """Framed 'NEW SESSION' button with cyan corner brackets (HUD style)."""

    clicked = pyqtSignal()

    def __init__(self, text: str, shortcut: str, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)
        plus = QLabel("+")
        plus.setFont(QFont(T.FONT_UI, 15, QFont.Weight.Bold))
        plus.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        lay.addWidget(plus)
        lbl = QLabel(text)
        lbl.setFont(_spaced_font(T.FONT_DISPLAY, 11, 4.0, bold=True))
        lbl.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        lay.addWidget(lbl)
        lay.addStretch()
        if shortcut:
            kbd = QLabel(shortcut)
            kbd.setFont(QFont(T.FONT_UI, 9))
            kbd.setStyleSheet(f"color: {T.CYAN_DIM}; background: transparent;")
            lay.addWidget(kbd)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        inset = 3
        rect = QRectF(inset, inset, W - inset * 2, H - inset * 2)

        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 209, 255, 22))
            p.drawRect(rect)

        faint = QColor(T.BORDER_HI)
        faint.setAlpha(120)
        p.setPen(QPen(faint, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)

        bl = 16
        p.setPen(QPen(QColor(T.CYAN), 2))
        x0, y0 = rect.left(), rect.top()
        x1, y1 = rect.right(), rect.bottom()
        for cx, cy, dx, dy in [(x0, y0, 1, 1), (x1, y0, -1, 1),
                               (x0, y1, 1, -1), (x1, y1, -1, -1)]:
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * bl, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * bl))


class _AgentRow(QFrame):
    """A selectable agent/skill launcher row."""

    clicked = pyqtSignal(str)

    def __init__(self, key: str, label: str, icon_name: str, active: bool = False,
                 trailing: str = "", trailing_color: str | None = None,
                 active_dot: bool = False, parent=None):
        super().__init__(parent)
        self._key = key
        self._active = active
        self._active_dot = active_dot
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 16, 0)
        lay.setSpacing(13)

        self._icon = _LineIcon(icon_name, size=22)
        lay.addWidget(self._icon)

        self._label = QLabel(label)
        self._label.setFont(_spaced_font(T.FONT_DISPLAY, 11, 0.8, bold=False))
        lay.addWidget(self._label)
        lay.addStretch()

        self._dot = None
        if active_dot:
            self._dot = QLabel("●")
            self._dot.setFont(QFont(T.FONT_UI, 7))
            self._dot.setFixedWidth(10)
            self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(self._dot)

        self._trail = None
        self._trail_color = trailing_color or T.TEXT_DIM
        if trailing:
            self._trail = QLabel(trailing)
            self._trail.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
            lay.addWidget(self._trail)

        self._apply()

    def set_active(self, active: bool):
        if active != self._active:
            self._active = active
            self._apply()

    def _apply(self):
        if self._active:
            self.setStyleSheet(
                "_AgentRow { background: rgba(126,184,212,0.07); "
                "border: 1px solid rgba(0,209,255,0.16); border-radius: 9px; }"
            )
            self._icon.set_color(T.CYAN)
            self._label.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
        else:
            self.setStyleSheet(
                "_AgentRow { background: transparent; border: 1px solid transparent; border-radius: 9px; }"
                "_AgentRow:hover { background: rgba(255,255,255,0.03); }"
            )
            self._icon.set_color(T.TEXT_DIM)
            self._label.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        if self._dot is not None:
            visible = self._active and self._active_dot
            self._dot.setVisible(visible)
            if visible:
                self._dot.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
        if self._trail is not None:
            self._trail.setStyleSheet(
                f"color: {self._trail_color}; background: transparent; border: none;"
            )

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(e)


class _SidebarEdgeRail(QWidget):
    """Full-height fused divider+scrollbar rail drawn on top of the sidebar.

    The native QScrollBar stays interactive underneath (this widget is mouse-
    transparent) but is fully invisible — we paint the track + thumb here so
    there is exactly one vertical line, never a gray splitter beside it.
    """

    def __init__(self, sidebar: "NavSidebar"):
        super().__init__(sidebar)
        self._sidebar = sidebar
        self.setObjectName("SidebarEdgeRail")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

    def sync_from_sidebar(self):
        sb = self._sidebar
        width, _track, _handle = sb._rail_metrics()
        self.setGeometry(sb.width() - width, 0, width, sb.height())
        self.update()
        self.raise_()

    def paintEvent(self, _event):
        sb = self._sidebar
        width, track, handle = sb._rail_metrics()
        if width <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Continuous divider track (replaces the old gray splitter line).
        p.fillRect(0, 0, width, self.height(), track)

        bar = sb._scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        # Manual thumb geometry — initStyleOption is protected in PyQt6.
        bar_h = max(1, bar.height())
        span = bar.maximum() + bar.pageStep()
        handle_h = max(36, int(bar_h * (bar.pageStep() / span))) if span > 0 else 36
        handle_h = min(handle_h, bar_h)
        travel = max(0, bar_h - handle_h)
        y_in_bar = int(travel * (bar.value() / bar.maximum())) if bar.maximum() else 0
        # mapToGlobal avoids parent-hierarchy issues between overlay and scrollbar.
        y = self.mapFromGlobal(bar.mapToGlobal(QPoint(0, y_in_bar))).y()
        y = max(0, y)
        h = max(8, handle_h)
        if y + h > self.height():
            h = self.height() - y
        if h > 0:
            p.fillRect(0, y, width, h, handle)


class NavSidebar(QWidget):
    """Screenshot-matched sidebar — platform nav, agents, workspaces, sessions."""

    _PLATFORM = (
        ("dashboard", "Dashboard", "grid", "dashboard"),
        ("chat", "Chat", "chat", "chat"),
        ("connectors", "Connectors", "plug", "connectors"),
        ("computer_use", "Computer Use", "monitor", "computer_use"),
        ("skills", "Skills", "puzzle", "almost_ready"),
        ("voice", "Voice", "mic", "almost_ready"),
        ("automations", "Automations", "clock", "almost_ready"),
    )
    _BUILDERS = (
        ("website", "Website Builder", "globe"),
        ("code", "Code Assistant", "code"),
        ("researcher", "Researcher", "researcher"),
    )

    new_chat = pyqtSignal()
    agent_selected = pyqtSignal(str)
    section_changed = pyqtSignal(str)
    chat_selected = pyqtSignal(str)
    workspace_selected = pyqtSignal(str)
    workspace_create = pyqtSignal()
    workspace_rename = pyqtSignal(str)
    workspace_delete = pyqtSignal(str)
    chat_rename = pyqtSignal(str)
    chat_delete = pyqtSignal(str)
    chat_pin = pyqtSignal(str)
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()
    profile_menu_action = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavSidebar")
        self._nav_rows: dict[str, _SidebarNavRow] = {}
        self._active_key = "dashboard"
        self._list_rows: list[_SideRow] = []

        root = QVBoxLayout(self)
        # Right margin 0 — scrollbar track sits on the barrier edge.
        root.setContentsMargins(10, 10, 0, 8)
        root.setSpacing(0)

        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 10, 0)
        top_lay.setSpacing(0)
        top_lay.addWidget(_SidebarLogo())
        top_lay.addSpacing(8)
        root.addWidget(top)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always show the rail so the barrier line is visible even with few chats.
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        body = QWidget()
        body.setMinimumWidth(0)
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._scroll_body = body
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setContentsMargins(0, 0, 10, 0)
        self._body_lay.setSpacing(1)

        self._body_lay.addWidget(self._section_label("PLATFORM"))
        for key, label, icon, agent in self._PLATFORM:
            row = _SidebarNavRow(key, label, icon, active=(key == "dashboard"))
            row.clicked.connect(lambda k, a=agent: self._on_platform(k, a))
            self._nav_rows[key] = row
            self._body_lay.addWidget(row)
            if key == "automations":
                more = _SidebarMoreBtn()
                more.clicked.connect(self._on_automations_more)
                self._body_lay.addWidget(more)

        self._body_lay.addSpacing(6)
        self._body_lay.addWidget(self._section_label("AGENTS"))
        for key, label, icon in self._BUILDERS:
            row = _SidebarNavRow(key, label, icon)
            row.clicked.connect(self._on_agent)
            self._nav_rows[key] = row
            self._body_lay.addWidget(row)

        self._body_lay.addSpacing(6)
        self._chats_section = self._section_label("CHATS")
        self._body_lay.addWidget(self._chats_section)
        self._chat_host = QVBoxLayout()
        self._chat_host.setSpacing(2)
        self._chat_wrap = QWidget()
        self._chat_wrap.setMinimumWidth(0)
        self._chat_wrap.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._chat_wrap.setLayout(self._chat_host)
        self._body_lay.addWidget(self._chat_wrap)

        self._body_lay.addStretch()
        self._scroll.setWidget(body)
        root.addWidget(self._scroll, stretch=1)

        foot_wrap = QWidget()
        foot_lay = QVBoxLayout(foot_wrap)
        foot_lay.setContentsMargins(0, 0, 10, 0)
        foot_lay.setSpacing(6)
        # Early-user welcome note above Permissions (dismissible).
        self._welcome_card = _SidebarWelcomeCard()
        self._welcome_card.clicked.connect(self._open_welcome_note)
        if is_welcome_card_dismissed():
            self._welcome_card.hide()
        foot_lay.addWidget(self._welcome_card)
        # Permissions sits above promo + profile chip.
        self._perm_btn = _SidebarPermissionsRow()
        self._perm_btn.clicked.connect(self._open_permissions)
        foot_lay.addWidget(self._perm_btn)
        # Cursor-style referral promo directly above the account row.
        self._referral_card = _SidebarReferralCard()
        self._referral_card.clicked.connect(
            lambda: self.profile_menu_action.emit("referral")
        )
        foot_lay.addWidget(self._referral_card)
        self._footer = _SidebarProfileFooter()
        self._footer.menu_requested.connect(self._open_profile_menu)
        self._footer.settings_requested.connect(self.settings_requested.emit)
        self._footer.update_requested.connect(self.update_requested.emit)
        foot_lay.addWidget(self._footer)
        root.addWidget(foot_wrap)

        self._profile_menu: ProfileMenuPopover | None = None

        self.setMinimumWidth(T.SB_MIN_W)
        self.setMaximumWidth(T.SB_MAX_W)
        self.setMouseTracking(True)

        # Single fused edge: full-height overlay rail + scrollbar thumb on top.
        # (The QSplitter handle in ui.py is intentionally invisible.)
        self.setStyleSheet(
            f"QWidget#NavSidebar {{ background: {T.BG_PANEL}; border: none; }}"
        )
        self._rail_hot = False
        self._rail_width_idle = 2
        self._rail_width_hot = 3
        self._scroll_fade = QTimer(self)
        self._scroll_fade.setSingleShot(True)
        self._scroll_fade.timeout.connect(lambda: self._set_rail_hot(False))

        self._edge_rail = _SidebarEdgeRail(self)
        self._edge_rail.raise_()

        sb = self._scroll.verticalScrollBar()
        sb.installEventFilter(self)
        self._scroll.installEventFilter(self)
        self._edge_rail.installEventFilter(self)
        sb.valueChanged.connect(self._on_rail_scroll)
        sb.rangeChanged.connect(lambda *_: self._edge_rail.update())
        self._apply_edge_rail_style()

        self._cached_chats: list[dict] = []
        self._active_chat_id: str | None = None

    def _rail_metrics(self) -> tuple[int, QColor, QColor]:
        """Return (width, track_color, handle_color) for idle/hot states."""
        if self._rail_hot:
            return (
                self._rail_width_hot,
                QColor(0, 209, 255, 72),
                QColor(0, 209, 255, 230),
            )
        return (
            self._rail_width_idle,
            QColor(0, 209, 255, 40),
            QColor(0, 209, 255, 130),
        )

    def _apply_edge_rail_style(self):
        width, _track, _handle = self._rail_metrics()
        # Native scrollbar is invisible but keeps its hit-target under the rail.
        # The overlay paints the only visible divider + thumb.
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: transparent;"
            f"  width: {width}px;"
            "  margin: 0px;"
            "  border: none;"
            "  border-radius: 0px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: transparent;"
            "  border-radius: 0px;"
            "  min-height: 36px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            " { height: 0px; width: 0px; border: none; background: transparent; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            " { background: transparent; }"
        )
        self._edge_rail.sync_from_sidebar()
        self._sync_scroll_body_width()

    def _sync_scroll_body_width(self) -> None:
        """Pin scroll content to viewport width so right-side chat actions stay visible."""
        body = getattr(self, "_scroll_body", None)
        if body is None:
            return
        w = int(self._scroll.viewport().width())
        if w > 0:
            body.setFixedWidth(w)

    def _set_rail_hot(self, hot: bool):
        if self._rail_hot == hot:
            return
        self._rail_hot = hot
        self._apply_edge_rail_style()

    def _on_rail_scroll(self, *_):
        self._set_rail_hot(True)
        self._edge_rail.update()
        self._scroll_fade.start(700)

    def _near_right_edge(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - 12

    def eventFilter(self, obj, event):
        et = event.type()
        sb = self._scroll.verticalScrollBar()
        if obj in (self._scroll, sb, self._edge_rail):
            if et == QEvent.Type.Enter:
                self._scroll_fade.stop()
                self._set_rail_hot(True)
            elif et == QEvent.Type.Leave:
                self._scroll_fade.start(280)
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_scroll_body_width()
        self._edge_rail.sync_from_sidebar()
        self._edge_rail.raise_()

    def mouseMoveEvent(self, event):
        if self._near_right_edge(event.position().toPoint()):
            self._scroll_fade.stop()
            self._set_rail_hot(True)
        elif not self._scroll.verticalScrollBar().underMouse():
            self._scroll_fade.start(280)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._scroll_fade.start(280)
        super().leaveEvent(event)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(T.SB_FONT, T.SB_SECTION_SIZE, QFont.Weight.Bold))
        lbl.setStyleSheet(
            f"color: {T.SB_TEXT_MUTED}; background: transparent; "
            f"padding: 8px 8px 4px; letter-spacing: 1.2px;"
        )
        return lbl

    def _on_platform(self, key: str, agent: str):
        if self._active_key in self._nav_rows:
            self._nav_rows[self._active_key].set_active(False)
        self._active_key = key
        if key in self._nav_rows:
            self._nav_rows[key].set_active(True)
        self.agent_selected.emit(agent)

    def _on_agent(self, key: str):
        if self._active_key in self._nav_rows:
            self._nav_rows[self._active_key].set_active(False)
        self._active_key = key
        self._nav_rows[key].set_active(True)
        self.agent_selected.emit(key)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def refresh(self, workspaces: list[dict], chats: list[dict],
                active_ws_id: str = "", active_chat_id: str | None = None):
        self._cached_chats = list(chats)
        self._active_chat_id = active_chat_id
        self._list_rows.clear()

        self._clear_layout(self._chat_host)
        if hasattr(self, "_chats_section"):
            self._chats_section.setText("CHATS")
            self._chats_section.setStyleSheet(
                f"color: {T.SB_TEXT_MUTED}; background: transparent; "
                f"padding: 8px 8px 4px; letter-spacing: 1.2px;"
            )
        self._sync_scroll_body_width()
        for chat in chats:
            cid = chat.get("id", "")
            title = chat.get("title", "Session")
            active = cid == active_chat_id
            row = _ChatSidebarRow(
                title, cid, active, bool(chat.get("pinned")),
                on_select=lambda c=cid: self.chat_selected.emit(c),
                on_delete=lambda c=cid: self.chat_delete.emit(c),
                on_rename=lambda c=cid: self.chat_rename.emit(c),
            )
            self._list_rows.append(row)
            self._chat_host.addWidget(row)

        add_chat = _SidebarNewSessionBtn()
        add_chat.clicked.connect(lambda *_: self.new_chat.emit())
        self._chat_host.addWidget(add_chat)

    def refresh_automations(self, automations: list[dict]):
        # WORKFLOWS sidebar section removed — keep as no-op for callers.
        return

    def _on_automations_more(self) -> None:
        # Open the Coming Soon roadmap page (do not switch to agent chat).
        if self._active_key in self._nav_rows:
            self._nav_rows[self._active_key].set_active(False)
        self._active_key = "automations"
        if "automations" in self._nav_rows:
            self._nav_rows["automations"].set_active(True)
        self.section_changed.emit("automations_more")

    def _open_profile_menu(self) -> None:
        if self._profile_menu is None:
            self._profile_menu = ProfileMenuPopover(self)
            self._profile_menu.action_selected.connect(self._on_profile_menu_action)
        self._profile_menu.popup_above(self._footer)

    def _on_profile_menu_action(self, action: str) -> None:
        if action == "permissions":
            self._open_permissions()
            return
        if action == "settings":
            self.settings_requested.emit()
        self.profile_menu_action.emit(action)

    def _open_welcome_note(self) -> None:
        try:
            dlg = WelcomeFoundersDialog(self.window() or self)
            dlg.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.information(self, "Welcome", str(e))

    def _open_permissions(self) -> None:
        try:
            from jarvis_ui.permissions_panel import PermissionsDialog

            dlg = PermissionsDialog(self.window() or self)
            dlg.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Permissions", str(e))

    def refresh_user_account(self) -> None:
        self._footer.refresh_account()
        if self._profile_menu is not None and self._profile_menu.isVisible():
            self._profile_menu.refresh()

    def set_update_available(self, available: bool, *, downloading: bool = False) -> None:
        self._footer.set_update_available(available, downloading=downloading)


class PreviewPanel(QWidget):
    """Persistent workspace: tabbed renderers for generated sites, code, files and AI results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: str | None = None
        self._current_text: str = ""
        self._artifacts: list[dict] = []
        self._tab_buttons: dict[str, QPushButton] = {}
        self._empty_widget: QWidget | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        self._title = QLabel("PREVIEW")
        self._title.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 1px;")
        self._badge = QLabel("")
        self._badge.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        self._badge.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._title)
        hdr.addWidget(self._badge)
        hdr.addStretch()
        self._open_btn = self._tool_btn("Open ↗")
        self._open_btn.clicked.connect(self._open_external)
        self._copy_btn = self._tool_btn("Copy")
        self._copy_btn.clicked.connect(self._copy)
        self._clear_btn = self._tool_btn("Clear All")
        self._clear_btn.clicked.connect(self.reset)
        for b in (self._open_btn, self._copy_btn, self._clear_btn):
            hdr.addWidget(b)
        lay.addLayout(hdr)

        self._tabs_scroll = QScrollArea()
        self._tabs_scroll.setWidgetResizable(True)
        self._tabs_scroll.setFixedHeight(34)
        self._tabs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tabs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tabs_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._tabs_host = QWidget()
        self._tabs_lay = QHBoxLayout(self._tabs_host)
        self._tabs_lay.setContentsMargins(0, 0, 0, 0)
        self._tabs_lay.setSpacing(6)
        self._tabs_lay.addStretch()
        self._tabs_scroll.setWidget(self._tabs_host)
        lay.addWidget(self._tabs_scroll)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"""
            QStackedWidget {{
                background: {T.BG_CARD}; border: 1px solid {T.BORDER_HI}; border-radius: 12px;
            }}
        """)
        lay.addWidget(self._stack, stretch=1)

        # Page 0: empty state
        empty = QWidget()
        self._empty_widget = empty
        el = QVBoxLayout(empty)
        el.addStretch()
        glyph = QLabel("◍")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setFont(QFont(T.FONT_UI, 40))
        glyph.setStyleSheet(f"color: {T.BORDER_HI}; background: transparent;")
        el.addWidget(glyph)
        hint = QLabel("Generated sites, code, files and results\nwill show up here, live.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFont(QFont(T.FONT_UI, 9))
        hint.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        el.addWidget(hint)
        el.addStretch()
        self._stack.addWidget(empty)

        self.reset()

    def _tool_btn(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 7px; padding: 0 8px; }}
            QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}
        """)
        return b

    def _set_header(self, title: str, badge: str, show_open: bool, show_copy: bool):
        self._title.setText(title[:42])
        self._badge.setText(badge)
        self._open_btn.setVisible(show_open)
        self._copy_btn.setVisible(show_copy)
        self._clear_btn.setVisible(True)

    def reset(self):
        self._current_path = None
        self._current_text = ""
        self._artifacts = []
        self._tab_buttons = {}
        while self._tabs_lay.count():
            it = self._tabs_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._tabs_lay.addStretch()
        while self._stack.count() > 1:
            widget = self._stack.widget(1)
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._title.setText("PREVIEW")
        self._badge.setText("")
        self._open_btn.setVisible(False)
        self._copy_btn.setVisible(False)
        self._clear_btn.setVisible(False)
        self._stack.setCurrentIndex(0)

    def show_web(self, path: str, title: str = ""):
        return self.add_artifact({"kind": "web", "title": title or "Website", "payload": path, "path": path})

    def show_code(self, title: str, code: str, path: str | None = None):
        return self.add_artifact({"kind": "code", "title": title or "Code", "payload": code, "path": path or ""})

    def show_text(self, title: str, content: str, path: str | None = None):
        return self.add_artifact({"kind": "text", "title": title or "Result", "payload": content, "path": path or ""})

    def load_artifacts(self, artifacts: list[dict], active_id: str | None = None):
        self.reset()
        for artifact in artifacts or []:
            self.add_artifact(dict(artifact), persist=False, activate=False)
        if self._artifacts:
            target = active_id or self._artifacts[-1].get("id")
            self.activate(target)

    def add_artifact(self, artifact: dict, persist: bool = True, activate: bool = True) -> dict:
        artifact.setdefault("id", f"local_{len(self._artifacts) + 1}")
        artifact.setdefault("title", "Output")
        artifact.setdefault("kind", "text")
        artifact.setdefault("payload", "")
        artifact.setdefault("path", "")
        self._artifacts.append(artifact)

        widget = self._build_artifact_widget(artifact)
        widget.setProperty("artifact_id", artifact["id"])
        self._stack.addWidget(widget)

        btn = self._artifact_tab(artifact)
        self._tabs_lay.insertWidget(max(0, self._tabs_lay.count() - 1), btn)
        self._tab_buttons[artifact["id"]] = btn
        self._clear_btn.setVisible(True)
        if activate:
            self.activate(artifact["id"])
        return artifact

    def activate(self, artifact_id: str | None):
        if not artifact_id:
            return
        for idx in range(self._stack.count()):
            widget = self._stack.widget(idx)
            if widget.property("artifact_id") == artifact_id:
                self._stack.setCurrentWidget(widget)
                artifact = next((a for a in self._artifacts if a.get("id") == artifact_id), {})
                kind = artifact.get("kind", "text").upper()
                if artifact.get("kind") == "web":
                    self._current_path = artifact.get("path") or artifact.get("payload")
                else:
                    self._current_path = artifact.get("path")
                self._current_text = artifact.get("payload", "")
                self._set_header(artifact.get("title", "Output"), kind, bool(self._current_path), kind != "WEB")
                for aid, btn in self._tab_buttons.items():
                    self._style_artifact_tab(btn, aid == artifact_id)
                return

    def _artifact_tab(self, artifact: dict) -> QPushButton:
        icon = {"web": "◫", "code": "</>", "file": "▤", "text": "≣"}.get(artifact.get("kind"), "≣")
        btn = QPushButton(f"{icon} {artifact.get('title', 'Output')[:18]}")
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        btn.clicked.connect(lambda _, aid=artifact["id"]: self.activate(aid))
        self._style_artifact_tab(btn, False)
        return btn

    def _style_artifact_tab(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(0,209,255,0.16); color: {T.CYAN};
                    border: 1px solid {T.CYAN_DIM}; border-radius: 8px; padding: 0 10px; }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{ background: {T.BG_CARD}; color: {T.TEXT_MED};
                    border: 1px solid {T.BORDER}; border-radius: 8px; padding: 0 10px; }}
                QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}
            """)

    def _build_artifact_widget(self, artifact: dict) -> QWidget:
        kind = artifact.get("kind", "text")
        payload = artifact.get("payload", "")
        path = artifact.get("path") or (payload if kind == "web" else "")
        if kind == "web" and _WEB_ENGINE:
            web = QWebEngineView()
            web.setStyleSheet("background: white; border-radius: 12px;")
            web.load(QUrl.fromLocalFile(path))
            return web
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(f"""
            QTextEdit {{
                background: {T.BG_CARD}; color: {T.TEXT};
                border: none; border-radius: 12px; padding: 14px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}
        """)
        if kind in ("code", "web"):
            text.setFont(QFont(T.FONT_DISPLAY, 9))
            if kind == "web":
                try:
                    from pathlib import Path as _P
                    payload = _P(path).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    payload = path
            text.setPlainText(payload)
        else:
            text.setFont(QFont(T.FONT_UI, 10))
            text.setHtml(markdown_to_html(payload))
        return text

    def _open_external(self):
        if self._current_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_path))

    def _copy(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self._current_text or self._current_path or "")


class _AutoText(QTextBrowser):
    """Read-only rich-text view that grows to fit its content (no inner scroll)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        try:
            self.document().documentLayout().documentSizeChanged.connect(lambda *_: self._fit())
        except Exception:
            pass

    def _fit(self):
        doc = self.document()
        w = max(40, self.viewport().width())
        doc.setTextWidth(w)
        h = int(doc.size().height()) + 6
        if self.height() != h:
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def setHtml(self, html_text: str):
        super().setHtml(html_text)
        self._fit()


class _ActivityItem(QFrame):
    """Collapsible inline timeline item (Cursor-style)."""

    def __init__(self, label: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"_ActivityItem {{ background: rgba(0,209,255,0.04); "
            f"border: 1px solid {T.BORDER}; border-radius: 8px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(4)

        self._btn = QPushButton(("▸  " + label) if detail else ("•  " + label))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
        self._btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {T.CYAN}; border: none; "
            f"text-align: left; padding: 0; }}"
        )
        lay.addWidget(self._btn)

        self._detail = None
        if detail:
            self._detail = _AutoText()
            self._detail.setFont(QFont(T.FONT_UI, 9))
            self._detail.setHtml(markdown_to_html(detail))
            self._detail.setVisible(False)
            lay.addWidget(self._detail)
            self._btn.clicked.connect(self._toggle)

    def _toggle(self):
        if not self._detail:
            return
        vis = not self._detail.isVisible()
        self._detail.setVisible(vis)
        text = self._btn.text()[3:]
        self._btn.setText(("▾  " if vis else "▸  ") + text)


class _JarvisChatOrb(QWidget):
    """Self-contained animated A.U.R.A badge for the chat header."""

    def __init__(self, size: int = 76, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.muted = False
        self.speaking = False
        self.user_speaking = False
        self.state = "LISTENING"
        self._voice_level = 0.0
        self._smooth_voice = 0.0
        self._rings = [0.0, 120.0, 240.0]
        self._tick = 0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(32)

    def set_voice_level(self, level: float) -> None:
        self._voice_level = max(0.0, float(level))
        if self.muted:
            self._voice_level = 0.0

    def _step(self) -> None:
        self._tick += 1
        threshold = 380.0
        target = 1.0 if self._voice_level > threshold and not self.muted else 0.0
        self._smooth_voice += (target - self._smooth_voice) * 0.28
        self.user_speaking = self._voice_level > threshold and not self.muted
        active = self.speaking or self.user_speaking or self.state in (
            "THINKING", "PROCESSING", "SPEAKING",
        )
        speed = 2.4 if self.user_speaking else (1.8 if active else 0.7)
        for i in range(3):
            self._rings[i] = (self._rings[i] + speed * (1 if i != 1 else -1)) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        fw = min(w, h)
        accent = QColor(T.CHAT_ASSIST_ACCENT if not self.muted else T.RED)
        active = self.speaking or self.user_speaking or self.state in (
            "THINKING", "PROCESSING", "SPEAKING",
        )
        pulse = 1.0 + (0.06 if active else 0.0) + min(0.1, self._smooth_voice * 0.1)

        p.fillRect(self.rect(), QColor(T.CHAT_BG))
        for i, (r_frac, alpha) in enumerate(
            ((0.46, 40), (0.38, 65), (0.30, 90), (0.22, 120))
        ):
            rr = fw * r_frac * pulse
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))

        for idx, (r_frac, arc_len) in enumerate(((0.42, 100), (0.34, 72), (0.26, 48))):
            ring_r = fw * r_frac
            a_val = 200 - idx * 45
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), a_val), 1.8))
            rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            p.drawArc(rect, int(self._rings[idx] * 16), int(arc_len * 16))

        p.setPen(QPen(accent, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - fw * 0.13, cy - fw * 0.13, fw * 0.26, fw * 0.26))

        font = QFont(T.CHAT_FONT, max(6, int(fw * 0.10)), QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 150)
        p.setFont(font)
        p.setPen(QPen(accent))
        p.drawText(
            QRectF(cx - fw * 0.42, cy - fw * 0.10, fw * 0.84, fw * 0.20),
            Qt.AlignmentFlag.AlignCenter,
            "A.U.R.A",
        )


class _ChatHudHeader(QWidget):
    """Compact HUD orb pinned to the top-right of the chat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orb = _JarvisChatOrb(76, self)
        self.setStyleSheet(f"background: {T.CHAT_BG}; border: none;")
        self.setFixedHeight(92)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.CHAT_SIDE_PAD, 8, T.CHAT_SIDE_PAD, 8)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

    def orb_widget(self) -> _JarvisChatOrb:
        return self._orb

    def set_compact(self, _compact: bool) -> None:
        return


class _ChatAvatar(QWidget):
    """Lens-style assistant avatar from the screenshot mock."""

    def __init__(self, role: str = "assistant", parent=None):
        super().__init__(parent)
        self._role = role
        self.setFixedSize(22, 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(T.CHAT_ASSIST_ACCENT)
        if self._role == "user":
            p.setPen(QPen(QColor(T.CHAT_TEXT_DIM), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(2, 2, 18, 18)
            return
        p.setPen(QPen(accent, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2.5, 2.5, 17, 17))
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 90), 1.0))
        p.drawEllipse(QRectF(5.5, 5.5, 11, 11))
        p.setBrush(QBrush(accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(8.5, 8.5, 5, 5))


class _ChatEmptyHero(QWidget):
    """Center greeting when the thread is empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 48, 24, 24)
        lay.setSpacing(12)
        lay.addStretch(1)
        greet = QLabel("Yo, I'm here. What are we doing?")
        greet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        greet.setFont(QFont(T.CHAT_FONT, 22, QFont.Weight.DemiBold))
        greet.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent;")
        greet.setWordWrap(True)
        lay.addWidget(greet)
        lay.addStretch(2)


class ConversationView(QWidget):
    """Screenshot-style message feed."""

    messages_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.CHAT_BG};")
        self._stream_view: _AutoText | None = None
        self._stream_text = ""
        self._message_count = 0
        self._stick_to_bottom = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {T.CHAT_BG}; border: none; }}"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,0.12); border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._feed_host = QWidget()
        self._feed_host.setStyleSheet(f"background: {T.CHAT_BG};")
        self._feed = QVBoxLayout(self._feed_host)
        self._feed.setContentsMargins(T.CHAT_SIDE_PAD, 8, T.CHAT_SIDE_PAD, 24)
        self._feed.setSpacing(T.CHAT_MSG_SPACING)
        self._feed.addStretch(1)
        self._scroll.setWidget(self._feed_host)
        root.addWidget(self._scroll, stretch=1)

        scroll_bar = self._scroll.verticalScrollBar()
        scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
        scroll_bar.valueChanged.connect(self._on_scroll_value_changed)

        self._status = QLabel("")
        self._status.setFont(QFont(T.CHAT_FONT, 11))
        self._status.setStyleSheet(
            f"color: {T.CHAT_ASSIST_ACCENT}; background: {T.CHAT_BG}; padding: 6px 24px;"
        )
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setVisible(False)
        root.addWidget(self._status)

    def _insert(self, widget: QWidget):
        idx = max(0, self._feed.count() - 1)
        self._feed.insertWidget(idx, widget)
        self._message_count += 1
        self.messages_changed.emit(True)
        QTimer.singleShot(0, lambda: self._scroll_bottom(force=True))

    def _on_scroll_range_changed(self, _min: int, max_val: int) -> None:
        if self._stick_to_bottom and max_val > 0:
            self._scroll_bottom()

    def _on_scroll_value_changed(self, value: int) -> None:
        bar = self._scroll.verticalScrollBar()
        self._stick_to_bottom = value >= bar.maximum() - 64

    def _scroll_bottom(self, force: bool = False) -> None:
        if force:
            self._stick_to_bottom = True
        if not self._stick_to_bottom:
            return
        bar = self._scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        bar.setValue(bar.maximum())
        QTimer.singleShot(50, lambda: bar.setValue(bar.maximum()))

    def has_messages(self) -> bool:
        return self._message_count > 0

    @staticmethod
    def _chat_html(text: str) -> str:
        html_text = markdown_to_html(text)
        for old, new in (
            ("#8ffcff", "#e5e7eb"),
            ("#d8f8ff", "#f3f4f6"),
            ("color:#00d4ff", "color:#00d1ff"),
        ):
            html_text = html_text.replace(old, new)
        return html_text

    def _track_body_scroll(self, body: _AutoText) -> None:
        try:
            body.document().documentLayout().documentSizeChanged.connect(
                lambda *_: self._scroll_bottom()
            )
        except Exception:
            pass

    def _bubble(self, role: str) -> _AutoText:
        ts = datetime.now().strftime("%H:%M")

        if role == "user":
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            outer = QHBoxLayout(wrap)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            outer.addStretch(1)

            card = QFrame()
            card.setObjectName("chatUserCard")
            card.setMaximumWidth(T.CHAT_USER_MAX_W)
            card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            card.setStyleSheet(
                f"QFrame#chatUserCard {{ background: {T.CHAT_BUBBLE}; border: none; "
                f"border-radius: {T.CHAT_BUBBLE_RADIUS}px; }}"
            )
            bl = QHBoxLayout(card)
            bl.setContentsMargins(18, 14, 16, 14)
            bl.setSpacing(12)

            body = _AutoText()
            body.setFont(QFont(T.CHAT_FONT, 15))
            body.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent;")
            bl.addWidget(body, stretch=1)

            meta = QVBoxLayout()
            meta.setContentsMargins(0, 0, 0, 0)
            meta.setSpacing(2)
            time = QLabel(ts)
            time.setFont(QFont(T.CHAT_FONT, 10))
            time.setAlignment(Qt.AlignmentFlag.AlignRight)
            time.setStyleSheet(f"color: {T.CHAT_TEXT_DIM}; background: transparent;")
            meta.addWidget(time)
            tick = QLabel("✓")
            tick.setFont(QFont(T.CHAT_FONT, 11, QFont.Weight.Bold))
            tick.setAlignment(Qt.AlignmentFlag.AlignRight)
            tick.setStyleSheet(f"color: {T.CHAT_ASSIST_ACCENT}; background: transparent;")
            meta.addWidget(tick)
            bl.addLayout(meta)

            outer.addWidget(card, stretch=0)
            self._insert(wrap)
            return body

        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("chatAssistCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card.setStyleSheet(
            f"QFrame#chatAssistCard {{ background: {T.CHAT_BUBBLE}; "
            f"border: none; border-radius: {T.CHAT_BUBBLE_RADIUS}px; }}"
        )
        col = QVBoxLayout(card)
        col.setContentsMargins(18, 16, 18, 18)
        col.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_ChatAvatar("assistant"), alignment=Qt.AlignmentFlag.AlignTop)
        name = QLabel("A.U.R.A")
        name.setFont(QFont(T.CHAT_FONT, 13, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {T.CHAT_ASSIST_ACCENT}; background: transparent;")
        head.addWidget(name, alignment=Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        time = QLabel(ts)
        time.setFont(QFont(T.CHAT_FONT, 10))
        time.setStyleSheet(f"color: {T.CHAT_TEXT_DIM}; background: transparent;")
        head.addWidget(time, alignment=Qt.AlignmentFlag.AlignTop)
        col.addLayout(head)

        body = _AutoText()
        body.setFont(QFont(T.CHAT_FONT, 15))
        body.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent;")
        self._track_body_scroll(body)
        col.addWidget(body)
        outer.addWidget(card)
        self._insert(wrap)
        return body

    def add_user(self, text: str):
        self._bubble("user").setHtml(self._chat_html(text))

    def add_assistant(self, text: str):
        self._bubble("assistant").setHtml(self._chat_html(text))

    def add_activity(self, label: str, detail: str = ""):
        self._insert(_ActivityItem(label, detail))

    def add_artifact_card(self, kind: str, title: str, payload: str = "", path: str = ""):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T.BG_ELEVATED}; border: 1px solid {T.BORDER}; border-radius: 12px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        icon = {"web": "🌐", "code": "</>", "text": "▤"}.get(kind, "▤")
        tag = QLabel(f"{icon}  {title or kind.title()}")
        tag.setFont(QFont(T.CHAT_FONT, 11, QFont.Weight.DemiBold))
        tag.setStyleSheet(f"color: {T.CHAT_ASSIST_ACCENT}; background: transparent;")
        head.addWidget(tag)
        head.addStretch()
        if path:
            open_btn = QPushButton("Open")
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.setFont(QFont(T.CHAT_FONT, 10))
            open_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {T.CHAT_TEXT_DIM}; "
                f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 2px 10px; }}"
            )
            open_btn.clicked.connect(lambda _, p=path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(p) if not str(p).startswith("http") else QUrl(p)
            ))
            head.addWidget(open_btn)
        lay.addLayout(head)

        if kind == "web" and _WEB_ENGINE and (path or payload):
            view = QWebEngineView()
            view.setFixedHeight(280)
            try:
                if path and str(path).startswith("http"):
                    view.setUrl(QUrl(path))
                elif path:
                    view.setUrl(QUrl.fromLocalFile(path))
                else:
                    view.setHtml(payload)
            except Exception:
                pass
            lay.addWidget(view)
        else:
            body = _AutoText()
            body.setFont(QFont(T.CHAT_FONT, 13))
            if kind == "code":
                lang = (Path(path).suffix.lstrip(".") if path else "") or "code"
                body.setHtml(markdown_to_html(f"```{lang}\n{payload}\n```"))
            else:
                body.setHtml(markdown_to_html(payload))
            lay.addWidget(body)
        self._insert(frame)

    def stream_delta(self, delta: str):
        if self._stream_view is None:
            self._stream_view = self._bubble("assistant")
            self._stream_text = ""
        self._stream_text += delta
        self._stream_view.setHtml(self._chat_html(self._stream_text))
        self._scroll_bottom()

    def stream_end(self, full_text: str = ""):
        if self._stream_view is not None:
            final = full_text.strip() or self._stream_text
            self._stream_view.setHtml(self._chat_html(final))
            self._stream_view = None
            self._stream_text = ""
        elif full_text.strip():
            self.add_assistant(full_text)
        self.clear_live_activity()
        self._scroll_bottom(force=True)

    def set_live_activity(self, label: str):
        self._status.setText(f"{label}…")
        self._status.setVisible(True)

    def clear_live_activity(self):
        self._status.setVisible(False)
        self._status.setText("")

    def clear(self):
        self._stream_view = None
        self._stream_text = ""
        self._message_count = 0
        while self._feed.count() > 1:
            item = self._feed.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.messages_changed.emit(False)
        self.clear_live_activity()
        bar = self._scroll.verticalScrollBar()
        bar.setValue(0)

    def load(self, messages: list[dict], artifacts: list[dict] | None = None):
        self.clear()
        art_by_id = {a.get("id"): a for a in (artifacts or [])}
        for msg in messages or []:
            role = msg.get("role", "")
            content = msg.get("content", "")
            meta = msg.get("meta", {}) or {}
            if role == "user":
                self.add_user(content)
            elif role == "assistant":
                self.add_assistant(content)
            elif role in ("activity", "tool"):
                self.add_activity(meta.get("label") or content or "Activity", meta.get("detail", ""))
            elif role == "artifact":
                art = art_by_id.get(meta.get("artifact_id")) or {}
                self.add_artifact_card(
                    art.get("kind") or meta.get("kind", "text"),
                    art.get("title") or meta.get("title", "Output"),
                    art.get("payload", ""),
                    art.get("path") or meta.get("path", ""),
                )
        self._scroll_bottom(force=True)


class _ChatBarIconButton(QPushButton):
    def __init__(self, kind: str, size: int = 32, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._muted = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.06); }"
        )

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(T.CHAT_BAR_ICON), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        if self._kind == "attach":
            p.drawArc(int(cx - 6), int(cy - 8), 12, 12, 30 * 16, 300 * 16)
            p.drawLine(int(cx - 3), int(cy + 2), int(cx - 3), int(cy + 7))
            p.drawLine(int(cx + 3), int(cy + 2), int(cx + 3), int(cy + 7))
        elif self._kind == "plus":
            p.drawLine(int(cx - 6), int(cy), int(cx + 6), int(cy))
            p.drawLine(int(cx), int(cy - 6), int(cx), int(cy + 6))
        elif self._kind == "mic":
            color = QColor(T.RED) if self._muted else QColor(T.CHAT_BAR_ICON)
            pen.setColor(color)
            p.setPen(pen)
            p.drawRoundedRect(int(cx - 4), int(cy - 9), 8, 12, 4, 4)
            p.drawArc(int(cx - 7), int(cy - 1), 14, 10, 0, -180 * 16)
            p.drawLine(int(cx), int(cy + 9), int(cx), int(cy + 12))
            if self._muted:
                p.drawLine(int(cx - 7), int(cy - 7), int(cx + 7), int(cy + 7))

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self.update()


class _ChatSendButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background: {T.CHAT_ASSIST_ACCENT}; border: none; border-radius: 18px; }}"
            f"QPushButton:hover {{ background: #33eeff; }}"
            f"QPushButton:pressed {{ background: #00c4db; }}"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#ffffff"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        p.drawLine(int(cx - 4), int(cy + 3), int(cx + 4), int(cy - 5))
        p.drawLine(int(cx + 4), int(cy - 5), int(cx + 1), int(cy - 5))
        p.drawLine(int(cx + 4), int(cy - 5), int(cx + 4), int(cy - 2))


class _AttachmentChip(QFrame):
    """Small thumbnail chip for one attached image, with a remove button."""

    removed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; border-radius: 10px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(6)

        thumb = QLabel()
        thumb.setFixedSize(34, 34)
        thumb.setStyleSheet("border: none; border-radius: 6px; background: transparent;")
        try:
            from PyQt6.QtGui import QPixmap

            pix = QPixmap(path)
            if not pix.isNull():
                thumb.setPixmap(
                    pix.scaled(
                        34, 34,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except Exception:
            pass
        lay.addWidget(thumb)

        name = QLabel(Path(path).name)
        name.setFont(QFont(T.CHAT_FONT, 10))
        name.setStyleSheet(f"color: {T.CHAT_TEXT}; border: none; background: transparent;")
        name.setMaximumWidth(160)
        lay.addWidget(name)

        close = QPushButton("✕")
        close.setFixedSize(18, 18)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8b98a8; font-size: 11px; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        close.clicked.connect(lambda: self.removed.emit(self._path))
        lay.addWidget(close)


class CenterInputBar(QWidget):
    submitted = pyqtSignal(str)
    files_submitted = pyqtSignal(str, list)
    plan_requested = pyqtSignal()
    mute_clicked = pyqtSignal()

    _IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
    _MAX_ATTACHMENTS = 4

    def __init__(self, providers: list[str], parent=None):
        super().__init__(parent)
        self._providers = providers or ["Live Voice (Gemini)"]
        self._attachments: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Attachment chips strip (hidden until a photo is added).
        self._chips_host = QWidget()
        chips_lay = QHBoxLayout(self._chips_host)
        chips_lay.setContentsMargins(T.CHAT_SIDE_PAD + 8, 0, T.CHAT_SIDE_PAD, 8)
        chips_lay.setSpacing(8)
        chips_lay.addStretch()
        self._chips_lay = chips_lay
        self._chips_host.hide()
        root.addWidget(self._chips_host)

        host = QWidget()
        host_lay = QHBoxLayout(host)
        host_lay.setContentsMargins(T.CHAT_SIDE_PAD, 0, T.CHAT_SIDE_PAD, 20)
        host_lay.setSpacing(0)

        self._pill = QFrame()
        self._pill.setObjectName("chatInputPill")
        self._pill.setFixedHeight(T.CHAT_BAR_HEIGHT)
        self._pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._pill.setStyleSheet(
            f"QFrame#chatInputPill {{ background: {T.CHAT_BAR_BG}; border: none; border-radius: 26px; }}"
        )

        row = QHBoxLayout(self._pill)
        row.setContentsMargins(18, 0, 10, 0)
        row.setSpacing(4)

        self._attach = _ChatBarIconButton("plus", 32)
        self._attach.clicked.connect(self._show_extras_menu)
        row.addWidget(self._attach)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message A.U.R.A...")
        self._input.setFont(QFont(T.CHAT_FONT, 15))
        self._input.setFrame(False)
        self._input.setMinimumHeight(36)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {T.CHAT_BAR_TEXT}; border: none; padding: 0 8px;
            }}
            QLineEdit::placeholder {{ color: {T.CHAT_BAR_PLACEHOLDER}; }}
        """)
        self._input.returnPressed.connect(self._submit)
        row.addWidget(self._input, stretch=1)

        self._mic = _ChatBarIconButton("mic", 32)
        self._mic.clicked.connect(self.mute_clicked.emit)
        row.addWidget(self._mic)

        self._send = _ChatSendButton()
        self._send.clicked.connect(self._submit)
        row.addWidget(self._send)

        host_lay.addWidget(self._pill, stretch=1)
        root.addWidget(host)

        self._provider_combo = QComboBox(self)
        self._provider_combo.addItems(self._providers)
        self._provider_combo.hide()

    _MENU_QSS = f"""
        QMenu {{
            background: {T.BG_ELEVATED};
            color: {T.CHAT_TEXT};
            border: 1px solid {T.BORDER_HI};
            border-radius: 12px;
            padding: 8px 6px;
            font-size: 13px;
        }}
        QMenu::item {{
            padding: 9px 26px 9px 12px;
            border-radius: 8px;
            margin: 1px 4px;
        }}
        QMenu::item:selected {{ background: rgba(64, 224, 208, 0.12); }}
        QMenu::item:disabled {{ color: {T.TEXT_DIM}; }}
        QMenu::separator {{
            height: 1px;
            background: {T.BORDER};
            margin: 6px 10px;
        }}
        QMenu::icon {{ padding-left: 10px; }}
        QMenu::right-arrow {{ width: 12px; height: 12px; }}
    """

    @staticmethod
    def _menu_icon(kind: str, color: str = T.TEXT_MED) -> "QIcon":
        """Small line icon for the plus-menu, painted in theme color."""
        from PyQt6.QtGui import QIcon, QPixmap

        logical = 18
        pm = QPixmap(logical * 2, logical * 2)
        pm.setDevicePixelRatio(2.0)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = logical / 24.0

        def P(x, y):
            return QPointF(x * s, y * s)

        def R(x, y, w, h):
            return QRectF(x * s, y * s, w * s, h * s)

        if kind == "image":
            p.drawRoundedRect(R(3.5, 5, 17, 14), 3 * s, 3 * s)
            p.drawEllipse(R(7, 8, 3.4, 3.4))
            p.drawPolyline(QPolygonF([P(5, 17), P(11, 11.5), P(15, 15), P(17.5, 12.8), P(20, 15.4)]))
        elif kind == "plan":
            for y in (7, 12, 17):
                p.drawEllipse(R(4.4, y - 0.9, 1.8, 1.8))
                p.drawLine(P(9.5, y), P(20, y))
        elif kind == "models":
            p.drawPolygon(QPolygonF([P(12, 3.5), P(20, 8), P(20, 16), P(12, 20.5), P(4, 16), P(4, 8)]))
            p.drawLine(P(4, 8), P(12, 12.4))
            p.drawLine(P(20, 8), P(12, 12.4))
            p.drawLine(P(12, 12.4), P(12, 20.5))
        p.end()
        return QIcon(pm)

    def _style_cursor_menu(self, menu: QMenu) -> None:
        menu.setStyleSheet(self._MENU_QSS)
        menu.setWindowFlags(
            menu.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def _show_extras_menu(self):
        menu = QMenu(self)
        self._style_cursor_menu(menu)

        header = menu.addAction("Add photos, models, tools…")
        header.setEnabled(False)
        menu.addSeparator()

        attach_action = menu.addAction(self._menu_icon("image"), "Image")
        attach_action.triggered.connect(self._pick_photos)

        plan_action = menu.addAction(self._menu_icon("plan"), "Plan mode")
        plan_action.triggered.connect(self.plan_requested.emit)

        menu.addSeparator()

        prov_menu = menu.addMenu(self._menu_icon("models"), "Models")
        self._style_cursor_menu(prov_menu)
        for item in self._providers:
            action = prov_menu.addAction(item)
            action.triggered.connect(lambda _, t=item: self._provider_combo.setCurrentText(t))

        menu.exec(self._attach.mapToGlobal(QPoint(0, -8)))

    def _pick_photos(self):
        from PyQt6.QtWidgets import QFileDialog

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach photos", str(Path.home()), self._IMAGE_FILTER
        )
        for p in paths:
            self.add_attachment(p)

    def add_attachment(self, path: str) -> bool:
        """Add one image to the pending attachments strip. Returns True if added."""
        path = str(path or "").strip()
        if not path or path in self._attachments:
            return False
        if len(self._attachments) >= self._MAX_ATTACHMENTS:
            return False
        if not Path(path).is_file():
            return False
        self._attachments.append(path)
        chip = _AttachmentChip(path)
        chip.removed.connect(self._remove_attachment)
        # Keep the trailing stretch last.
        self._chips_lay.insertWidget(self._chips_lay.count() - 1, chip)
        self._chips_host.show()
        return True

    def _remove_attachment(self, path: str) -> None:
        self._attachments = [p for p in self._attachments if p != path]
        for i in range(self._chips_lay.count() - 1, -1, -1):
            w = self._chips_lay.itemAt(i).widget()
            if isinstance(w, _AttachmentChip) and w._path == path:
                w.setParent(None)
                w.deleteLater()
        if not self._attachments:
            self._chips_host.hide()

    def _clear_attachments(self) -> None:
        for p in list(self._attachments):
            self._remove_attachment(p)

    def _submit(self):
        text = self._input.text().strip()
        files = list(self._attachments)
        if not text and not files:
            return
        self._input.clear()
        if files:
            self._clear_attachments()
            self.files_submitted.emit(text or "What is in this image?", files)
        else:
            self.submitted.emit(text)

    def get_provider(self) -> str:
        text = self._provider_combo.currentText().strip()
        low = text.lower()
        if "live voice" in low or "claude" in low or "opus" in low:
            return "auto"
        return text.split(" — ")[0].strip().lower()

    def set_muted(self, muted: bool) -> None:
        self._mic.set_muted(bool(muted))


class ChatCenterPane(QWidget):
    """Screenshot-matched center workspace: header, HUD, chat feed, input bar."""

    submitted = pyqtSignal(str)
    files_submitted = pyqtSignal(str, list)
    plan_requested = pyqtSignal()
    mute_clicked = pyqtSignal()

    def __init__(self, providers: list[str], dashboard_hud: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.CHAT_BG};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._top = QWidget()
        self._top.setFixedHeight(44)
        self._top.setStyleSheet(f"background: {T.BG}; border: none;")
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(20, 0, 20, 0)
        self._online_label = QLabel("●  SYSTEM ONLINE")
        self._online_label.setFont(QFont(T.CHAT_FONT, 11, QFont.Weight.Medium))
        self._online_label.setStyleSheet(f"color: {T.SB_STATUS_ON}; background: transparent;")
        tl.addWidget(self._online_label)
        tl.addStretch()

        self.model_combo = QComboBox()
        model_items = providers or ["Live Voice (Gemini)", "Auto Router"]
        self.model_combo.addItems(model_items)
        self.model_combo.setFixedHeight(30)
        self.model_combo.setMinimumWidth(140)
        self.model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background: {T.BG_CARD}; color: {T.CHAT_TEXT};
                border: 1px solid {T.BORDER}; border-radius: 15px; padding: 0 14px;
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {T.BG_ELEVATED}; color: {T.CHAT_TEXT};
                selection-background-color: rgba(64,224,208,0.15);
            }}
        """)
        tl.addWidget(self.model_combo)
        lay.addWidget(self._top)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, stretch=1)

        # Dashboard — same HudCanvas look as Chat, with voice-reactive motion
        dash_hud = dashboard_hud if dashboard_hud is not None else hud_widget
        self._dashboard = DashboardHeroView(dash_hud)
        self._dashboard.submitted.connect(self.submitted.emit)
        self._dashboard.mute_clicked.connect(self.mute_clicked.emit)
        self._stack.addWidget(self._dashboard)

        # Chat — HUD top-right + screenshot feed + input
        self._chat_page = QWidget()
        self._chat_page.setStyleSheet(f"background: {T.CHAT_BG};")
        chat_lay = QVBoxLayout(self._chat_page)
        chat_lay.setContentsMargins(0, 0, 0, 0)
        chat_lay.setSpacing(0)

        self._hud_header = _ChatHudHeader()
        chat_lay.addWidget(self._hud_header, stretch=0)

        self._chat_body = QStackedWidget()
        self._chat_body.setStyleSheet(f"background: {T.CHAT_BG};")
        self._empty_hero = _ChatEmptyHero()
        self._conv = ConversationView()
        self._conv.messages_changed.connect(self._on_messages_changed)
        self._chat_body.addWidget(self._empty_hero)
        self._chat_body.addWidget(self._conv)
        chat_lay.addWidget(self._chat_body, stretch=1)

        self._input_bar = CenterInputBar(providers)
        self._input_bar.submitted.connect(self.submitted.emit)
        self._input_bar.files_submitted.connect(self.files_submitted.emit)
        self._input_bar.plan_requested.connect(self.plan_requested.emit)
        self._input_bar.mute_clicked.connect(self.mute_clicked.emit)
        chat_lay.addWidget(self._input_bar)

        self._stack.addWidget(self._chat_page)
        self._stack.setCurrentIndex(0)

        self._hud = self._hud_header.orb_widget()
        self._hud_host = QWidget()
        self._hud_host.hide()

        self._on_messages_changed(self._conv.has_messages())

    def chat_orb(self) -> _JarvisChatOrb:
        return self._hud

    @property
    def conv(self) -> ConversationView:
        return self._conv

    @property
    def input_bar(self) -> CenterInputBar:
        return self._input_bar

    def set_hud_compact(self, compact: bool) -> None:
        self._hud_header.set_compact(compact)

    def set_view_mode(self, mode: str) -> None:
        """Dashboard = hero HUD; chat = screenshot conversation layout."""
        dashboard = mode == "dashboard"
        self._top.setVisible(dashboard)
        self._stack.setCurrentIndex(0 if dashboard else 1)

    def set_muted(self, muted: bool) -> None:
        self._input_bar.set_muted(muted)
        self._dashboard.set_muted(muted)
        self._hud.muted = bool(muted)

    def set_speaking(self, speaking: bool) -> None:
        self._dashboard.set_speaking(speaking)
        self._hud.speaking = bool(speaking)

    def set_voice_level(self, level: float) -> None:
        self._dashboard.set_voice_level(level)
        self._hud.set_voice_level(level)

    def set_state(self, state: str) -> None:
        self._hud.state = state

    def _on_messages_changed(self, has_messages: bool) -> None:
        self._chat_body.setCurrentIndex(1 if has_messages else 0)

# AvatarCircle
# _open_permissions
