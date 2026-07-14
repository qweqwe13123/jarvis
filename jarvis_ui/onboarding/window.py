"""OnboardingWindow — welcome → permissions → Gemini API key."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from jarvis_ui.onboarding import tokens as T
from jarvis_ui.onboarding.pages import ApiKeySetupPage, PermissionsOnlyPage, save_api_keys
from jarvis_ui.onboarding.persistence import mark_onboarding_done
from jarvis_ui.onboarding.welcome_antigravity import AntigravityWelcomePage


def _has_gemini_key() -> bool:
    import json
    import sys
    from pathlib import Path

    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parents[2]
    path = base / "config" / "api_keys.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(str(data.get("gemini_api_key", "")).strip()) and bool(
            data.get("os_system")
        )
    except Exception:
        return False


class OnboardingWindow(QWidget):
    finished = pyqtSignal()
    skipped = pyqtSignal()

    def __init__(self, parent=None, *, preview: bool = False):
        super().__init__(parent)
        self._preview = preview
        self._completed = False
        self.setObjectName("OnboardingWindow")
        self.setWindowTitle("AURA Setup" + (" · Preview" if preview else ""))
        self.resize(560, 720)
        self.setMinimumSize(480, 600)
        self.setStyleSheet("QWidget#OnboardingWindow { background: #0B0B0B; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._welcome = AntigravityWelcomePage()
        self._welcome.continue_clicked.connect(self._show_permissions)
        self._stack.addWidget(self._welcome)

        self._permissions = PermissionsOnlyPage()
        self._permissions.cta.clicked.connect(self._after_permissions)
        self._stack.addWidget(self._permissions)

        self._api = ApiKeySetupPage()
        self._api.submitted.connect(self._on_api_submitted)
        self._stack.addWidget(self._api)

        self._stack.setCurrentWidget(self._welcome)

    def _show_permissions(self) -> None:
        self.setStyleSheet(f"QWidget#OnboardingWindow {{ background: {T.CREAM}; }}")
        self.resize(T.WIN_W, T.WIN_H)
        self._stack.setCurrentWidget(self._permissions)
        if hasattr(self._permissions, "play_enter"):
            self._permissions.play_enter()

    def _after_permissions(self) -> None:
        # Always collect the key inside onboarding — MainWindow crash must not block this.
        if _has_gemini_key() and not self._preview:
            self._complete()
            return
        self.setStyleSheet(f"QWidget#OnboardingWindow {{ background: {T.CREAM}; }}")
        self.resize(T.WIN_W, T.WIN_H)
        self._stack.setCurrentWidget(self._api)
        if hasattr(self._api, "play_enter"):
            self._api.play_enter()

    def _on_api_submitted(self, key: str, os_name: str) -> None:
        if not self._preview:
            try:
                save_api_keys(key, os_name)
            except Exception as e:
                print(f"[AURA] Failed to save API key: {e}")
                return
        self._complete()

    def _complete(self) -> None:
        self._completed = True
        if not self._preview:
            mark_onboarding_done()
        self.finished.emit()
        self.hide()
        QTimer.singleShot(50, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._completed:
            self.skipped.emit()
        super().closeEvent(event)
