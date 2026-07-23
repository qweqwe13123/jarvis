"""Devices hub — live linked Windows / Mac installs for multi-device control."""

from __future__ import annotations

import platform
import sys
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
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
    if raw.get("allow_kvm_input") is True:
        bits.append("kvm")
    return " · allows: " + (", ".join(bits) if bits else "none")


class _DeviceRow(QFrame):
    rename_clicked = pyqtSignal(str, str)
    revoke_clicked = pyqtSignal(str, str)
    test_clicked = pyqtSignal(str, str)
    share_input_clicked = pyqtSignal(str, str)  # device_id, name

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
        display = str(device.get("name") or "Unnamed device")
        if online and not is_this:
            share = _btn("Share input", primary=True)
            share.setToolTip("Use this Mac/PC keyboard & mouse on that computer (KVM)")
            share.clicked.connect(lambda: self.share_input_clicked.emit(did, display))
            btns.addWidget(share)

            test = _btn("Test open")
            test.clicked.connect(lambda: self.test_clicked.emit(did, display))
            btns.addWidget(test)

        rename = _btn("Rename")
        rename.clicked.connect(
            lambda: self.rename_clicked.emit(did, str(device.get("name") or ""))
        )
        btns.addWidget(rename)

        if not is_this:
            revoke = _btn("Remove")
            revoke.clicked.connect(lambda: self.revoke_clicked.emit(did, display))
            btns.addWidget(revoke)

        lay.addLayout(btns)


