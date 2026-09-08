import json
import os
import stat
import tempfile
import threading
from app.core.constants import SETTINGS_PATH
from app.core.logger import logger

_cache: dict | None = None
_lock = threading.Lock()


def load_settings() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
        data: dict = {}
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
                else:
                    logger.warning("Settings file is not a dict, using defaults")
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
        _cache = data
        return dict(_cache)


def save_settings(settings: dict):
    global _cache
    if not isinstance(settings, dict):
        raise TypeError("settings must be a dict")
    with _lock:
        snapshot = dict(settings)
        parent = os.path.dirname(SETTINGS_PATH)
        try:
            if parent:
                os.makedirs(parent, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=parent or None, prefix=".settings_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, ensure_ascii=False, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.chmod(tmp, 0o600)
                except Exception:
                    pass
                os.replace(tmp, SETTINGS_PATH)
            finally:
                try:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                except Exception:
                    pass
            _cache = snapshot
        except Exception as e:
            logger.error("Error saving settings: %s", e)
            raise


def get_setting(key: str, default=None):
    return load_settings().get(key, default)


def set_setting(key: str, value):
    settings = load_settings()
    settings[key] = value
    try:
        save_settings(settings)
    except Exception:
        pass
