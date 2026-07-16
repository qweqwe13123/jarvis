"""Cursor-style paywall dialog for mid-session Pro unlock."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class PaywallDialog(QDialog):
    def __init__(self, reason: str = "upgrade", parent=None):
        super().__init__(parent)
        self.setWindowTitle("AURA Pro")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._choice = "close"
        self.setStyleSheet("QDialog { background: #0a0a0a; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 24)
        root.setSpacing(0)

        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background: #141414;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
            }
            """
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(26, 26, 26, 22)
        lay.setSpacing(0)

        badge = QLabel("PRO REQUIRED" if reason != "sign_in" else "SIGN IN")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.DemiBold))
        badge.setStyleSheet("color: #a1a1aa; letter-spacing: 2px;")
        lay.addWidget(badge)
        lay.addSpacing(12)

        title = QLabel(
            "Sign in to continue" if reason == "sign_in" else "Unlimited AURA"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(".AppleSystemUIFont", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #fafafa;")
        lay.addWidget(title)
        lay.addSpacing(10)

        if reason == "sign_in":
            body = (
                "Sign in with the same Google account you use on hiauraai.com, "
                "then subscribe to Pro for unlimited desktop use."
            )
        else:
            body = (
                "AURA desktop unlocks with Pro — $20 / month for unlimited sessions, "
                "voice, agents, and computer control. Cancel anytime."
            )
        msg = QLabel(body)
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setFont(QFont(".AppleSystemUIFont", 13))
        msg.setStyleSheet("color: #a1a1aa;")
        lay.addWidget(msg)

        if reason != "sign_in":
            lay.addSpacing(16)
            price = QLabel("$20 / month")
            price.setAlignment(Qt.AlignmentFlag.AlignCenter)
            price.setFont(QFont(".AppleSystemUIFont", 18, QFont.Weight.DemiBold))
            price.setStyleSheet("color: #ffffff;")
            lay.addWidget(price)

        lay.addSpacing(22)
        row = QHBoxLayout()
        row.setSpacing(10)

        if reason == "sign_in":
            primary = QPushButton("Sign in with Google")
            primary.clicked.connect(self._sign_in)
            row.addWidget(primary)
        else:
            refresh = QPushButton("I've subscribed")
            refresh.clicked.connect(self._refresh)
            refresh.setStyleSheet(
                """
                QPushButton {
                    background: transparent; color: #e4e4e7;
                    border: 1px solid rgba(255,255,255,0.14);
                    border-radius: 10px; padding: 10px 14px; font-weight: 600;
                }
                QPushButton:hover { border-color: rgba(255,255,255,0.28); }
                """
            )
            row.addWidget(refresh)
            primary = QPushButton("Subscribe — $20 / month")
            primary.clicked.connect(self._upgrade)
            row.addWidget(primary)

        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.setStyleSheet(
            """
            QPushButton {
                background: #fafafa; color: #0a0a0a; border: none;
                border-radius: 10px; padding: 10px 14px; font-weight: 700;
            }
            QPushButton:hover { background: #e4e4e7; }
            """
        )
        primary.setDefault(True)
        lay.addLayout(row)
        root.addWidget(card)

    def _sign_in(self) -> None:
        self._choice = "sign_in"
        self.accept()

    def _upgrade(self) -> None:
        self._choice = "upgrade"
        self.accept()

    def _refresh(self) -> None:
        self._choice = "refresh"
        self.accept()

    @property
    def choice(self) -> str:
        return self._choice


def prompt_paywall(parent, reason: str = "upgrade") -> str:
    dlg = PaywallDialog(reason=reason, parent=parent)
    dlg.exec()
    return dlg.choice
