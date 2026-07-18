"""Request / inspect OS permissions used during onboarding.

macOS uses TCC / System Settings. Windows and Linux open the matching privacy
pages and use Qt prompts for microphone / camera when available.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import warnings
from collections.abc import Callable
from typing import Literal

PermissionKind = Literal["mic", "camera", "screen", "a11y", "automation"]
ResultCallback = Callable[..., None]

_REQUIRED: tuple[PermissionKind, ...] = (
    "mic",
    "camera",
    "screen",
    "a11y",
    "automation",
)

_prompt_attempts: dict[str, int] = {}

_AUTOMATION_TARGETS: tuple[str, ...] = (
    "com.apple.finder",
    "com.apple.systemevents",
    "com.apple.Safari",
    "com.apple.Terminal",
)
_AUTOMATION_GATE_BUNDLE = "com.apple.finder"

_AE_CORE = int.from_bytes(b"core", "big")
_AE_GETD = int.from_bytes(b"getd", "big")
_ERR_NOT_PERMITTED = -1743
_ERR_NEEDS_CONSENT = -1744
_ERR_PROC_NOT_FOUND = -600

_MAC_PREF: dict[str, str] = {
    "mic": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "a11y": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}

_WIN_SETTINGS: dict[str, str] = {
    "mic": "ms-settings:privacy-microphone",
    "camera": "ms-settings:privacy-webcam",
    # Win11 graphics capture / screen privacy; falls back gracefully on older builds.
    "screen": "ms-settings:privacy-graphicscapture",
    "a11y": "ms-settings:easeofaccess-keyboard",
    "automation": "ms-settings:appsfeatures",
}


def required_kinds() -> tuple[PermissionKind, ...]:
    return _REQUIRED


def supports_in_app_prompt(kind: PermissionKind) -> bool:
    return kind in _REQUIRED


def reset_prompt_attempts() -> None:
    _prompt_attempts.clear()


def is_granted(kind: PermissionKind) -> bool | None:
    """Fresh OS read — never cache across calls."""
    system = platform.system()
    try:
        if kind in ("mic", "camera"):
            if system == "Darwin":
                return _mic_camera_granted(kind)
            return _qt_status(kind)
        if system == "Darwin":
            if kind == "screen":
                return _screen_granted()
            if kind == "a11y":
                return _a11y_granted()
            if kind == "automation":
                return _automation_granted()
        # Windows / Linux: no macOS-style TCC gate — unknown until user opens Settings.
        if kind in ("screen", "a11y", "automation"):
            return None
    except Exception:
        return None
    return None


def all_required_granted() -> bool:
    return all(is_granted(k) is True for k in _REQUIRED)


def permission_snapshot() -> dict[str, bool]:
    """Fresh map for UI sync."""
    return {k: is_granted(k) is True for k in _REQUIRED}


def screen_needs_relaunch() -> bool:
    """True when Screen Recording is often enabled in Settings but this process
    still cannot see it — macOS requires relaunch after the toggle."""
    if platform.system() != "Darwin":
        return False
    try:
        from Quartz import CGPreflightScreenCaptureAccess

        return not bool(CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def open_system_settings(kind: PermissionKind) -> bool:
    """Open the OS privacy / capability page for this permission."""
    system = platform.system()
    try:
        if system == "Darwin":
            url = _MAC_PREF.get(kind)
            if not url:
                return False
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if system == "Windows":
            uri = _WIN_SETTINGS.get(kind) or "ms-settings:privacy"
            try:
                os.startfile(uri)  # type: ignore[attr-defined]
                return True
            except Exception:
                from core.win_subprocess import popen as _win_popen

                _win_popen(
                    ["cmd", "/c", "start", "", uri],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
        # Linux — best-effort desktop settings.
        cmds: list[list[str]] = []
        if kind in ("mic", "camera"):
            cmds.extend(
                [
                    ["gnome-control-center", "applications"],
                    ["gnome-control-center", "privacy"],
                    ["systemsettings", "kcm_pulseaudio"],
                    ["systemsettings5", "kcm_pulseaudio"],
                ]
            )
        elif kind == "a11y":
            cmds.extend(
                [
                    ["gnome-control-center", "universal-access"],
                    ["systemsettings", "kcm_access"],
                    ["systemsettings5", "kcm_access"],
                ]
            )
        else:
            cmds.extend(
                [
                    ["gnome-control-center", "privacy"],
                    ["gnome-control-center", "applications"],
                    ["systemsettings"],
                    ["systemsettings5"],
                ]
            )
        cmds.append(["xdg-open", "settings://privacy"])
        for cmd in cmds:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def request_in_app(
    kind: PermissionKind,
    on_result: ResultCallback | None = None,
) -> None:
    def _done(
        ok: bool,
        *,
        needs_settings: bool = False,
        prompted: bool = False,
    ) -> None:
        if on_result is None:
            return
        try:
            on_result(
                bool(ok),
                needs_settings=bool(needs_settings),
                prompted=bool(prompted),
            )
        except TypeError:
            try:
                on_result(bool(ok), needs_settings=bool(needs_settings))
            except TypeError:
                on_result(bool(ok))

    if is_granted(kind) is True:
        _done(True)
        return

    attempt = _prompt_attempts.get(kind, 0) + 1
    _prompt_attempts[kind] = attempt

    # Windows / Linux path.
    if platform.system() != "Darwin":
        _request_non_darwin(kind, _done, attempt=attempt)
        return

    if kind in ("mic", "camera"):
        _request_mic_camera(kind, _done, attempt=attempt)
        return
    if kind == "screen":
        _request_screen(_done, attempt=attempt)
        return
    if kind == "a11y":
        _request_a11y(_done, attempt=attempt)
        return
    if kind == "automation":
        _request_automation(_done, attempt=attempt)
        return
    _done(False, needs_settings=True)


def _request_non_darwin(
    kind: PermissionKind,
    done: ResultCallback,
    *,
    attempt: int,
) -> None:
    """Qt mic/camera prompts + open the matching OS settings page."""
    if kind in ("mic", "camera"):
        existing = _qt_status(kind)
        if existing is True:
            done(True, prompted=False)
            return

        def _finish(ok: bool, *, prompted: bool = True) -> None:
            granted = bool(ok) or (_qt_status(kind) is True)
            if not granted:
                open_system_settings(kind)
            # Still mark progress so onboarding can continue after Settings opens.
            done(True, needs_settings=not granted, prompted=prompted)

        if _request_via_qt(kind, lambda ok: _finish(ok, prompted=True)):
            return
        opened = open_system_settings(kind)
        done(opened, needs_settings=True, prompted=False)
        return

    # Screen / accessibility / automation — open the relevant settings page.
    opened = open_system_settings(kind)
    done(opened, needs_settings=not opened, prompted=True)


def _settings_on_retry(attempt: int, *, force: bool = False) -> bool:
    return force or attempt >= 2


# ── mic / camera ─────────────────────────────────────────────────────────────

def _mic_camera_granted(kind: Literal["mic", "camera"]) -> bool | None:
    """Granted if ANY reliable signal says authorized."""
    votes: list[bool | None] = []
    votes.append(_av_status(kind))
    votes.append(_qt_status(kind))
    if any(v is True for v in votes):
        return True
    if any(v is False for v in votes):
        return False
    return None


def _qt_status(kind: Literal["mic", "camera"]) -> bool | None:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return None
        perm = _qt_permission(kind)
        if perm is None:
            return None
        status = app.checkPermission(perm)
        if status == Qt.PermissionStatus.Granted:
            return True
        if status == Qt.PermissionStatus.Denied:
            return False
        return None
    except Exception:
        return None


def _request_mic_camera(
    kind: Literal["mic", "camera"],
    done: ResultCallback,
    *,
    attempt: int,
) -> None:
    existing = is_granted(kind)
    if existing is True:
        done(True)
        return

    if existing is False:
        done(False, needs_settings=_settings_on_retry(attempt), prompted=False)
        return

    def _finish(ok: bool, *, prompted: bool = True) -> None:
        granted = is_granted(kind) is True
        done(
            granted,
            needs_settings=(
                False
                if granted
                else _settings_on_retry(attempt, force=is_granted(kind) is False)
            ),
            prompted=prompted,
        )

    if _request_via_avfoundation(kind, lambda ok: _finish(ok, prompted=True)):
        return
    if _request_via_qt(kind, lambda ok: _finish(ok, prompted=True)):
        return
    done(False, needs_settings=_settings_on_retry(attempt, force=True), prompted=False)


def _qt_permission(kind: Literal["mic", "camera"]):
    try:
        from PyQt6.QtMultimedia import QCameraPermission, QMicrophonePermission
    except Exception:
        return None
    if kind == "mic":
        return QMicrophonePermission()
    return QCameraPermission()


def _request_via_qt(
    kind: Literal["mic", "camera"], on_result: Callable[[bool], None]
) -> bool:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None or not hasattr(app, "requestPermission"):
            return False
        perm = _qt_permission(kind)
        if perm is None:
            return False

        def _cb(status) -> None:
            on_result(status == Qt.PermissionStatus.Granted)

        app.requestPermission(perm, _cb)
        return True
    except Exception:
        return False


def _av_status(kind: Literal["mic", "camera"]) -> bool | None:
    try:
        device, media = _av_capture(kind)
        if device is None:
            return None
        status = int(device.authorizationStatusForMediaType_(media))
        if status == 3:
            return True
        if status in (1, 2):
            return False
        return None
    except Exception:
        return None


def _request_via_avfoundation(
    kind: Literal["mic", "camera"], on_result: Callable[[bool], None]
) -> bool:
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        device, media = _av_capture(kind)
        if device is None:
            return False

        status = int(device.authorizationStatusForMediaType_(media))
        if status == 3:
            on_result(True)
            return True
        if status in (1, 2):
            return False

        box: dict[str, bool | None] = {"done": None}

        def _handler(granted) -> None:
            box["done"] = bool(granted)

        device.requestAccessForMediaType_completionHandler_(media, _handler)
        app = QApplication.instance()

        def _poll(n: int = 0) -> None:
            if box["done"] is not None:
                on_result(bool(box["done"]))
                return
            if n > 300:
                on_result(False)
                return
            if app is not None:
                QTimer.singleShot(100, lambda: _poll(n + 1))
            else:
                on_result(False)

        if app is not None:
            QTimer.singleShot(50, lambda: _poll(0))
        else:
            import time

            for _ in range(300):
                if box["done"] is not None:
                    break
                time.sleep(0.1)
            on_result(bool(box["done"]))
        return True
    except Exception:
        return False


def _av_capture(kind: Literal["mic", "camera"]):
    try:
        from Foundation import NSBundle
        import objc

        path = "/System/Library/Frameworks/AVFoundation.framework"
        bundle = NSBundle.bundleWithPath_(path)
        if bundle is not None and not bundle.isLoaded():
            bundle.load()
        AVCaptureDevice = objc.lookUpClass("AVCaptureDevice")
        media = "soun" if kind == "mic" else "vide"
        return AVCaptureDevice, media
    except Exception:
        return None, None


# ── screen ───────────────────────────────────────────────────────────────────

def _screen_granted() -> bool | None:
    """Combine preflight + window-list signal (more reliable after Settings)."""
    preflight: bool | None = None
    try:
        from Quartz import CGPreflightScreenCaptureAccess

        preflight = bool(CGPreflightScreenCaptureAccess())
        if preflight:
            return True
    except Exception:
        preflight = None

    # If we can see other apps' window metadata, Screen Recording is effectively on.
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
        import os

        info = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
        me = os.getpid()
        foreign = 0
        for win in info or []:
            try:
                owner_pid = int(win.get("kCGWindowOwnerPID", 0) or 0)
            except Exception:
                owner_pid = 0
            name = str(win.get("kCGWindowName") or "")
            if owner_pid and owner_pid != me and name:
                foreign += 1
        if foreign >= 2:
            return True
    except Exception:
        pass

    if preflight is False:
        return False
    return None


def _request_screen(done: ResultCallback, *, attempt: int) -> None:
    try:
        from Quartz import CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess
    except Exception:
        done(False, needs_settings=True, prompted=False)
        return

    if is_granted("screen") is True:
        done(True, prompted=False)
        return

    prompted = False
    try:
        CGRequestScreenCaptureAccess()
        prompted = True
    except Exception:
        pass

    if is_granted("screen") is not True:
        try:
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListOptionOnScreenOnly,
            )

            CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )
            prompted = True
        except Exception:
            pass

    granted = is_granted("screen") is True
    done(
        granted,
        needs_settings=_settings_on_retry(attempt) if not granted else False,
        prompted=prompted,
    )


# ── accessibility ────────────────────────────────────────────────────────────

def _a11y_granted() -> bool | None:
    try:
        from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary, NSNumber

        if bool(AXIsProcessTrusted()):
            return True
        # Explicit non-prompting re-check (fresh TCC read).
        opts = NSDictionary.dictionaryWithObject_forKey_(
            NSNumber.numberWithBool_(False),
            "AXTrustedCheckOptionPrompt",
        )
        return bool(AXIsProcessTrustedWithOptions(opts))
    except Exception:
        try:
            from ApplicationServices import AXIsProcessTrusted

            return bool(AXIsProcessTrusted())
        except Exception:
            return None


def _request_a11y(done: ResultCallback, *, attempt: int) -> None:
    if _a11y_granted() is True:
        done(True, prompted=False)
        return
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary, NSNumber

        opts = NSDictionary.dictionaryWithObject_forKey_(
            NSNumber.numberWithBool_(True),
            "AXTrustedCheckOptionPrompt",
        )
        trusted = bool(AXIsProcessTrustedWithOptions(opts))
        # Re-read after sheet — don't trust the return alone.
        if not trusted:
            trusted = _a11y_granted() is True
        done(
            trusted,
            needs_settings=_settings_on_retry(attempt) if not trusted else False,
            prompted=True,
        )
    except Exception:
        done(False, needs_settings=_settings_on_retry(attempt, force=True), prompted=False)


# ── automation ───────────────────────────────────────────────────────────────

def _automation_granted() -> bool | None:
    status = _ae_status(_AUTOMATION_GATE_BUNDLE, ask_user=False)
    if status == 0:
        return True
    if status == _ERR_NOT_PERMITTED:
        return False
    return None


def _request_automation(done: ResultCallback, *, attempt: int) -> None:
    if _automation_granted() is True:
        done(True, prompted=False)
        return

    _warm_system_events()
    prompted = False
    permanently_denied = False

    for bundle in _AUTOMATION_TARGETS:
        code = _ae_status(bundle, ask_user=False)
        if code == 0:
            continue
        if code == _ERR_NOT_PERMITTED:
            if bundle == _AUTOMATION_GATE_BUNDLE:
                permanently_denied = True
            continue
        if code == _ERR_PROC_NOT_FOUND:
            _launch_bundle(bundle)
        _ae_status(bundle, ask_user=True)
        prompted = True
        if bundle == _AUTOMATION_GATE_BUNDLE and _automation_granted() is True:
            done(True, prompted=True)
            return

    granted = _automation_granted() is True
    done(
        granted,
        needs_settings=(
            False
            if granted
            else _settings_on_retry(attempt, force=permanently_denied and not prompted)
        ),
        prompted=prompted,
    )


def _warm_system_events() -> None:
    try:
        subprocess.run(
            ["open", "-b", "com.apple.systemevents"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _launch_bundle(bundle_id: str) -> None:
    try:
        subprocess.run(
            ["open", "-b", bundle_id],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _ae_fn():
    try:
        import objc

        ns: dict = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            objc.loadBundleFunctions(
                objc.loadBundle(
                    "ApplicationServices",
                    globals(),
                    bundle_path=(
                        "/System/Library/Frameworks/ApplicationServices.framework"
                    ),
                ),
                ns,
                [
                    (
                        "AEDeterminePermissionToAutomateTarget",
                        b"i^{AEDesc=I^^{OpaqueAEDataStorageType}}IIZ",
                    )
                ],
            )
        return ns.get("AEDeterminePermissionToAutomateTarget")
    except Exception:
        return None


def _ae_status(bundle_id: str, *, ask_user: bool) -> int | None:
    try:
        from Foundation import NSAppleEventDescriptor

        fn = _ae_fn()
        if fn is None:
            return None
        desc = NSAppleEventDescriptor.descriptorWithBundleIdentifier_(bundle_id)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return int(fn(desc.aeDesc(), _AE_CORE, _AE_GETD, bool(ask_user)))
    except Exception:
        return None
