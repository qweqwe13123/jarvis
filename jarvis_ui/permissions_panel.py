"""In-app Permissions panel — polished macOS privacy grants for AURA."""

from __future__ import annotations

import math
import platform
import subprocess
from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T

_SETTINGS_URLS = {
    "mic": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "a11y": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}

_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("mic", "Microphone", "Voice mode and double-clap wake."),
    ("camera", "Camera", "Vision only when you ask AURA to look."),
    ("screen", "Screen Recording", "See your display for computer control."),
    ("a11y", "Accessibility", "Clicks, typing, and app control you request."),
    ("automation", "Automation", "Open and drive apps you ask for."),
)


def _open_privacy(kind: str) -> None:
    url = _SETTINGS_URLS.get(kind)
    if not url:
        return
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", url], check=False)
        else:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))
    except Exception:
        pass


class _PermGlyph(QWidget):
    """Soft circular glyph for each permission kind."""

    def __init__(self, kind: str, size: int = 36, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._d = size
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:  # noqa: N802
        d = self._d
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, d, d)
        grad.setColorAt(0.0, QColor(0, 209, 255, 36))
        grad.setColorAt(1.0, QColor(0, 120, 180, 22))
        p.setPen(QPen(QColor(0, 209, 255, 70), 1.0))
        p.setBrush(grad)
        p.drawEllipse(QRectF(1, 1, d - 2, d - 2))

        pen = QPen(QColor(T.CYAN), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        s = d / 24.0

        def P(x: float, y: float) -> QPointF:
            return QPointF(x * s, y * s)

        def R(x: float, y: float, w: float, h: float) -> QRectF:
            return QRectF(x * s, y * s, w * s, h * s)

        k = self._kind
        if k == "mic":
            p.drawRoundedRect(R(9.5, 5, 5, 9), 2.5 * s, 2.5 * s)
            p.drawArc(R(7, 11, 10, 7), 0, -180 * 16)
            p.drawLine(P(12, 18), P(12, 20))
            p.drawLine(P(9, 20), P(15, 20))
        elif k == "camera":
            p.drawRoundedRect(R(5, 8, 10, 8), 2 * s, 2 * s)
            path = QPainterPath()
            path.moveTo(15.5 * s, 10 * s)
            path.lineTo(19.5 * s, 8 * s)
            path.lineTo(19.5 * s, 16 * s)
            path.lineTo(15.5 * s, 14 * s)
            path.closeSubpath()
            p.drawPath(path)
        elif k == "screen":
            p.drawRoundedRect(R(4, 6, 16, 11), 2 * s, 2 * s)
            p.drawLine(P(9, 19), P(15, 19))
            p.drawLine(P(12, 17), P(12, 19))
        elif k == "a11y":
            p.drawEllipse(R(9.5, 5, 5, 5))
            p.drawLine(P(12, 10.5), P(12, 16))
            p.drawLine(P(8, 12.5), P(16, 12.5))
            p.drawLine(P(12, 16), P(9, 20))
            p.drawLine(P(12, 16), P(15, 20))
        else:  # automation
            p.drawEllipse(R(7, 7, 10, 10))
            p.drawEllipse(R(10.5, 10.5, 3, 3))
            for a in (0, 60, 120, 180, 240, 300):
                rad = math.radians(a)
                x1 = 12 + 6.2 * math.cos(rad)
                y1 = 12 + 6.2 * math.sin(rad)
                x2 = 12 + 8.2 * math.cos(rad)
                y2 = 12 + 8.2 * math.sin(rad)
                p.drawLine(P(x1, y1), P(x2, y2))
        p.end()


class _ShieldMark(QWidget):
    """Header shield for the Permissions dialog."""

    def __init__(self, size: int = 44, parent=None):
        super().__init__(parent)
        self._d = size
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:  # noqa: N802
        d = float(self._d)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        g = QRadialGradient(d / 2, d / 2, d * 0.55)
        g.setColorAt(0.0, QColor(0, 209, 255, 55))
        g.setColorAt(1.0, QColor(0, 209, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QRectF(0, 0, d, d))

        # Plate
        p.setPen(QPen(QColor(0, 209, 255, 90), 1.2))
        plate = QLinearGradient(0, 0, d, d)
        plate.setColorAt(0.0, QColor(12, 32, 48))
        plate.setColorAt(1.0, QColor(8, 20, 32))
        p.setBrush(plate)
        p.drawEllipse(QRectF(3, 3, d - 6, d - 6))

        # Shield path
        s = d / 28.0
        path = QPainterPath()
        path.moveTo(14 * s, 7 * s)
        path.cubicTo(18.5 * s, 7.5 * s, 21.5 * s, 9.2 * s, 21.5 * s, 11.5 * s)
        path.lineTo(21.5 * s, 15.8 * s)
        path.cubicTo(21.5 * s, 20.2 * s, 17.8 * s, 22.8 * s, 14 * s, 24.2 * s)
        path.cubicTo(10.2 * s, 22.8 * s, 6.5 * s, 20.2 * s, 6.5 * s, 15.8 * s)
        path.lineTo(6.5 * s, 11.5 * s)
        path.cubicTo(6.5 * s, 9.2 * s, 9.5 * s, 7.5 * s, 14 * s, 7 * s)
        path.closeSubpath()

        p.setPen(QPen(QColor(T.CYAN), 1.6))
        p.setBrush(QColor(0, 209, 255, 28))
        p.drawPath(path)

        # Check
        pen = QPen(QColor(T.CYAN), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(10.2 * s, 15.2 * s), QPointF(12.8 * s, 17.6 * s))
        p.drawLine(QPointF(12.8 * s, 17.6 * s), QPointF(17.8 * s, 12.2 * s))
        p.end()


class _PermRow(QFrame):
    def __init__(
        self,
        key: str,
        title: str,
        body: str,
        on_action: Callable[[str], None],
        parent=None,
    ):
        super().__init__(parent)
        self._key = key
        self._on_action = on_action
        self.setObjectName("AuraPermRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)

        lay.addWidget(_PermGlyph(key, 36), 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(2)
        self._title = QLabel(title)
        self._title.setFont(QFont(T.CHAT_FONT, 13, QFont.Weight.DemiBold))
        self._body = QLabel(body)
        self._body.setFont(QFont(T.CHAT_FONT, 11))
        self._body.setWordWrap(True)
        col.addWidget(self._title)
        col.addWidget(self._body)
        lay.addLayout(col, stretch=1)

        self._status = QLabel("…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFixedHeight(26)
        self._status.setMinimumWidth(78)
        self._status.setFont(QFont(T.CHAT_FONT, 10, QFont.Weight.Medium))
        lay.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)

        self._btn = QPushButton("Allow")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedHeight(32)
        self._btn.setMinimumWidth(88)
        self._btn.setFont(QFont(T.CHAT_FONT, 12, QFont.Weight.DemiBold))
        self._btn.clicked.connect(lambda: self._on_action(self._key))
        lay.addWidget(self._btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._apply_chrome()

    def _apply_chrome(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#AuraPermRow {{
                background: {T.BG_CARD};
                border: 1px solid {T.BORDER};
                border-radius: 14px;
            }}
            QFrame#AuraPermRow:hover {{
                border: 1px solid {T.BORDER_HI};
                background: {T.BG_ELEVATED};
            }}
            """
        )
        self._title.setStyleSheet(
            f"color: {T.WHITE}; background: transparent; border: none;"
        )
        self._body.setStyleSheet(
            f"color: {T.TEXT_MED}; background: transparent; border: none;"
        )
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(0, 209, 255, 0.12);
                color: {T.CYAN};
                border: 1px solid rgba(0, 209, 255, 0.32);
                border-radius: 10px;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background: rgba(0, 209, 255, 0.20);
                border-color: rgba(0, 209, 255, 0.50);
            }}
            QPushButton:disabled {{
                background: rgba(255,255,255,0.03);
                color: {T.TEXT_DIM};
                border: 1px solid {T.BORDER};
            }}
            """
        )

    def set_state(self, granted: bool | None, *, busy: bool = False) -> None:
        if busy:
            self._status.setText("Checking")
            self._status.setStyleSheet(
                f"color: {T.TEXT_MED}; background: rgba(255,255,255,0.04); "
                f"border: 1px solid {T.BORDER}; border-radius: 9px; padding: 0 8px;"
            )
            self._btn.setEnabled(False)
            self._btn.setText("Waiting")
            return
        if granted is True:
            self._status.setText("Granted")
            self._status.setStyleSheet(
                f"color: {T.GREEN}; background: rgba(0, 255, 148, 0.08); "
                f"border: 1px solid rgba(0, 255, 148, 0.28); border-radius: 9px; padding: 0 8px;"
            )
            self._btn.setEnabled(False)
            self._btn.setText("Done")
        elif granted is False:
            self._status.setText("Denied")
            self._status.setStyleSheet(
                "color: #ff8a9b; background: rgba(255, 80, 100, 0.08); "
                "border: 1px solid rgba(255, 80, 100, 0.28); border-radius: 9px; padding: 0 8px;"
            )
            self._btn.setEnabled(True)
            self._btn.setText("Settings")
        else:
            self._status.setText("Needed")
            self._status.setStyleSheet(
                f"color: {T.CYAN}; background: rgba(0, 209, 255, 0.08); "
                f"border: 1px solid rgba(0, 209, 255, 0.28); border-radius: 9px; padding: 0 8px;"
            )
            self._btn.setEnabled(True)
            self._btn.setText("Allow")


class PermissionsDialog(QDialog):
    """Polished permissions sheet for the main-window sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PermissionsDialog")
        self.setWindowTitle("Permissions")
        self.setModal(True)
        self.setMinimumSize(520, 580)
        self.resize(560, 640)
        self.setStyleSheet(
            f"""
            QDialog#PermissionsDialog {{
                background: {T.BG};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # —— Header card ——
        header = QFrame()
        header.setObjectName("PermHeader")
        header.setStyleSheet(
            f"""
            QFrame#PermHeader {{
                background: {T.BG_PANEL};
                border: none;
                border-bottom: 1px solid {T.BORDER};
            }}
            """
        )
        h = QVBoxLayout(header)
        h.setContentsMargins(26, 22, 26, 18)
        h.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(_ShieldMark(46), 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("Permissions")
        title.setFont(QFont(T.CHAT_FONT, 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.WHITE}; background: transparent;")
        titles.addWidget(title)
        sub = QLabel(
            "AURA only uses these when you ask. Grant what you need — "
            "change anything later in System Settings."
        )
        sub.setWordWrap(True)
        sub.setFont(QFont(T.CHAT_FONT, 12))
        sub.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent;")
        titles.addWidget(sub)
        top.addLayout(titles, stretch=1)
        h.addLayout(top)
        h.addSpacing(14)

        self._progress = QLabel("0 of 5 ready")
        self._progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress.setFixedHeight(28)
        self._progress.setFont(QFont(T.CHAT_FONT, 11, QFont.Weight.DemiBold))
        self._progress.setStyleSheet(
            f"""
            color: {T.CYAN};
            background: rgba(0, 209, 255, 0.08);
            border: 1px solid rgba(0, 209, 255, 0.22);
            border-radius: 14px;
            padding: 0 14px;
            """
        )
        h.addWidget(self._progress, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(header)

        # —— List ——
        body = QWidget()
        body.setStyleSheet(f"background: {T.BG};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(22, 16, 22, 8)
        bl.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {T.BORDER_HI}; border-radius: 4px; min-height: 28px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(host)
        self._list.setContentsMargins(0, 0, 4, 0)
        self._list.setSpacing(10)

        self._rows: dict[str, _PermRow] = {}
        for key, title_t, body_t in _ITEMS:
            row = _PermRow(key, title_t, body_t, self._on_row_action)
            self._rows[key] = row
            self._list.addWidget(row)
        self._list.addStretch()
        scroll.setWidget(host)
        bl.addWidget(scroll, stretch=1)
        root.addWidget(body, stretch=1)

        # —— Footer ——
        foot = QFrame()
        foot.setObjectName("PermFooter")
        foot.setStyleSheet(
            f"""
            QFrame#PermFooter {{
                background: {T.BG_PANEL};
                border-top: 1px solid {T.BORDER};
            }}
            """
        )
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(22, 14, 22, 16)
        fl.setSpacing(10)

        self._summary = QLabel("")
        self._summary.setFont(QFont(T.CHAT_FONT, 11))
        self._summary.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        fl.addWidget(self._summary, stretch=1)

        refresh = QPushButton("Refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.setFixedHeight(36)
        refresh.setFont(QFont(T.CHAT_FONT, 12, QFont.Weight.Medium))
        refresh.clicked.connect(self.refresh)
        refresh.setStyleSheet(
            f"""
            QPushButton {{
                background: {T.BG_ELEVATED}; color: {T.WHITE};
                border: 1px solid {T.BORDER_HI}; border-radius: 10px; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {T.CYAN}; color: {T.CYAN}; }}
            """
        )
        fl.addWidget(refresh)

        close = QPushButton("Done")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedHeight(36)
        close.setMinimumWidth(100)
        close.setFont(QFont(T.CHAT_FONT, 12, QFont.Weight.DemiBold))
        close.clicked.connect(self.accept)
        close.setStyleSheet(
            f"""
            QPushButton {{
                background: {T.CYAN}; color: #041018;
                border: none; border-radius: 10px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: #33daff; }}
            QPushButton:pressed {{ background: #00b8e0; }}
            """
        )
        fl.addWidget(close)
        root.addWidget(foot)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(1500)
        self._sync_timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()
        self._sync_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._sync_timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        try:
            from jarvis_ui.onboarding.permissions_native import is_granted, required_kinds
        except Exception:
            for row in self._rows.values():
                row.set_state(True)
            self._summary.setText("Permissions are available on macOS.")
            self._progress.setText("Ready")
            return

        granted_n = 0
        total = len(required_kinds())
        for key, row in self._rows.items():
            ok = is_granted(key)  # type: ignore[arg-type]
            row.set_state(ok)
            if ok is True:
                granted_n += 1
        self._summary.setText(f"{granted_n} of {total} granted · updates live")
        self._progress.setText(f"{granted_n} of {total} ready")

    def _on_row_action(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        try:
            from jarvis_ui.onboarding.permissions_native import (
                is_granted,
                request_in_app,
                supports_in_app_prompt,
            )
        except Exception:
            _open_privacy(key)
            return

        if is_granted(key) is True:  # type: ignore[arg-type]
            return

        if is_granted(key) is False:  # type: ignore[arg-type]
            _open_privacy(key)
            return

        row.set_state(None, busy=True)

        def _done(ok: bool, **kwargs) -> None:
            needs_settings = bool(kwargs.get("needs_settings"))
            QTimer.singleShot(0, lambda: self._finish_prompt(key, ok, needs_settings))

        if supports_in_app_prompt(key):  # type: ignore[arg-type]
            request_in_app(key, _done)  # type: ignore[arg-type]
        else:
            _open_privacy(key)
            self.refresh()

    def _finish_prompt(self, key: str, ok: bool, needs_settings: bool) -> None:
        if needs_settings and not ok:
            _open_privacy(key)
        self.refresh()