class DevicesView(QWidget):
    """Live linked-devices hub with remote-control permissions."""

    # Emitted from a background thread with a fresh device-sync snapshot so the
    # network fetch never blocks (and never lags) the UI thread.
    _snapshot_ready = pyqtSignal(object)

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
            "Link your Windows PC and Mac. Ask AURA to open apps on the other machine, "
            "or share one keyboard & mouse over LAN — built into AURA."
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
        self._cb_system.setToolTip(
            "Power actions from your other signed-in devices already work (same account). "
            "This shows the capability; leave on."
        )
        self._cb_kvm = QCheckBox("Allow shared keyboard & mouse (KVM over LAN)")
        for cb in (self._cb_control, self._cb_files, self._cb_system, self._cb_kvm):
            cb.setFont(_sans(12))
            cb.setStyleSheet(
                f"QCheckBox {{ color: {T.TEXT_MED}; background: transparent; spacing: 8px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; }}"
            )
            cb.toggled.connect(self._on_perm_toggled)
            pl.addWidget(cb)
        root.addWidget(self._perm_card)
        root.addSpacing(14)

        # Shared keyboard & mouse (KVM) — built into AURA
        self._kvm_card = self._build_kvm_card()
        root.addWidget(self._kvm_card)
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
        self._kvm_busy = False
        self._net_busy = False
        self._peer_devices: list[dict] = []
        self._kvm_timer = QTimer(self)
        self._kvm_timer.setInterval(2000)
        self._kvm_timer.timeout.connect(self._refresh_kvm_status)
        self._snapshot_ready.connect(self._apply_snapshot)


    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh()
        self._timer.start()
        self._kvm_timer.start()
        self._refresh_kvm_status()

    def hideEvent(self, event):  # noqa: N802
        self._timer.stop()
        self._kvm_timer.stop()
        super().hideEvent(event)

    def _ghost_btn(self, text: str, *, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30)
        b.setFont(_sans(11, QFont.Weight.Medium))
        if primary:
            b.setStyleSheet(
                f"QPushButton {{ background: {T.CHAT_ASSIST_ACCENT}; color: #041018; "
                f"border: none; border-radius: 8px; padding: 0 14px; }}"
                f"QPushButton:hover {{ background: #33eeff; }}"
                f"QPushButton:disabled {{ background: {T.BG_ELEVATED}; color: {T.TEXT_DIM}; }}"
            )
        else:
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; "
                f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 0 14px; }}"
                f"QPushButton:hover {{ border-color: {T.BORDER_HI}; color: {T.CHAT_TEXT}; }}"
                f"QPushButton:disabled {{ color: {T.TEXT_DIM}; border-color: {T.BORDER}; }}"
            )
        return b

    def _build_kvm_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("DevicesKvm")
        card.setStyleSheet(
            f"QFrame#DevicesKvm {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; "
            f"border-radius: 14px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        t = QLabel("Shared keyboard & mouse")
        t.setFont(_sans(13, QFont.Weight.DemiBold))
        t.setStyleSheet(f"color: {T.CHAT_TEXT}; background: transparent; border: none;")
        titles.addWidget(t)
        hint = QLabel(
            "Move the cursor past the screen edge to control another linked computer. "
            "No extra apps to install — KVM runs inside AURA on your LAN."
        )
        hint.setWordWrap(True)
        hint.setFont(_sans(11))
        hint.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
        titles.addWidget(hint)
        head.addLayout(titles, stretch=1)
        lay.addLayout(head)

        # Role
        role_row = QHBoxLayout()
        role_row.setSpacing(10)
        rl = QLabel("This device")
        rl.setFont(_sans(12))
        rl.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        rl.setMinimumWidth(100)
        role_row.addWidget(rl)
        self._kvm_role = QComboBox()
        self._kvm_role.addItem("Server — has keyboard & mouse", "server")
        self._kvm_role.addItem("Client — controlled by the other PC", "client")
        self._kvm_role.setFixedHeight(32)
        self._kvm_role.setFont(_sans(12))
        self._kvm_role.setStyleSheet(self._combo_style())
        self._kvm_role.currentIndexChanged.connect(self._on_kvm_prefs_changed)
        role_row.addWidget(self._kvm_role, stretch=1)
        lay.addLayout(role_row)

        # Peer device
        peer_row = QHBoxLayout()
        peer_row.setSpacing(10)
        plbl = QLabel("Peer device")
        plbl.setFont(_sans(12))
        plbl.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        plbl.setMinimumWidth(100)
        peer_row.addWidget(plbl)
        self._kvm_peer = QComboBox()
        self._kvm_peer.setFixedHeight(32)
        self._kvm_peer.setFont(_sans(12))
        self._kvm_peer.setStyleSheet(self._combo_style())
        self._kvm_peer.currentIndexChanged.connect(self._on_kvm_peer_changed)
        peer_row.addWidget(self._kvm_peer, stretch=1)
        lay.addLayout(peer_row)

        # Layout
        lay_row = QHBoxLayout()
        lay_row.setSpacing(10)
        ll = QLabel("Layout")
        ll.setFont(_sans(12))
        ll.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        ll.setMinimumWidth(100)
        lay_row.addWidget(ll)
        self._kvm_layout = QComboBox()
        from jarvis_ui.kvm.config import LAYOUT_LABELS

        for key, label in LAYOUT_LABELS.items():
            self._kvm_layout.addItem(label, key)
        self._kvm_layout.setFixedHeight(32)
        self._kvm_layout.setFont(_sans(12))
        self._kvm_layout.setStyleSheet(self._combo_style())
        self._kvm_layout.currentIndexChanged.connect(self._on_kvm_prefs_changed)
        lay_row.addWidget(self._kvm_layout, stretch=1)
        lay.addLayout(lay_row)

        # Peer host (LAN IP)
        host_row = QHBoxLayout()
        host_row.setSpacing(10)
        hl = QLabel("Peer LAN IP")
        hl.setFont(_sans(12))
        hl.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        hl.setMinimumWidth(100)
        host_row.addWidget(hl)
        self._kvm_host = QLineEdit()
        self._kvm_host.setPlaceholderText("e.g. 192.168.1.42 — required for Client")
        self._kvm_host.setFixedHeight(32)
        self._kvm_host.setFont(_sans(12))
        self._kvm_host.setStyleSheet(
            f"QLineEdit {{ background: {T.BG_ELEVATED}; color: {T.CHAT_TEXT}; "
            f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 0 10px; }}"
            f"QLineEdit:focus {{ border: 1px solid {T.BORDER_HI}; }}"
        )
        self._kvm_host.editingFinished.connect(self._on_kvm_prefs_changed)
        host_row.addWidget(self._kvm_host, stretch=1)
        lay.addLayout(host_row)

        self._kvm_engine = QLabel("")
        self._kvm_engine.setWordWrap(True)
        self._kvm_engine.setFont(_sans(11))
        self._kvm_engine.setStyleSheet(
            f"color: {T.TEXT_DIM}; background: transparent; border: none;"
        )
        lay.addWidget(self._kvm_engine)

        self._kvm_status = QLabel("Status: —")
        self._kvm_status.setWordWrap(True)
        self._kvm_status.setFont(_sans(12, QFont.Weight.Medium))
        self._kvm_status.setStyleSheet(
            f"color: {T.CHAT_TEXT}; background: transparent; border: none;"
        )
        lay.addWidget(self._kvm_status)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._kvm_start = self._ghost_btn("Start", primary=True)
        self._kvm_start.clicked.connect(self._on_kvm_start)
        actions.addWidget(self._kvm_start)
        self._kvm_stop = self._ghost_btn("Stop")
        self._kvm_stop.clicked.connect(self._on_kvm_stop)
        actions.addWidget(self._kvm_stop)
        actions.addStretch(1)
        lay.addLayout(actions)

        return card

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background: {T.BG_ELEVATED}; color: {T.CHAT_TEXT}; "
            f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 0 10px; }}"
            f"QComboBox:hover {{ border-color: {T.BORDER_HI}; }}"
            f"QComboBox::drop-down {{ border: none; width: 24px; }}"
            f"QComboBox QAbstractItemView {{ background: {T.BG_CARD}; color: {T.CHAT_TEXT}; "
            f"selection-background-color: {T.BORDER_HI}; border: 1px solid {T.BORDER}; }}"
        )

    def refresh(self) -> None:
        from jarvis_ui import user_account as UA
        from jarvis_ui import device_sync as DS

        if not UA.is_authenticated():
            self._status.setText("Sign in from the profile menu to link this computer.")
            self._perm_card.setEnabled(False)
            self._kvm_card.setEnabled(False)
            self._render_devices([])
            self._refresh_kvm_status()
            return

        self._perm_card.setEnabled(True)
        self._kvm_card.setEnabled(True)

        # Paint instantly from the cached snapshot (no network → no lag), then
        # fetch fresh data off the UI thread and update when it arrives.
        try:
            cached = DS.start_device_sync().snapshot()
            self._apply_snapshot(cached)
        except Exception:
            pass
        self._kick_network_refresh()

    def _kick_network_refresh(self) -> None:
        """Fetch a fresh snapshot on a background thread (never blocks the UI)."""
        if self._net_busy:
            return
        self._net_busy = True

        def _work() -> None:
            from jarvis_ui import device_sync as DS

            try:
                snap = DS.start_device_sync().refresh_now()
            except Exception as e:
                snap = {"error": str(e)}
            finally:
                self._net_busy = False
            try:
                self._snapshot_ready.emit(snap)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True, name="DevicesRefresh").start()

    def _apply_snapshot(self, snap: object) -> None:
        """Render a snapshot on the UI thread (from cache or the network worker)."""
        if not isinstance(snap, dict):
            return
        from jarvis_ui import device_sync as DS

        devices = list(snap.get("devices") or [])
        err = str(snap.get("error") or "")
        if err and not devices:
            # Keep whatever is already on screen; just surface the error.
            self._status.setText(err)
            self._refresh_kvm_status()
            return

        online_n = sum(1 for d in devices if d.get("online"))
        last = str(snap.get("last_job") or "")
        self._status.setText(
            f"{len(devices)} linked · {online_n} online · this device: {snap.get('name')}"
            + (f" · {last}" if last else "")
        )
        self._load_perm_checks(snap.get("permissions") or DS.get_local_permissions())
        for d in devices:
            if d.get("isThisDevice") or d.get("is_this_device"):
                self._this_device_id = str(d.get("id") or "")
                break
        self._peer_devices = [
            d
            for d in devices
            if not (d.get("isThisDevice") or d.get("is_this_device"))
        ]
        self._populate_kvm_peers()
        self._render_devices(devices)
        self._refresh_kvm_status()

    def _load_perm_checks(self, perms: dict) -> None:
        self._perm_busy = True
        try:
            self._cb_control.setChecked(bool(perms.get("allow_remote_control", True)))
            self._cb_files.setChecked(bool(perms.get("allow_remote_files", False)))
            self._cb_system.setChecked(bool(perms.get("allow_remote_system", False)))
            self._cb_kvm.setChecked(bool(perms.get("allow_kvm_input", False)))
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
                "allow_kvm_input": self._cb_kvm.isChecked(),
            }
            DS.set_local_permissions(perms)
            if self._this_device_id:
                try:
                    DS.patch_remote_permissions(self._this_device_id, perms)
                except Exception:
                    pass
            # Push on next heartbeat — off the UI thread so toggling is snappy.
            self._kick_network_refresh()
            self._status.setText("Permissions saved — other devices will see them on next sync.")
            self._refresh_kvm_status()
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
            row.share_input_clicked.connect(self._on_share_input)
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

    # ── KVM ─────────────────────────────────────────────────────────────────

    def _populate_kvm_peers(self) -> None:
        if self._kvm_busy:
            return
        self._kvm_busy = True
        try:
            from jarvis_ui.kvm import prefs as kvm_prefs

            pref = kvm_prefs.load_prefs()
            cur = str(pref.get("peer_device_id") or "")
            self._kvm_peer.blockSignals(True)
            self._kvm_peer.clear()
            self._kvm_peer.addItem("Select a linked device…", "")
            for d in self._peer_devices:
                did = str(d.get("id") or "")
                name = str(d.get("name") or "Device")
                online = "online" if d.get("online") else "offline"
                lan = str(d.get("lan_ip") or d.get("lanIp") or "").strip()
                label = f"{name} · {online}"
                if lan:
                    label += f" · {lan}"
                self._kvm_peer.addItem(label, did)
            idx = self._kvm_peer.findData(cur)
            self._kvm_peer.setCurrentIndex(max(0, idx))
            self._kvm_peer.blockSignals(False)

            # Role / layout / host from prefs
            self._kvm_role.blockSignals(True)
            ridx = self._kvm_role.findData(str(pref.get("role") or "server"))
            self._kvm_role.setCurrentIndex(max(0, ridx))
            self._kvm_role.blockSignals(False)

            self._kvm_layout.blockSignals(True)
            lidx = self._kvm_layout.findData(str(pref.get("layout") or "peer_right"))
            self._kvm_layout.setCurrentIndex(max(0, lidx))
            self._kvm_layout.blockSignals(False)

            if not self._kvm_host.hasFocus():
                self._kvm_host.blockSignals(True)
                self._kvm_host.setText(str(pref.get("peer_host") or ""))
                self._kvm_host.blockSignals(False)
        finally:
            self._kvm_busy = False

    def _selected_peer(self) -> dict | None:
        did = str(self._kvm_peer.currentData() or "")
        if not did:
            return None
        for d in self._peer_devices:
            if str(d.get("id") or "") == did:
                return d
        return None

    def _on_kvm_peer_changed(self, *_args) -> None:
        if self._kvm_busy:
            return
        peer = self._selected_peer()
        if peer is None:
            self._on_kvm_prefs_changed()
            return
        lan = str(peer.get("lan_ip") or peer.get("lanIp") or "").strip()
        if lan and not self._kvm_host.text().strip():
            self._kvm_host.setText(lan)
        self._on_kvm_prefs_changed()

    def _on_kvm_prefs_changed(self, *_args) -> None:
        if self._kvm_busy:
            return
        peer = self._selected_peer()
        from jarvis_ui.kvm import get_kvm_manager

        get_kvm_manager().update_prefs(
            role=str(self._kvm_role.currentData() or "server"),
            layout=str(self._kvm_layout.currentData() or "peer_right"),
            peer_device_id=str(self._kvm_peer.currentData() or ""),
            peer_name=str(peer.get("name") or "") if peer else "",
            peer_host=self._kvm_host.text().strip(),
        )
        self._refresh_kvm_status()

    def _refresh_kvm_status(self) -> None:
        try:
            from jarvis_ui.kvm import get_kvm_manager

            snap = get_kvm_manager().snapshot()
        except Exception as e:
            self._kvm_status.setText(f"Status: error — {e}")
            return

        eng = snap.engine_label
        lan = snap.lan_ip or "—"
        link = "peer linked" if snap.connected else "waiting for peer"
        mode = "controlling peer" if snap.remote else "local"
        self._kvm_engine.setText(
            f"Engine: {eng}  ·  This LAN IP: {lan}  ·  Port: {snap.port}  ·  {link}"
        )
        st = snap.status.value
        color = {
            "running": "#34d399",
            "starting": T.CHAT_ASSIST_ACCENT,
            "error": "#f87171",
            "missing": "#fbbf24",
            "stopped": T.TEXT_MED,
        }.get(st, T.TEXT_MED)
        self._kvm_status.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        detail = snap.message or st
        if snap.status.value == "running":
            detail = f"{detail}  ·  {mode}"
        self._kvm_status.setText(f"Status: {st} — {detail}")

        running = snap.status.value == "running"
        # Start is always available when stopped — pressing it grants the local
        # KVM permission automatically (implicit consent on your own machine).
        self._kvm_start.setEnabled(not running)
        self._kvm_stop.setEnabled(running or snap.status.value == "starting")

    def _ensure_kvm_permission(self) -> None:
        """Pressing Start on your own machine implies consent — turn the
        KVM permission on and persist it so incoming invites also work."""
        if self._cb_kvm.isChecked():
            return
        self._cb_kvm.blockSignals(True)
        self._cb_kvm.setChecked(True)
        self._cb_kvm.blockSignals(False)
        try:
            from jarvis_ui import device_sync as DS

            perms = {
                "allow_remote_control": self._cb_control.isChecked(),
                "allow_remote_files": self._cb_files.isChecked(),
                "allow_remote_system": self._cb_system.isChecked(),
                "allow_kvm_input": True,
            }
            DS.set_local_permissions(perms)
            if self._this_device_id:
                try:
                    DS.patch_remote_permissions(self._this_device_id, perms)
                except Exception:
                    pass
        except Exception:
            pass

    def _prompt_input_permission(self, message: str) -> None:
        from jarvis_ui.kvm.permission import open_input_settings

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("KVM needs input permission")
        box.setText(message or "Grant input permission, then press Start again.")
        open_btn = box.addButton("Open Settings", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            open_input_settings()

    def _on_kvm_start(self) -> None:
        # One-click Start (Barrier-style): grant the local permission implicitly.
        self._ensure_kvm_permission()
        self._on_kvm_prefs_changed()
        try:
            from jarvis_ui.kvm import KvmRole, get_kvm_manager

            role = KvmRole(str(self._kvm_role.currentData() or "server"))
            peer = self._selected_peer()
            mgr = get_kvm_manager()
            snap = mgr.start(
                role=role,
                peer_host=self._kvm_host.text().strip(),
                peer_name=str(peer.get("name") or "") if peer else "",
                peer_device_id=str(self._kvm_peer.currentData() or ""),
                layout=str(self._kvm_layout.currentData() or "peer_right"),
                invite_peer=True,
            )
            self._refresh_kvm_status()
            if snap.status.value == "error":
                if getattr(snap, "needs_input_permission", False):
                    self._prompt_input_permission(snap.message)
                else:
                    QMessageBox.warning(self, "KVM", snap.message)
            elif snap.status.value == "running" and role == KvmRole.SERVER:
                QMessageBox.information(
                    self,
                    "KVM server running",
                    "Built into AURA — no extra install.\n\n"
                    "Move your mouse past the screen edge toward the peer.\n"
                    "Press Ctrl+Shift+Alt+Q to return control here.\n\n"
                    f"Your LAN IP (for the other PC if needed): {snap.lan_ip or '—'}\n"
                    "On the other computer: set role to Client, enter this IP and "
                    "Start — or accept the automatic invite.",
                )
        except Exception as e:
            QMessageBox.warning(self, "KVM", str(e))
            self._refresh_kvm_status()

    def _on_kvm_stop(self) -> None:
        try:
            from jarvis_ui.kvm import get_kvm_manager

            get_kvm_manager().stop()
            self._refresh_kvm_status()
        except Exception as e:
            QMessageBox.warning(self, "KVM", str(e))

    def _on_share_input(self, device_id: str, name: str) -> None:
        """Quick path from a device row → fill KVM card and start as server."""
        if not self._cb_kvm.isChecked():
            self._cb_kvm.setChecked(True)
        idx = self._kvm_peer.findData(device_id)
        if idx >= 0:
            self._kvm_peer.setCurrentIndex(idx)
        self._kvm_role.setCurrentIndex(self._kvm_role.findData("server"))
        peer = self._selected_peer()
        lan = ""
        if peer:
            lan = str(peer.get("lan_ip") or peer.get("lanIp") or "").strip()
        if lan:
            self._kvm_host.setText(lan)
        self._on_kvm_prefs_changed()
        ans = QMessageBox.question(
            self,
            "Share input",
            f"Start built-in KVM and invite “{name}” to connect?\n\n"
            "Both machines need AURA running on the same Wi‑Fi, "
            "with KVM permission enabled on the other PC.",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._on_kvm_start()
