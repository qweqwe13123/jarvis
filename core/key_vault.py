from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_PATH = BASE_DIR / "config" / "key_vault.json"


def _machine_secret() -> bytes:
    basis = f"{sys.platform}|{os.uname().nodename if hasattr(os, 'uname') else 'host'}|jarvis"
    return hashlib.sha256(basis.encode("utf-8")).digest()


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _read_vault() -> dict:
    if not VAULT_PATH.exists():
        return {"profiles": {"default": {}}, "active_profile": "default"}
    try:
        return json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"profiles": {"default": {}}, "active_profile": "default"}


def _write_vault(data: dict) -> None:
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _keychain_get(name: str) -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "jarvis", "-s", f"jarvis:{name}", "-w"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _keychain_set(name: str, value: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["security", "add-generic-password", "-a", "jarvis", "-s", f"jarvis:{name}", "-w", value, "-U"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        pass


def save_provider_key(name: str, value: str, profile: str = "default") -> None:
    data = _read_vault()
    data.setdefault("profiles", {}).setdefault(profile, {})
    plain = value.strip()
    crypt = _xor_crypt(plain.encode("utf-8"), _machine_secret())
    data["profiles"][profile][name] = base64.b64encode(crypt).decode("ascii")
    data["active_profile"] = profile
    _write_vault(data)
    _keychain_set(name, plain)


def get_provider_key(name: str, profile: str | None = None) -> str:
    keychain_value = _keychain_get(name)
    if keychain_value:
        return keychain_value
    data = _read_vault()
    profile_name = profile or data.get("active_profile", "default")
    enc = data.get("profiles", {}).get(profile_name, {}).get(name, "")
    if not enc:
        return ""
    try:
        raw = base64.b64decode(enc.encode("ascii"))
        dec = _xor_crypt(raw, _machine_secret()).decode("utf-8")
        return dec.strip()
    except Exception:
        return ""
