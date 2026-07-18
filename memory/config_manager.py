import json
from pathlib import Path

from core.app_paths import api_keys_path, data_dir


def get_base_dir() -> Path:
    return data_dir()


BASE_DIR = get_base_dir()
CONFIG_DIR = api_keys_path().parent
CONFIG_FILE = api_keys_path()


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()
    path = api_keys_path()

    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["gemini_api_key"] = gemini_api_key.strip()

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_api_keys() -> dict:
    path = api_keys_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}


def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")


def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)
