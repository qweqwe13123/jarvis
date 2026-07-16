"""Floating AI overlay — modern mini-chat that stays on top of every app."""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QParallelAnimationGroup,
    QRect, QRectF, Qt, pyqtSignal, QTimer, QSize,
)
from PyQt6.QtGui import (
    QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QLinearGradient, QBrush,
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from jarvis_ui import theme as T
from memory import workspace_manager as ws


_OVERLAY_W = 420
_COMPACT_H = 148
_EXPANDED_H = 520
_RADIUS = 28
_ANIM_MS = 200

# Premium dark glass (navy-tinted to match Jarvis)
_BG_TOP = QColor(10, 18, 28, 242)
_BG_BOT = QColor(6, 12, 20, 248)
_BORDER = QColor(0, 209, 255, 55)
_MUTED = "#7eb8d4"
_TEXT = "#e8f8ff"
_SEND = "#00d1ff"
_USER_BUBBLE = "rgba(0, 209, 255, 0.16)"
_AI_BUBBLE = "rgba(255, 255, 255, 0.06)"


class _IconBtn(QWidget):
    clicked = pyqtSignal()

    def __init__(self, kind: str, size: int = 22, accent: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self._accent = accent
        self._active = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, on: bool):
        self._active = on
        self.update()

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
            e.accept()
            return
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._kind == "send":
            bg = QColor(_SEND)
            if self._hover:
                bg = QColor("#33daff")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
            pen = QPen(QColor("#050a14"), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            s = self.width() / 32.0
            path = QPainterPath()
            path.moveTo(QPointF(9 * s, 16 * s))
            path.lineTo(QPointF(23 * s, 9 * s))
            path.lineTo(QPointF(16 * s, 23 * s))
            path.lineTo(QPointF(14 * s, 17 * s))
            path.closeSubpath()
            p.drawPath(path)
            return

        color = QColor(_SEND if (self._active or self._accent) else ("#FFFFFF" if self._hover else _MUTED))
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = self.width() / 22.0

        def P(x, y):
            return QPointF(x * s, y * s)

        def R(x, y, w, h):
            return QRectF(x * s, y * s, w * s, h * s)

        k = self._kind
        if k == "home":
            path = QPainterPath()
            path.moveTo(P(11, 4))
            path.lineTo(P(19, 11))
            path.lineTo(P(19, 18))
            path.lineTo(P(14, 18))
            path.lineTo(P(14, 13))
            path.lineTo(P(8, 13))
            path.lineTo(P(8, 18))
            path.lineTo(P(3, 18))
            path.lineTo(P(3, 11))
            path.closeSubpath()
            p.drawPath(path)
        elif k == "mic":
            if self._active:
                p.setBrush(QColor(0, 209, 255, 40))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(self.rect().adjusted(0, 0, -1, -1))
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(R(8, 3, 6, 10), 3 * s, 3 * s)
            p.drawArc(R(5, 9, 12, 8), 0, -180 * 16)
            p.drawLine(P(11, 17), P(11, 19))
            p.drawLine(P(8, 19), P(14, 19))
        elif k == "wave":
            for x, h in ((6, 6), (10, 12), (14, 8), (18, 14)):
                p.drawLine(P(x, 11 - h / 2), P(x, 11 + h / 2))
        elif k == "close":
            p.drawLine(P(7, 7), P(15, 15))
            p.drawLine(P(15, 7), P(7, 15))


class _OverlayChrome(QWidget):
    """Glass panel with cyan edge glow."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, _RADIUS, _RADIUS)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, _BG_TOP)
        grad.setColorAt(1.0, _BG_BOT)
        p.setPen(QPen(_BORDER, 1.2))
        p.setBrush(QBrush(grad))
        p.drawPath(path)

        # Soft top highlight
        hi = QLinearGradient(0, 0, 0, 28)
        hi.setColorAt(0.0, QColor(255, 255, 255, 18))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hi)
        clip = QPainterPath()
        clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), _RADIUS - 1, _RADIUS - 1)
        p.setClipPath(clip)
        p.drawRect(QRectF(0, 0, self.width(), 28))


class _MsgBubble(QFrame):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("OverlayBubble")
        bg = _USER_BUBBLE if is_user else _AI_BUBBLE
        border = "rgba(0,209,255,0.28)" if is_user else "rgba(255,255,255,0.08)"
        self.setStyleSheet(
            f"QFrame#OverlayBubble {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 16px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        who = QLabel("You" if is_user else "Jarvis")
        who.setFont(QFont(T.SB_FONT, 10, QFont.Weight.DemiBold))
        who.setStyleSheet(
            f"color: {_SEND if not is_user else '#a5f3fc'}; background: transparent; border: none;"
        )
        lay.addWidget(who)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setFont(QFont(T.SB_FONT, 13))
        body.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(body)
        self._body = body

    def set_text(self, text: str):
        self._body.setText(text)


class FloatingOverlay(QWidget):
    """Always-on-top mini chat. Created once; show/hide only."""

    submitted = pyqtSignal(str)
    home_clicked = pyqtSignal()
    voice_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self._anim_group: QParallelAnimationGroup | None = None
        self._closing = False
        self._drag_origin: QPoint | None = None
        self._click_away = False  # keep open during conversation
        self._busy = False
        self._expanded = False
        self._stream_bubble: _MsgBubble | None = None
        self._voice_level = 0.0

        self.setObjectName("FloatingOverlay")
        self.setWindowTitle("Jarvis")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.resize(_OVERLAY_W, _COMPACT_H)
        self.setMinimumWidth(_OVERLAY_W)
        self.setMaximumWidth(_OVERLAY_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 14)
        root.setSpacing(0)

        self._chrome = _OverlayChrome()
        shadow = QGraphicsDropShadowEffect(self._chrome)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 180))
        self._chrome.setGraphicsEffect(shadow)

        chrome_lay = QVBoxLayout(self._chrome)
        chrome_lay.setContentsMargins(16, 14, 16, 14)
        chrome_lay.setSpacing(10)

        # —— top bar ——
        top = QHBoxLayout()
        top.setSpacing(8)
        self._home = _IconBtn("home", 18)
        self._home.clicked.connect(self.home_clicked.emit)
        top.addWidget(self._home, alignment=Qt.AlignmentFlag.AlignVCenter)

        brand = QLabel("Jarvis")
        brand.setFont(QFont(T.SB_FONT, 13, QFont.Weight.DemiBold))
        brand.setStyleSheet(f"color: {_TEXT}; background: transparent; border: none;")
        top.addWidget(brand, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._status = QLabel("Ready")
        self._status.setFont(QFont(T.SB_FONT, 11))
        self._status.setStyleSheet(
            f"color: {_MUTED}; background: rgba(0,209,255,0.08); border: 1px solid rgba(0,209,255,0.18);"
            f"border-radius: 9px; padding: 2px 10px;"
        )
        top.addWidget(self._status, alignment=Qt.AlignmentFlag.AlignVCenter)
        top.addStretch()

        self._quota = QLabel(self._quota_text())
        self._quota.setFont(QFont(T.SB_FONT, 11))
        self._quota.setStyleSheet(f"color: {_MUTED}; background: transparent; border: none;")
        top.addWidget(self._quota, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._wave = _IconBtn("wave", 18)
        self._wave.clicked.connect(self.voice_clicked.emit)
        top.addWidget(self._wave, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._close_btn = _IconBtn("close", 16)
        self._close_btn.clicked.connect(self.hide_animated)
        top.addWidget(self._close_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        chrome_lay.addLayout(top)

        # —— conversation (hidden until first message) ——
        self._feed_wrap = QWidget()
        self._feed_wrap.setStyleSheet("background: transparent;")
        self._feed_wrap.setVisible(False)
        fw = QVBoxLayout(self._feed_wrap)
        fw.setContentsMargins(0, 0, 0, 0)
        fw.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; margin: 2px; }"
            "QScrollBar::handle:vertical { background: rgba(0,209,255,0.35); border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._feed_host = QWidget()
        self._feed_host.setStyleSheet("background: transparent;")
        self._feed = QVBoxLayout(self._feed_host)
        self._feed.setContentsMargins(2, 2, 2, 2)
        self._feed.setSpacing(8)
        self._feed.addStretch(1)
        self._scroll.setWidget(self._feed_host)
        fw.addWidget(self._scroll)
        chrome_lay.addWidget(self._feed_wrap, stretch=1)

        # —— voice meter ——
        self._meter = QFrame()
        self._meter.setFixedHeight(3)
        self._meter.setStyleSheet(
            "background: rgba(0,209,255,0.12); border: none; border-radius: 2px;"
        )
        self._meter_fill = QFrame(self._meter)
        self._meter_fill.setStyleSheet(
            f"background: {_SEND}; border: none; border-radius: 2px;"
        )
        self._meter_fill.setGeometry(0, 0, 0, 3)
        self._meter.setVisible(False)
        chrome_lay.addWidget(self._meter)

        # —— input ——
        self._input_wrap = QFrame()
        self._input_wrap.setObjectName("OverlayInput")
        self._input_wrap.setFixedHeight(50)
        self._input_wrap.setStyleSheet(
            "QFrame#OverlayInput {"
            "  background: rgba(0, 0, 0, 0.28);"
            "  border: 1px solid rgba(0, 209, 255, 0.22);"
            "  border-radius: 18px;"
            "}"
        )
        il = QHBoxLayout(self._input_wrap)
        il.setContentsMargins(14, 0, 8, 0)
        il.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Jarvis anything…")
        self._input.setFont(QFont(T.SB_FONT, 14))
        self._input.setFrame(False)
        self._input.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {_TEXT}; border: none; "
            f"selection-background-color: {_SEND}; selection-color: #050a14; }}"
            f"QLineEdit::placeholder {{ color: {_MUTED}; }}"
        )
        self._input.returnPressed.connect(self._submit)
        il.addWidget(self._input, stretch=1)

        self._mic = _IconBtn("mic", 22)
        self._mic.clicked.connect(self.voice_clicked.emit)
        il.addWidget(self._mic, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._send = _IconBtn("send", 34)
        self._send.clicked.connect(self._submit)
        il.addWidget(self._send, alignment=Qt.AlignmentFlag.AlignVCenter)

        chrome_lay.addWidget(self._input_wrap)
        root.addWidget(self._chrome)

        self.hide()

    # ------------------------------------------------------------------ public API
    def set_click_away(self, enabled: bool) -> None:
        self._click_away = enabled

    def toggle(self) -> None:
        if self.isVisible() and not self._closing:
            self.hide_animated()
        else:
            self.show_animated()

    def show_animated(self) -> None:
        self._closing = False
        self._stop_anim()
        self._quota.setText(self._quota_text())
        self._place_on_screen()
        target = self.geometry()
        start = QRect(target)
        start.moveTop(target.top() + 14)
        dw, dh = 8, 6
        start.adjust(dw, dh, -dw, -dh)

        self.setWindowOpacity(0.0)
        self.setGeometry(start)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        op = QPropertyAnimation(self, b"windowOpacity", self)
        op.setDuration(_ANIM_MS)
        op.setStartValue(0.0)
        op.setEndValue(1.0)
        op.setEasingCurve(QEasingCurve.Type.OutCubic)
        geo = QPropertyAnimation(self, b"geometry", self)
        geo.setDuration(_ANIM_MS)
        geo.setStartValue(start)
        geo.setEndValue(target)
        geo.setEasingCurve(QEasingCurve.Type.OutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(op)
        group.addAnimation(geo)
        self._anim_group = group
        group.start()

    def hide_animated(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._stop_anim()
        self.remember_position()
        target = self.geometry()
        end = QRect(target)
        end.moveTop(target.top() + 10)
        end.adjust(6, 4, -6, -4)

        op = QPropertyAnimation(self, b"windowOpacity", self)
        op.setDuration(_ANIM_MS)
        op.setStartValue(self.windowOpacity())
        op.setEndValue(0.0)
        op.setEasingCurve(QEasingCurve.Type.InCubic)
        geo = QPropertyAnimation(self, b"geometry", self)
        geo.setDuration(_ANIM_MS)
        geo.setStartValue(target)
        geo.setEndValue(end)
        geo.setEasingCurve(QEasingCurve.Type.InCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(op)
        group.addAnimation(geo)
        group.finished.connect(self._after_hide)
        self._anim_group = group
        group.start()

    def remember_position(self) -> None:
        g = self.frameGeometry()
        ws.save_settings({"overlay_x": g.x(), "overlay_y": g.y()})

    def add_user(self, text: str) -> None:
        self._ensure_expanded()
        self._finish_stream()
        self._append_bubble(text, is_user=True)
        self.set_status("Thinking")
        self._busy = True

    def add_assistant(self, text: str) -> None:
        self._ensure_expanded()
        self._finish_stream()
        self._append_bubble(text, is_user=False)
        self._busy = False
        if self._status.text() in ("Thinking", "Processing", "Speaking"):
            self.set_status("Listening" if self._mic._active else "Ready")

    def stream_delta(self, text: str) -> None:
        """`text` is the full accumulated assistant reply so far."""
        self._ensure_expanded()
        self._busy = True
        self.set_status("Speaking")
        if self._stream_bubble is None:
            self._stream_bubble = self._append_bubble(text or "…", is_user=False)
        else:
            self._stream_bubble.set_text(text or "…")
        self._scroll_to_bottom()

    def stream_end(self, text: str = "") -> None:
        if self._stream_bubble is not None and text.strip():
            self._stream_bubble.set_text(text)
        self._finish_stream()
        self._busy = False
        self.set_status("Ready")

    def set_status(self, state: str) -> None:
        label = {
            "LISTENING": "Listening",
            "THINKING": "Thinking",
            "PROCESSING": "Processing",
            "SPEAKING": "Speaking",
            "MUTED": "Muted",
            "Ready": "Ready",
            "Listening": "Listening",
            "Thinking": "Thinking",
            "Speaking": "Speaking",
        }.get(state, state)
        self._status.setText(label)
        speaking = label in ("Speaking", "Listening", "Thinking")
        color = _SEND if speaking else _MUTED
        self._status.setStyleSheet(
            f"color: {color}; background: rgba(0,209,255,0.10); "
            f"border: 1px solid rgba(0,209,255,0.22); border-radius: 9px; padding: 2px 10px;"
        )
        self._mic.set_active(label == "Listening")
        self._wave.set_active(label == "Speaking")
        self._meter.setVisible(label in ("Listening", "Speaking"))

    def set_voice_level(self, level: float) -> None:
        self._voice_level = max(0.0, min(1.0, float(level)))
        if self._meter.isVisible():
            w = int(self._meter.width() * self._voice_level)
            self._meter_fill.setGeometry(0, 0, w, 3)

    def set_muted(self, muted: bool) -> None:
        if muted:
            self.set_status("Muted")
        elif not self._busy:
            self.set_status("Ready")

    # ------------------------------------------------------------------ internals
    def _ensure_expanded(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self._feed_wrap.setVisible(True)
        # Grow downward from current top-left.
        g = self.geometry()
        self.setMinimumHeight(_EXPANDED_H)
        self.resize(_OVERLAY_W, _EXPANDED_H)
        # Keep on screen
        screen = QGuiApplication.screenAt(g.topLeft()) or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            bottom = g.y() + _EXPANDED_H
            if bottom > avail.y() + avail.height() - 8:
                self.move(g.x(), max(avail.y() + 8, avail.y() + avail.height() - _EXPANDED_H - 8))

    def _append_bubble(self, text: str, is_user: bool) -> _MsgBubble:
        bubble = _MsgBubble(text, is_user)
        # Insert before the trailing stretch
        idx = max(0, self._feed.count() - 1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if is_user:
            row.addStretch(1)
            row.addWidget(bubble, stretch=0)
        else:
            row.addWidget(bubble, stretch=1)
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        wrap.setLayout(row)
        bubble.setMaximumWidth(int(_OVERLAY_W * 0.78))
        self._feed.insertWidget(idx, wrap)
        self._scroll_to_bottom()
        return bubble

    def _finish_stream(self):
        self._stream_bubble = None

    def _scroll_to_bottom(self):
        QTimer.singleShot(30, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _after_hide(self):
        self.hide()
        self.setWindowOpacity(1.0)
        self._closing = False
        self.dismissed.emit()

    def _stop_anim(self):
        if self._anim_group is not None:
            self._anim_group.stop()
            self._anim_group = None

    def _submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        # Stay open — conversation continues here.
        self.submitted.emit(text)
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _quota_text(self) -> str:
        try:
            from pathlib import Path
            import json
            path = Path(__file__).resolve().parents[1] / "runtime" / "usage_state.json"
            daily = 300
            try:
                keys = json.loads(
                    (Path(__file__).resolve().parents[1] / "config" / "api_keys.json").read_text()
                )
                daily = int((keys.get("free_limits") or {}).get("daily", 300))
            except Exception:
                pass
            used = 0
            if path.exists():
                data = json.loads(path.read_text())
                used = int(data.get("used_day", 0))
            left = max(0, daily - used)
            return f"{left} left"
        except Exception:
            return "Ready"

    def _place_on_screen(self) -> None:
        settings = ws.get_settings()
        x = settings.get("overlay_x")
        y = settings.get("overlay_y")
        h = self.height()
        screen = QGuiApplication.screenAt(QPoint(int(x or 0), int(y or 0)))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)

        if x is None or y is None:
            nx = avail.x() + (avail.width() - _OVERLAY_W) // 2
            ny = avail.y() + int(avail.height() * 0.12)
        else:
            nx, ny = int(x), int(y)
            nx = min(max(nx, avail.x() + 8), avail.x() + avail.width() - _OVERLAY_W - 8)
            ny = min(max(ny, avail.y() + 8), avail.y() + avail.height() - h - 8)
        self.move(nx, ny)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide_animated()
            e.accept()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(e.position().toPoint())
            # Don't start drag from input / buttons
            if child is self._input or (child and self._input_wrap.isAncestorOf(child)):
                super().mousePressEvent(e)
                return
            self._drag_origin = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_origin is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_origin)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag_origin is not None:
            self._drag_origin = None
            self.remember_position()
        super().mouseReleaseEvent(e)

    def changeEvent(self, e):
        # Click-away disabled by default so voice + replies can continue.
        if (
            getattr(self, "_click_away", False)
            and e.type() == QEvent.Type.ActivationChange
            and self.isVisible()
            and not self.isActiveWindow()
            and not getattr(self, "_closing", False)
            and not getattr(self, "_busy", False)
        ):
            QTimer.singleShot(180, self._maybe_hide_on_focus_loss)
        super().changeEvent(e)

    def _maybe_hide_on_focus_loss(self):
        if (
            self._click_away
            and self.isVisible()
            and not self.isActiveWindow()
            and not self._closing
            and not self._busy
        ):
            self.hide_animated()

    def closeEvent(self, e):
        e.ignore()
        self.hide_animated()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._meter.isVisible():
            self.set_voice_level(self._voice_level)
