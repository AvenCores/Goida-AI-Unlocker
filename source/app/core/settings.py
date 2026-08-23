import json
import os
from app.core.constants import SETTINGS_PATH

_cache: dict | None = None


def load_settings() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _cache = data
            except Exception:
                pass
    return dict(_cache)


def save_settings(settings: dict):
    global _cache
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        _cache = dict(settings)
    except Exception as e:
        print(f"Error saving settings: {e}")


def get_setting(key: str, default=None):
    return load_settings().get(key, default)


def set_setting(key: str, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
