import os
import sys
import subprocess
import shutil
import atexit
import time as _time
from pathlib import Path
from app.core.logger import logger
from app.core.constants import _ADDITIONAL_HOSTS_VERSION_RE

def open_target(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path], start_new_session=True)
        else:
            # Linux fallbacks
            env = os.environ.copy()
            
            # PyInstaller fix: restore original environment variables
            # PyInstaller sets LD_LIBRARY_PATH which can break system tools like xdg-open
            if getattr(sys, 'frozen', False):
                for var in ['LD_LIBRARY_PATH', 'PATH', 'PYTHONPATH']:
                    orig_var = var + '_ORIG'
                    if orig_var in env:
                        env[var] = env[orig_var]
                    elif var == 'LD_LIBRARY_PATH':
                        # If no original LD_LIBRARY_PATH, it's safer to remove it
                        env.pop(var, None)

            success = False
            for cmd_name in ["xdg-open", "gio", "kde-open", "gnome-open"]:
                try:
                    executable = shutil.which(cmd_name)
                    if executable:
                        # Use list for command to avoid shell injection and handle spaces
                        cmd = [cmd_name, str(path)]
                        subprocess.Popen(
                            cmd, 
                            env=env, 
                            start_new_session=True, 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL
                        )
                        success = True
                        break
                except Exception as e:
                    logger.debug("Failed to use %s: %s", cmd_name, e)
                    continue
            
            if not success:
                logger.error("All open commands failed for %s. Try installing xdg-utils.", path)
    except Exception as e:
        logger.error("Open error for %s: %s", path, e)

from functools import lru_cache

@lru_cache(maxsize=1)
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
        # Optimization: only read first few lines instead of splitting entire content
        lines = []
        count = 0
        for line_bytes in content.splitlines():
            lines.append(line_bytes.decode("utf-8", errors="ignore").strip())
            count += 1
            if count >= 2:
                break
        
        if len(lines) >= 2:
            line = lines[1]
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
