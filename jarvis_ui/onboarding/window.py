"""OnboardingWindow — welcome → permissions → Gemini API key."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from jarvis_ui.onboarding import tokens as T
from jarvis_ui.onboarding.pages import ApiKeySetupPage, PermissionsOnlyPage, save_api_keys
from jarvis_ui.onboarding.persistence import mark_onboarding_done
from jarvis_ui.onboarding.welcome_antigravity import AntigravityWelcomePage


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

        # Production: live Google probe. Preview tooling: format-only (no network).
        self._api = ApiKeySetupPage(require_live_verify=not preview)
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
        # Always show Gemini key step on download/setup (welcome → permissions → key).
        self.setStyleSheet(f"QWidget#OnboardingWindow {{ background: {T.CREAM}; }}")
        self.resize(T.WIN_W, T.WIN_H)
        if hasattr(self._api, "prefill_existing_key"):
            try:
                self._api.prefill_existing_key()
            except Exception:
                pass
        self._stack.setCurrentWidget(self._api)
        if hasattr(self._api, "play_enter"):
            self._api.play_enter()

    def _on_api_submitted(self, key: str, os_name: str) -> None:
        # Keep this slot exception-free: PyQt6 aborts the process on slot errors
        # (common when writing keys while still on a DMG volume).
        try:
            if not self._preview:
                save_api_keys(key, os_name)
            # Defer teardown so the submit slot returns cleanly.
            QTimer.singleShot(0, self._complete)
        except Exception as e:
            print(f"[AURA] Failed to save API key: {e}")
            try:
                from PyQt6.QtWidgets import QMessageBox

                QMessageBox.critical(
                    self,
                    "Could not save API key",
                    f"AURA could not save your Gemini key.\n\n{e}",
                )
            except Exception:
                pass

    def _complete(self) -> None:
        if self._completed:
            return
        self._completed = True
        try:
            if not self._preview:
                mark_onboarding_done()
        except Exception as e:
            print(f"[AURA] mark_onboarding_done failed: {e}")
        try:
            self.finished.emit()
        except Exception:
            pass
        try:
            self.hide()
        except Exception:
            pass
        QTimer.singleShot(80, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._completed:
            self.skipped.emit()
        super().closeEvent(event)
