"""Cursor-style Pro subscription gate — dark centered card after onboarding."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui.onboarding.widgets import FadePage

PRO_PRICE = "$20"
PRO_PERIOD = "/ month"


class CursorProGatePage(FadePage):
    """Premium dark modal: subscribe for unlimited AURA desktop."""

    unlocked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CursorProGate")
        self.setStyleSheet(
            """
            QWidget#CursorProGate {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a0a, stop:0.45 #111111, stop:1 #0d1117
                );
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 40, 32, 40)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("ProCard")
        card.setFixedWidth(440)
        card.setStyleSheet(
            """
            QFrame#ProCard {
                background: #141414;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 16px;
            }
            """
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 32, 32, 28)
        card_lay.setSpacing(0)

        badge = QLabel("PRO REQUIRED")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.DemiBold))
        badge.setStyleSheet(
            "color: #a1a1aa; background: transparent; letter-spacing: 2px;"
        )
        card_lay.addWidget(badge)
        card_lay.addSpacing(14)

        title = QLabel("Unlimited AURA")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(".AppleSystemUIFont", 26, QFont.Weight.Bold))
        title.setStyleSheet("color: #fafafa; background: transparent;")
        card_lay.addWidget(title)
        card_lay.addSpacing(10)

        subtitle = QLabel(
            "Subscribe to Pro to unlock the desktop app without limits — "
            "voice, agents, computer use, and memory."
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(QFont(".AppleSystemUIFont", 13))
        subtitle.setStyleSheet("color: #a1a1aa; background: transparent;")
        card_lay.addWidget(subtitle)
        card_lay.addSpacing(22)

        price_row = QHBoxLayout()
        price_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price = QLabel(PRO_PRICE)
        price.setFont(QFont(".AppleSystemUIFont", 40, QFont.Weight.Bold))
        price.setStyleSheet("color: #ffffff; background: transparent;")
        period = QLabel(PRO_PERIOD)
        period.setFont(QFont(".AppleSystemUIFont", 14))
        period.setStyleSheet("color: #71717a; background: transparent; padding-top: 18px;")
        price_row.addWidget(price)
        price_row.addSpacing(6)
        price_row.addWidget(period)
        card_lay.addLayout(price_row)
        card_lay.addSpacing(6)

        note = QLabel("Billed monthly · Cancel anytime · Same Google account as the website")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setFont(QFont(".AppleSystemUIFont", 11))
        note.setStyleSheet("color: #52525b; background: transparent;")
        card_lay.addWidget(note)
        card_lay.addSpacing(22)

        features = [
            "Unlimited desktop assistant sessions",
            "Voice, agents, browser & computer control",
            "Higher cloud limits synced with your account",
            "Priority updates for the Mac app",
        ]
        for text in features:
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel("✓")
            check.setFixedWidth(18)
            check.setStyleSheet("color: #22c55e; background: transparent; font-weight: 700;")
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setFont(QFont(".AppleSystemUIFont", 13))
            lab.setStyleSheet("color: #d4d4d8; background: transparent;")
            row.addWidget(check)
            row.addWidget(lab, 1)
            card_lay.addLayout(row)
            card_lay.addSpacing(8)

        card_lay.addSpacing(14)

        self._status = QLabel("Finish setup, then unlock Pro to continue.")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(QFont(".AppleSystemUIFont", 12))
        self._status.setStyleSheet("color: #71717a; background: transparent;")
        card_lay.addWidget(self._status)
        card_lay.addSpacing(18)

        self._subscribe = QPushButton("Subscribe — $20 / month")
        self._subscribe.setCursor(Qt.CursorShape.PointingHandCursor)
        self._subscribe.setFixedHeight(44)
        self._subscribe.setFont(QFont(".AppleSystemUIFont", 13, QFont.Weight.DemiBold))
        self._subscribe.setStyleSheet(
            """
            QPushButton {
                background: #fafafa;
                color: #0a0a0a;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover { background: #e4e4e7; }
            QPushButton:pressed { background: #d4d4d8; }
            """
        )
        self._subscribe.clicked.connect(self._upgrade)
        card_lay.addWidget(self._subscribe)
        card_lay.addSpacing(10)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)

        self._refresh_btn = QPushButton("I've subscribed — Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFixedHeight(40)
        self._refresh_btn.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.Medium))
        self._refresh_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #e4e4e7;
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 0 14px;
            }
            QPushButton:hover { border-color: rgba(255,255,255,0.28); background: rgba(255,255,255,0.04); }
            """
        )
        self._refresh_btn.clicked.connect(self._refresh)
        secondary.addWidget(self._refresh_btn)

        self._continue = QPushButton("Continue")
        self._continue.setEnabled(False)
        self._continue.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue.setFixedHeight(40)
        self._continue.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.DemiBold))
        self._continue.setStyleSheet(
            """
            QPushButton {
                background: #27272a;
                color: #52525b;
                border: none;
                border-radius: 10px;
                padding: 0 16px;
            }
            QPushButton:enabled {
                background: #22c55e;
                color: #052e16;
            }
            QPushButton:enabled:hover { background: #4ade80; }
            """
        )
        self._continue.clicked.connect(self._on_continue)
        secondary.addWidget(self._continue)
        card_lay.addLayout(secondary)

        card_lay.addSpacing(14)
        foot = QLabel(
            '<a href="#signin" style="color:#60a5fa; text-decoration:none;">Sign in again</a>'
            "  ·  "
            '<a href="https://www.hiauraai.com/pricing" style="color:#71717a; text-decoration:none;">hiauraai.com/pricing</a>'
        )
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setOpenExternalLinks(False)
        foot.linkActivated.connect(self._on_foot_link)
        foot.setStyleSheet("background: transparent;")
        card_lay.addWidget(foot)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        QTimer.singleShot(180, self._refresh)

    def _set_status(self, text: str, *, unlocked: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {'#4ade80' if unlocked else '#71717a'}; background: transparent;"
        )
        self._continue.setEnabled(unlocked)

    def _upgrade(self) -> None:
        try:
            from jarvis_ui.user_account import start_checkout

            start_checkout("pro")
            self._set_status(
                "Checkout opened in your browser. Complete payment, then tap I've subscribed."
            )
        except Exception as e:
            self._set_status(f"Could not open pricing: {e}")

    def _on_foot_link(self, url: str) -> None:
        if url == "#signin":
            self._resign()
            return
        try:
            from jarvis_ui.user_account import open_pricing

            open_pricing()
        except Exception:
            pass

    def _resign(self) -> None:
        try:
            from jarvis_ui.auth_async import start_sign_in_worker
        except Exception as e:
            self._set_status(f"Sign-in failed: {e}")
            return
        self._set_status("Opening browser for Google sign-in…")
        worker = start_sign_in_worker(self, timeout=180.0, replace_running=True)
        if worker is None:
            return

        def _ok() -> None:
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            self._refresh()

        def _err(msg: str) -> None:
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            if "cancelled" in (msg or "").lower():
                return
            self._set_status(f"Sign-in failed: {msg}")

        worker.succeeded.connect(_ok)
        worker.failed.connect(_err)
        worker.start()

    def _refresh(self) -> None:
        try:
            from jarvis_ui.auth_async import refresh_entitlements_async
            from jarvis_ui.user_account import ensure_paid_access, is_authenticated

            if not is_authenticated():
                self._set_status("Sign in with Google first, then subscribe on the website.")
                return

            def _after(_profile) -> None:
                ok, reason = ensure_paid_access(sync=False)
                if ok:
                    self._set_status(
                        "Pro is active. You're ready — tap Continue.", unlocked=True
                    )
                elif reason == "sign_in":
                    self._set_status("Session expired — use Sign in again.")
                else:
                    self._set_status("Still Free. Subscribe for $20/month, then refresh.")

            self._set_status("Checking subscription…")
            refresh_entitlements_async(_after)
        except Exception as e:
            self._set_status(f"Could not refresh plan: {e}")

    def _on_continue(self) -> None:
        try:
            from jarvis_ui.user_account import ensure_paid_access

            # Local check first (instant); network refresh happens in _refresh.
            ok, _ = ensure_paid_access(sync=False)
        except Exception:
            ok = False
        if ok:
            self.unlocked.emit()
        else:
            self._refresh()


# Keep alias for existing imports
ProSubscribePage = CursorProGatePage
