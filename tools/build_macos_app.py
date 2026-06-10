from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_NAME = "JARVIS.app"
APP = DIST / APP_NAME
APPLICATIONS_APP = Path("/Applications") / APP_NAME
CONTENTS = APP / "Contents"
MACOS = CONTENTS / "MacOS"
RESOURCES = CONTENTS / "Resources"


def write_text(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o755)


def _copy_to_applications() -> None:
    if APPLICATIONS_APP.exists():
        shutil.rmtree(APPLICATIONS_APP)
    shutil.copytree(APP, APPLICATIONS_APP, symlinks=True)
    try:
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(APPLICATIONS_APP)], check=False)
    except Exception:
        pass
    print(f"Installed: {APPLICATIONS_APP}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the JARVIS macOS app bundle.")
    parser.add_argument(
        "--install",
        action="store_true",
        help="Copy the app to /Applications so it launches like a normal macOS app.",
    )
    args = parser.parse_args()

    DIST.mkdir(exist_ok=True)
    if APP.exists():
        shutil.rmtree(APP)

    MACOS.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)

    icon = ROOT / "assets" / "JarvisMark.icns"
    if icon.exists():
        shutil.copy2(icon, RESOURCES / "JarvisMark.icns")

    launcher = f"""#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
cd "{ROOT}"

LOG_DIR="$HOME/Library/Logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/jarvis.log"

if [ -x "{ROOT}/.venv/bin/python" ]; then
  exec "{ROOT}/.venv/bin/python" "{ROOT}/main.py" >> "$LOG_FILE" 2>&1
fi

exec /usr/bin/env python3 "{ROOT}/main.py" >> "$LOG_FILE" 2>&1
"""
    write_text(MACOS / "JARVIS", launcher, executable=True)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>JARVIS</string>
  <key>CFBundleDisplayName</key>
  <string>JARVIS</string>
  <key>CFBundleIdentifier</key>
  <string>local.jarvis.app</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>JARVIS</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleIconFile</key>
  <string>JarvisMark</string>
  <key>LSBackgroundOnly</key>
  <false/>
  <key>LSUIElement</key>
  <false/>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>JARVIS needs microphone access for realtime voice control.</string>
  <key>NSCameraUsageDescription</key>
  <string>JARVIS uses the camera only when you ask it to look through the camera.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>JARVIS uses Apple Events to open apps, websites, Telegram, and automation actions you request.</string>
  <key>NSHumanReadableCopyright</key>
  <string>Personal local AI assistant.</string>
</dict>
</plist>
"""
    write_text(CONTENTS / "Info.plist", plist)

    readme = f"""JARVIS

Double-click "JARVIS.app" to launch the assistant.

This app bundle is a macOS launcher for:
{ROOT}

Keep the project folder in place so the app can use the local virtual environment,
memory, tools, config, wake listener, and generated projects.

If macOS blocks the app:
1. Right-click the app.
2. Press Open.
3. Confirm Open one time.

Permissions you may need to allow:
- Microphone for voice.
- Camera for camera vision.
- Accessibility / Automation for Telegram calls, browser control, and computer control.

Install as a normal app:
python tools/build_macos_app.py --install

Logs:
~/Library/Logs/jarvis.log
"""
    write_text(DIST / "INSTALL_README.txt", readme)
    print(f"Built: {APP}")
    if args.install:
        _copy_to_applications()


if __name__ == "__main__":
    main()
