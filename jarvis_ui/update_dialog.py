"""Minimal premium in-window Update panel for A.U.R.A."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from core.updater.service import UpdateService, UpdateState
from core.version import VERSION
from jarvis_ui import theme as T

_BG = "#0e141b"
_CARD = "#141b24"
_BORDER = "#243040"
_TEXT = "#e8eef4"
_TEXT_MED = "#8fa3b5"
_TEXT_DIM = "#6b8294"
_BTN_BG = "#1a222c"
_BTN_BORDER = "#2a3544"
_PRIMARY_BG = "#e8eef4"
_PRIMARY_FG = "#0e141b"
_FONT = T.SB_FONT

# Fixed inscription — always shown; remote/manifest notes are ignored.
_FIXED_WHATS_NEW = (
    "What's new\n"
    "\n"
    "•  Premium refinements across the desktop experience\n"
    "•  Smoother everyday interactions and wake\n"
    "•  Performance and reliability improvements\n"
    "•  Important bug fixes under the hood"
)


def _fmt_mib(n: int) -> str:
    """Human size for update progress (MiB, Cursor-style)."""
    mib = max(0, int(n)) / (1024 * 1024)
    if mib < 0.1:
        return f"{mib:.2f} MB"
    if mib < 10:
        return f"{mib:.1f} MB"
    return f"{mib:.0f} MB"


def _button_min_width(font: QFont, text: str, *, pad: int = 36) -> int:
    """Minimum button width from label metrics (Windows DPI-safe)."""
    return QFontMetrics(font).horizontalAdvance(text) + pad


class UpdateDialog(QDialog):
    """Frameless, parent-centered update card — calm SaaS typography."""

    def __init__(self, service: UpdateService, parent_pid: int, parent=None):
        super().__init__(parent)
        self._service = service
        self._parent_pid = parent_pid

        self.setObjectName("AuraUpdateCard")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(520)
        self.setMinimumHeight(380)

        shell = QFrame(self)
        shell.setObjectName("AuraUpdateShell")
        shell.setStyleSheet(
            f"QFrame#AuraUpdateShell {{"
            f"  background: {_BG};"
            f"  border: 1px solid {_BORDER};"
            f"  border-radius: 14px;"
            f"}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(shell)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(0)

        self._title = QLabel("A new version of A.U.R.A is available")
        self._title.setWordWrap(True)
        self._title.setFont(QFont(_FONT, 17, QFont.Weight.DemiBold))
        self._title.setStyleSheet(
            f"color: {_TEXT}; background: transparent; border: none;"
        )
        layout.addWidget(self._title)
        layout.addSpacing(8)

        self._version = QLabel("")
        self._version.setFont(QFont(_FONT, 12))
        self._version.setStyleSheet(
            f"color: {_TEXT_DIM}; background: transparent; border: none;"
        )
        layout.addWidget(self._version)
        layout.addSpacing(18)

        notes_wrap = QFrame()
        notes_wrap.setObjectName("AuraUpdateNotes")
        notes_wrap.setStyleSheet(
            f"QFrame#AuraUpdateNotes {{"
            f"  background: {_CARD};"
            f"  border: 1px solid {_BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )
        notes_lay = QVBoxLayout(notes_wrap)
        notes_lay.setContentsMargins(14, 12, 14, 12)

        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setFrameShape(QFrame.Shape.NoFrame)
        self._notes.setMinimumHeight(140)
        self._notes.setFont(QFont(_FONT, 12))
        self._notes.setStyleSheet(
            f"QTextEdit {{"
            f"  background: transparent;"
            f"  color: {_TEXT_MED};"
            f"  border: none;"
            f"  selection-background-color: rgba(255,255,255,0.08);"
            f"}}"
        )
        notes_lay.addWidget(self._notes)
        layout.addWidget(notes_wrap, stretch=1)
        layout.addSpacing(14)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {_BTN_BG}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {_TEXT_MED}; border-radius: 2px; }}"
        )
        self._progress.hide()
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont(_FONT, 11))
        self._status.setStyleSheet(
            f"color: {_TEXT_DIM}; background: transparent; border: none;"
        )
        layout.addWidget(self._status)
        layout.addSpacing(18)

        ghost_font = QFont(_FONT, 12)
        primary_font = QFont(_FONT, 12, QFont.Weight.DemiBold)

        self._later_btn = self._ghost_btn("Remind me later", ghost_font)
        self._skip_btn = self._ghost_btn("Skip this version", ghost_font)
        self._update_btn = self._primary_btn("Update now", primary_font)

        self._later_btn.clicked.connect(self.reject)
        self._skip_btn.clicked.connect(self._skip)
        self._update_btn.clicked.connect(self._start_update)

        actions = QVBoxLayout()
        actions.setSpacing(10)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)
        secondary.addWidget(self._later_btn)
        secondary.addWidget(self._skip_btn)
        secondary.addStretch(1)

        self._update_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        primary = QHBoxLayout()
        primary.addWidget(self._update_btn)

        actions.addLayout(secondary)
        actions.addLayout(primary)
        layout.addLayout(actions)

        self.setStyleSheet(f"QDialog#AuraUpdateCard {{ background: {_BG}; }}")

        self._service.on_change(self._schedule_render)
        self._render(self._service.state)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        geo = parent.geometry()
        # Prefer the top-level window rect when parent is the main window.
        top = parent.window() if hasattr(parent, "window") else parent
        if top is not None:
            geo = top.frameGeometry() if hasattr(top, "frameGeometry") else top.geometry()
            # Map to global if needed — for QDialog parenting, use window geometry.
            try:
                origin = top.mapToGlobal(top.rect().topLeft())
                x = origin.x() + (top.width() - self.width()) // 2
                y = origin.y() + (top.height() - self.height()) // 2
                self.move(max(0, x), max(0, y))
                return
            except Exception:
                pass
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    @staticmethod
    def _ghost_btn(text: str, font: QFont) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(34)
        btn.setFont(font)
        btn.setMinimumWidth(_button_min_width(font, text))
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {_BTN_BG};"
            f"  color: {_TEXT_MED};"
            f"  border: 1px solid {_BTN_BORDER};"
            f"  border-radius: 8px;"
            f"  padding: 0 16px;"
            f"  min-width: 0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: #222b36;"
            f"  color: {_TEXT};"
            f"  border-color: {_TEXT_DIM};"
            f"}}"
            f"QPushButton:disabled {{ color: {_TEXT_DIM}; opacity: 0.5; }}"
        )
        return btn

    @staticmethod
    def _primary_btn(text: str, font: QFont) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        btn.setFont(font)
        btn.setMinimumWidth(_button_min_width(font, text, pad=40))
        btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {_PRIMARY_BG};"
            f"  color: {_PRIMARY_FG};"
            f"  border: none;"
            f"  border-radius: 8px;"
            f"  padding: 0 18px;"
            f"  min-width: 0;"
            f"}}"
            f"QPushButton:hover {{ background: #ffffff; }}"
            f"QPushButton:pressed {{ background: #d0d8e0; }}"
            f"QPushButton:disabled {{"
            f"  background: #3a4554;"
            f"  color: {_TEXT_DIM};"
            f"}}"
        )
        return btn

    def _schedule_render(self, _state: UpdateState) -> None:
        QTimer.singleShot(0, lambda: self._render(self._service.state))

    def _render(self, state: UpdateState) -> None:
        release = state.release
        if not release:
            self.reject()
            return

        self._version.setText(f"Installed: v{VERSION}  →  Latest: v{release.version}")
        self._notes.setPlainText(_FIXED_WHATS_NEW)

        if state.downloading:
            self._update_btn.setEnabled(False)
            self._later_btn.setEnabled(False)
            self._skip_btn.setEnabled(False)
            self._progress.show()
            if state.total_bytes:
                pct = max(1, int(state.downloaded_bytes * 100 / state.total_bytes))
                self._progress.setValue(min(pct, 100))
                if state.downloaded_bytes >= state.total_bytes:
                    self._status.setText("Restarting AURA to finish the update…")
                else:
                    self._status.setText(
                        "Downloading… "
                        f"{_fmt_mib(state.downloaded_bytes)} / {_fmt_mib(state.total_bytes)}"
                    )
            else:
                self._progress.setRange(0, 0)
                self._status.setText("Downloading update…")
        elif state.error:
            self._status.setText(state.error)
            self._update_btn.setEnabled(True)
            self._later_btn.setEnabled(True)
            self._skip_btn.setEnabled(True)
            self._progress.hide()
        else:
            self._status.setText(
                "The update will download in the background and install automatically."
            )
            self._update_btn.setEnabled(True)
            self._later_btn.setEnabled(True)
            self._skip_btn.setEnabled(True)
            self._progress.hide()

    def _start_update(self) -> None:
        self._service.download_and_apply(self._parent_pid)

    def _skip(self) -> None:
        release = self._service.state.release
        if release:
            self._service.skip_version(release.version)
        self.reject()
