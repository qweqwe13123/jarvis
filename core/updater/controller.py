from __future__ import annotations

import os

from PyQt6.QtCore import QTimer

from core.updater.service import UpdateService, UpdateState
from core.version import UPDATE_CHECK_INTERVAL, UPDATE_CHECK_ON_STARTUP_DELAY
from jarvis_ui.update_dialog import UpdateDialog
from jarvis_ui.update_required_dialog import UpdateRequiredDialog


class UpdateController:
    """Checks for updates and drives the Update pill + soft/forced dialogs."""

    def __init__(self, window, pid: int) -> None:
        self._window = window
        self._pid = pid
        self._service = UpdateService()
        self._dialog: UpdateDialog | None = None
        self._required_dialog: UpdateRequiredDialog | None = None
        self._service.on_change(self._on_state)

        # Preview / kill-switch simulate: show the gate immediately.
        delay_ms = 200 if os.environ.get("AURA_SIMULATE_FORCE_UPDATE", "").lower() in {
            "1",
            "true",
            "yes",
        } else UPDATE_CHECK_ON_STARTUP_DELAY * 1000
        QTimer.singleShot(delay_ms, self._startup_check)
        self._periodic = QTimer(window)
        self._periodic.timeout.connect(self._periodic_check)
        self._periodic.start(UPDATE_CHECK_INTERVAL * 1000)

    @property
    def service(self) -> UpdateService:
        return self._service

    def _startup_check(self) -> None:
        if os.environ.get("JARVIS_SKIP_UPDATE_CHECK", "").lower() in {"1", "true", "yes"}:
            return
        if os.environ.get("AURA_SKIP_UPDATE_CHECK", "").lower() in {"1", "true", "yes"}:
            return
        self._service.check_for_updates(background=True)

    def _periodic_check(self) -> None:
        self._service.check_for_updates(background=True)

    def check_now(self) -> None:
        self._service.check_for_updates(background=True)

    def open_update_ui(self) -> None:
        """User clicked Update — open soft or forced install dialog."""
        state = self._service.state
        if state.force_required:
            self._show_required_dialog(state)
            return
        if state.release:
            self._show_dialog(state)
            return
        self._service.check_for_updates(background=True)

    def _on_state(self, state: UpdateState) -> None:
        main = getattr(self, "_on_state_main", None)
        if callable(main) and main is not UpdateController._on_state_main:
            main(state)
            return
        self._on_state_main(state)

    def _on_state_main(self, state: UpdateState) -> None:
        available = bool(state.release) and not state.error
        downloading = bool(state.downloading or state.applying or state.preparing)
        nav = getattr(self._window, "_nav", None)
        if nav is not None and hasattr(nav, "set_update_available"):
            try:
                # Always show the pill when an update (soft or forced) is ready.
                nav.set_update_available(
                    available or state.force_required, downloading=downloading
                )
            except Exception:
                pass

        if state.force_required and (state.release or state.min_supported_version):
            self._show_required_dialog(state)
            return

        if self._dialog is not None and not state.release and not state.downloading:
            try:
                self._dialog.reject()
            except Exception:
                pass

    def _show_required_dialog(self, state: UpdateState) -> None:
        if self._required_dialog is not None:
            try:
                self._required_dialog.raise_()
                self._required_dialog.activateWindow()
            except Exception:
                pass
            return
        # Close soft dialog if it was open.
        if self._dialog is not None:
            try:
                self._dialog.reject()
            except Exception:
                pass
            self._dialog = None
        self._required_dialog = UpdateRequiredDialog(
            self._service, self._parent_pid, parent=self._window
        )
        self._required_dialog.open()

    def _show_dialog(self, state: UpdateState) -> None:
        if state is None or not getattr(state, "release", None):
            return
        if state.force_required:
            self._show_required_dialog(state)
            return
        if self._dialog is not None:
            try:
                self._dialog.raise_()
                self._dialog.activateWindow()
            except Exception:
                pass
            return
        self._dialog = UpdateDialog(self._service, self._parent_pid, parent=self._window)
        self._dialog.finished.connect(self._clear_dialog)
        self._dialog.open()

    def _clear_dialog(self, *_args) -> None:
        self._dialog = None

    @property
    def _parent_pid(self) -> int:
        return self._pid
