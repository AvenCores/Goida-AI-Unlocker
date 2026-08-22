import os
import sys
import subprocess
import shutil
import atexit
import time as _time
from pathlib import Path
from app.core.logger import logger

def get_clean_system_env() -> dict:
    """Возвращает копию окружения без «мусора» PyInstaller.

    PyInstaller (onefile) задаёт LD_LIBRARY_PATH на свою временную папку,
    из-за чего системные инструменты (resolvectl, xdg-open и т.п.)
    подхватывают бандловые библиотеки вроде libcrypto.so.3 и падают с
    ошибкой вида "version `OPENSSL_3.4.0' not found". Функция восстанавливает
    оригинальные значения переменных (сохранённые PyInstaller как *_ORIG).
    """
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        for var in ['LD_LIBRARY_PATH', 'PATH', 'PYTHONPATH']:
            orig_var = var + '_ORIG'
            if orig_var in env:
                env[var] = env[orig_var]
            elif var == 'LD_LIBRARY_PATH':
                # Если нет оригинального LD_LIBRARY_PATH — безопаснее убрать
                env.pop(var, None)
    return env

def open_target(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path], start_new_session=True)
        else:
            # Linux fallbacks
            env = get_clean_system_env()

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

def extract_update_line(content: bytes | str) -> tuple[str, str]:
    try:
        if isinstance(content, bytes):
            lines = []
            pos = 0
            for _ in range(2):
                idx = content.find(b"\n", pos)
                if idx == -1:
                    lines.append(content[pos:].decode("utf-8", errors="ignore").strip())
                    break
                lines.append(content[pos:idx].decode("utf-8", errors="ignore").strip())
                pos = idx + 1
        else:
            lines = []
            pos = 0
            for _ in range(2):
                idx = content.find("\n", pos)
                if idx == -1:
                    lines.append(content[pos:].strip())
                    break
                lines.append(content[pos:idx].strip())
                pos = idx + 1
        
        if len(lines) >= 2:
            line = lines[1]
            for prefix in ("Последнее обновление:", "Last updated:"):
                if prefix in line:
                    date_part = line.split(prefix, 1)[1].strip()
                    return line, date_part
        return "", ""
    except Exception:
        return "", ""
