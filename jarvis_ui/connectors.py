"""Connectors library — Featured + All integrations (screenshot-matched cards)."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath
from PyQt6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from jarvis_ui import theme as T


# Soft light surface for the connectors library (matches reference screenshot).
_PAGE_BG = "#F4F2EC"
_CARD_BG = "#FFFFFF"
_CARD_BORDER = "#E6E2DA"
_TITLE = "#111827"
_DESC = "#6B7280"
_BADGE = "#9CA3AF"
_PLUS_BORDER = "#D1D5DB"
_PLUS_HOVER = "#F3F4F6"


@dataclass(frozen=True)
class Integration:
    key: str
    name: str
    description: str
    category: str
    brand: str  # icon painter key


FEATURED: list[Integration] = [
    Integration("gmail", "Gmail", "Inbox triage by voice — the assistant that reads sent mail too.", "Email", "gmail"),
    Integration("slack", "Slack", "Catch up on a thread in 10 seconds — across DMs, channels, and links.", "Messaging", "slack"),
    Integration("notion", "Notion", "Notion AI alternative that connects to your inbox, calendar, and Linear too.", "Docs", "notion"),
    Integration("gcal", "Google Calendar", "The meeting prep assistant that remembers what you discussed last time.", "Calendar", "gcal"),
    Integration("linear", "Linear", "Spec to Linear ticket in 5 seconds, from anywhere.", "Project tracking", "linear"),
    Integration("github", "GitHub", "PR review co-pilot that works across the editor, browser, and Linear.", "Code", "github"),
    Integration("figma", "Figma", "Design review AI that knows the PRD, the tickets, and the brand guidelines.", "Design", "figma"),
    Integration("gdrive", "Google Drive", "Google Drive AI assistant — find the doc, summarize it, draft the follow-up", "Files", "gdrive"),
]

ALL_INTEGRATIONS: list[Integration] = [
    Integration("gmail", "Gmail", "Inbox triage by voice — the assistant that reads sent mail too.", "Email", "gmail"),
    Integration("slack", "Slack", "Catch up on a thread in 10 seconds — across DMs, channels, and links.", "Messaging", "slack"),
    Integration("notion", "Notion", "Notion AI alternative that connects to your inbox, calendar, and Linear too.", "Docs", "notion"),
    Integration("gcal", "Google Calendar", "The meeting prep assistant that remembers what you discussed last time.", "Calendar", "gcal"),
    Integration("outlook", "Outlook", "Microsoft 365 AI alternative for people not paying for Copilot.", "Email", "outlook"),
    Integration("gdocs", "Google Docs", "Edit Docs from any app — the writing assistant that lives outside the browser tab.", "Docs", "gdocs"),
    Integration("gsheets", "Google Sheets", "Spreadsheet AI that explains what a cell is doing.", "Spreadsheets", "gsheets"),
    Integration("linear", "Linear", "Spec to Linear ticket in 5 seconds, from anywhere.", "Project tracking", "linear"),
    Integration("github", "GitHub", "PR review co-pilot that works across the editor, browser, and Linear.", "Code", "github"),
    Integration("figma", "Figma", "Design review AI that knows the PRD, the tickets, and the brand guidelines.", "Design", "figma"),
    Integration("pdf", "PDF Reader", "AI PDF reader that works on any PDF, in any app, on Mac or Windows", "Documents", "pdf"),
    Integration("browser", "Browser Context", "Read any webpage from any app — the AI sidekick for Chrome, Safari, and Arc", "System", "browser"),
    Integration("local", "Local Files", "Spotlight AI alternative — find files by what they are about, not their name", "System", "local"),
    Integration("gdrive", "Google Drive", "Google Drive AI assistant — find the doc, summarize it, draft the follow-up", "Files", "gdrive"),
    Integration("word", "Microsoft Word", "Microsoft Word AI assistant for people not paying for Copilot", "Docs", "word"),
    Integration("excel", "Microsoft Excel", "Excel AI that explains what a cell is doing — without the Copilot seat", "Spreadsheets", "excel"),
    Integration("ppt", "Microsoft PowerPoint", "PowerPoint AI assistant — review decks, suggest edits, draft speaker notes", "Slides", "ppt"),
    Integration("anotes", "Apple Notes", "Apple Notes AI that remembers across sessions and acts on what it finds", "Notes", "anotes"),
    Integration("acal", "Apple Calendar", "Voice-first Apple Calendar assistant — schedule, reschedule, brief in plain English", "Calendar", "acal"),
    Integration("aremind", "Apple Reminders", "AI todo assistant for Apple Reminders — capture from anywhere, never lose a task", "Tasks", "aremind"),
    Integration("canva", "Canva", "Canva AI assistant that reads designs and pulls in brand context", "Design", "canva"),
    Integration("asana", "Asana", "Asana AI assistant — turn conversations into tasks, surface what is blocked", "Project tracking", "asana"),
    Integration("trello", "Trello", "Trello AI assistant — automate card creation from email, Slack, and screenshots", "Project tracking", "trello"),
    Integration("clickup", "ClickUp", "ClickUp Brain alternative that works outside ClickUp too", "Project tracking", "clickup"),
    Integration("todoist", "Todoist", "Todoist AI that captures from any app — drop a task without breaking flow", "Tasks", "todoist"),
    Integration("discord", "Discord", "Discord AI assistant that catches you up on servers without bots in the channel", "Messaging", "discord"),
    Integration("classroom", "Google Classroom", "AI study buddy for Google Classroom — flashcards, summaries, assignment help", "Education", "classroom"),
    Integration("obsidian", "Obsidian", "Obsidian AI plugin alternative — vault-aware assistant that lives outside Obsidian too", "Notes", "obsidian"),
    Integration("evernote", "Evernote", "Evernote AI assistant — search by meaning, summarize, draft from notes", "Notes", "evernote"),
    Integration("airtable", "Airtable", "Airtable AI assistant — query bases in plain English, draft updates, surface trends", "Database", "airtable"),
    Integration("spotify", "Spotify", "Voice-first Spotify control — change the vibe without breaking focus", "Music", "spotify"),
]


class _BrandIcon(QWidget):
    """Rounded brand tile with a simple painted mark."""

    _COLORS = {
        "gmail": "#EA4335",
        "slack": "#4A154B",
        "notion": "#111111",
        "gcal": "#4285F4",
        "linear": "#5E6AD2",
        "github": "#24292F",
        "figma": "#F24E1E",
        "gdrive": "#1A73E8",
        "outlook": "#0078D4",
        "gdocs": "#4285F4",
        "gsheets": "#0F9D58",
        "pdf": "#E53935",
        "browser": "#5B8DEF",
        "local": "#6B7280",
        "word": "#2B579A",
        "excel": "#217346",
        "ppt": "#C43E1C",
        "anotes": "#FFCC00",
        "acal": "#FF3B30",
        "aremind": "#FF9500",
        "canva": "#00C4CC",
        "asana": "#F06A6A",
        "trello": "#0079BF",
        "clickup": "#7B68EE",
        "todoist": "#E44332",
        "discord": "#5865F2",
        "classroom": "#0F9D58",
        "obsidian": "#7C3AED",
        "evernote": "#00A82D",
        "airtable": "#18BFFF",
        "spotify": "#1DB954",
    }

    def __init__(self, brand: str, size: int = 44, parent=None):
        super().__init__(parent)
        self._brand = brand
        self._sz = size
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._COLORS.get(self._brand, T.CYAN))
        r = QRectF(0.5, 0.5, self._sz - 1, self._sz - 1)
        radius = self._sz * 0.28
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        # Soft inner highlight
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(QRectF(1, 1, self._sz - 2, self._sz * 0.42), radius, radius)

        p.setPen(QPen(QColor("#FFFFFF")))
        mark = self._brand
        s = self._sz / 44.0

        def P(x, y):
            return QPointF(x * s, y * s)

        if mark == "gmail":
            pen = QPen(QColor("#FFFFFF"), 2.2 * s)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(P(10, 14))
            path.lineTo(P(22, 24))
            path.lineTo(P(34, 14))
            path.lineTo(P(34, 30))
            path.lineTo(P(10, 30))
            path.closeSubpath()
            p.drawPath(path)
        elif mark == "slack":
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(11 * s, 18 * s, 8 * s, 16 * s), 3 * s, 3 * s)
            p.drawRoundedRect(QRectF(25 * s, 10 * s, 8 * s, 16 * s), 3 * s, 3 * s)
            p.drawRoundedRect(QRectF(18 * s, 11 * s, 16 * s, 8 * s), 3 * s, 3 * s)
            p.drawRoundedRect(QRectF(10 * s, 25 * s, 16 * s, 8 * s), 3 * s, 3 * s)
        elif mark == "notion":
            f = QFont(T.SB_FONT, int(16 * s))
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "N")
        elif mark in ("gcal", "acal"):
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(11 * s, 12 * s, 22 * s, 22 * s), 4 * s, 4 * s)
            p.setBrush(bg)
            p.drawRect(QRectF(11 * s, 12 * s, 22 * s, 7 * s))
            p.setPen(QPen(QColor("#FFFFFF")))
            f = QFont(T.SB_FONT, int(11 * s))
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(11 * s, 20 * s, 22 * s, 14 * s), Qt.AlignmentFlag.AlignCenter, "31")
        elif mark == "linear":
            pen = QPen(QColor("#FFFFFF"), 2.4 * s)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(P(14, 28), P(30, 14))
            p.drawEllipse(QRectF(26 * s, 10 * s, 8 * s, 8 * s))
        elif mark == "github":
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(13 * s, 12 * s, 18 * s, 18 * s))
            p.setBrush(bg)
            p.drawEllipse(QRectF(17 * s, 17 * s, 4 * s, 4 * s))
            p.drawEllipse(QRectF(23 * s, 17 * s, 4 * s, 4 * s))
        elif mark == "figma":
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(12 * s, 10 * s, 10 * s, 10 * s))
            p.drawEllipse(QRectF(22 * s, 10 * s, 10 * s, 10 * s))
            p.drawEllipse(QRectF(12 * s, 20 * s, 10 * s, 10 * s))
            p.drawRoundedRect(QRectF(22 * s, 20 * s, 10 * s, 14 * s), 5 * s, 5 * s)
        elif mark == "gdrive":
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            tri = QPainterPath()
            tri.moveTo(P(22, 10))
            tri.lineTo(P(34, 32))
            tri.lineTo(P(10, 32))
            tri.closeSubpath()
            p.drawPath(tri)
        elif mark == "spotify":
            pen = QPen(QColor("#FFFFFF"), 2.2 * s)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(12 * s, 14 * s, 20 * s, 12 * s), 20 * 16, 140 * 16)
            p.drawArc(QRectF(14 * s, 19 * s, 16 * s, 10 * s), 20 * 16, 140 * 16)
            p.drawArc(QRectF(16 * s, 24 * s, 12 * s, 8 * s), 20 * 16, 140 * 16)
        else:
            letter = (self._brand[:1] or "?").upper()
            if mark in ("gdocs", "gsheets", "word", "excel", "ppt"):
                letter = {"gdocs": "D", "gsheets": "S", "word": "W", "excel": "X", "ppt": "P"}[mark]
            elif mark == "discord":
                letter = "D"
            elif mark == "obsidian":
                letter = "O"
            f = QFont(T.SB_FONT, int(15 * s))
            f.setBold(True)
            # Dark text on yellow Apple Notes tile
            if mark == "anotes":
                p.setPen(QPen(QColor("#111111")))
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, letter)


class _PlusBtn(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConnPlusBtn")
        self._hover = False
        self._on = False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply()

    def set_connected(self, on: bool):
        self._on = on
        self._apply()
        self.update()

    def _apply(self):
        bg = _PLUS_HOVER if self._hover else _CARD_BG
        border = T.CYAN if self._on else _PLUS_BORDER
        self.setStyleSheet(
            f"QFrame#ConnPlusBtn {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 18px; }}"
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

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(T.CYAN if self._on else "#6B7280")
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        if self._on:
            # checkmark
            p.drawLine(QPointF(cx - 5, cy), QPointF(cx - 1, cy + 4))
            p.drawLine(QPointF(cx - 1, cy + 4), QPointF(cx + 6, cy - 4))
        else:
            p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))


class _IntegrationCard(QFrame):
    connect_toggled = pyqtSignal(str, bool)

    def __init__(self, item: Integration, parent=None):
        super().__init__(parent)
        self.setObjectName("IntegrationCard")
        self._item = item
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(88)
        self.setStyleSheet(
            f"QFrame#IntegrationCard {{ background: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; "
            f"border-radius: 24px; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 16, 14, 16)
        lay.setSpacing(14)

        lay.addWidget(_BrandIcon(item.brand, 44), alignment=Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(4)
        text.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setContentsMargins(0, 0, 0, 0)
        name = QLabel(item.name)
        name.setFont(QFont(T.SB_FONT, 14, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {_TITLE}; background: transparent; border: none;")
        title_row.addWidget(name, alignment=Qt.AlignmentFlag.AlignVCenter)
        badge = QLabel(item.category)
        badge.setFont(QFont(T.SB_FONT, 11))
        badge.setStyleSheet(f"color: {_BADGE}; background: transparent; border: none;")
        title_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()
        text.addLayout(title_row)

        desc = QLabel(item.description)
        desc.setWordWrap(True)
        desc.setFont(QFont(T.SB_FONT, 12))
        desc.setStyleSheet(f"color: {_DESC}; background: transparent; border: none;")
        desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text.addWidget(desc)
        lay.addLayout(text, stretch=1)

        self._plus = _PlusBtn()
        self._plus.clicked.connect(self._on_plus)
        lay.addWidget(self._plus, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _on_plus(self):
        # Integrations are gated — surface Coming soon instead of connecting.
        self.connect_toggled.emit(self._item.key, False)


class ConnectorsView(QWidget):
    """Full-page Connectors library shown when PLATFORM → Connectors is selected."""

    connect_requested = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConnectorsView")
        self.setStyleSheet(f"QWidget#ConnectorsView {{ background: {_PAGE_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_PAGE_BG}; border: none; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }"
            f"QScrollBar::handle:vertical {{ background: {_CARD_BORDER}; border-radius: 4px; min-height: 32px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        page = QWidget()
        page.setStyleSheet(f"background: {_PAGE_BG};")
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(36, 28, 36, 40)
        page_lay.setSpacing(0)
        page_lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        inner = QWidget()
        inner.setMaximumWidth(980)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(0)

        inner_lay.addWidget(self._section_header(
            "Featured integrations",
            "Start with the apps most Jarvis users connect first.",
        ))
        inner_lay.addSpacing(18)
        inner_lay.addLayout(self._cards_grid(FEATURED))
        inner_lay.addSpacing(40)
        inner_lay.addWidget(self._section_header(
            f"All integrations ({len(ALL_INTEGRATIONS)})",
            "Every integration Jarvis ships with today.",
        ))
        inner_lay.addSpacing(18)
        inner_lay.addLayout(self._cards_grid(ALL_INTEGRATIONS))
        inner_lay.addStretch()

        page_lay.addWidget(inner)
        scroll.setWidget(page)
        root.addWidget(scroll)

        self._toast = QLabel("Coming soon", self)
        self._toast.setObjectName("ConnComingSoonToast")
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setFont(QFont(T.SB_FONT, 14, QFont.Weight.DemiBold))
        self._toast.setStyleSheet(
            "QLabel#ConnComingSoonToast {"
            "  color: #FFFFFF;"
            "  background: rgba(17, 24, 39, 0.92);"
            "  border: none;"
            "  border-radius: 22px;"
            "  padding: 12px 28px;"
            "}"
        )
        self._toast.setFixedHeight(44)
        self._toast.adjustSize()
        self._toast.setMinimumWidth(max(160, self._toast.sizeHint().width() + 40))
        self._toast.hide()
        self._toast_opacity = QGraphicsOpacityEffect(self._toast)
        self._toast.setGraphicsEffect(self._toast_opacity)
        self._toast_anim: QPropertyAnimation | None = None
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_toast()

    def _place_toast(self) -> None:
        self._toast.adjustSize()
        tw = self._toast.width()
        th = self._toast.height()
        x = max(0, (self.width() - tw) // 2)
        y = max(0, self.height() - th - 36)
        self._toast.setGeometry(x, y, tw, th)
        self._toast.raise_()

    def _show_coming_soon(self, *_args) -> None:
        self._toast_timer.stop()
        if self._toast_anim is not None:
            self._toast_anim.stop()
        self._place_toast()
        self._toast_opacity.setOpacity(0.0)
        self._toast.show()
        self._toast.raise_()
        anim = QPropertyAnimation(self._toast_opacity, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._toast_anim = anim
        self._toast_timer.start(1600)

    def _hide_toast(self) -> None:
        if self._toast_anim is not None:
            self._toast_anim.stop()
        anim = QPropertyAnimation(self._toast_opacity, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(self._toast_opacity.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._toast.hide)
        anim.start()
        self._toast_anim = anim

    @staticmethod
    def _section_header(title: str, subtitle: str) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(6)
        h = QLabel(title)
        h.setFont(QFont(T.SB_FONT, 22, QFont.Weight.Bold))
        h.setStyleSheet(f"color: {_TITLE}; background: transparent; border: none;")
        lay.addWidget(h)
        s = QLabel(subtitle)
        s.setFont(QFont(T.SB_FONT, 13))
        s.setStyleSheet(f"color: {_DESC}; background: transparent; border: none;")
        s.setWordWrap(True)
        lay.addWidget(s)
        return wrap

    def _cards_grid(self, items: list[Integration]) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i, item in enumerate(items):
            card = _IntegrationCard(item)
            card.connect_toggled.connect(self._on_card_plus)
            grid.addWidget(card, i // 2, i % 2)
        # Odd last item: still left column only
        return grid

    def _on_card_plus(self, key: str, _connected: bool) -> None:
        self._show_coming_soon()
        self.connect_requested.emit(key, False)
