"""Launch first-run onboarding before the main AURA window."""

from __future__ import annotations

import sys

from jarvis_ui.onboarding.persistence import is_onboarding_done
from jarvis_ui.onboarding.window import OnboardingWindow


def run_onboarding_if_needed() -> bool:
    """Show premium Antigravity onboarding once. Returns True if it was shown."""
    if is_onboarding_done():
        return False

    from PyQt6.QtCore import QEventLoop, QTimer, Qt
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        from jarvis_ui.user_account import (
            install_deep_link_handler,
            install_update_controller_fix,
        )

        install_deep_link_handler()
        install_update_controller_fix()
    except Exception:
        pass

    win = OnboardingWindow(preview=False)
    # Destroying mid-transition causes macOS SIGTRAP with Qt animations.
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    loop = QEventLoop()
    done = {"ok": False}

    def _finished() -> None:
        done["ok"] = True
        if loop.isRunning():
            loop.quit()

    def _stop() -> None:
        if loop.isRunning():
            loop.quit()

    win.finished.connect(_finished)
    win.skipped.connect(_stop)

    win.show()
    win.raise_()
    win.activateWindow()
    loop.exec()

    # Tear down calmly before the main window takes over.
    try:
        win.hide()
        win.close()
        win.deleteLater()
        for _ in range(5):
            app.processEvents()
        QTimer.singleShot(0, lambda: None)
        app.processEvents()
    except Exception:
        pass

    if done["ok"]:
        try:
            from core.first_run import mark_shown

            mark_shown()
        except Exception:
            pass
        return True
    return False
