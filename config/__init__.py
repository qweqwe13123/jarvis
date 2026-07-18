# config/__init__.py
import json
import platform
from pathlib import Path

from core.app_paths import api_keys_path


def get_config() -> dict:
    path = api_keys_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    name = platform.system().lower()
    if name == "darwin":
        return "mac"
    if name == "windows":
        return "windows"
    return "linux"


def is_windows() -> bool:
    return get_os() == "windows"


def is_mac() -> bool:
    return get_os() == "mac"


def is_linux() -> bool:
    return get_os() == "linux"
