"""In-app referral dialog — AURA navy backdrop + card (no email invite)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T
from jarvis_ui.components import _LineIcon

_UI = ".AppleSystemUIFont"


class _FetchReferralWorker(QThread):
    ok = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def run(self) -> None:
        try:
            from jarvis_ui import user_account as UA

            stats = UA.fetch_referral_stats()
            self.ok.emit(stats)
        except Exception as exc:
            self.fail.emit(str(exc) or "Could not load referral link")


def _friendly_error(raw: str) -> str:
    lower = (raw or "").lower()
    if "401" in lower or "not signed in" in lower or "sign in" in lower:
        return "Sign in to unlock your personal AURA invite link."
    if "session expired" in lower:
        return "Your session expired. Sign in again to get your invite link."
    if "cannot reach" in lower or "timed out" in lower or "network" in lower:
        return "Couldn’t reach AURA. Check your connection and try again."
    if "503" in lower or "database" in lower:
        return "Referral is temporarily unavailable. Try again shortly."
    return "Couldn’t load your invite link. Open the website or try again."


def _title_font() -> QFont:
    f = QFont(_UI, 20, QFont.Weight.Bold)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def _line_height(font: QFont) -> int:
    """Full glyph height + padding so macOS fonts are never clipped."""
    fm = QFontMetrics(font)
    return max(fm.height(), fm.ascent() + fm.descent()) + 6


class ReferralDialog(QDialog):
    """Full-window blue dimmer + AURA card. Title uses separate lines (no clip)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReferralDialog")
        self.setWindowTitle("Refer friends — AURA")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("QDialog#ReferralDialog { background: transparent; }")

        # Cover the parent (or a sensible default) so no gray system sheet shows.
        if parent is not None:
            self.setGeometry(parent.rect())
            self.move(parent.mapToGlobal(parent.rect().topLeft()))
        else:
            self.resize(720, 560)

        self._link = ""
        self._worker: _FetchReferralWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(1)

        center = QHBoxLayout()
        center.setContentsMargins(24, 24, 24, 24)
        center.addStretch(1)

        card = QFrame()
        card.setObjectName("ReferralCard")
        card.setFixedWidth(420)
        card.setStyleSheet(
            f"""
            QFrame#ReferralCard {{
                background: {T.BG_ELEVATED};
                border: 1px solid {T.BORDER_HI};
                border-radius: 20px;
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(56)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 40, 70, 180))
        card.setGraphicsEffect(shadow)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 26, 28, 28)
        lay.setSpacing(0)

        # Top cyan hairline
        accent = QFrame()
        accent.setFixedHeight(2)
        accent.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 transparent, stop:0.15 {T.CYAN}, stop:0.85 {T.CYAN}, stop:1 transparent);"
            "border: none;"
        )
        lay.addWidget(accent)
        lay.addSpacing(20)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(14)
        header.setContentsMargins(0, 0, 0, 0)

        gift_wrap = QFrame()
        gift_wrap.setFixedSize(44, 44)
        gift_wrap.setStyleSheet(
            f"background: {T.SB_ACCENT_SOFT}; border: 1px solid {T.SB_ACCENT_BORDER}; "
            "border-radius: 14px;"
        )
        gw = QHBoxLayout(gift_wrap)
        gw.setContentsMargins(0, 0, 0, 0)
        gw.addWidget(_LineIcon("gift", T.CYAN, size=22), 0, Qt.AlignmentFlag.AlignCenter)
        header.addWidget(gift_wrap, 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(6)
        titles.setContentsMargins(0, 0, 0, 0)

        eyebrow = QLabel("AURA REFERRAL")
        eyebrow.setFont(QFont(_UI, 10, QFont.Weight.DemiBold))
        eyebrow.setFixedHeight(_line_height(eyebrow.font()))
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        eyebrow.setStyleSheet(
            f"color: {T.CYAN}; background: transparent; border: none;"
        )
        titles.addWidget(eyebrow)

        # Two separate labels — avoids QLabel word-wrap clipping on macOS.
        tf = _title_font()
        th = _line_height(tf)
        for line in ("Refer friends,", "earn Pro credit"):
            lbl = QLabel(line)
            lbl.setFont(tf)
            lbl.setFixedHeight(th)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            lbl.setStyleSheet(
                f"color: {T.WHITE}; background: transparent; border: none;"
            )
            titles.addWidget(lbl)

        header.addLayout(titles, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; color: {T.TEXT_DIM}; border: none;
                border-radius: 8px; font-size: 14px;
            }}
            QPushButton:hover {{
                background: rgba(0, 209, 255, 0.12); color: {T.WHITE};
            }}
            """
        )
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(header)
        lay.addSpacing(18)

        body = QLabel(
            "Share AURA with friends. They get $5 off their first Pro month — "
            "you get $5 credit when they subscribe.\n\n"
            "Every 3 paid friends unlocks a free Pro month (up to 3 per year)."
        )
        body.setWordWrap(True)
        body.setFont(QFont(_UI, 13))
        body.setStyleSheet(
            f"color: {T.TEXT_MED}; background: transparent; border: none; padding: 0;"
        )
        body.setMinimumHeight(88)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(body)
        lay.addSpacing(12)

        history = QPushButton("View referral history →")
        history.setCursor(Qt.CursorShape.PointingHandCursor)
        history.setFlat(True)
        history.setFixedHeight(24)
        history.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; border: none; text-align: left;
                color: {T.CYAN}; font-size: 13px; font-weight: 500; padding: 0;
            }}
            QPushButton:hover {{ color: #5adfff; }}
            """
        )
        history.clicked.connect(self._open_history)
        lay.addWidget(history, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addSpacing(22)

        link_lbl = QLabel("Your invite link")
        link_lbl.setFont(QFont(_UI, 12, QFont.Weight.DemiBold))
        link_lbl.setFixedHeight(_line_height(link_lbl.font()))
        link_lbl.setStyleSheet(
            f"color: {T.TEXT}; background: transparent; border: none;"
        )
        lay.addWidget(link_lbl)
        lay.addSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._link_edit = QLineEdit()
        self._link_edit.setReadOnly(True)
        self._link_edit.setPlaceholderText("Your link appears here after sign-in")
        self._link_edit.setFixedHeight(44)
        self._link_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background: {T.BG_PANEL};
                color: {T.TEXT};
                border: 1px solid {T.BORDER};
                border-radius: 12px;
                padding: 0 14px;
                font-size: 12px;
                font-family: '{_UI}';
            }}
            QLineEdit:focus {{ border: 1px solid {T.CYAN_DIM}; }}
            """
        )
        row.addWidget(self._link_edit, stretch=1)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedHeight(44)
        self._copy_btn.setMinimumWidth(90)
        self._copy_btn.setEnabled(False)
        self._copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(0, 209, 255, 0.16);
                color: {T.WHITE};
                border: 1px solid {T.SB_ACCENT_BORDER};
                border-radius: 12px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 600;
                font-family: '{_UI}';
            }}
            QPushButton:hover {{ background: rgba(0, 209, 255, 0.28); }}
            QPushButton:disabled {{
                color: {T.TEXT_DIM};
                background: {T.BG_PANEL};
                border: 1px solid {T.BORDER};
            }}
            """
        )
        self._copy_btn.clicked.connect(self._copy_link)
        row.addWidget(self._copy_btn)
        lay.addLayout(row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont(_UI, 12))
        self._status.setMinimumHeight(22)
        self._set_status("")
        lay.addSpacing(12)
        lay.addWidget(self._status)

        self._cta = QPushButton("Sign in to get your link")
        self._cta.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta.setFixedHeight(44)
        self._cta.hide()
        self._cta.setStyleSheet(
            f"""
            QPushButton {{
                background: {T.CYAN};
                color: #041018;
                border: none;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
                font-family: '{_UI}';
            }}
            QPushButton:hover {{ background: #5adfff; }}
            """
        )
        self._cta.clicked.connect(self._request_sign_in)
        lay.addSpacing(14)
        lay.addWidget(self._cta)

        center.addWidget(card)
        center.addStretch(1)
        root.addLayout(center)
        root.addStretch(1)

        self._load()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Blue dimmer behind the card — no gray system sheet."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Deep AURA navy wash (not gray).
        p.fillRect(self.rect(), QColor(5, 14, 28, 210))
        # Soft cyan glow in the center.
        glow = QColor(0, 209, 255, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        cx, cy = self.width() // 2, self.height() // 2
        p.drawEllipse(cx - 220, cy - 160, 440, 320)
        super().paintEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
            self.move(parent.mapToGlobal(parent.rect().topLeft()))

    def _set_status(self, text: str, *, kind: str = "muted") -> None:
        colors = {
            "muted": T.TEXT_DIM,
            "ok": T.GREEN,
            "error": "#ff8a9a",
        }
        self._status.setStyleSheet(
            f"color: {colors.get(kind, T.TEXT_DIM)}; background: transparent; border: none;"
        )
        self._status.setText(text)

    def _load(self) -> None:
        from jarvis_ui import user_account as UA

        if not UA.is_authenticated():
            self._set_status("Sign in to unlock your personal AURA invite link.")
            self._link_edit.setPlaceholderText("Your link appears here after sign-in")
            self._cta.setText("Sign in to get your link")
            self._cta.show()
            try:
                self._cta.clicked.disconnect()
            except Exception:
                pass
            self._cta.clicked.connect(self._request_sign_in)
            return

        self._set_status("Loading your invite link…")
        self._worker = _FetchReferralWorker()
        self._worker.ok.connect(self._on_stats)
        self._worker.fail.connect(self._on_fail)
        self._worker.start()

    def _on_stats(self, stats: dict) -> None:
        link = str(stats.get("link") or "").strip()
        code = str(stats.get("code") or "").strip()
        if not link and code:
            from jarvis_ui import user_account as UA

            link = f"{UA.web_base()}/r/{code}"
        self._link = link
        self._link_edit.setText(link)
        self._copy_btn.setEnabled(bool(link))
        paid = int(stats.get("paid") or 0)
        invited = int(stats.get("invited") or 0)
        if invited or paid:
            self._set_status(f"{invited} invited · {paid} subscribed", kind="ok")
        else:
            self._set_status("Share your link — credit lands when friends go Pro.")
        self._cta.hide()

    def _on_fail(self, message: str) -> None:
        friendly = _friendly_error(message)
        self._set_status(friendly, kind="error")
        self._link_edit.clear()
        self._link_edit.setPlaceholderText("Open on the website to grab your link")
        self._copy_btn.setEnabled(False)

        lower = (message or "").lower()
        needs_signin = "401" in lower or "not signed in" in lower or "session" in lower
        if needs_signin:
            self._cta.setText("Sign in")
            try:
                self._cta.clicked.disconnect()
            except Exception:
                pass
            self._cta.clicked.connect(self._request_sign_in)
        else:
            self._cta.setText("Open on website")
            try:
                self._cta.clicked.disconnect()
            except Exception:
                pass
            self._cta.clicked.connect(self._open_history)
        self._cta.show()

    def _copy_link(self) -> None:
        text = (self._link or self._link_edit.text() or "").strip()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self._copy_btn.setText("Copied")
        self._set_status("Link copied — share it with friends.", kind="ok")
        QTimer.singleShot(1600, lambda: self._copy_btn.setText("Copy"))

    def _open_history(self) -> None:
        from jarvis_ui import user_account as UA

        UA.open_referral()

    def _request_sign_in(self) -> None:
        self.done(2)


def show_referral_dialog(parent: QWidget | None = None) -> int:
    """Show the dialog. Returns QDialog result (2 = user wants sign-in)."""
    dlg = ReferralDialog(parent)
    return int(dlg.exec())
