"""Reusable premium onboarding primitives (light split-pane language)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui.onboarding import tokens as T


def aura_logo(size: int = 88) -> QLabel:
    """AURA brand mark — never fall back to a plain letter if the PNG ships."""
    lab = QLabel()
    lab.setFixedSize(size, size)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setStyleSheet("background: transparent; border: none;")
    try:
        from jarvis_ui.paths import brand_asset_path

        candidate = brand_asset_path(
            "aura_logo_onboarding.png",
            "aura_logo.png",
            "aura_logo_square_bg.png",
        )
    except Exception:
        candidate = None
        root = Path(__file__).resolve().parents[2]
        for name in (
            "aura_logo_onboarding.png",
            "aura_logo.png",
            "aura_logo_square_bg.png",
        ):
            p = root / "assets" / name
            if p.is_file():
                candidate = p
                break
    if candidate is not None:
        pm = QPixmap(str(candidate))
        if not pm.isNull():
            lab.setPixmap(
                pm.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return lab
    # Last resort only — means assets were not packaged.
    lab.setText("A")
    lab.setFont(T.display(max(12, size // 2), QFont.Weight.Bold))
    lab.setStyleSheet(
        f"color: {T.CYAN}; background: rgba(0,183,224,0.12); border-radius: {size // 4}px;"
    )
    return lab


class NaturePanel(QWidget):
    """Soft procedural 'meadow' backdrop — organic, not a stock photo clone."""

    def __init__(self, parent=None, *, dusk: bool = False):
        super().__init__(parent)
        self._dusk = dusk
        self._t = 0.0
        self._anim = QPropertyAnimation(self, b"phase")
        self._anim.setDuration(8000)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def get_phase(self) -> float:
        return self._t

    def set_phase(self, v: float) -> None:
        self._t = float(v)
        self.update()

    phase = pyqtProperty(float, get_phase, set_phase)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w * 0.2, h)
        if self._dusk:
            g.setColorAt(0.0, QColor(28, 42, 38))
            g.setColorAt(0.45, QColor(46, 78, 58))
            g.setColorAt(1.0, QColor(18, 24, 32))
        else:
            g.setColorAt(0.0, QColor(120, 168, 92))
            g.setColorAt(0.35, QColor(78, 140, 62))
            g.setColorAt(0.7, QColor(42, 110, 54))
            g.setColorAt(1.0, QColor(28, 72, 40))
        p.fillRect(self.rect(), g)

        # Soft sun bloom
        bloom = QPainterPath()
        ox = w * (0.7 + 0.04 * self._t)
        oy = h * (0.18 - 0.02 * self._t)
        bloom.addEllipse(QRectF(ox - 90, oy - 90, 220, 220))
        p.fillPath(bloom, QColor(255, 240, 180, 40 if not self._dusk else 18))

        # Blades / texture strokes
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(28):
            x = (i * 37 + int(self._t * 20)) % max(w, 1)
            y = h * 0.55 + (i % 5) * 18
            path = QPainterPath()
            path.moveTo(x, h)
            path.quadTo(x + 8, y, x + 3, y - 40 - (i % 7) * 6)
            path.quadTo(x - 4, y, x - 2, h)
            alpha = 28 + (i % 4) * 8
            p.fillPath(path, QColor(20, 60, 30, alpha))
        p.end()


class ProgressDots(QWidget):
    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self._total = max(1, total)
        self._index = 0
        self.setFixedHeight(8)

    def set_index(self, index: int) -> None:
        self._index = max(0, min(index, self._total - 1))
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap = 7
        size = 6
        total_w = self._total * size + (self._total - 1) * gap
        x0 = (self.width() - total_w) / 2
        y = (self.height() - size) / 2
        for i in range(self._total):
            x = x0 + i * (size + gap)
            if i == self._index:
                p.setBrush(QColor(T.INK))
            else:
                p.setBrush(QColor(20, 20, 20, 40))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x, y, size, size))
        p.end()


class BlackPillButton(QPushButton):
    def __init__(self, text: str, parent=None, *, wide: bool = True):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(T.sans(14, QFont.Weight.DemiBold))
        self.setFixedHeight(52)
        if wide:
            self.setMinimumWidth(240)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {T.INK};
                color: white;
                border: none;
                border-radius: 16px;
                padding: 0 28px;
            }}
            QPushButton:hover {{ background: #2a2a2a; }}
            QPushButton:pressed {{ background: #000; }}
            QPushButton:disabled {{
                background: #4a4a4a;
                color: rgba(255, 255, 255, 0.72);
            }}
            """
        )


class GhostButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(T.sans(12, QFont.Weight.DemiBold))
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {T.MUTED};
                border: none;
                padding: 0 10px;
            }}
            QPushButton:hover {{ color: {T.INK}; }}
            """
        )


class SoftCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SoftCard")
        self.setStyleSheet(
            f"""
            QFrame#SoftCard {{
                background: white;
                border: 1px solid {T.LINE};
                border-radius: 18px;
            }}
            """
        )


class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setStyleSheet(
            f"""
            QFrame#GlassCard {{
                background: {T.GLASS};
                border: 1px solid {T.GLASS_BORDER};
                border-radius: 22px;
            }}
            """
        )


class TipBubble(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("TipBubble")
        self.setStyleSheet(
            f"""
            QFrame#TipBubble {{
                background: {T.TIP_BG};
                border-radius: 14px;
                border: none;
            }}
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        icon = QLabel("✦")
        icon.setStyleSheet(f"color: {T.TIP_TEXT}; background: transparent; border: none;")
        lay.addWidget(icon)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setFont(T.sans(12))
        lab.setStyleSheet(f"color: {T.TIP_TEXT}; background: transparent; border: none;")
        lay.addWidget(lab, 1)


class StatusChip(QLabel):
    def __init__(self, text: str = "Allowed", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(30)
        self.setMinimumWidth(84)
        self.setFont(T.sans(12, QFont.Weight.DemiBold))
        self.set_allowed(False)

    def set_allowed(self, allowed: bool) -> None:
        if allowed:
            self.setText("Allowed")
            self.setStyleSheet(
                f"""
                QLabel {{
                    background: white;
                    color: {T.INK};
                    border: 1px solid {T.LINE};
                    border-radius: 15px;
                    padding: 0 12px;
                }}
                """
            )
        else:
            self.setText("Allow")
            self.setStyleSheet(
                f"""
                QLabel {{
                    background: {T.INK};
                    color: white;
                    border: none;
                    border-radius: 15px;
                    padding: 0 12px;
                }}
                """
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)


class PermissionRow(QFrame):
    toggled = pyqtSignal(str)

    def __init__(self, key: str, title: str, body: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._on = False
        self.setObjectName("PermissionRow")
        self.setStyleSheet(
            f"""
            QFrame#PermissionRow {{
                background: white;
                border: 1px solid {T.LINE};
                border-radius: 16px;
            }}
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setFont(T.sans(14, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        b = QLabel(body)
        b.setFont(T.sans(12))
        b.setWordWrap(True)
        b.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
        col.addWidget(t)
        col.addWidget(b)
        lay.addLayout(col, 1)
        self._chip = StatusChip()
        lay.addWidget(self._chip)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._on:
            self._on = True
            self._chip.set_allowed(True)
            self.toggled.emit(self._key)
        super().mousePressEvent(event)


class KeyCap(QLabel):
    def __init__(self, top: str, bottom: str = "", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(108, 108)
        if bottom:
            self.setText(f"{top}\n{bottom}")
        else:
            self.setText(top)
        self.setFont(T.sans(15, QFont.Weight.DemiBold))
        self.setStyleSheet(
            f"""
            QLabel {{
                background: #F3F0E8;
                color: {T.INK};
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 18px;
            }}
            """
        )


class FadePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

    def play_enter(self) -> None:
        self._fx.setOpacity(0.0)
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(T.ANIM_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim = anim
        anim.start()


class SplitPage(FadePage):
    """Cream left narrative + nature right showcase."""

    def __init__(self, parent=None, *, dusk: bool = False):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.left = QWidget()
        self.left.setObjectName("SplitLeft")
        self.left.setStyleSheet(f"QWidget#SplitLeft {{ background: {T.CREAM}; }}")
        self.left_layout = QVBoxLayout(self.left)
        self.left_layout.setContentsMargins(44, 36, 40, 36)
        self.left_layout.setSpacing(0)

        self.right = QWidget()
        self.right.setObjectName("SplitRight")
        rr = QVBoxLayout(self.right)
        rr.setContentsMargins(0, 0, 0, 0)
        self.nature = NaturePanel(dusk=dusk)
        rr.addWidget(self.nature)
        self.right_overlay = QVBoxLayout(self.nature)
        self.right_overlay.setContentsMargins(28, 36, 28, 36)
        self.right_overlay.setSpacing(14)

        outer.addWidget(self.left, 42)
        outer.addWidget(self.right, 58)

    def set_brand(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(10)
        mark = aura_logo(28)
        row.addWidget(mark)
        name = QLabel("AURA")
        name.setFont(T.sans(15, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        row.addWidget(name)
        row.addStretch(1)
        self.left_layout.addLayout(row)
        self.left_layout.addSpacing(36)


def title_html(main: str, italic_word: str | None = None) -> QLabel:
    """Editorial headline; optional italic middle word like Welcome *to* AURA."""
    lab = QLabel()
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setWordWrap(True)
    if italic_word and italic_word in main:
        parts = main.split(italic_word, 1)
        html = (
            f"<span style='color:{T.INK}; font-size:34px; font-weight:700;'>"
            f"{parts[0]}<i>{italic_word}</i>{parts[1]}</span>"
        )
    else:
        html = (
            f"<span style='color:{T.INK}; font-size:34px; font-weight:700;'>{main}</span>"
        )
    lab.setText(html)
    lab.setStyleSheet("background: transparent; border: none;")
    return lab


def muted(text: str, size: int = 14) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setFont(T.sans(size))
    lab.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
    return lab
