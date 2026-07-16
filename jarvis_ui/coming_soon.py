"""Coming Soon roadmap — premium SaaS-style future of AURA."""
from __future__ import annotations

import platform

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtProperty,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)


_PAGE = "#F9F8F3"
_CARD = "#FFFFFF"
_INK = "#141414"
_MUTED = "#6B7280"
_SOFT = "#9CA3AF"
_BORDER = "#EBE8E1"
_BADGE_BG = "#F3F1EB"
_ACCENT = "#111111"


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
    f = QFont(family, size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
    return f


FEATURES: list[dict] = [
    {
        "icon": "🎨",
        "title": "AI Image Studio",
        "body": (
            "Generate stunning images, product photos, logos, illustrations, "
            "marketing creatives, social media posts, and professional graphics in seconds."
        ),
    },
    {
        "icon": "🎬",
        "title": "AI Video Studio",
        "body": (
            "Create cinematic videos, commercials, YouTube Shorts, TikToks, advertisements, "
            "animations, product showcases, and more — all powered by AI."
        ),
    },
    {
        "icon": "💼",
        "title": "AI Career Assistant",
        "body": (
            "Your personal career advisor. AURA will analyze your experience, skills, goals, "
            "and location to find better jobs, improve your resume, prep interviews, "
            "apply automatically, and track applications."
        ),
    },
    {
        "icon": "💰",
        "title": "AI Income Finder",
        "body": (
            "Discover personalized income opportunities based on your experience, skills, "
            "interests, and available time — freelance, remote jobs, side businesses, "
            "and passive income ideas tailored to you."
        ),
    },
    {
        "icon": "📈",
        "title": "Market Intelligence",
        "body": (
            "Stay ahead of the market. AURA monitors trending industries, growing businesses, "
            "emerging technologies, new business ideas, market demand, and high-growth opportunities."
        ),
    },
    {
        "icon": "🤖",
        "title": "Autonomous AI Agent",
        "body": (
            "Your AI won't just answer questions — it will work for you. Research, complete "
            "repetitive tasks, write documents, organize files, manage projects, and automate workflows."
        ),
    },
    {
        "icon": "🌍",
        "title": "Universal Translator",
        "body": (
            "Write, speak, and communicate naturally in dozens of languages with AI-powered "
            "translation and localization. Perfect for work, travel, and global communication."
        ),
    },
    {
        "icon": "📄",
        "title": "AI Workspace",
        "body": (
            "Generate and edit documents, presentations, PDFs, reports, Excel spreadsheets, "
            "business plans, and contracts — everything in one place."
        ),
    },
    {
        "icon": "🌐",
        "title": "Smart Web Research",
        "body": (
            "Instead of searching the internet yourself, AURA will search, analyze, compare, "
            "summarize, verify sources, and provide the final answer in seconds."
        ),
    },
    {
        "icon": "📅",
        "title": "Intelligent Productivity",
        "body": (
            "One place to manage everything: calendar, notes, reminders, tasks, goals, "
            "and daily planning — powered entirely by AI."
        ),
    },
    {
        "icon": "🧑‍💻",
        "title": "AI Developer",
        "body": (
            "Build websites, mobile apps, automations, scripts, APIs, and complete software "
            "projects with AI assistance. From idea to production."
        ),
    },
    {
        "icon": "📣",
        "title": "Marketing & Content",
        "body": (
            "Generate ads, landing pages, email campaigns, SEO content, social media posts, "
            "video scripts, and product descriptions designed to help businesses grow faster."
        ),
    },
    {
        "icon": "🏢",
        "title": "Business Assistant",
        "body": (
            "Automate everyday business operations: customer support, emails, scheduling, "
            "reports, CRM updates, research, and internal documentation — handled by AI."
        ),
    },
]

VISION_POINTS = [
    ("✨", "Create faster"),
    ("💼", "Build better careers"),
    ("💰", "Increase their income"),
    ("📈", "Discover new opportunities"),
    ("🎨", "Generate professional content"),
    ("🤖", "Automate repetitive work"),
    ("📚", "Learn new skills"),
    ("🚀", "Start and grow businesses"),
    ("⏳", "Save valuable time every day"),
]


class _FeatureCard(QFrame):
    def __init__(self, icon: str, title: str, body: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setStyleSheet(
            f"QFrame#FeatureCard {{"
            f"  background: {_CARD};"
            f"  border: 1px solid {_BORDER};"
            f"  border-radius: 22px;"
            f"}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 20)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        ic = QLabel(icon)
        ic.setFont(QFont(_sans(22).family(), 22))
        ic.setStyleSheet("background: transparent; border: none;")
        top.addWidget(ic)
        top.addStretch()
        badge = QLabel("Coming Soon")
        badge.setFont(_sans(10, QFont.Weight.DemiBold))
        badge.setStyleSheet(
            f"color: {_SOFT}; background: {_BADGE_BG}; border: none; "
            f"border-radius: 999px; padding: 4px 10px;"
        )
        top.addWidget(badge)
        lay.addLayout(top)

        h = QLabel(title)
        h.setFont(_sans(16, QFont.Weight.DemiBold))
        h.setStyleSheet(f"color: {_INK}; background: transparent; border: none;")
        h.setWordWrap(True)
        lay.addWidget(h)

        d = QLabel(body)
        d.setFont(_sans(13))
        d.setStyleSheet(f"color: {_MUTED}; background: transparent; border: none;")
        d.setWordWrap(True)
        d.setMinimumHeight(72)
        lay.addWidget(d)
        lay.addStretch(1)


class _FadeLabel(QLabel):
    """Soft opacity pulse for the footer tagline."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._opacity = 1.0

    def getOpacity(self) -> float:
        return self._opacity

    def setOpacity(self, value: float):
        self._opacity = value
        # Approximate fade via text color alpha
        a = max(0.35, min(1.0, value))
        # ink with alpha via rgba
        self.setStyleSheet(
            f"color: rgba(20,20,20,{a:.2f}); background: transparent; border: none;"
        )

    opacity = pyqtProperty(float, getOpacity, setOpacity)


class ComingSoonView(QWidget):
    """Opened from sidebar More — roadmap of upcoming AURA capabilities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ComingSoonView")
        self.setStyleSheet(f"QWidget#ComingSoonView {{ background: {_PAGE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_PAGE}; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}"
            f"QScrollBar::handle:vertical {{ background: #D8D4CB; border-radius: 4px; min-height: 36px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        page = QWidget()
        page.setStyleSheet(f"background: {_PAGE};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 48, 48, 64)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        inner = QWidget()
        inner.setMaximumWidth(980)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)

        # —— Hero: Coming soon ——
        hero = QLabel("Coming soon")
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hf = _sans(56, QFont.Weight.Bold)
        hf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 96)
        hero.setFont(hf)
        hero.setStyleSheet(f"color: {_INK}; background: transparent; border: none;")
        il.addWidget(hero)
        il.addSpacing(18)

        hero_sub = QLabel("The Future of AURA")
        hero_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_sub.setFont(_sans(15, QFont.Weight.Medium))
        hero_sub.setStyleSheet(f"color: {_MUTED}; background: transparent;")
        il.addWidget(hero_sub)
        il.addSpacing(40)

        # —— Intro ——
        intro_card = QFrame()
        intro_card.setObjectName("IntroCard")
        intro_card.setStyleSheet(
            f"QFrame#IntroCard {{ background: {_CARD}; border: 1px solid {_BORDER}; "
            f"border-radius: 28px; }}"
        )
        icl = QVBoxLayout(intro_card)
        icl.setContentsMargins(36, 32, 36, 32)
        icl.setSpacing(14)

        intro_kicker = QLabel("🚀  More than an AI assistant.")
        intro_kicker.setFont(_sans(18, QFont.Weight.DemiBold))
        intro_kicker.setStyleSheet(f"color: {_INK}; background: transparent;")
        intro_kicker.setWordWrap(True)
        icl.addWidget(intro_kicker)

        intro_body = QLabel(
            "We're building an intelligent platform designed to help you work smarter, "
            "create faster, earn more, and automate everyday life.\n\n"
            "This is just the beginning.\n\n"
            "New capabilities are constantly being developed and will be released over time."
        )
        intro_body.setFont(_sans(14))
        intro_body.setStyleSheet(f"color: {_MUTED}; background: transparent;")
        intro_body.setWordWrap(True)
        icl.addWidget(intro_body)
        il.addWidget(intro_card)
        il.addSpacing(48)

        # —— Section: Coming Soon features ——
        sec = QLabel("✨  Coming Soon")
        sec.setFont(_sans(22, QFont.Weight.Bold))
        sec.setStyleSheet(f"color: {_INK}; background: transparent;")
        il.addWidget(sec)
        sec_sub = QLabel("A growing suite of AI capabilities — shipping over time.")
        sec_sub.setFont(_sans(13))
        sec_sub.setStyleSheet(f"color: {_MUTED}; background: transparent; margin-top: 4px;")
        il.addWidget(sec_sub)
        il.addSpacing(20)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i, feat in enumerate(FEATURES):
            card = _FeatureCard(feat["icon"], feat["title"], feat["body"])
            grid.addWidget(card, i // 2, i % 2)
        il.addLayout(grid)
        il.addSpacing(56)

        # —— Vision ——
        vision_title = QLabel("🌍  Our Vision")
        vision_title.setFont(_sans(22, QFont.Weight.Bold))
        vision_title.setStyleSheet(f"color: {_INK}; background: transparent;")
        il.addWidget(vision_title)
        il.addSpacing(8)
        vision_lead = QLabel(
            "We don't want to build another chatbot.\n"
            "We're building an intelligent operating system that helps people:"
        )
        vision_lead.setFont(_sans(14))
        vision_lead.setStyleSheet(f"color: {_MUTED}; background: transparent;")
        vision_lead.setWordWrap(True)
        il.addWidget(vision_lead)
        il.addSpacing(16)

        vision_card = QFrame()
        vision_card.setObjectName("VisionCard")
        vision_card.setStyleSheet(
            f"QFrame#VisionCard {{ background: {_CARD}; border: 1px solid {_BORDER}; "
            f"border-radius: 28px; }}"
        )
        vl = QVBoxLayout(vision_card)
        vl.setContentsMargins(28, 24, 28, 24)
        vl.setSpacing(12)
        for icon, text in VISION_POINTS:
            row = QHBoxLayout()
            row.setSpacing(12)
            ei = QLabel(icon)
            ei.setFixedWidth(28)
            ei.setStyleSheet("background: transparent;")
            row.addWidget(ei)
            et = QLabel(text)
            et.setFont(_sans(14, QFont.Weight.Medium))
            et.setStyleSheet(f"color: {_INK}; background: transparent;")
            row.addWidget(et, stretch=1)
            vl.addLayout(row)
        il.addWidget(vision_card)
        il.addSpacing(20)

        goal = QLabel("Our goal is simple:\nOne AI. Unlimited possibilities.")
        goal.setAlignment(Qt.AlignmentFlag.AlignCenter)
        goal.setFont(_sans(18, QFont.Weight.DemiBold))
        goal.setStyleSheet(f"color: {_INK}; background: transparent;")
        il.addWidget(goal)
        il.addSpacing(48)

        # —— Footer animated block ——
        footer = QFrame()
        footer.setObjectName("SoonFooter")
        footer.setStyleSheet(
            f"QFrame#SoonFooter {{"
            f"  background: {_CARD};"
            f"  border: 1px solid {_BORDER};"
            f"  border-radius: 32px;"
            f"}}"
        )
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(40, 40, 40, 40)
        fl.setSpacing(14)

        self._footer_title = _FadeLabel("AURA is just getting started.")
        self._footer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer_title.setFont(_sans(26, QFont.Weight.Bold))
        self._footer_title.setWordWrap(True)
        fl.addWidget(self._footer_title)

        footer_body = QLabel(
            "Every month, new AI capabilities will be added to make AURA more powerful, "
            "more intelligent, and more useful.\n\nThe best is yet to come. ✨"
        )
        footer_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_body.setFont(_sans(14))
        footer_body.setStyleSheet(f"color: {_MUTED}; background: transparent;")
        footer_body.setWordWrap(True)
        fl.addWidget(footer_body)
        il.addWidget(footer)

        lay.addWidget(inner)
        scroll.setWidget(page)
        root.addWidget(scroll)

        self._pulse = QPropertyAnimation(self._footer_title, b"opacity", self)
        self._pulse.setDuration(2200)
        self._pulse.setStartValue(0.45)
        self._pulse.setEndValue(1.0)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)
        # Ping-pong via direction reverse on finished isn't built-in for loop;
        # use keyframes instead.
        self._pulse.setKeyValueAt(0.0, 0.45)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setKeyValueAt(1.0, 0.45)
        QTimer.singleShot(400, self._pulse.start)

    def showEvent(self, e):
        super().showEvent(e)
        if self._pulse.state() != QPropertyAnimation.State.Running:
            self._pulse.start()
