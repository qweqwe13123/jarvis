# -*- mode: python ; coding: utf-8 -*-
import platform
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "AURA"

datas = [
    (str(ROOT / "core" / "prompt.txt"), "core"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "jarvis_ui"), "jarvis_ui"),
    (str(ROOT / "packaging" / "updater_stub.py"), "packaging"),
]

hiddenimports = [
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "google.genai",
    "sounddevice",
    "cv2",
    "playwright",
    "duckduckgo_search",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
        version="1.0.0",
        info_plist={
            "CFBundleDisplayName": "A.U.R.A",
            "NSMicrophoneUsageDescription": "A.U.R.A needs the microphone for voice mode.",
            "NSCameraUsageDescription": "A.U.R.A needs the camera for vision features.",
            "NSHighResolutionCapable": True,
        },
    )
