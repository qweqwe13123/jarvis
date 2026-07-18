# -*- mode: python ; coding: utf-8 -*-
import platform
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "AURA"

# Keep bundle version in sync with core.version.VERSION
sys.path.insert(0, str(ROOT))
try:
    from core.version import VERSION as APP_VERSION
except Exception:
    APP_VERSION = "1.0.0"

_raw_datas = [
    (ROOT / "core" / "prompt.txt", "core"),
    (ROOT / "config", "config"),
    (ROOT / "assets", "assets"),
    (ROOT / "jarvis_ui", "jarvis_ui"),
    (ROOT / "launcher", "launcher"),
    (ROOT / "resources" / "skills", "resources/skills"),
    (ROOT / "packages" / "aura-openclaw" / "aura_openclaw", "aura_openclaw"),
    (ROOT / "packaging" / "updater_stub.py", "packaging"),
]
datas = [(str(src), dst) for src, dst in _raw_datas if Path(src).exists()]
# Never ship live secrets inside the notarized bundle (breaks Gatekeeper if
# written later; also leaks keys). Users save keys to Application Support.
datas = [
    (src, dst)
    for src, dst in datas
    if Path(src).name != "api_keys.json"
]
_example = ROOT / "config" / "api_keys.example.json"
if _example.exists():
    datas.append((str(_example), "config"))

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
    "launcher",
    "launcher.wake_listener",
    "launcher.install_launch_agent",
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
    "core.gemini_models",
    "core.model_router",
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
        version=APP_VERSION,
        info_plist={
            "CFBundleDisplayName": "AURA",
            "CFBundleName": "AURA",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSMicrophoneUsageDescription": "AURA needs the microphone for voice mode and wake.",
            "NSCameraUsageDescription": "AURA needs the camera for vision features.",
            "NSAppleEventsUsageDescription": "AURA uses Apple Events to open apps and automate tasks you request.",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            # Prevent macOS "restore windows after crash" dialogs after onboarding.
            "NSQuitAlwaysKeepsWindows": False,
            "NSSupportsAutomaticTermination": False,
        },
    )
