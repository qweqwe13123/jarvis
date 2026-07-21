"""Devices hub — live linked Windows / Mac installs for multi-device control."""

from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T


def _sans(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
    f = QFont(family, size, weight)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    return f


def _platform_label(plat: str | None) -> str:
    p = (plat or "").lower()
    if p == "darwin":
        return "macOS"
    if p == "win32":
        return "Windows"
    if p.startswith("linux"):
        return "Linux"
    return plat or "Unknown"


def _perm_summary(device: dict) -> str:
    raw = device.get("permissions") or {}
    if not isinstance(raw, dict):
        raw = {}
    bits = []
    if raw.get("allow_remote_control", True) is not False:
        bits.append("control")
    if raw.get("allow_remote_files") is True:
        bits.append("files")
    if raw.get("allow_remote_system") is True:
        bits.append("system")
    return " · allows: " + (", ".join(bits) if bits else "none")


class _DeviceRow(QFrame):
    rename_clicked = pyqtSignal(str, str)
    revoke_clicked = pyqtSignal(str, str)
    test_clicked = pyqtSignal(str, str)

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self._device = device
        self.setObjectName("DeviceRow")
        online = bool(device.get("online"))
        is_this = bool(device.get("isThisDevice") or device.get("is_this_device"))
        border = T.BORDER_HI if online else T.BORDER
        self.setStyleSheet(
            f"""
            QFrame#DeviceRow {{
                background: {T.BG_CARD};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 14, 14)
        lay.setSpacing(14)

        dot = QLabel("●")
        dot.setFont(_sans(14))
        dot.setStyleSheet(
            f"color: {'#34d399' if online else '#6b7280'}; "
            "background: transparent; border: none;"
        )
        lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        name = str(device.get("name") or "Unnamed device")
        if is_this:
            name = (
                f"{name}  ·  This Mac"
                if sys.platform == "darwin"
                else f"{name}  ·  This PC"
            )
        title = QLabel(name)
        title.setFont(_sans(14, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent; border: none;")
        mid.addWidget(title)

        meta = QLabel(
            f"{_platform_label(device.get('platform'))}"
            + (
                f"  ·  v{device.get('appVersion') or device.get('app_version')}"
                if (device.get("appVersion") or device.get("app_version"))
                else ""
            )
            + (f"  ·  {'Online' if online else 'Offline'}")
            + _perm_summary(device)
        )
        meta.setWordWrap(True)
        meta.setFont(_sans(12))
        meta.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
        mid.addWidget(meta)
        lay.addLayout(mid, stretch=1)

        btns = QHBoxLayout()
        btns.setSpacing(8)

        def _btn(text: str, primary: bool = False) -> QPushButton:
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30)
            b.setFont(_sans(11, QFont.Weight.Medium))
            if primary:
                b.setStyleSheet(
                    f"QPushButton {{ background: {T.CHAT_ASSIST_ACCENT}; color: #041018; "
                    f"border: none; border-radius: 8px; padding: 0 12px; }}"
                    f"QPushButton:hover {{ background: #33eeff; }}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; "
                    f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 0 12px; }}"
                    f"QPushButton:hover {{ border-color: {T.BORDER_HI}; color: {T.CHAT_TEXT}; }}"
                )
            return b

        did = str(device.get("id") or "")
        if online and not is_this:
            test = _btn("Test open", primary=True)
            test.clicked.connect(lambda: self.test_clicked.emit(did, name))
            btns.addWidget(test)

        rename = _btn("Rename")
        rename.clicked.connect(
            lambda: self.rename_clicked.emit(did, str(device.get("name") or ""))
        )
        btns.addWidget(rename)

        if not is_this:
            revoke = _btn("Remove")
            revoke.clicked.connect(lambda: self.revoke_clicked.emit(did, name))
            btns.addWidget(revoke)

        lay.addLayout(btns)


class DevicesView(QWidget):
    """Live linked-devices hub with remote-control permissions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DevicesView")
        self.setStyleSheet(f"QWidget#DevicesView {{ background: {T.CHAT_BG}; }}")
        self._this_device_id = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("Devices")
        title.setFont(_sans(28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.WHITE}; background: transparent; border: none;")
        titles.addWidget(title)
        self._subtitle = QLabel(
            "Link your Windows PC and Mac. When both are online, ask AURA to open apps, "
            "browse, click, type, or run tasks on the other machine — gated by the toggles below."
        )
        self._subtitle.setWordWrap(True)
        self._subtitle.setFont(_sans(13))
        self._subtitle.setStyleSheet(
            f"color: {T.TEXT_DIM}; background: transparent; border: none;"
        )
        titles.addWidget(self._subtitle)
        head.addLayout(titles, stretch=1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFixedHeight(34)
        self._refresh_btn.setFont(_sans(12, QFont.Weight.Medium))
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {T.BG_ELEVATED}; color: {T.CHAT_TEXT}; "
            f"border: 1px solid {T.BORDER_HI}; border-radius: 10px; padding: 0 16px; }}"
            f"QPushButton:hover {{ background: {T.BG_CARD}; }}"
        )
        self._refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self._refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)
        root.addSpacing(18)

        # Permissions card (this machine)
        self._perm_card = QFrame()
        self._perm_card.setObjectName("DevicesPerms")
        self._perm_card.setStyleSheet(
            f"QFrame#DevicesPerms {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; "
            f"border-radius: 14px; }}"
        )
        pl = QVBoxLayout(self._perm_card)
        pl.setContentsMargins(18, 14, 18, 14)
        pl.setSpacing(8)
        pt = QLabel("What other devices may do on this computer")
        pt.setFont(_sans(13, QFont.Weight.DemiBold))
        pt.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent; border: none;")
        pl.addWidget(pt)

        self._cb_control = QCheckBox("Allow remote control (apps, browser, mouse/keyboard, agents)")
        self._cb_files = QCheckBox("Allow remote files (read / write / delete)")
        self._cb_system = QCheckBox("Allow remote system (shutdown, restart, lock)")
        for cb in (self._cb_control, self._cb_files, self._cb_system):
            cb.setFont(_sans(12))
            cb.setStyleSheet(
                f"QCheckBox {{ color: {T.TEXT_MED}; background: transparent; spacing: 8px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; }}"
            )
            cb.toggled.connect(self._on_perm_toggled)
            pl.addWidget(cb)
        root.addWidget(self._perm_card)
        root.addSpacing(14)

        self._status = QLabel("")
        self._status.setFont(_sans(12))
        self._status.setStyleSheet(
            f"color: {T.TEXT_MED}; background: transparent; border: none;"
        )
        root.addWidget(self._status)
        root.addSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(10)
        self._list_lay.addStretch(1)
        scroll.setWidget(self._list_host)
        root.addWidget(scroll, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(8000)
        self._timer.timeout.connect(self.refresh)
        self._perm_busy = False

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        from jarvis_ui import user_account as UA
        from jarvis_ui import device_sync as DS

        if not UA.is_authenticated():
            self._status.setText("Sign in from the profile menu to link this computer.")
            self._perm_card.setEnabled(False)
            self._render_devices([])
            return

        self._perm_card.setEnabled(True)
        try:
            snap = DS.start_device_sync().refresh_now()
            devices = list(snap.get("devices") or [])
            err = str(snap.get("error") or "")
            online_n = sum(1 for d in devices if d.get("online"))
            last = str(snap.get("last_job") or "")
            self._status.setText(
                err
                or (
                    f"{len(devices)} linked · {online_n} online · this device: {snap.get('name')}"
                    + (f" · {last}" if last else "")
                )
            )
            self._load_perm_checks(snap.get("permissions") or DS.get_local_permissions())
            for d in devices:
                if d.get("isThisDevice") or d.get("is_this_device"):
                    self._this_device_id = str(d.get("id") or "")
                    break
            self._render_devices(devices)
        except Exception as e:
            self._status.setText(str(e))
            self._render_devices([])

    def _load_perm_checks(self, perms: dict) -> None:
        self._perm_busy = True
        try:
            self._cb_control.setChecked(bool(perms.get("allow_remote_control", True)))
            self._cb_files.setChecked(bool(perms.get("allow_remote_files", False)))
            self._cb_system.setChecked(bool(perms.get("allow_remote_system", False)))
        finally:
            self._perm_busy = False

    def _on_perm_toggled(self, *_args) -> None:
        if self._perm_busy:
            return
        try:
            from jarvis_ui import device_sync as DS

            perms = {
                "allow_remote_control": self._cb_control.isChecked(),
                "allow_remote_files": self._cb_files.isChecked(),
                "allow_remote_system": self._cb_system.isChecked(),
            }
            DS.set_local_permissions(perms)
            if self._this_device_id:
                try:
                    DS.patch_remote_permissions(self._this_device_id, perms)
                except Exception:
                    pass
            # Push on next heartbeat immediately.
            DS.start_device_sync().refresh_now()
            self._status.setText("Permissions saved — other devices will see them on next sync.")
        except Exception as e:
            QMessageBox.warning(self, "Devices", str(e))

    def _clear_list(self) -> None:
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_devices(self, devices: list[dict]) -> None:
        self._clear_list()
        if not devices:
            empty = QFrame()
            empty.setObjectName("DevicesEmpty")
            empty.setStyleSheet(
                f"QFrame#DevicesEmpty {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; "
                f"border-radius: 14px; }}"
            )
            el = QVBoxLayout(empty)
            el.setContentsMargins(22, 20, 22, 20)
            t = QLabel("No linked devices yet")
            t.setFont(_sans(14, QFont.Weight.DemiBold))
            t.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent; border: none;")
            el.addWidget(t)
            h = QLabel(
                "Install AURA on your other computer, sign in with the same account, "
                "and open this page — both will appear here when online."
            )
            h.setWordWrap(True)
            h.setFont(_sans(12))
            h.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
            el.addWidget(h)
            self._list_lay.addWidget(empty)
            self._list_lay.addStretch(1)
            return

        for d in devices:
            row = _DeviceRow(d)
            row.rename_clicked.connect(self._on_rename)
            row.revoke_clicked.connect(self._on_revoke)
            row.test_clicked.connect(self._on_test)
            self._list_lay.addWidget(row)
        self._list_lay.addStretch(1)

    def _on_rename(self, device_id: str, current: str) -> None:
        name, ok = QInputDialog.getText(
            self, "Rename device", "Display name:", text=current
        )
        if not ok or not name.strip():
            return
        try:
            from jarvis_ui import device_sync as DS

            snap = DS.start_device_sync().snapshot()
            if str(snap.get("device_key") or "") and any(
                str(d.get("id")) == device_id and d.get("isThisDevice")
                for d in (snap.get("devices") or [])
            ):
                DS.set_device_display_name(name.strip())
            DS.rename_remote_device(device_id, name.strip())
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Devices", str(e))

    def _on_revoke(self, device_id: str, name: str) -> None:
        ans = QMessageBox.question(
            self,
            "Remove device",
            f"Remove “{name}” from your account? You can re-link by signing in again on that machine.",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            from jarvis_ui import device_sync as DS

            DS.revoke_remote_device(device_id)
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Devices", str(e))

    def _on_test(self, device_id: str, name: str) -> None:
        try:
            from jarvis_ui import device_sync as DS

            DS.enqueue_job(
                device_id,
                "open_url",
                {"url": "https://www.hiauraai.com"},
            )
            QMessageBox.information(
                self,
                "Test sent",
                f"Asked “{name}” to open hiauraai.com.\n"
                "Keep AURA running on that machine — it should open within a few seconds.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Devices", str(e))
