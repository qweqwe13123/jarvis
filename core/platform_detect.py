"""Runtime OS and CPU architecture detection for builds and updates."""

from __future__ import annotations

import platform
import sys


def normalize_os() -> str:
    """Returns: darwin | windows | linux"""
    name = platform.system().lower()
    if name == "darwin":
        return "darwin"
    if name == "windows":
        return "windows"
    return "linux"


def normalize_arch(machine: str | None = None) -> str:
    """Returns: arm64 | x64"""
    raw = (machine or platform.machine()).lower()
    if raw in {"arm64", "aarch64"}:
        return "arm64"
    if raw in {"x86_64", "amd64", "x64"}:
        return "x64"
    return "x64"


def platform_key() -> str:
    """Canonical target key used in release manifests, e.g. darwin-arm64."""
    return f"{normalize_os()}-{normalize_arch()}"


def platform_label() -> str:
    os_name = normalize_os()
    arch = normalize_arch()
    labels = {
        ("darwin", "arm64"): "macOS (Apple Silicon)",
        ("darwin", "x64"): "macOS (Intel)",
        ("windows", "x64"): "Windows 64-bit",
        ("linux", "x64"): "Linux 64-bit",
    }
    return labels.get((os_name, arch), f"{os_name} {arch}")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
