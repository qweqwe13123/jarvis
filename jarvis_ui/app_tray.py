"""System tray / macOS menu-bar controller for Jarvis."""
from __future__ import annotations

import platform
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _jarvis_tray_icon() -> QIcon:
    root = Path(__file__).resolve().parents[1]
    for candidate in (
        root / "assets" / "aura_logo.png",
        root / "assets" / "aura_logo_onboarding.png",
        root / "assets" / "aura_logo_square_bg.png",
    ):
        if candidate.exists():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon

    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#061018"))
    p.setPen(QColor("#00d1ff"))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    f = QFont("Menlo", 22)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "A")
    p.end()
    return QIcon(pm)


class AppTrayController(QObject):
    open_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None

    def start(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._menu = QMenu()
        act_open = QAction("Open AURA", self._menu)
        act_open.triggered.connect(self.open_requested.emit)
        act_settings = QAction("Settings", self._menu)
        act_settings.triggered.connect(self.settings_requested.emit)
        act_update = QAction("Check for updates", self._menu)
        act_update.triggered.connect(self.update_requested.emit)
        act_quit = QAction("Quit", self._menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(act_open)
        self._menu.addAction(act_settings)
        self._menu.addSeparator()
        self._menu.addAction(act_update)
        self._menu.addSeparator()
        self._menu.addAction(act_quit)

        self._tray = QSystemTrayIcon(_jarvis_tray_icon(), parent=self.parent())
        self._tray.setToolTip("AURA")
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

        # macOS: also expose a minimal application menu when running as accessory.
        if platform.system() == "Darwin":
            try:
                app = QApplication.instance()
                if app is not None:
                    app.setQuitOnLastWindowClosed(False)
            except Exception:
                pass

    def stop(self) -> None:
        if self._tray is not None:
            self._tray.hide()
            self._tray = None

    def show_message(self, title: str, body: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 3500)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_requested.emit()
