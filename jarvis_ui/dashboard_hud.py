"""Dashboard hero view — Chat-style HUD circle + dedicated input bar."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from jarvis_ui import theme as T


class _DashboardSendButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background: {T.CYAN}; border: none; border-radius: 17px; }}"
            f"QPushButton:hover {{ background: #52ebe0; }}"
            f"QPushButton:pressed {{ background: {T.CYAN_DIM}; }}"
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#061014"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        p.drawLine(int(cx - 4), int(cy + 3), int(cx + 4), int(cy - 5))
        p.drawLine(int(cx + 4), int(cy - 5), int(cx + 1), int(cy - 5))
        p.drawLine(int(cx + 4), int(cy - 5), int(cx + 4), int(cy - 2))


class _DashboardMicButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 14px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.06); }"
        )
        self._muted = False

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(T.RED) if self._muted else QColor("#8b949e")
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        p.drawRoundedRect(int(cx - 3), int(cy - 7), 6, 9, 3, 3)
        p.drawArc(int(cx - 6), int(cy - 1), 12, 8, 0, -180 * 16)
        p.drawLine(int(cx), int(cy + 7), int(cx), int(cy + 9))
        if self._muted:
            p.drawLine(int(cx - 6), int(cy - 6), int(cx + 6), int(cy + 6))


class DashboardInputBar(QWidget):
    submitted = pyqtSignal(str)
    mute_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(28, 0, 28, 28)
        row.addStretch(1)

        self._pill = QFrame()
        self._pill.setObjectName("dashboardInputPill")
        self._pill.setFixedHeight(T.CHAT_BAR_HEIGHT)
        self._pill.setMaximumWidth(T.CHAT_BAR_MAX_WIDTH)
        self._pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._pill.setStyleSheet(
            f"QFrame#dashboardInputPill {{"
            f"  background: {T.BG_CARD};"
            f"  border: 1px solid {T.BORDER};"
            f"  border-radius: 26px;"
            f"}}"
        )

        inner = QHBoxLayout(self._pill)
        inner.setContentsMargins(20, 0, 8, 0)
        inner.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message A.U.R.A...")
        self._input.setFont(QFont(T.CHAT_FONT, 15))
        self._input.setFrame(False)
        self._input.setMinimumHeight(36)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {T.CHAT_BAR_TEXT};
                border: none;
                padding: 0 4px;
            }}
            QLineEdit::placeholder {{ color: #6b7280; }}
        """)
        self._input.returnPressed.connect(self._submit)
        inner.addWidget(self._input, stretch=1)

        self._mic = _DashboardMicButton()
        self._mic.clicked.connect(self.mute_clicked.emit)
        inner.addWidget(self._mic)

        self._send = _DashboardSendButton()
        self._send.clicked.connect(self._submit)
        inner.addWidget(self._send)

        row.addWidget(self._pill, stretch=1)
        row.addStretch(1)
        root.addWidget(host)

    def _submit(self) -> None:
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self.submitted.emit(text)

    def set_muted(self, muted: bool) -> None:
        self._mic.set_muted(muted)


class DashboardHeroView(QWidget):
    """Dashboard center: same HudCanvas visual as Chat + dedicated input."""

    submitted = pyqtSignal(str)
    mute_clicked = pyqtSignal()

    def __init__(self, hud_widget: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.BG};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.hud = hud_widget
        if hasattr(self.hud, "set_dashboard_mode"):
            self.hud.set_dashboard_mode(True)
        self.hud.setMinimumHeight(360)
        lay.addWidget(self.hud, stretch=1)

        self.input_bar = DashboardInputBar()
        self.input_bar.submitted.connect(self.submitted.emit)
        self.input_bar.mute_clicked.connect(self.mute_clicked.emit)
        lay.addWidget(self.input_bar)

    def set_muted(self, muted: bool) -> None:
        if hasattr(self.hud, "muted"):
            self.hud.muted = muted
        if muted and hasattr(self.hud, "set_voice_level"):
            self.hud.set_voice_level(0.0)
        self.input_bar.set_muted(muted)

    def set_speaking(self, speaking: bool) -> None:
        if hasattr(self.hud, "speaking"):
            self.hud.speaking = speaking

    def set_voice_level(self, level: float) -> None:
        if hasattr(self.hud, "set_voice_level"):
            self.hud.set_voice_level(level)
