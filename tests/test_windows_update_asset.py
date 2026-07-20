"""Windows in-app update must prefer ZIP + blockmap (Cursor-style), not Inno .exe."""

from __future__ import annotations

from pathlib import Path

from core.updater.installer import _windows_setup_args
from core.updater.manifest import _pick_asset_fields


def test_windows_prefers_zip_update_over_exe_primary():
    url, sha, name, size, bm_url, bm_sha = _pick_asset_fields(
        {
            "filename": "AURA-1.0.29-win-x64.exe",
            "url": "https://example.com/AURA-1.0.29-win-x64.exe",
            "sha256": "a" * 64,
            "size": 100,
            "update_filename": "AURA-1.0.29-win-x64.zip",
            "update_url": "https://example.com/AURA-1.0.29-win-x64.zip",
            "update_sha256": "b" * 64,
            "update_size": 90,
            "update_blockmap_url": "https://example.com/AURA-1.0.29-win-x64.zip.blockmap",
            "update_blockmap_sha256": "c" * 64,
        }
    )
    assert name.endswith(".zip")
    assert url.endswith(".zip")
    assert sha == "b" * 64
    assert size == 90
    assert bm_url.endswith(".zip.blockmap")
    assert bm_sha == "c" * 64


def test_windows_falls_back_to_update_exe_when_no_zip():
    url, sha, name, *_ = _pick_asset_fields(
        {
            "update_filename": "AURA-1.0.23-win-x64.exe",
            "update_url": "https://example.com/AURA-1.0.23-win-x64.exe",
            "update_sha256": "d" * 64,
            "update_size": 50,
        }
    )
    assert name.endswith(".exe")
    assert url.endswith(".exe")
    assert sha == "d" * 64


def test_windows_setup_args_no_embedded_quotes():
    args = _windows_setup_args(Path(r"C:\Users\test\AppData\Local\Programs\AURA"))
    assert "/SP-" in args
    assert "/VERYSILENT" in args
    dir_arg = next(a for a in args if a.startswith("/DIR="))
    assert '"' not in dir_arg
    assert "AURA" in dir_arg
