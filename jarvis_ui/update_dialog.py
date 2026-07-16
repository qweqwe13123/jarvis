from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.updater.service import UpdateService, UpdateState
from core.version import VERSION


class UpdateDialog(QDialog):
    def __init__(self, service: UpdateService, parent_pid: int, parent=None):
        super().__init__(parent)
        self._service = service
        self._parent_pid = parent_pid
        self.setWindowTitle("Update available")
        self.setModal(True)
        self.resize(520, 420)

        self._title = QLabel("A new version of AURA is available")
        self._title.setStyleSheet("font-size: 18px; font-weight: 600; color: #e8f8ff;")

        self._version = QLabel("")
        self._version.setStyleSheet("color: #7eb8d4;")

        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setStyleSheet(
            "background: #08121c; color: #c8eeff; border: 1px solid #143040; border-radius: 8px;"
        )

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.hide()

        self._status = QLabel("")
        self._status.setStyleSheet("color: #5a8fa8; font-size: 12px;")

        self._update_btn = QPushButton("Update now")
        self._later_btn = QPushButton("Remind me later")
        self._skip_btn = QPushButton("Skip this version")

        self._update_btn.clicked.connect(self._start_update)
        self._later_btn.clicked.connect(self.reject)
        self._skip_btn.clicked.connect(self._skip)

        actions = QHBoxLayout()
        actions.addWidget(self._later_btn)
        actions.addWidget(self._skip_btn)
        actions.addStretch(1)
        actions.addWidget(self._update_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._version)
        layout.addWidget(self._notes, stretch=1)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addLayout(actions)

        self.setStyleSheet("background: #050a14;")
        # Progress updates come from a worker thread — schedule UI on the GUI thread.
        self._service.on_change(self._schedule_render)
        self._render(self._service.state)

    def _schedule_render(self, _state: UpdateState) -> None:
        QTimer.singleShot(0, lambda: self._render(self._service.state))

    def _render(self, state: UpdateState) -> None:
        release = state.release
        if not release:
            self.reject()
            return

        self._version.setText(f"Installed: v{VERSION}  →  Latest: v{release.version}")
        self._notes.setPlainText(release.notes or "Performance improvements and bug fixes.")

        if state.downloading:
            self._update_btn.setEnabled(False)
            self._later_btn.setEnabled(False)
            self._skip_btn.setEnabled(False)
            self._progress.show()
            if state.total_bytes:
                pct = max(1, int(state.downloaded_bytes * 100 / state.total_bytes))
                self._progress.setValue(min(pct, 100))
                self._status.setText(
                    f"Downloading update… {state.downloaded_bytes // 1024} / {state.total_bytes // 1024} KB"
                )
            else:
                self._progress.setRange(0, 0)
                self._status.setText("Downloading update…")
        elif state.error:
            self._status.setText(state.error)
            self._update_btn.setEnabled(True)
        else:
            self._status.setText(
                "The update will download in the background and install automatically."
            )
            self._update_btn.setEnabled(True)

    def _start_update(self) -> None:
        self._service.download_and_apply(self._parent_pid)

    def _skip(self) -> None:
        release = self._service.state.release
        if release:
            self._service.skip_version(release.version)
        self.reject()
