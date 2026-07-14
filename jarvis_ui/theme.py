"""Screenshot-matched JARVIS design tokens."""
from __future__ import annotations

import platform

# Classic JARVIS navy / cyan palette (pleasant blue, not charcoal-black).
BG = "#050a14"
BG_PANEL = "#08121c"
BG_CARD = "#0c1824"
BG_ELEVATED = "#102030"
BORDER = "#143040"
BORDER_HI = "#1e4a62"
CYAN = "#00d1ff"
CYAN_DIM = "#0a6a88"
GREEN = "#00ff94"
GREEN_DIM = "#0a5c40"
ORANGE = "#ff5c00"
RED = "#ff4466"
TEXT = "#c8eeff"
TEXT_DIM = "#5a8fa8"
TEXT_MED = "#7eb8d4"
WHITE = "#e8f8ff"

SIDEBAR_W = 240
RIGHT_W = 320
FONT_UI = "Menlo"
FONT_DISPLAY = "Courier New"

# Sidebar — compact SaaS layout, classic cyan accents
SB_FONT = "SF Pro Text"
SB_PAD = 6
SB_ROW_H = 32
SB_ICON = 16
SB_FONT_SIZE = 13
SB_SECTION_SIZE = 10
SB_ACCENT = CYAN
SB_ACCENT_SOFT = "rgba(0, 209, 255, 0.10)"
SB_ACCENT_BORDER = "rgba(0, 209, 255, 0.22)"
SB_HOVER = "rgba(0, 209, 255, 0.06)"
SB_TEXT = "#c8eeff"
SB_TEXT_ACTIVE = "#e8f8ff"
SB_TEXT_MUTED = "#5a8fa8"
SB_STATUS_ON = GREEN
SB_STATUS_OFF = "#3d5a6e"
SB_MIN_W = 200
SB_MAX_W = 300
SB_DEFAULT_W = 220

# Chat center panel — same navy family
CHAT_FONT = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
CHAT_FONT_MONO = "Menlo" if platform.system() == "Darwin" else "Consolas"
CHAT_BG = BG
CHAT_MAX_WIDTH = 1200
CHAT_SIDE_PAD = 48
CHAT_USER_MAX_W = 420
CHAT_BUBBLE = BG_CARD
CHAT_ASSIST_CARD = CHAT_BUBBLE
CHAT_ASSIST_ACCENT = CYAN
CHAT_TEXT = WHITE
CHAT_TEXT_DIM = TEXT_DIM
CHAT_BORDER = BORDER
CHAT_ACCENT = CHAT_ASSIST_ACCENT
CHAT_MSG_SPACING = 22
CHAT_BUBBLE_RADIUS = 20

# Input bar — pill
CHAT_BAR_MAX_WIDTH = 768
CHAT_BAR_HEIGHT = 52
CHAT_BAR_BG = CHAT_BUBBLE
CHAT_BAR_TEXT = WHITE
CHAT_BAR_PLACEHOLDER = TEXT_DIM
CHAT_BAR_ICON = TEXT_MED

CHAT_INPUT_BG = CHAT_BAR_BG
CHAT_INPUT_BORDER = BORDER
CHAT_RADIUS = 18
CHAT_ANIM_MS = 180
