# -*- mode: python ; coding: utf-8 -*-
import platform
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "AURA"

_raw_datas = [
    (ROOT / "core" / "prompt.txt", "core"),
    (ROOT / "config", "config"),
    (ROOT / "jarvis_ui", "jarvis_ui"),
    (ROOT / "launcher", "launcher"),
    (ROOT / "resources" / "skills", "resources/skills"),
    (ROOT / "packages" / "aura-openclaw" / "aura_openclaw", "aura_openclaw"),
    (ROOT / "packaging" / "updater_stub.py", "packaging"),
]
datas = [(str(src), dst) for src, dst in _raw_datas if Path(src).exists()]

# LiteLLM reads JSON/tokenizer assets relative to its package path at import time.
# Skip the proxy UI tree — it is huge and unused by the desktop app.
datas += [
    (src, dst)
    for src, dst in collect_data_files("litellm")
    if "/proxy/" not in Path(src).as_posix()
]

hiddenimports = [
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "google.genai",
    "sounddevice",
    "cv2",
    "playwright",
    "duckduckgo_search",
    "aura_openclaw",
    "aura_openclaw.gateway",
    "aura_openclaw.gateway.embedded",
    "aura_openclaw.gateway.client",
    "aura_openclaw.gateway.protocol",
    "aura_openclaw.skills",
    "aura_openclaw.skills.registry",
    "aura_openclaw.skills.builtin",
    "core.integrations.openclaw",
    "core.integrations.openclaw.bootstrap",
    "core.integrations.openclaw.service",
    "core.integrations.openclaw.runtime_manager",
    "core.integrations.openclaw.config_bridge",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "rth_prefer_disk_jarvis_ui.py")],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if platform.system() == "Darwin":
    icon = ROOT / "assets" / "JarvisMark.icns"
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(icon) if icon.exists() else None,
        bundle_identifier="app.hiaura.aura.desktop",
        version="1.0.2",
        info_plist={
            "CFBundleDisplayName": "AURA",
            "CFBundleName": "AURA",
            "CFBundleShortVersionString": "1.0.1",
            "CFBundleVersion": "1.0.1",
            "NSMicrophoneUsageDescription": "AURA needs the microphone for voice mode and wake.",
            "NSCameraUsageDescription": "AURA needs the camera for vision features.",
            "NSAppleEventsUsageDescription": "AURA uses Apple Events to open apps and automate tasks you request.",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
