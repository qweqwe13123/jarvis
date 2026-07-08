"""JARVIS workspace UI components — screenshot-matched design."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QUrl, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QDesktopServices, QPainter, QPen, QColor, QPolygonF, QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from jarvis_ui.markdown_utils import markdown_to_html
from jarvis_ui import theme as T

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
            title = "You" if role == "user" else "JARVIS"
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
            hdr = QLabel(entry.get("title", "JARVIS"))
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
        tag = QLabel("YOU" if is_user else "JARVIS")
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
        self.setFixedHeight(40 if subtitle else 34)
        self._apply_style(active)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.setSpacing(8)

        ic = QLabel(icon)
        ic.setFont(QFont(T.FONT_UI, 9))
        ic.setStyleSheet(f"color: {T.CYAN if active else T.TEXT_DIM}; background: transparent; border: none;")
        ic.setFixedWidth(16)
        lay.addWidget(ic)

        textcol = QVBoxLayout()
        textcol.setSpacing(0)
        name = QLabel(title)
        name.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold if active else QFont.Weight.Normal))
        name.setStyleSheet(f"color: {T.WHITE if active else T.TEXT_MED}; background: transparent; border: none;")
        textcol.addWidget(name)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(QFont(T.FONT_UI, 7))
            sub.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
            textcol.addWidget(sub)
        lay.addLayout(textcol, stretch=1)

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
                    background: rgba(0, 209, 255, 0.12);
                    border: 1px solid rgba(0, 209, 255, 0.30);
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                _SideRow {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
                _SideRow:hover {{ background: rgba(255,255,255,0.04); border: 1px solid {T.BORDER}; }}
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


class NavSidebar(QWidget):
    """Screenshot-matched left navigation: agents, skills, and monetization tools."""

    _AGENTS = (
        ("general", "General Chat", "chat"),
        ("website", "Website Builder", "globe"),
        ("code", "Code Assistant", "code"),
        ("automation", "Automation", "automation"),
        ("writer", "Writer", "writer"),
        ("researcher", "Researcher", "researcher"),
        ("designer", "Designer", "designer"),
    )
    _MONEY = (
        ("maps_prospector", "Maps Prospector", "maps", "$"),
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.BG_PANEL}; border-right: 1px solid {T.BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(0)

        new_btn = _BracketButton("NEW SESSION", "⌘N")
        new_btn.clicked.connect(self.new_chat.emit)
        lay.addWidget(new_btn)
        lay.addSpacing(22)

        lay.addWidget(self._section_label("AGENTS · SKILLS", T.CYAN_DIM))
        lay.addSpacing(8)

        self._agent_rows: dict[str, _AgentRow] = {}
        self._active_agent = "general"
        for key, label, icon in self._AGENTS:
            row = _AgentRow(
                key, label, icon,
                active=(key == "general"),
                active_dot=(key == "general"),
            )
            row.clicked.connect(self._on_agent)
            self._agent_rows[key] = row
            lay.addWidget(row)

        lay.addSpacing(22)
        if self._MONEY:
            lay.addWidget(self._section_label("MAKE MONEY", "#a84858"))
            lay.addSpacing(8)

            for key, label, icon, trail in self._MONEY:
                row = _AgentRow(
                    key, label, icon,
                    trailing=trail,
                    trailing_color=T.TEXT_DIM,
                )
                row.clicked.connect(self._on_agent)
                self._agent_rows[key] = row
                lay.addWidget(row)

        lay.addStretch()
        lay.addWidget(self._section_label("SYSTEM", T.CYAN_DIM))
        lay.addSpacing(6)
        settings = _AgentRow("settings", "Settings", "settings")
        settings.clicked.connect(lambda *_: self.settings_requested.emit())
        lay.addWidget(settings)

        self._cached_chats: list[dict] = []
        self._active_chat_id: str | None = None

    @staticmethod
    def _section_label(text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(_spaced_font(T.FONT_UI, 8, 2.8, bold=True))
        lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        return lbl

    def _on_agent(self, key: str):
        if key != self._active_agent:
            self._agent_rows[self._active_agent].set_active(False)
            self._active_agent = key
            self._agent_rows[key].set_active(True)
        self.agent_selected.emit(key)

    def refresh(self, workspaces: list[dict], chats: list[dict],
                active_ws_id: str = "", active_chat_id: str | None = None):
        self._cached_chats = list(chats)
        self._active_chat_id = active_chat_id

    def refresh_automations(self, automations: list[dict]):
        pass


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


class ConversationView(QWidget):
    """Single continuous conversation feed (ChatGPT / Cursor style).

    Replaces the old multi-tab response-card system: every user message,
    assistant reply, inline activity/tool log and generated artifact is appended
    to ONE chronological vertically-scrolling thread with auto-scroll, markdown,
    syntax-highlighted code and streaming support.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream_view: _AutoText | None = None
        self._stream_text = ""
        self._artifact_open = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("CONVERSATION")
        title.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 1px;")
        header.addWidget(title)
        header.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFont(QFont(T.FONT_UI, 8))
        self._clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {T.TEXT_DIM}; "
            f"border: 1px solid {T.BORDER}; border-radius: 6px; padding: 3px 10px; }}"
            f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
        )
        self._clear_btn.clicked.connect(self.clear)
        header.addWidget(self._clear_btn)
        root.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; }}"
            f"QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._feed = QVBoxLayout(host)
        self._feed.setContentsMargins(2, 2, 8, 2)
        self._feed.setSpacing(10)
        self._feed.addStretch()
        self._scroll.setWidget(host)
        root.addWidget(self._scroll, stretch=1)

        self._empty = QLabel("Start talking or type below — the full conversation appears here.")
        self._empty.setWordWrap(True)
        self._empty.setFont(QFont(T.FONT_UI, 9))
        self._empty.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        self._feed.insertWidget(0, self._empty)

        self._status = QLabel("")
        self._status.setFont(QFont(T.FONT_UI, 9))
        self._status.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        self._status.setVisible(False)
        root.addWidget(self._status)

    # ----- feed helpers ----------------------------------------------------
    def _insert(self, widget: QWidget):
        if self._empty.isVisible():
            self._empty.setVisible(False)
        self._feed.insertWidget(self._feed.count() - 1, widget)
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _bubble(self, role: str, who: str, accent: str) -> _AutoText:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; "
            f"border-left: 2px solid {accent}; border-radius: 10px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(4)
        tag = QLabel(who)
        tag.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {accent}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(tag)
        body = _AutoText()
        body.setFont(QFont(T.FONT_UI, 10))
        lay.addWidget(body)
        self._insert(frame)
        return body

    # ----- public API ------------------------------------------------------
    def add_user(self, text: str):
        body = self._bubble("user", "YOU", T.GREEN)
        body.setHtml(markdown_to_html(text))

    def add_assistant(self, text: str):
        body = self._bubble("assistant", "JARVIS", T.CYAN)
        body.setHtml(markdown_to_html(text))

    def add_activity(self, label: str, detail: str = ""):
        self._insert(_ActivityItem(label, detail))

    def add_artifact_card(self, kind: str, title: str, payload: str = "", path: str = ""):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER_HI}; "
            f"border-radius: 10px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        icon = {"web": "🌐", "code": "</>", "text": "▤"}.get(kind, "▤")
        tag = QLabel(f"{icon}  {title or kind.title()}")
        tag.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        head.addWidget(tag)
        head.addStretch()
        if path:
            open_btn = QPushButton("Open")
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.setFont(QFont(T.FONT_UI, 8))
            open_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; "
                f"border: 1px solid {T.BORDER}; border-radius: 6px; padding: 2px 10px; }}"
                f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
            )
            open_btn.clicked.connect(lambda _, p=path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(p) if not str(p).startswith("http") else QUrl(p)
            ))
            head.addWidget(open_btn)
        lay.addLayout(head)

        if kind == "web" and _WEB_ENGINE and (path or payload):
            view = QWebEngineView()
            view.setFixedHeight(320)
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
            body.setFont(QFont(T.FONT_UI, 10))
            if kind == "code":
                lang = (Path(path).suffix.lstrip(".") if path else "") or "code"
                body.setHtml(markdown_to_html(f"```{lang}\n{payload}\n```"))
            else:
                body.setHtml(markdown_to_html(payload))
            lay.addWidget(body)

        self._insert(frame)

    # ----- streaming -------------------------------------------------------
    def stream_delta(self, delta: str):
        if self._stream_view is None:
            self._stream_view = self._bubble("assistant", "JARVIS", T.CYAN)
            self._stream_text = ""
        self._stream_text += delta
        self._stream_view.setHtml(markdown_to_html(self._stream_text))
        QTimer.singleShot(0, self._scroll_bottom)

    def stream_end(self, full_text: str = ""):
        if self._stream_view is not None:
            final = full_text.strip() or self._stream_text
            self._stream_view.setHtml(markdown_to_html(final))
            self._stream_view = None
            self._stream_text = ""
        elif full_text.strip():
            self.add_assistant(full_text)
        self.clear_live_activity()

    # ----- transient status (Thinking… / Running…) -------------------------
    def set_live_activity(self, label: str):
        self._status.setText(f"●  {label}…")
        self._status.setVisible(True)

    def clear_live_activity(self):
        self._status.setVisible(False)
        self._status.setText("")

    # ----- session restore -------------------------------------------------
    def clear(self):
        self._stream_view = None
        self._stream_text = ""
        while self._feed.count() > 1:  # keep trailing stretch
            item = self._feed.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        if self._feed.indexOf(self._empty) == -1:
            self._feed.insertWidget(0, self._empty)
        self._empty.setVisible(True)
        self.clear_live_activity()

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
                self.add_activity(meta.get("label") or content or "Activity",
                                  meta.get("detail", ""))
            elif role == "artifact":
                art = art_by_id.get(meta.get("artifact_id")) or {}
                self.add_artifact_card(
                    art.get("kind") or meta.get("kind", "text"),
                    art.get("title") or meta.get("title", "Output"),
                    art.get("payload", ""),
                    art.get("path") or meta.get("path", ""),
                )
        QTimer.singleShot(0, self._scroll_bottom)


