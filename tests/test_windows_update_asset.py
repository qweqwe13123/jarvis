"""Windows in-app update must prefer ZIP + blockmap (Cursor-style), not Inno .exe."""

from __future__ import annotations

from pathlib import Path

from core.updater.installer import _windows_setup_args, _windows_zip_apply_ps_body
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


def test_windows_zip_apply_ps_is_fast_swap_not_post_quit_extract():
    """After quit we only swap a pre-extracted payload (Cursor-style)."""
    body = _windows_zip_apply_ps_body(
        log=Path(r"C:\Users\test\AppData\Local\AURA\logs\updater.log"),
        parent_pid=1234,
        pkg=Path(r"C:\Users\test\AppData\Local\AURA\updates\pending\AURA-1.0.39-win-x64.zip"),
        target=Path(r"C:\Users\test\AppData\Local\Programs\AURA"),
        payload=Path(r"C:\Users\test\AppData\Local\AURA\updates\pending\prepared-1\payload"),
        work=Path(r"C:\Users\test\AppData\Local\AURA\updates\pending\prepared-1"),
        script=Path(r"C:\Users\test\AppData\Local\AURA\updates\pending\apply-zip-1.ps1"),
        expected="1.0.39",
    )
    assert body.count("(") == body.count(")")
    assert body.count("{") == body.count("}")
    assert "Wait-AuraUnlocked" in body
    assert "Move-Item" in body
    assert "Start-Process" in body
    assert "Start-Job -ScriptBlock" not in body
    assert "never Start-Job" in body or "scheduling bak cleanup" in body
    assert "swap verified OK" in body or "will launch next" in body
    assert "version.txt" in body
    assert "Expand-Archive" not in body
    assert "need 1-7" in body
    assert "JARVIS.exe')) {{" not in body


def test_windows_spawn_does_not_use_start_empty_title():
    import inspect
    from core.updater.installer import _spawn_hidden_powershell

    src = inspect.getsource(_spawn_hidden_powershell)
    assert "start \\\"\\\" /b" not in src
    assert '["cmd.exe", "/c", inner]' not in src
    assert '"powershell.exe"' in src or "'powershell.exe'" in src
    assert "-File" in src
    assert "0x00000008" not in src
