"""Non-blocking sign-in / sign-out / entitlement sync for a smooth UI."""

from __future__ import annotations

import threading
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

# Generation token: bumping it invalidates any older poll loop immediately.
_sign_in_generation = 0
_sign_in_cancel = threading.Event()
_sign_in_lock = threading.Lock()


def cancel_active_sign_in() -> None:
    """Invalidate any in-flight ``sign_in`` poll loop."""
    global _sign_in_generation
    with _sign_in_lock:
        _sign_in_generation += 1
        _sign_in_cancel.set()


def current_sign_in_generation() -> int:
    return _sign_in_generation


class SignInWorker(QThread):
    """Runs domain Google login off the UI thread."""

    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    browser_opened = pyqtSignal(str)

    def __init__(
        self,
        *,
        timeout: float = 180.0,
        generation: int = 0,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._timeout = float(timeout)
        self._generation = int(generation)

    def run(self) -> None:  # noqa: N802
        try:
            from jarvis_ui.user_account import sign_in

            self.status.emit("Opening browser…")

            def _on_browser(url: str) -> None:
                self.browser_opened.emit(url)
                self.status.emit("Browser opened — finish login on the website.")

            def _still_current() -> bool:
                return current_sign_in_generation() == self._generation

            sign_in(
                timeout=self._timeout,
                pump_events=False,
                is_current=_still_current,
                on_browser_opened=_on_browser,
            )
            if not _still_current():
                self.failed.emit("Sign-in cancelled. Tap Sign in again.")
                return
            self.succeeded.emit()
        except Exception as e:
            self.failed.emit(str(e) or "Sign-in failed")


class _OnceBridge(QObject):
    done = pyqtSignal(object)


_entitlement_lock = threading.Lock()
_entitlement_busy = False


def refresh_entitlements_async(
    on_done: Callable[[object], None] | None = None,
) -> None:
    """Refresh plan in a daemon thread; callback runs on the GUI thread."""
    global _entitlement_busy
    with _entitlement_lock:
        if _entitlement_busy:
            return
        _entitlement_busy = True

    bridge = _OnceBridge()
    if on_done is not None:
        bridge.done.connect(on_done)

    def work() -> None:
        global _entitlement_busy
        profile = None
        try:
            from jarvis_ui.user_account import get_access_token, refresh_entitlements

            if get_access_token():
                profile = refresh_entitlements()
        except Exception:
            profile = None
        finally:
            with _entitlement_lock:
                _entitlement_busy = False
            bridge.done.emit(profile)
            bridge.deleteLater()

    threading.Thread(target=work, daemon=True, name="AuraEntitlements").start()


def sign_out_async(on_done: Callable[[], None] | None = None) -> None:
    """Clear local session immediately; cancel pending sign-in; revoke remote async."""
    cancel_active_sign_in()
    from jarvis_ui.user_account import sign_out

    sign_out(revoke_remote_async=True)
    if on_done is not None:
        on_done()


def start_sign_in_worker(
    parent: QObject,
    *,
    timeout: float = 180.0,
    replace_running: bool = True,
) -> SignInWorker | None:
    """
    Start a SignInWorker. A new tap always bumps generation so any previous
    poll dies, then opens a fresh browser login session.
    """
    global _sign_in_generation
    with _sign_in_lock:
        existing = getattr(parent, "_sign_in_worker", None)
        if isinstance(existing, SignInWorker) and existing.isRunning():
            if not replace_running:
                return None
            # Invalidate old loop, then start a new generation for this attempt.
            _sign_in_generation += 1
            _sign_in_cancel.set()
            existing.requestInterruption()
            existing.wait(600)
        else:
            # Fresh attempt — still bump so stale deep-link codes don't bind oddly.
            _sign_in_generation += 1

        _sign_in_cancel.clear()
        gen = _sign_in_generation
        worker = SignInWorker(timeout=timeout, generation=gen, parent=parent)
        parent._sign_in_worker = worker  # type: ignore[attr-defined]
        return worker
