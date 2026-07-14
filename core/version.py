"""Application version and update channel configuration."""

from __future__ import annotations

# Bump this for every public release. Keep in sync with packaging/build.py.
VERSION = "1.0.2"

APP_NAME = "A.U.R.A"
APP_ID = "app.hiaura.aura.desktop"
UPDATE_CHANNEL = "stable"

# Override at build time or via AURA_UPDATE_MANIFEST_URL env var.
DEFAULT_UPDATE_MANIFEST_URL = "https://www.hiauraai.com/api/releases/latest"

# Check intervals (seconds)
UPDATE_CHECK_ON_STARTUP_DELAY = 8
UPDATE_CHECK_INTERVAL = 4 * 60 * 60  # 4 hours
