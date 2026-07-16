"""Minimal Coming Soon placeholder — Voice / Skills / Automations."""
from __future__ import annotations

import platform

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


_PAGE = "#0a0d12"
_INK = "#FFFFFF"
_MUTED = "#9CA3AF"


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
    f = QFont(family, size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 96)
    return f


class AlmostReadyView(QWidget):
    """Centered placeholder: almost ready / coming soon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AlmostReadyView")
        self.setStyleSheet(f"QWidget#AlmostReadyView {{ background: {_PAGE}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.setSpacing(14)
        lay.addStretch(1)

        title = QLabel("Coming soon")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(_sans(56, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_INK}; background: transparent; border: none;")
        lay.addWidget(title)

        sub = QLabel("Almost ready — launching soon.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(_sans(16, QFont.Weight.Medium))
        sub.setStyleSheet(f"color: {_MUTED}; background: transparent; border: none;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        lay.addStretch(1)