class CenterInputBar(QWidget):
    submitted = pyqtSignal(str)
    plan_requested = pyqtSignal()

    def __init__(self, providers: list[str], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 0, 28, 14)
        lay.setSpacing(7)

        input_box = QFrame()
        input_box.setStyleSheet(f"""
            QFrame {{
                background: {T.BG_CARD};
                border: 1px solid {T.BORDER_HI};
                border-radius: 14px;
            }}
        """)
        ib_lay = QVBoxLayout(input_box)
        ib_lay.setContentsMargins(16, 10, 12, 8)
        ib_lay.setSpacing(6)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Напиши или просто скажи, что нужно…")
        self._input.setFont(QFont(T.FONT_UI, 11))
        self._input.setMinimumHeight(46)
        self._input.setMaximumHeight(84)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; color: {T.WHITE};
                border: none; padding: 0;
            }}
            QScrollBar:vertical {{ background: transparent; width: 5px; }}
            QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 2px; }}
        """)
        ib_lay.addWidget(self._input)
        self._input.installEventFilter(self)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        plus = QPushButton("+")
        plus.setFixedSize(26, 26)
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setFont(QFont(T.FONT_UI, 12, QFont.Weight.Bold))
        plus.setStyleSheet(self._chip_style())
        bottom.addWidget(plus)

        self._provider_combo = QComboBox()
        models = providers or ["Live Voice (Gemini)"]
        self._provider_combo.addItems(models)
        self._provider_combo.setFixedHeight(26)
        self._provider_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._provider_combo.setStyleSheet(f"""
            QComboBox {{
                background: {T.BG_PANEL}; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 13px;
                padding: 2px 12px; min-width: 170px; font-size: 11px;
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {T.BG_CARD}; color: {T.WHITE};
                selection-background-color: rgba(0,209,255,0.15);
            }}
        """)
        bottom.addWidget(self._provider_combo)

        plan = QPushButton("✧ Plan")
        plan.setFixedHeight(26)
        plan.setCursor(Qt.CursorShape.PointingHandCursor)
        plan.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        plan.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 13px; padding: 0 12px;
            }}
            QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}
        """)
        plan.clicked.connect(self.plan_requested.emit)
        bottom.addWidget(plan)

        bottom.addStretch()

        send = QPushButton("Send  ↵")
        send.setFixedHeight(28)
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        send.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,209,255,0.14); color: {T.CYAN};
                border: 1px solid {T.CYAN_DIM}; border-radius: 14px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: rgba(0,209,255,0.24); }}
        """)
        send.clicked.connect(self._submit)
        bottom.addWidget(send)
        ib_lay.addLayout(bottom)
        lay.addWidget(input_box)

        hint = QLabel("🎙  Voice is always on · Enter to send · Shift+Enter for a new line")
        hint.setFont(QFont(T.FONT_UI, 7))
        hint.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

    def _chip_style(self) -> str:
        return f"""
            QPushButton {{
                background: {T.BG_PANEL}; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 13px;
            }}
            QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}
        """

    def _submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.submitted.emit(text)

    def get_provider(self) -> str:
        text = self._provider_combo.currentText().strip()
        low = text.lower()
        if "live voice" in low or "claude" in low or "opus" in low:
            return "auto"
        return text.split(" — ")[0].strip().lower()

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._submit()
                    return True
        return super().eventFilter(obj, event)
