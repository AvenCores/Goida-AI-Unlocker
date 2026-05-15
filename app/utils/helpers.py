import os
import sys
import subprocess
import atexit
import time as _time
from pathlib import Path
from typing import Optional
from app.core.logger import logger
from app.core.constants import _ADDITIONAL_HOSTS_VERSION_RE, resource_path

def open_target(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        logger.error("Open error for %s: %s", path, e)

def is_windows_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def safe_remove(path: str, retries: int = 3, delay: float = 0.3):
    for _ in range(retries):
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
            return
        except PermissionError:
            _time.sleep(delay)
        except Exception:
            break
    try:
        p = Path(path)
        if p.exists():
            atexit.register(lambda p=p: p.exists() and p.unlink())
    except Exception:
        pass

def sanitize_backup_action(action: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in action.strip().lower())
    return cleaned or "manual"

def extract_update_line(content: bytes) -> tuple[str, str]:
    try:
        lines = content.decode("utf-8", errors="ignore").splitlines()
        if len(lines) > 1:
            line = lines[1].strip()
            for prefix in ("Последнее обновление:", "Last updated:"):
                if prefix in line:
                    date_part = line.split(prefix, 1)[1].strip()
                    return line, date_part
        return "", ""
    except Exception:
        return "", ""

def extract_additional_version(text: str) -> str:
    match = _ADDITIONAL_HOSTS_VERSION_RE.search(text)
    return match.group(1) if match else ""
