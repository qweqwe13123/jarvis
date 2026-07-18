"""Auto-install from DMG → /Applications (no drag-and-drop, no Install button).

Flow when the user double-clicks AURA.app on the installer disk:
  1) Brief splash ("Installing AURA…")
  2) ditto copy into /Applications (preserves codesign + staple)
  3) Relaunch from /Applications
  4) This DMG process exits → onboarding runs in the installed app

If already launched from /Applications (or anywhere not under /Volumes),
this module is a no-op.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def app_bundle_path() -> Path | None:
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    exe = Path(sys.executable).resolve()
    # …/AURA.app/Contents/MacOS/AURA
    if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
        return exe.parent.parent.parent
    return None


def running_from_removable_volume() -> bool:
    """True when the .app lives on a DMG /Volumes mount (read-only installer)."""
    app = app_bundle_path()
    if app is None:
        return False
    try:
        resolved = app.resolve()
    except Exception:
        resolved = app
    parts = resolved.parts
    if "Volumes" in parts:
        return True
    try:
        if not os.access(resolved, os.W_OK):
            if Path("/Volumes") in resolved.parents or str(resolved).startswith("/Volumes/"):
                return True
    except Exception:
        pass
    return False


def applications_target() -> Path:
    return Path("/Applications") / "AURA.app"


def install_to_applications() -> Path:
    """Copy current bundle into /Applications (ditto preserves codesign + staple).

    On failure, restores any previous /Applications/AURA.app from a backup.
    """
    src = app_bundle_path()
    if src is None or not src.is_dir():
        raise RuntimeError("Could not locate AURA.app bundle")
    if not (src / "Contents" / "MacOS").is_dir():
        raise RuntimeError("Installer disk copy looks incomplete")

    dst = applications_target()
    bak = Path(str(dst) + ".aura-install-bak")
    if bak.exists():
        shutil.rmtree(bak, ignore_errors=True)

    had_previous = False
    if dst.exists():
        had_previous = True
        try:
            dst.rename(bak)
        except Exception:
            # Last resort: remove in place (cannot rename, e.g. permissions).
            shutil.rmtree(dst, ignore_errors=True)
            had_previous = False

    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        try:
            subprocess.check_call(
                ["ditto", str(src), str(dst)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as ditto_err:
            # Fallback only if ditto is unavailable; prefer failing over a
            # codesign-breaking Python copy when ditto exists but errored.
            if shutil.which("ditto"):
                raise RuntimeError(
                    f"Could not copy AURA into Applications ({ditto_err}). "
                    "Check that you can write to /Applications."
                ) from ditto_err
            shutil.copytree(src, dst, symlinks=True)

        if not (dst / "Contents" / "MacOS").is_dir():
            raise RuntimeError("Installed app looks incomplete")

        # Best-effort: drop quarantine so Gatekeeper trusts the relocated copy.
        subprocess.call(
            ["xattr", "-dr", "com.apple.quarantine", str(dst)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        if had_previous and bak.exists():
            try:
                bak.rename(dst)
            except Exception:
                pass
        raise

    if bak.exists():
        shutil.rmtree(bak, ignore_errors=True)
    return dst


def relaunch_installed(dst: Path | None = None) -> None:
    """Open the installed app in a new process (detached from the DMG instance)."""
    target = dst or applications_target()
    subprocess.Popen(
        ["open", "-n", str(target)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_install_gate_if_needed() -> bool:
    """
    If launched from a DMG, auto-install to Applications and relaunch.

    Returns True if this process should exit (install handled / user quit).
    Returns False when not on a removable volume (normal launch continues).
    """
    if not running_from_removable_volume():
        return False

    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from jarvis_ui.onboarding import tokens as T
    from jarvis_ui.onboarding.widgets import BlackPillButton, aura_logo

    class _InstallWorker(QThread):
        ok = pyqtSignal(str)
        fail = pyqtSignal(str)

        def run(self) -> None:  # noqa: D401 — QThread entry
            try:
                path = install_to_applications()
                self.ok.emit(str(path))
            except Exception as exc:
                self.fail.emit(str(exc) or "Install failed")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    win = QWidget()
    win.setObjectName("InstallGate")
    win.setWindowTitle("Installing AURA")
    win.setFixedSize(440, 280)
    win.setStyleSheet(f"QWidget#InstallGate {{ background: {T.CREAM}; }}")

    root = QVBoxLayout(win)
    root.setContentsMargins(40, 36, 40, 32)
    root.setSpacing(0)

    brand = QHBoxLayout()
    brand.setSpacing(10)
    brand.addWidget(aura_logo(36))
    name = QLabel("AURA")
    name.setFont(T.sans(16, QFont.Weight.DemiBold))
    name.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
    brand.addWidget(name)
    brand.addStretch(1)
    root.addLayout(brand)
    root.addSpacing(28)

    title = QLabel("Installing AURA…")
    title.setObjectName("InstallTitle")
    title.setFont(T.display(24, QFont.Weight.DemiBold))
    title.setWordWrap(True)
    title.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
    root.addWidget(title)
    root.addSpacing(10)

    body = QLabel(
        "Copying to Applications so your key, setup, and updates "
        "work reliably. This takes a few seconds."
    )
    body.setObjectName("InstallBody")
    body.setWordWrap(True)
    body.setFont(T.sans(13))
    body.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
    root.addWidget(body)
    root.addSpacing(18)

    status = QLabel("Preparing…")
    status.setWordWrap(True)
    status.setFont(T.sans(12))
    status.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
    root.addWidget(status)
    root.addStretch(1)

    actions = QHBoxLayout()
    actions.setSpacing(12)

    retry_btn = BlackPillButton("Try again")
    retry_btn.setMinimumWidth(140)
    retry_btn.hide()

    quit_btn = QPushButton("Quit")
    quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    quit_btn.setFixedHeight(40)
    quit_btn.setStyleSheet(
        f"QPushButton {{ background: transparent; color: {T.MUTED}; border: none; "
        f"font-size: 13px; }}"
        f"QPushButton:hover {{ color: {T.INK}; }}"
    )
    quit_btn.hide()

    actions.addWidget(retry_btn, 0, Qt.AlignmentFlag.AlignLeft)
    actions.addWidget(quit_btn, 0, Qt.AlignmentFlag.AlignLeft)
    actions.addStretch(1)
    root.addLayout(actions)

    worker: _InstallWorker | None = None
    installing = {"active": False}

    def _set_busy(busy: bool) -> None:
        installing["active"] = busy
        if busy:
            title.setText("Installing AURA…")
            body.setText(
                "Copying to Applications so your key, setup, and updates "
                "work reliably. This takes a few seconds."
            )
            status.setText("Copying to Applications…")
            status.setStyleSheet(
                f"color: {T.MUTED}; background: transparent; border: none;"
            )
            retry_btn.hide()
            quit_btn.hide()
            quit_btn.setEnabled(False)
        else:
            quit_btn.setEnabled(True)

    def _on_ok(path: str) -> None:
        _set_busy(False)
        title.setText("Almost ready")
        body.setText("Installed. Opening AURA from Applications…")
        status.setText("Opening…")
        app.processEvents()
        try:
            relaunch_installed(Path(path))
        except Exception as exc:
            _on_fail(f"Installed, but could not open AURA.\n\n{exc}")
            return
        # Give launchd a beat to start the new process, then exit the DMG instance.
        QTimer.singleShot(350, app.quit)

    def _on_fail(message: str) -> None:
        _set_busy(False)
        title.setText("Couldn’t install AURA")
        body.setText(
            "AURA needs to live in Applications. "
            "Check that you can write to /Applications, then try again."
        )
        status.setText(message[:280])
        status.setStyleSheet(
            "color: #C0392B; background: transparent; border: none;"
        )
        retry_btn.show()
        quit_btn.show()

    def _start() -> None:
        nonlocal worker
        if installing["active"]:
            return
        _set_busy(True)
        worker = _InstallWorker()
        worker.ok.connect(_on_ok)
        worker.fail.connect(_on_fail)
        worker.start()

    retry_btn.clicked.connect(_start)
    quit_btn.clicked.connect(app.quit)

    # Paint splash first, then start copy (no Install button).
    win.show()
    win.raise_()
    win.activateWindow()
    QTimer.singleShot(80, _start)
    app.exec()
    return True
