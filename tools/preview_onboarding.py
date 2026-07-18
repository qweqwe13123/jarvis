#!/usr/bin/env python3
"""Preview AURA onboarding (welcome + Google + logo) without full app boot."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from jarvis_ui.onboarding.persistence import reset_onboarding_for_preview
from jarvis_ui.onboarding.window import OnboardingWindow
from jarvis_ui.paths import brand_asset_path


def main() -> int:
    logo = brand_asset_path(
        "aura_logo_onboarding.png", "aura_logo.png", "aura_logo_square_bg.png"
    )
    google = brand_asset_path(
        "google_g_72.png", "google_g.png", "google_g_54.png", "google_g.svg"
    )
    print("logo asset:", logo)
    print("google asset:", google)
    if logo is None or google is None:
        print("WARNING: brand assets missing — onboarding will show letter fallbacks")

    reset_onboarding_for_preview()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = OnboardingWindow(preview=True)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    win.show()
    win.raise_()
    win.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
