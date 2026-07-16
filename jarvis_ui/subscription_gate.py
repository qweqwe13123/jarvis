"""Soft Pro subscription gate — dismissible, re-opens on next paid action."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


PRO_PRICE = "$20"
PRO_PERIOD = "/mo"


class SubscriptionGateDialog(QDialog):
    """Cursor-style Pro card. User can leave (“Not now”) and browse the app;
    chat / voice / agents should re-open this dialog until Pro is active.
    """

    unlocked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None, *, reason: str = "preview"):
        super().__init__(parent)
        self.setObjectName("SubscriptionGateDialog")
        self.setWindowTitle("Upgrade to Pro")
        # Window-modal: blocks parent while open, but Esc / Not now closes it
        # so the main UI is usable again afterward.
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(440)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("GateCard")
        card.setStyleSheet(
            """
            QFrame#GateCard {
                background: #121214;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 18px;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 18)
        shadow.setColor(Qt.GlobalColor.black)
        card.setGraphicsEffect(shadow)
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(0)

        header = QHBoxLayout()
        brand = QLabel("AURA")
        brand.setFont(QFont(".AppleSystemUIFont", 11, QFont.Weight.DemiBold))
        brand.setStyleSheet(
            "color: #a1a1aa; background: transparent; letter-spacing: 3px;"
        )
        header.addWidget(brand)
        header.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setToolTip("Back to app")
        close_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #71717a;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.06);
                color: #e4e4e7;
            }
            """
        )
        close_btn.clicked.connect(self._dismiss)
        header.addWidget(close_btn)
        lay.addLayout(header)
        lay.addSpacing(12)

        title = QLabel("Continue with Pro")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(".AppleSystemUIFont", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #fafafa; background: transparent;")
        lay.addWidget(title)
        lay.addSpacing(10)

        if reason == "preview":
            blurb = (
                "You've used your free preview. Subscribe to keep chatting, "
                "speaking with voice, and running agents on your Mac."
            )
        else:
            blurb = (
                "Pro unlocks unlimited desktop sessions — voice, agents, "
                "computer use, and memory synced with your website account."
            )
        subtitle = QLabel(blurb)
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(QFont(".AppleSystemUIFont", 13))
        subtitle.setStyleSheet("color: #a1a1aa; background: transparent;")
        lay.addWidget(subtitle)
        lay.addSpacing(20)

        price_row = QHBoxLayout()
        price_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price = QLabel(PRO_PRICE)
        price.setFont(QFont(".AppleSystemUIFont", 40, QFont.Weight.Bold))
        price.setStyleSheet("color: #ffffff; background: transparent;")
        period = QLabel(PRO_PERIOD)
        period.setFont(QFont(".AppleSystemUIFont", 15))
        period.setStyleSheet(
            "color: #71717a; background: transparent; padding-top: 16px;"
        )
        price_row.addWidget(price)
        price_row.addSpacing(4)
        price_row.addWidget(period)
        lay.addLayout(price_row)
        lay.addSpacing(6)

        billed = QLabel("Billed monthly · Cancel anytime")
        billed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        billed.setFont(QFont(".AppleSystemUIFont", 11))
        billed.setStyleSheet("color: #52525b; background: transparent;")
        lay.addWidget(billed)
        lay.addSpacing(18)

        for text in (
            "Unlimited chat & live voice on desktop",
            "Agents, browser & computer control",
            "Same Google account as hiauraai.com",
            "Priority Mac updates",
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel("✓")
            check.setFixedWidth(18)
            check.setStyleSheet(
                "color: #34d399; background: transparent; font-weight: 700;"
            )
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setFont(QFont(".AppleSystemUIFont", 13))
            lab.setStyleSheet("color: #d4d4d8; background: transparent;")
            row.addWidget(check)
            row.addWidget(lab, 1)
            lay.addLayout(row)
            lay.addSpacing(8)

        lay.addSpacing(10)

        self._status = QLabel("Complete checkout, then refresh your plan.")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(QFont(".AppleSystemUIFont", 12))
        self._status.setStyleSheet("color: #71717a; background: transparent;")
        lay.addWidget(self._status)
        lay.addSpacing(14)

        self._subscribe = QPushButton("Subscribe to Pro")
        self._subscribe.setCursor(Qt.CursorShape.PointingHandCursor)
        self._subscribe.setFixedHeight(46)
        self._subscribe.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.DemiBold))
        self._subscribe.setStyleSheet(
            """
            QPushButton {
                background: #fafafa;
                color: #0a0a0a;
                border: none;
                border-radius: 11px;
            }
            QPushButton:hover { background: #e4e4e7; }
            QPushButton:pressed { background: #d4d4d8; }
            """
        )
        self._subscribe.clicked.connect(self._upgrade)
        lay.addWidget(self._subscribe)
        lay.addSpacing(10)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)

        self._refresh_btn = QPushButton("I've subscribed")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFixedHeight(42)
        self._refresh_btn.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.Medium))
        self._refresh_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #e4e4e7;
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 11px;
            }
            QPushButton:hover {
                border-color: rgba(255,255,255,0.28);
                background: rgba(255,255,255,0.04);
            }
            """
        )
        self._refresh_btn.clicked.connect(self._refresh)
        secondary.addWidget(self._refresh_btn)

        self._signin = QPushButton("Sign in")
        self._signin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signin.setFixedHeight(42)
        self._signin.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.Medium))
        self._signin.setStyleSheet(
            """
            QPushButton {
                background: #1c1c1f;
                color: #e4e4e7;
                border: none;
                border-radius: 11px;
            }
            QPushButton:hover { background: #27272a; }
            """
        )
        self._signin.clicked.connect(self._resign)
        secondary.addWidget(self._signin)
        lay.addLayout(secondary)

        lay.addSpacing(12)
        not_now = QPushButton("Not now — back to app")
        not_now.setCursor(Qt.CursorShape.PointingHandCursor)
        not_now.setFixedHeight(40)
        not_now.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.Medium))
        not_now.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #a1a1aa;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                color: #fafafa;
                background: rgba(255,255,255,0.04);
            }
            """
        )
        not_now.clicked.connect(self._dismiss)
        lay.addWidget(not_now)

        lay.addSpacing(8)
        foot = QLabel(
            '<a href="https://www.hiauraai.com/pricing" '
            'style="color:#71717a; text-decoration:none;">hiauraai.com/pricing</a>'
        )
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setOpenExternalLinks(True)
        foot.setStyleSheet("background: transparent;")
        lay.addWidget(foot)

        self._poll = QTimer(self)
        self._poll.setInterval(4000)
        self._poll.timeout.connect(self._refresh)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._dismiss)

        self.adjustSize()
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        geo = parent.frameGeometry()
        size = self.sizeHint()
        x = geo.x() + (geo.width() - size.width()) // 2
        y = geo.y() + max(40, (geo.height() - size.height()) // 2)
        self.move(x, y)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._center_on_parent()
        if not self._poll.isActive():
            self._poll.start()
            QTimer.singleShot(200, self._refresh)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._poll.stop()
        super().hideEvent(event)

    def reject(self) -> None:
        self._dismiss()

    def _dismiss(self) -> None:
        self._poll.stop()
        self.dismissed.emit()
        self.hide()
        self.close()

    def _set_status(self, text: str, *, ok: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {'#34d399' if ok else '#71717a'}; background: transparent;"
        )

    def _upgrade(self) -> None:
        try:
            from jarvis_ui.user_account import start_checkout

            start_checkout("pro")
            self._set_status(
                "Checkout opened in your browser. Finish payment, then tap I've subscribed."
            )
        except Exception as e:
            self._set_status(f"Could not open checkout: {e}")

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
                self._set_status("Restarting sign-in…")
                return
            self._set_status(f"Sign-in failed: {msg}")

        worker.succeeded.connect(_ok)
        worker.failed.connect(_err)
        worker.browser_opened.connect(
            lambda _u: self._set_status("Browser opened — finish login, then tap I've subscribed.")
        )
        worker.start()

    def _refresh(self) -> None:
        try:
            from jarvis_ui.auth_async import refresh_entitlements_async
            from jarvis_ui.user_account import ensure_paid_access, is_authenticated

            if not is_authenticated():
                self._set_status("Sign in with Google, then subscribe on the website.")
                return

            def _after(_profile) -> None:
                try:
                    ok, reason = ensure_paid_access(sync=False)
                    if ok:
                        self._set_status("Pro is active. Unlocking…", ok=True)
                        self._poll.stop()
                        QTimer.singleShot(350, self._finish_unlocked)
                    elif reason == "sign_in":
                        self._set_status("Session expired — tap Sign in.")
                    else:
                        self._set_status("Still Free. Subscribe for $20/mo, then refresh.")
                except Exception as e:
                    self._set_status(f"Could not refresh plan: {e}")

            self._set_status("Checking subscription…")
            refresh_entitlements_async(_after)
        except Exception as e:
            self._set_status(f"Could not refresh plan: {e}")

    def _finish_unlocked(self) -> None:
        self.unlocked.emit()
        self.accept()
