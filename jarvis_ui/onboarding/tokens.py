"""AURA onboarding visual language — light, editorial, split-pane.

Inspired by premium desktop AI onboarding (space, cream canvas, glass panels)
but branded for AURA: cyan accents, AURA mark, unique copy and layouts.
"""

from __future__ import annotations

import platform

from PyQt6.QtGui import QColor, QFont

# Cream / bone canvas (not stark white)
CREAM = "#F6F4EF"
CREAM_SOFT = "#FBFAF7"
INK = "#141414"
INK_SOFT = "#3A3A3A"
MUTED = "#7A7A72"
LINE = "rgba(20,20,20,0.08)"
LINE_SOFT = "rgba(20,20,20,0.05)"
CHIP = "#EFEDE7"
CHIP_BORDER = "rgba(20,20,20,0.10)"

# AURA accent (keep brand, not purple clone)
CYAN = "#00B7E0"
CYAN_DEEP = "#007A99"
GLASS = "rgba(12, 18, 24, 0.55)"
GLASS_BORDER = "rgba(255,255,255,0.14)"
TIP_BG = "#2A2218"
TIP_TEXT = "#E8D9C0"

WIN_W = 1080
WIN_H = 700
LEFT_RATIO = 0.42
ANIM_MS = 260


def sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
    f = QFont(family, size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def display(size: int, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    f = sans(size, weight)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)
    return f


def q(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c
