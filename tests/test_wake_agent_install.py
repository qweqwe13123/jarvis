"""Tests for cross-platform double-clap wake install + launch helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from launcher import install_wake_agent as iwa


def test_program_command_includes_wake_flags_and_gaps():
    cmd = iwa._program_command()
    joined = " ".join(cmd)
    assert "--threshold" in cmd or "--threshold" in joined
    assert "0.08" in cmd
    assert "2.40" in cmd
    assert "0.12" in cmd


def test_windows_install_creates_schtasks(monkeypatch, tmp_path):
    monkeypatch.setattr(iwa.sys, "platform", "win32")
    monkeypatch.setattr(iwa, "_support_wake", lambda: tmp_path / "wake")
    monkeypatch.setattr(
        iwa,
        "_program_command",
        lambda: [r"C:\Users\t\AppData\Local\Programs\AURA\AURA.exe", "--wake-listener", "0.08"],
    )
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    monkeypatch.setattr(iwa, "_run", fake_run)
    iwa._install_windows()
    create = next(c for c in calls if c[:2] == ["schtasks", "/Create"])
    assert "/TN" in create and iwa.WIN_TASK in create
    assert "/SC" in create and "ONLOGON" in create
    assert "/RL" in create and "LIMITED" in create
    tr = create[create.index("/TR") + 1]
    assert "AURA.exe" in tr
    assert "--wake-listener" in tr
    assert (tmp_path / "wake" / "installed").is_file()


def test_windows_uninstall_deletes_task(monkeypatch, tmp_path):
    monkeypatch.setattr(iwa.sys, "platform", "win32")
    monkeypatch.setattr(iwa, "_support_wake", lambda: tmp_path / "wake")
    (tmp_path / "wake").mkdir(parents=True)
    (tmp_path / "wake" / "installed").write_text("x", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        return m

    monkeypatch.setattr(iwa, "_run", fake_run)
    iwa._uninstall_windows()
    assert any(c[:3] == ["schtasks", "/Delete", "/TN"] for c in calls)
    assert not (tmp_path / "wake" / "installed").exists()


def test_linux_systemd_unit_contents(monkeypatch, tmp_path):
    monkeypatch.setattr(iwa.sys, "platform", "linux")
    monkeypatch.setattr(iwa, "_support_wake", lambda: tmp_path / "wake")
    monkeypatch.setattr(iwa, "_systemd_user_dir", lambda: tmp_path / "systemd")
    monkeypatch.setattr(iwa, "_systemd_available", lambda: True)
    cmd = ["/opt/AURA.AppImage", "--wake-listener", "--threshold", "0.08"]
    monkeypatch.setattr(iwa, "_program_command", lambda: cmd)

    def fake_run(c, check=False, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    monkeypatch.setattr(iwa, "_run", fake_run)
    iwa._install_linux()
    unit = (tmp_path / "systemd" / iwa.LINUX_UNIT).read_text(encoding="utf-8")
    assert "ExecStart=" in unit
    assert "--wake-listener" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit
    assert (tmp_path / "wake" / "installed").is_file()


def test_linux_autostart_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(iwa.sys, "platform", "linux")
    monkeypatch.setattr(iwa, "_support_wake", lambda: tmp_path / "wake")
    monkeypatch.setattr(iwa, "_systemd_available", lambda: False)
    monkeypatch.setattr(iwa, "_autostart_path", lambda: tmp_path / "autostart" / "aura-wake.desktop")
    monkeypatch.setattr(
        iwa,
        "_program_command",
        lambda: ["/home/u/AURA.AppImage", "--wake-listener", "--threshold", "0.08"],
    )
    monkeypatch.setattr(iwa.subprocess, "Popen", MagicMock())
    iwa._install_linux()
    desk = (tmp_path / "autostart" / "aura-wake.desktop").read_text(encoding="utf-8")
    assert desk.startswith("[Desktop Entry]")
    assert "Exec=" in desk
    assert "--wake-listener" in desk


def test_launch_aura_win_does_not_use_open(monkeypatch):
    from launcher import wake_listener as wl

    monkeypatch.setattr(wl.sys, "platform", "win32")
    monkeypatch.setattr(wl, "_app_running", lambda: False)
    monkeypatch.setattr(wl, "_frozen_exe", lambda: None)
    exe = Path(r"C:\Users\t\AppData\Local\Programs\AURA\AURA.exe")
    monkeypatch.setattr(wl, "_windows_install_exe", lambda: exe)
    pops: list = []

    def fake_popen(args, **kwargs):
        pops.append(list(args))
        return MagicMock()

    monkeypatch.setattr(wl.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(wl, "_log", lambda m: None)
    wl._launch_aura()
    assert pops
    assert pops[0][0] == str(exe)
    assert not any(a[0] == "open" for a in pops)
    assert not any("osascript" in str(a) for a in pops)


def test_launch_aura_linux_prefers_appimage(monkeypatch, tmp_path):
    from launcher import wake_listener as wl

    app = tmp_path / "AURA-1.0.0-linux-x64.AppImage"
    app.write_text("x", encoding="utf-8")
    app.chmod(0o755)
    monkeypatch.setattr(wl.sys, "platform", "linux")
    monkeypatch.setattr(wl, "_app_running", lambda: False)
    monkeypatch.setattr(wl, "_frozen_exe", lambda: None)
    monkeypatch.setattr(wl, "_linux_install_candidates", lambda: [app])
    pops: list = []
    monkeypatch.setattr(
        wl.subprocess, "Popen", lambda args, **kw: pops.append(list(args)) or MagicMock()
    )
    monkeypatch.setattr(wl, "_log", lambda m: None)
    monkeypatch.setattr(wl.os, "access", lambda p, m: True)
    wl._launch_aura()
    assert pops and pops[0][0] == str(app)


def test_launch_when_running_brings_to_front(monkeypatch):
    from launcher import wake_listener as wl

    monkeypatch.setattr(wl, "_app_running", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr(wl, "_bring_to_front", lambda: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(wl, "_log", lambda m: None)
    wl._launch_aura()
    assert called["n"] == 1
