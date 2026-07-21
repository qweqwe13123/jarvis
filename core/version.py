"""Application version and update channel configuration."""

from __future__ import annotations

# Bump this for every public release. Keep in sync with packaging/build.py.
VERSION = "1.0.45"

# Monotonic release counter — bump +1 with every public VERSION bump.
# Used with MAX_RELEASES_BEHIND to force-update clients that fall too far behind.
RELEASE_INDEX = 45

# Allow current + this many prior releases (3 total). Older → update required.
MAX_RELEASES_BEHIND = 2

APP_NAME = "A.U.R.A"
APP_ID = "app.hiaura.aura.desktop"
UPDATE_CHANNEL = "stable"

# Override at build time or via AURA_UPDATE_MANIFEST_URL env var.
DEFAULT_UPDATE_MANIFEST_URL = "https://www.hiauraai.com/api/releases/latest"

# Check intervals (seconds)
UPDATE_CHECK_ON_STARTUP_DELAY = 8
UPDATE_CHECK_INTERVAL = 4 * 60 * 60  # 4 hours
