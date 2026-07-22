"""Shared keyboard & mouse (software KVM) — built into AURA."""

from __future__ import annotations

from jarvis_ui.kvm.manager import (
    KvmEngine,
    KvmManager,
    KvmRole,
    KvmStatus,
    get_kvm_manager,
)
from jarvis_ui.kvm.protocol import DEFAULT_PORT

__all__ = [
    "DEFAULT_PORT",
    "KvmEngine",
    "KvmManager",
    "KvmRole",
    "KvmStatus",
    "get_kvm_manager",
]
