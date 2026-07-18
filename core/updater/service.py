from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.platform_detect import is_frozen
from core.updater.downloader import download_asset_smart
from core.updater.installer import launch_updater
from core.updater.manifest import (
    ReleaseInfo,
    fetch_manifest,
    force_update_required,
    parse_release,
)


@dataclass
class UpdateState:
    checking: bool = False
    downloading: bool = False
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    error: str = ""
    release: ReleaseInfo | None = None
    package_path: Path | None = None
    force_required: bool = False
    min_supported_version: str = ""


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
                force_required=self._state.force_required,
                min_supported_version=self._state.min_supported_version,
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
        from core.platform_detect import normalize_os

        os_name = normalize_os()
        if os_name == "darwin":
            root = Path.home() / "Library" / "Application Support" / "AURA"
        elif os_name == "windows":
            local = os.environ.get("LOCALAPPDATA")
            root = Path(local) / "AURA" if local else Path.home() / "AppData" / "Local" / "AURA"
        else:
            root = Path.home() / ".config" / "AURA"
        root.mkdir(parents=True, exist_ok=True)
        return root / "update_skip.json"

    def _load_skip(self) -> str:
        try:
            data = json.loads(self._skip_path().read_text(encoding="utf-8"))
            return str(data.get("version", ""))
        except Exception:
            return ""

    def skip_version(self, version: str) -> None:
        # Never allow skipping a forced (unsupported) release.
        if self.state.force_required:
            return
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
                forced, min_label = force_update_required(manifest)
                release = parse_release(manifest, require_newer=not forced)
                if (
                    release
                    and not forced
                    and release.version == self._skipped_version
                ):
                    release = None
                if release is not None and forced:
                    # Ensure force flag is always set on the release object.
                    release = ReleaseInfo(
                        version=release.version,
                        released_at=release.released_at,
                        notes=release.notes,
                        asset=release.asset,
                        platform=release.platform,
                        min_supported_version=release.min_supported_version
                        or min_label,
                        release_index=release.release_index,
                        min_release_index=release.min_release_index,
                        force_required=True,
                    )
                self._set(
                    release=release,
                    force_required=forced,
                    min_supported_version=min_label
                    or (release.min_supported_version if release else ""),
                )
            except Exception as exc:
                self._set(
                    error=str(exc),
                    release=None,
                    force_required=False,
                    min_supported_version="",
                )
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
                    raise RuntimeError(
                        "Auto-update is available in packaged desktop builds only."
                    )

                def progress(done: int, total: int | None) -> None:
                    self._set(downloaded_bytes=done, total_bytes=total)

                package = download_asset_smart(
                    release.asset,
                    version=release.version,
                    on_progress=progress,
                    prefer_differential=True,
                )
                self._set(package_path=package)
                time.sleep(0.3)
                launch_updater(package, parent_pid)
                os._exit(0)
            except Exception as exc:
                self._set(error=str(exc), downloading=False)

        threading.Thread(target=_run, daemon=True).start()
