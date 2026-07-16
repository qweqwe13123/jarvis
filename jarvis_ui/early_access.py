"""Early Access gate — Website Builder / Code Assistant unlock after founding clients."""
from __future__ import annotations

import platform

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
    f = QFont(family, size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
    return f


class EarlyAccessView(QWidget):
    """Centered early-access hold page for gated builder features."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EarlyAccessView")
        self.setStyleSheet(
            f"QWidget#EarlyAccessView {{ background: {T.BG}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(56, 56, 56, 56)
        root.setSpacing(0)
        root.addStretch(2)

        self._stage = QWidget()
        self._stage.setMaximumWidth(560)
        stage = QVBoxLayout(self._stage)
        stage.setContentsMargins(0, 0, 0, 0)
        stage.setSpacing(0)
        stage.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        badge = QLabel("EARLY ACCESS")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(_sans(11, QFont.Weight.DemiBold))
        badge.setStyleSheet(
            f"color: {T.CYAN}; background: transparent; border: none; "
            "letter-spacing: 2.4px;"
        )
        stage.addWidget(badge)
        stage.addSpacing(22)

        self._title = QLabel("Opening after the first 10 clients")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setFont(_sans(34, QFont.Weight.Bold))
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"color: {T.WHITE}; background: transparent; border: none;"
        )
        stage.addWidget(self._title)
        stage.addSpacing(18)

        rule = QFrame()
        rule.setFixedSize(48, 2)
        rule.setStyleSheet(
            f"background: {T.CYAN}; border: none; border-radius: 1px;"
        )
        stage.addWidget(rule, 0, Qt.AlignmentFlag.AlignHCenter)
        stage.addSpacing(22)

        self._body = QLabel(
            "Website Builder and Code Assistant will unlock with every feature "
            "once we welcome our first 10 clients."
        )
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setFont(_sans(16, QFont.Weight.Normal))
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"color: {T.TEXT_MED}; background: transparent; border: none;"
        )
        stage.addWidget(self._body)
        stage.addSpacing(28)

        thanks = QLabel("Thank you for your patience.")
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thanks.setFont(_sans(15, QFont.Weight.Medium))
        thanks.setStyleSheet(
            f"color: {T.TEXT}; background: transparent; border: none;"
        )
        stage.addWidget(thanks)
        stage.addSpacing(36)

        progress = QLabel("0  /  10  founding clients")
        progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress.setFont(_sans(12, QFont.Weight.Medium))
        progress.setStyleSheet(
            f"color: {T.TEXT_DIM}; background: transparent; border: none; "
            "letter-spacing: 1.1px;"
        )
        stage.addWidget(progress)

        root.addWidget(self._stage, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(3)

        self._opacity = QGraphicsOpacityEffect(self._stage)
        self._opacity.setOpacity(0.0)
        self._stage.setGraphicsEffect(self._opacity)
        self._fade_anim: QPropertyAnimation | None = None

    def set_feature(self, name: str) -> None:
        """Optionally tailor the body copy to a single gated feature."""
        name = (name or "").strip()
        if not name:
            return
        self._body.setText(
            f"{name} will unlock with every feature "
            "once we welcome our first 10 clients."
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in()

    def _fade_in(self) -> None:
        if self._fade_anim is not None:
            self._fade_anim.stop()
        self._opacity.setOpacity(0.0)
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(450)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._fade_anim = anim
