from __future__ import annotations

import os

from PyQt6.QtCore import QTimer

from core.updater.service import UpdateService
from core.version import UPDATE_CHECK_INTERVAL, UPDATE_CHECK_ON_STARTUP_DELAY
from jarvis_ui.update_dialog import UpdateDialog


class UpdateController:
    def __init__(self, window, pid: int) -> None:
        self._window = window
        self._pid = pid
        self._service = UpdateService()
        self._dialog: UpdateDialog | None = None
        self._service.on_change(self._on_state)

        QTimer.singleShot(UPDATE_CHECK_ON_STARTUP_DELAY * 1000, self._startup_check)
        self._periodic = QTimer(window)
        self._periodic.timeout.connect(self._periodic_check)
        self._periodic.start(UPDATE_CHECK_INTERVAL * 1000)

    def _startup_check(self) -> None:
        if os.environ.get("JARVIS_SKIP_UPDATE_CHECK", "").lower() in {"1", "true", "yes"}:
            return
        self._service.check_for_updates(background=True)

    def _periodic_check(self) -> None:
        self._service.check_for_updates(background=True)

    def _on_state(self, state) -> None:
        if state.release and not state.downloading and self._dialog is None:
            self._dialog = UpdateDialog(self._service, self._parent_pid, parent=self._window)
            self._dialog.finished.connect(self._clear_dialog)
            self._dialog.open()

    def _clear_dialog(self, *_args) -> None:
        self._dialog = None

    @property
    def _parent_pid(self) -> int:
        return self._pid
