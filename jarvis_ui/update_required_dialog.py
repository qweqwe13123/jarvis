"""Blocking “Your version is outdated — update required” gate for AURA."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.updater.service import UpdateService, UpdateState
from core.version import APP_NAME, VERSION
from jarvis_ui import theme as T
from jarvis_ui.components import _LineIcon

_UI = ".AppleSystemUIFont"


def _fmt_mib(n: int) -> str:
    mib = max(0, int(n)) / (1024 * 1024)
    if mib < 0.1:
        return f"{mib:.2f} MB"
    if mib < 10:
        return f"{mib:.1f} MB"
    return f"{mib:.0f} MB"


def _line_height(font: QFont) -> int:
    fm = QFontMetrics(font)
    return max(fm.height(), fm.ascent() + fm.descent()) + 6


class UpdateRequiredDialog(QDialog):
    """Full-window navy dimmer + forced update card. Cannot be dismissed."""

    def __init__(self, service: UpdateService, parent_pid: int, parent=None):
        super().__init__(parent)
        self._service = service
        self._parent_pid = parent_pid

        self.setObjectName("UpdateRequiredDialog")
        self.setWindowTitle(f"Update required — {APP_NAME}")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet(
            "QDialog#UpdateRequiredDialog { background: transparent; }"
        )

        if parent is not None:
            self.setGeometry(parent.rect())
            self.move(parent.mapToGlobal(parent.rect().topLeft()))
        else:
            self.resize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(1)

        center = QHBoxLayout()
        center.setContentsMargins(24, 24, 24, 24)
        center.addStretch(1)

        card = QFrame()
        card.setObjectName("UpdateRequiredCard")
        card.setFixedWidth(440)
        card.setStyleSheet(
            f"""
            QFrame#UpdateRequiredCard {{
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

        accent = QFrame()
        accent.setFixedHeight(2)
        accent.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 transparent, stop:0.15 {T.CYAN}, stop:0.85 {T.CYAN}, stop:1 transparent);"
            "border: none;"
        )
        lay.addWidget(accent)
        lay.addSpacing(22)

        # Icon plate
        icon_row = QHBoxLayout()
        icon_row.addStretch(1)
        icon_wrap = QFrame()
        icon_wrap.setFixedSize(64, 64)
        icon_wrap.setStyleSheet(
            "background: rgba(0, 209, 255, 0.10);"
            "border: 1px solid rgba(0, 209, 255, 0.28);"
            "border-radius: 18px;"
        )
        iw = QHBoxLayout(icon_wrap)
        iw.setContentsMargins(0, 0, 0, 0)
        iw.addWidget(_LineIcon("download", T.CYAN, size=28), 0, Qt.AlignmentFlag.AlignCenter)
        icon_row.addWidget(icon_wrap)
        icon_row.addStretch(1)
        lay.addLayout(icon_row)
        lay.addSpacing(18)

        eyebrow = QLabel("UPDATE REQUIRED")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eyebrow.setFont(QFont(_UI, 10, QFont.Weight.DemiBold))
        eyebrow.setFixedHeight(_line_height(eyebrow.font()))
        eyebrow.setStyleSheet(
            f"color: {T.CYAN}; background: transparent; border: none;"
            "letter-spacing: 1px;"
        )
        lay.addWidget(eyebrow)
        lay.addSpacing(8)

        title = QLabel("Your version is outdated")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont(_UI, 20, QFont.Weight.Bold))
        title.setFixedHeight(_line_height(title.font()) + 2)
        title.setStyleSheet(
            f"color: {T.WHITE}; background: transparent; border: none;"
        )
        lay.addWidget(title)
        lay.addSpacing(10)

        self._body = QLabel(
            f"This build of {APP_NAME} is no longer supported.\n"
            "Update to continue using the app safely."
        )
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        self._body.setFont(QFont(_UI, 13))
        self._body.setStyleSheet(
            f"color: {T.TEXT_MED}; background: transparent; border: none;"
        )
        lay.addWidget(self._body)
        lay.addSpacing(18)

        # Version strip
        ver_strip = QFrame()
        ver_strip.setObjectName("UpdateRequiredVersions")
        ver_strip.setStyleSheet(
            f"""
            QFrame#UpdateRequiredVersions {{
                background: rgba(0, 209, 255, 0.06);
                border: 1px solid rgba(0, 209, 255, 0.16);
                border-radius: 12px;
            }}
            """
        )
        ver_lay = QHBoxLayout(ver_strip)
        ver_lay.setContentsMargins(16, 12, 16, 12)
        ver_lay.setSpacing(10)

        self._installed = QLabel(f"v{VERSION}")
        self._installed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._installed.setFont(QFont(_UI, 12, QFont.Weight.DemiBold))
        self._installed.setStyleSheet(
            f"color: {T.TEXT_DIM}; background: transparent; border: none;"
        )
        ver_lay.addWidget(self._installed, stretch=1)

        arrow = QLabel("→")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFont(QFont(_UI, 14, QFont.Weight.Bold))
        arrow.setStyleSheet(
            f"color: {T.CYAN}; background: transparent; border: none;"
        )
        ver_lay.addWidget(arrow)

        self._latest = QLabel("—")
        self._latest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._latest.setFont(QFont(_UI, 12, QFont.Weight.DemiBold))
        self._latest.setStyleSheet(
            f"color: {T.CYAN}; background: transparent; border: none;"
        )
        ver_lay.addWidget(self._latest, stretch=1)
        lay.addWidget(ver_strip)
        lay.addSpacing(14)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.06); border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {T.CYAN}; border-radius: 2px; }}"
        )
        self._progress.hide()
        lay.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setFont(QFont(_UI, 11))
        self._status.setStyleSheet(
            f"color: {T.TEXT_DIM}; background: transparent; border: none;"
        )
        lay.addWidget(self._status)
        lay.addSpacing(18)

        self._update_btn = QPushButton("Update now")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setFixedHeight(44)
        self._update_btn.setFont(QFont(_UI, 13, QFont.Weight.DemiBold))
        self._update_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {T.CYAN};
                color: #041018;
                border: none;
                border-radius: 12px;
            }}
            QPushButton:hover {{ background: #33daff; }}
            QPushButton:pressed {{ background: #00b8e0; }}
            QPushButton:disabled {{
                background: #1e4a62;
                color: {T.TEXT_DIM};
            }}
            """
        )
        self._update_btn.clicked.connect(self._start_update)
        lay.addWidget(self._update_btn)
        lay.addSpacing(10)

        self._quit_btn = QPushButton("Quit")
        self._quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quit_btn.setFixedHeight(36)
        self._quit_btn.setFont(QFont(_UI, 12))
        self._quit_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {T.TEXT_DIM};
                border: 1px solid {T.BORDER};
                border-radius: 10px;
            }}
            QPushButton:hover {{
                color: {T.TEXT};
                border-color: {T.BORDER_HI};
            }}
            """
        )
        self._quit_btn.clicked.connect(self._quit_app)
        lay.addWidget(self._quit_btn)

        center.addWidget(card)
        center.addStretch(1)
        root.addLayout(center)
        root.addStretch(1)

        self._service.on_change(self._schedule_render)
        self._render(self._service.state)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(5, 14, 28, 220))
        glow = QColor(0, 209, 255, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        cx, cy = self.width() // 2, self.height() // 2
        p.drawEllipse(cx - 240, cy - 180, 480, 360)
        super().paintEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
            self.move(parent.mapToGlobal(parent.rect().topLeft()))

    def reject(self) -> None:  # noqa: N802
        # Block Escape / outside dismiss — only Quit or Update may leave.
        return

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def _schedule_render(self, _state: UpdateState) -> None:
        QTimer.singleShot(0, lambda: self._render(self._service.state))

    def _render(self, state: UpdateState) -> None:
        release = state.release
        latest = release.version if release else state.min_supported_version
        if latest:
            self._latest.setText(f"v{latest}")
        else:
            self._latest.setText("latest")

        if state.downloading:
            self._update_btn.setEnabled(False)
            self._quit_btn.setEnabled(False)
            self._progress.show()
            if state.total_bytes:
                pct = max(1, int(state.downloaded_bytes * 100 / state.total_bytes))
                self._progress.setRange(0, 100)
                self._progress.setValue(min(pct, 100))
                self._status.setText(
                    "Downloading… "
                    f"{_fmt_mib(state.downloaded_bytes)} / {_fmt_mib(state.total_bytes)}"
                )
            else:
                self._progress.setRange(0, 0)
                self._status.setText("Downloading update…")
            self._status.setStyleSheet(
                f"color: {T.TEXT_MED}; background: transparent; border: none;"
            )
        elif state.error:
            self._progress.hide()
            self._update_btn.setEnabled(True)
            self._quit_btn.setEnabled(True)
            self._status.setText(state.error)
            self._status.setStyleSheet(
                f"color: {T.RED}; background: transparent; border: none;"
            )
        else:
            self._progress.hide()
            self._update_btn.setEnabled(True)
            self._quit_btn.setEnabled(True)
            self._update_btn.setText("Update now")
            self._status.setText(
                "Update to continue — Quit closes AURA until you install the new version."
            )
            self._status.setStyleSheet(
                f"color: {T.TEXT_DIM}; background: transparent; border: none;"
            )

    def _start_update(self) -> None:
        self._service.download_and_apply(self._parent_pid)

    def _quit_app(self) -> None:
        # Hard exit: next launch shows this gate again until the app is updated.
        app = QApplication.instance()
        if app is not None:
            app.quit()
        raise SystemExit(0)
