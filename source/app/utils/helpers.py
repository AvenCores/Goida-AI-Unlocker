import os
import sys
import subprocess
import shutil
import atexit
import time as _time
import threading
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
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            env = get_clean_system_env()
            for cmd_name in ("xdg-open", "gio", "kde-open", "gnome-open"):
                try:
                    if shutil.which(cmd_name):
                        subprocess.Popen(
                            [cmd_name, str(path)],
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                        )
                        return
                except Exception as e:
                    logger.debug("Failed to use %s: %s", cmd_name, e)
            logger.error("All open commands failed for %s. Try installing xdg-utils.", path)
    except Exception as e:
        logger.error("Open error for %s: %s", path, e)


_admin_cache_lock = threading.Lock()
_admin_cache: tuple[float, bool] | None = None
_ADMIN_CACHE_TTL = 10.0


def is_windows_admin() -> bool:
    """Проверка прав администратора с коротким TTL-кэшем (10с)."""
    global _admin_cache
    if sys.platform != "win32":
        return False
    now = _time.monotonic()
    with _admin_cache_lock:
        if _admin_cache is not None and (now - _admin_cache[0]) < _ADMIN_CACHE_TTL:
            return _admin_cache[1]
    try:
        import ctypes

        result = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        result = False
    with _admin_cache_lock:
        _admin_cache = (now, result)
    return result


def safe_remove(path: str, retries: int = 3, delay: float = 0.3):
    for _ in range(retries):
        try:
            p = Path(path)
            p.unlink(missing_ok=True)
            return
        except PermissionError:
            _time.sleep(delay)
        except FileNotFoundError:
            return
        except Exception:
            break
    try:
        p = Path(path)

        def _late_remove(p=p):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        atexit.register(_late_remove)
    except Exception:
        pass


def sanitize_backup_action(action: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in action.strip().lower()
    )
    return cleaned or "manual"


_UPDATE_LINE_PREFIXES = ("Последнее обновление:", "Last updated:")


def extract_update_line(content: bytes | str) -> tuple[str, str]:
    """Ищет в первых строках hosts метку даты обновления.

    Возвращает (полная_строка, дата) или ("", ""), если метка не найдена.
    Сканирует первые 10 строк (устойчиво к BOM/пустым строкам/смене шапки).
    """
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig", errors="ignore")
        else:
            # Убираем BOM если есть
            if content.startswith("﻿"):
                content = content.lstrip("﻿")
        lines = content.splitlines()
        for line in lines[:10]:
            stripped = line.strip()
            for prefix in _UPDATE_LINE_PREFIXES:
                if prefix in stripped:
                    return stripped, stripped.split(prefix, 1)[1].strip()
        return "", ""
    except Exception:
        return "", ""
