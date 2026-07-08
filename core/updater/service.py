from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.platform_detect import is_frozen
from core.updater.downloader import download_asset
from core.updater.installer import install_dir, launch_updater
from core.updater.manifest import ReleaseInfo, fetch_manifest, parse_release


@dataclass
class UpdateState:
    checking: bool = False
    downloading: bool = False
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    error: str = ""
    release: ReleaseInfo | None = None
    package_path: Path | None = None


class UpdateService:
    def __init__(self) -> None:
        self._state = UpdateState()
        self._lock = threading.Lock()
        self._skipped_version: str = self._load_skip()
        self._listeners: list[Callable[[UpdateState], None]] = []

    @property
    def state(self) -> UpdateState:
        with self._lock:
            return UpdateState(
                checking=self._state.checking,
                downloading=self._state.downloading,
                downloaded_bytes=self._state.downloaded_bytes,
                total_bytes=self._state.total_bytes,
                error=self._state.error,
                release=self._state.release,
                package_path=self._state.package_path,
            )

    def on_change(self, callback: Callable[[UpdateState], None]) -> None:
        self._listeners.append(callback)

    def _emit(self) -> None:
        snapshot = self.state
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._state, key, value)
        self._emit()

    def _skip_path(self) -> Path:
        base = install_dir()
        if base.suffix == ".app":
            root = base.parent
        else:
            root = Path.home() / ".jarvis"
        root.mkdir(parents=True, exist_ok=True)
        return root / "update_skip.json"

    def _load_skip(self) -> str:
        try:
            data = json.loads(self._skip_path().read_text(encoding="utf-8"))
            return str(data.get("version", ""))
        except Exception:
            return ""

    def skip_version(self, version: str) -> None:
        self._skipped_version = version
        self._skip_path().write_text(json.dumps({"version": version}), encoding="utf-8")
        self._set(release=None)

    def check_for_updates(self, background: bool = True) -> None:
        if self._state.checking:
            return

        def _run() -> None:
            self._set(checking=True, error="")
            try:
                manifest = fetch_manifest()
                release = parse_release(manifest)
                if release and release.version == self._skipped_version:
                    release = None
                self._set(release=release)
            except Exception as exc:
                self._set(error=str(exc), release=None)
            finally:
                self._set(checking=False)

        if background:
            threading.Thread(target=_run, daemon=True).start()
        else:
            _run()

    def download_and_apply(self, parent_pid: int) -> None:
        release = self.state.release
        if not release or self._state.downloading:
            return

        def _run() -> None:
            self._set(downloading=True, downloaded_bytes=0, total_bytes=None, error="")
            try:
                if not is_frozen():
                    raise RuntimeError("Auto-update is available in packaged desktop builds only.")

                def progress(done: int, total: int | None) -> None:
                    self._set(downloaded_bytes=done, total_bytes=total)

                package = download_asset(release.asset, on_progress=progress)
                self._set(package_path=package)
                time.sleep(0.3)
                launch_updater(package, parent_pid)
                os._exit(0)
            except Exception as exc:
                self._set(error=str(exc), downloading=False)

        threading.Thread(target=_run, daemon=True).start()
