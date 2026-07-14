"""Premium AURA onboarding — welcome + permissions (wired into main)."""

from __future__ import annotations

from jarvis_ui.onboarding.launcher import run_onboarding_if_needed
from jarvis_ui.onboarding.persistence import is_onboarding_done, mark_onboarding_done
from jarvis_ui.onboarding.window import OnboardingWindow

__all__ = [
    "OnboardingWindow",
    "is_onboarding_done",
    "mark_onboarding_done",
    "run_onboarding_if_needed",
]
