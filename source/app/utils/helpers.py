import os
import sys
import subprocess
import shutil
import atexit
import time as _time
from functools import lru_cache
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
    if getattr(sys, "frozen", False):
        for var in ("LD_LIBRARY_PATH", "PATH", "PYTHONPATH"):
            orig_var = var + "_ORIG"
            if orig_var in env:
                env[var] = env[orig_var]
            elif var == "LD_LIBRARY_PATH":
                env.pop(var, None)
    return env


def open_target(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path], start_new_session=True)
        else:
            env = get_clean_system_env()
            for cmd_name in ("xdg-open", "gio", "kde-open", "gnome-open"):
                try:
                    if shutil.which(cmd_name):
                        subprocess.Popen(
                            [cmd_name, str(path)],
                            env=env,
                            start_new_session=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        return
                except Exception as e:
                    logger.debug("Failed to use %s: %s", cmd_name, e)
            logger.error("All open commands failed for %s. Try installing xdg-utils.", path)
    except Exception as e:
        logger.error("Open error for %s: %s", path, e)


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
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in action.strip().lower()
    )
    return cleaned or "manual"


_UPDATE_LINE_PREFIXES = ("Последнее обновление:", "Last updated:")


def extract_update_line(content: bytes | str) -> tuple[str, str]:
    """Ищет во второй строке hosts метку даты обновления.

    Возвращает (полная_строка, дата) или ("", ""), если метка не найдена.
    """
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        lines = content.splitlines()
        if len(lines) < 2:
            return "", ""
        line = lines[1].strip()
        for prefix in _UPDATE_LINE_PREFIXES:
            if prefix in line:
                return line, line.split(prefix, 1)[1].strip()
        return "", ""
    except Exception:
        return "", ""
