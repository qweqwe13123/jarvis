"""Probe local machine for Local AI model recommendation."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class HardwareProfile:
    os_name: str  # macOS / Windows / Linux
    arch: str
    ram_gb: float
    disk_free_gb: float
    apple_silicon: bool
    has_nvidia: bool
    cpu_cores: int
    summary: str  # human one-liner

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ram_gb() -> float:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return 8.0


def _disk_free_gb() -> float:
    try:
        root = "C:\\" if sys.platform == "win32" else "/"
        return round(shutil.disk_usage(root).free / (1024**3), 1)
    except Exception:
        return 20.0


def _cpu_cores() -> int:
    try:
        import psutil

        return int(psutil.cpu_count(logical=True) or 4)
    except Exception:
        return 4


def _apple_silicon() -> bool:
    if sys.platform != "darwin":
        return False
    machine = (platform.machine() or "").lower()
    if machine in ("arm64", "aarch64"):
        return True
    try:
        import subprocess

        out = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            text=True,
            timeout=2,
        )
        return "apple" in out.lower()
    except Exception:
        return False


def _has_nvidia() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        import subprocess

        subprocess.check_output(
            ["nvidia-smi", "-L"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return True
    except Exception:
        return False


def _os_label() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform == "win32":
        return "Windows"
    return "Linux"


def probe_hardware() -> HardwareProfile:
    ram = _ram_gb()
    disk = _disk_free_gb()
    apple = _apple_silicon()
    nvidia = _has_nvidia()
    cores = _cpu_cores()
    arch = (platform.machine() or "unknown").lower()
    os_name = _os_label()

    bits = [os_name]
    if apple:
        bits.append("Apple Silicon")
    elif arch:
        bits.append(arch)
    bits.append(f"{ram:g} GB memory")
    if nvidia:
        bits.append("NVIDIA GPU")
    bits.append(f"{disk:g} GB free")

    return HardwareProfile(
        os_name=os_name,
        arch=arch,
        ram_gb=ram,
        disk_free_gb=disk,
        apple_silicon=apple,
        has_nvidia=nvidia,
        cpu_cores=cores,
        summary=" · ".join(bits),
    )
