import sys
import tempfile
import urllib.request
import subprocess
import os
import threading
import atexit
import time as _time
import re as _re
import shutil
import json
import textwrap as _tw
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache
from typing import Optional, Callable
import logging

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QHBoxLayout, QGraphicsOpacityEffect, QStackedWidget, QSizePolicy,
    QToolButton, QAbstractButton, QGridLayout, QMenu, QMessageBox
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QSize, QLocale, QRunnable,
    QThreadPool, Signal, QObject, Slot
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("goida_unlocker")

# ----------------------------------------------------------------------
# Constants & Paths
# ----------------------------------------------------------------------
HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts") if sys.platform == "win32" else Path("/etc/hosts")
HOSTS_BACKUP_DIR = Path.home() / ".goida-ai-unlocker" / "hosts-backups"
HOSTS_BACKUP_PREFIX = "hosts_backup_"

ADDITIONAL_HOSTS_URL = "https://raw.githubusercontent.com/AvenCores/Goida-AI-Unlocker/refs/heads/main/additional_hosts.py"
APP_VERSION = "0.0.0"
SUPPORTED_LANGUAGES = ("ru", "en")
CURRENT_LANGUAGE = "ru"
_LAYOUT_FILLER = "\u3164"

# ----------------------------------------------------------------------
# Regex
# ----------------------------------------------------------------------
_ADDITIONAL_HOSTS_VERSION_RE = _re.compile(r"# additional_hosts_version\s+(\S+)")
_HOSTS_VERSION_BLOCK_RE = _re.compile(r'version_add\s*=\s*["\']([^"\']+)["\']')
_HOSTS_CONTENT_RE = _re.compile(r'hosts_add\s*=\s*"""(.*?)"""', _re.S)

_MONTH_NAME_ALIASES = {
    "январь": 0, "января": 0, "january": 0,
    "февраль": 1, "февраля": 1, "february": 1,
    "март": 2, "марта": 2, "march": 2,
    "апрель": 3, "апреля": 3, "april": 3,
    "май": 4, "мая": 4, "may": 4,
    "июнь": 5, "июня": 5, "june": 5,
    "июль": 6, "июля": 6, "july": 6,
    "август": 7, "августа": 7, "august": 7,
    "сентябрь": 8, "сентября": 8, "september": 8,
    "октябрь": 9, "октября": 9, "october": 9,
    "ноябрь": 10, "ноября": 10, "november": 10,
    "декабрь": 11, "декабря": 11, "december": 11,
}

_MONTH_NAME_OUTPUTS = {
    "ru": [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ],
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
}

_MONTH_NAME_RE = _re.compile(
    r"\b("
    + "|".join(sorted(
        (_re.escape(name) for name in _MONTH_NAME_ALIASES),
        key=len, reverse=True
    ))
    + r")\b",
    _re.IGNORECASE,
)

# ----------------------------------------------------------------------
# HTTP Client (thread-safe cached)
# ----------------------------------------------------------------------
class HttpClient:
    _lock = threading.Lock()
    _cache: dict[str, tuple[float, str]] = {}
    CACHE_TTL = 300.0
    REMOTE_CACHE_TTL = 60.0
    _remote_main_line_cache: Optional[tuple[float, tuple[str, str]]] = None
    _remote_add_ver_cache: Optional[tuple[float, str]] = None

    @classmethod
    def fetch(cls, url: str, timeout: int = 10, bypass_cache: bool = False) -> str:
        now = _time.time()
        key = url
        with cls._lock:
            if not bypass_cache and key in cls._cache:
                ts, content = cls._cache[key]
                if now - ts < cls.CACHE_TTL:
                    return content
        try:
            req = urllib.request.Request(
                f"{url}?t={int(now)}" if bypass_cache else url,
                headers={"User-Agent": "GoidaUnlocker/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
            with cls._lock:
                cls._cache[key] = (now, data)
            return data
        except Exception as e:
            logger.error("HTTP fetch failed for %s: %s", url, e)
            return ""

    @classmethod
    def fetch_additional_hosts(cls) -> tuple[str, str]:
        raw = cls.fetch(ADDITIONAL_HOSTS_URL, bypass_cache=True)
        if not raw:
            return "", ""
        ver_match = _HOSTS_VERSION_BLOCK_RE.search(raw)
        hosts_match = _HOSTS_CONTENT_RE.search(raw)
        version = ver_match.group(1) if ver_match else ""
        hosts_block = hosts_match.group(1).strip() if hosts_match else ""
        hosts_block = _tw.dedent(hosts_block)
        if not hosts_block:
            version = ""
        return version, hosts_block

    @classmethod
    def get_remote_main_line_cached(cls) -> tuple[str, str]:
        now = _time.time()
        with cls._lock:
            if cls._remote_main_line_cache and now - cls._remote_main_line_cache[0] < cls.REMOTE_CACHE_TTL:
                return cls._remote_main_line_cache[1]
        try:
            url = f"https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts?t={int(now)}"
            data = urllib.request.urlopen(url, timeout=10).read()
            remote_line, remote_date = _extract_update_line(data)
        except Exception:
            remote_line, remote_date = "", ""
        with cls._lock:
            cls._remote_main_line_cache = (now, (remote_line, remote_date))
        return remote_line, remote_date

    @classmethod
    def get_remote_add_version_cached(cls) -> str:
        now = _time.time()
        with cls._lock:
            if cls._remote_add_ver_cache and now - cls._remote_add_ver_cache[0] < cls.REMOTE_CACHE_TTL:
                return cls._remote_add_ver_cache[1]
        try:
            ver = cls.fetch_additional_hosts()[0]
        except Exception:
            ver = ""
        with cls._lock:
            cls._remote_add_ver_cache = (now, ver)
        return ver


# ----------------------------------------------------------------------
# Hosts Manager (cached read, atomic write, validation)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class HostsStatusResult:
    key: str
    color: str
    date: str


class HostsManager:
    def __init__(self):
        self._cache: Optional[tuple[float, str]] = None
        self._lock = threading.Lock()

    def read(self) -> str:
        if not HOSTS_PATH.exists():
            return ""
        mtime = HOSTS_PATH.stat().st_mtime
        with self._lock:
            if self._cache and self._cache[0] == mtime:
                return self._cache[1]
        try:
            content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            with self._lock:
                self._cache = (mtime, content)
            return content
        except Exception as e:
            logger.error("Failed to read hosts: %s", e)
            return ""

    def invalidate_cache(self):
        with self._lock:
            self._cache = None

    def is_installed(self) -> bool:
        return "dns.malw.link" in self.read()

    def get_local_add_version(self) -> str:
        return _extract_additional_version(self.read())

    @staticmethod
    def validate_content(content: str) -> bool:
        lines = content.strip().splitlines()
        valid = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and _re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", parts[0]):
                valid += 1
        return valid > 0 or "localhost" in content

    def backup(self, action: str) -> Optional[Path]:
        try:
            data = HOSTS_PATH.read_bytes()
        except Exception as e:
            logger.error("Backup read error: %s", e)
            return None
        try:
            HOSTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            tag = _sanitize_backup_action(action)
            ts = _time.strftime("%Y%m%d_%H%M%S")
            ns = _time.time_ns() % 1_000_000
            name = f"{HOSTS_BACKUP_PREFIX}{tag}_{ts}_{ns:06d}.txt"
            path = HOSTS_BACKUP_DIR / name
            created = _time.strftime("%Y-%m-%d %H:%M:%S")
            header = (
                f"# Goida AI Unlocker hosts backup\n"
                f"# action {tag}\n"
                f"# created_at {created}\n"
                f"# source {HOSTS_PATH}\n\n"
            ).encode("utf-8")
            path.write_bytes(header + data)
            return path
        except Exception as e:
            logger.error("Backup write error: %s", e)
            return None

    def get_latest_backup(self) -> Optional[Path]:
        if not HOSTS_BACKUP_DIR.is_dir():
            return None
        files = [
            f for f in HOSTS_BACKUP_DIR.iterdir()
            if f.is_file()
            and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
            and f.name.lower().endswith(".txt")
        ]
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    @staticmethod
    def _normalize_hosts_content(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()

    def _verify_applied_content(self, expected_content: str) -> bool:
        try:
            actual_content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error("Failed to read hosts for verification: %s", e)
            return False
        return self._normalize_hosts_content(actual_content) == self._normalize_hosts_content(expected_content)

    def apply(self, content: str) -> bool:
        temp_path: Optional[str] = None
        ps_script_path: Optional[str] = None

        try:
            if not self.validate_content(content):
                logger.error("Hosts content validation failed")
                return False

            fd, temp_path = tempfile.mkstemp()
            os.close(fd)
            Path(temp_path).write_text(content, encoding="utf-8")

            if sys.platform == "win32":
                safe_src = temp_path.replace("'", "''")
                safe_dst = str(HOSTS_PATH).replace("'", "''")
                safe_script = ""
                ps = (
                    "$ErrorActionPreference = 'Stop'\n"
                    f"$source = '{safe_src}'\n"
                    f"$dest = '{safe_dst}'\n"
                    "try {\n"
                    "    Copy-Item -LiteralPath $source -Destination $dest -Force\n"
                    "    try { Clear-DnsClientCache | Out-Null } catch {}\n"
                    "    try { ipconfig /flushdns | Out-Null } catch {}\n"
                    "    exit 0\n"
                    "} catch {\n"
                    "    exit 1\n"
                    "}\n"
                )
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ps1", encoding="utf-8") as f:
                    f.write(ps)
                    ps_script_path = f.name
                safe_script = ps_script_path.replace("'", "''")

                elevated = False
                try:
                    if _is_windows_admin():
                        r = subprocess.run(
                            [
                                "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                                "-ExecutionPolicy", "Bypass", "-File", ps_script_path
                            ],
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=60
                        )
                    else:
                        cmd = [
                            "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                            "-ExecutionPolicy", "Bypass", "-Command",
                            "$ErrorActionPreference = 'Stop'; "
                            "try { "
                            f"$p = Start-Process powershell -Verb runAs -WindowStyle Hidden "
                            f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{safe_script}\"' "
                            "-Wait -PassThru -ErrorAction Stop; "
                            "if ($null -eq $p) { exit 1 }; "
                            "exit $p.ExitCode "
                            "} catch { "
                            "exit 1 "
                            "}"
                        ]
                        r = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
                    elevated = r.returncode == 0
                except Exception:
                    elevated = False

                if not elevated:
                    raise PermissionError(tr("admin_hint_windows"))
            else:
                flush = (
                    "resolvectl flush-caches 2>/dev/null || "
                    "systemd-resolve --flush-caches 2>/dev/null || "
                    "/etc/init.d/nscd restart 2>/dev/null || "
                    "killall -HUP dnsmasq 2>/dev/null || true"
                )
                if os.geteuid() == 0:
                    shutil.copy(temp_path, HOSTS_PATH)
                    os.chmod(HOSTS_PATH, 0o644)
                    subprocess.run(flush, shell=True)
                else:
                    s_src = temp_path.replace("'", "'\\''")
                    s_dst = str(HOSTS_PATH).replace("'", "'\\''")
                    bash_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"
                    elevated = False

                    for launcher, args in (
                        ("pkexec", ["pkexec", "bash", "-c", bash_cmd]),
                        ("sudo", ["sudo", "bash", "-c", bash_cmd]),
                    ):
                        if shutil.which(launcher):
                            try:
                                r = subprocess.run(args, timeout=120)
                                elevated = r.returncode == 0
                                if elevated:
                                    break
                            except Exception:
                                continue

                    if not elevated:
                        for su_tool in ("gksudo", "kdesudo"):
                            if shutil.which(su_tool):
                                try:
                                    r = subprocess.run([su_tool, "bash", "-c", bash_cmd], timeout=120)
                                    elevated = r.returncode == 0
                                    if elevated:
                                        break
                                except Exception:
                                    continue

                    if not elevated:
                        raise PermissionError(tr("admin_hint_unix"))

            _time.sleep(0.5)
            self.invalidate_cache()
            if not self._verify_applied_content(content):
                logger.error("Hosts apply verification failed: target file content does not match expected content")
                return False
            return True
        except Exception as e:
            logger.error("Apply hosts failed: %s", e)
            return False
        finally:
            if temp_path:
                _safe_remove(temp_path)
            if ps_script_path:
                _safe_remove(ps_script_path)

    def update(self) -> bool:
        url = "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts"
        if not self.backup("install"):
            return False
        content = HttpClient.fetch(url)
        if not content:
            return False
        add_ver, add_hosts = HttpClient.fetch_additional_hosts()
        if add_hosts:
            content += f"\n# additional_hosts_version {add_ver}\n{add_hosts.strip()}\n"
        return self.apply(content)

    def restore(self) -> bool:
        if not self.backup("uninstall"):
            return False
        default_hosts = "127.0.0.1       localhost\n::1             localhost\n"
        if sys.platform == "win32":
            default_hosts = (
                "# Copyright (c) 1993-2009 Microsoft Corp.\n#\n"
                "# This is a sample HOSTS file used by Microsoft TCP/IP for Windows.\n#\n"
                "# This file contains the mappings of IP addresses to host names. Each\n"
                "# entry should be kept on an individual line. The IP address should\n"
                "# be placed in the first column followed by the corresponding host name.\n"
                "# The IP address and the host name should be separated by at least one\n# space.\n#\n"
                "# Additionally, comments (such as these) may be inserted on individual\n"
                "# lines or following the machine name denoted by a '#' symbol.\n#\n"
                "# For example:\n#\n#      102.54.94.97     rhino.acme.com          # source server\n"
                "#       38.25.63.10     x.acme.com              # x client host\n\n"
                "# localhost name resolution is handled within DNS itself.\n"
                "#   127.0.0.1       localhost\n#   ::1             localhost"
            )
        return self.apply(default_hosts)

    def check_status(self) -> HostsStatusResult:
        if not HOSTS_PATH.exists() or not self.is_installed():
            return HostsStatusResult("not_installed", "#e06c75", "")

        try:
            raw = HOSTS_PATH.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            local_line, local_date = _extract_update_line(raw)
            local_add_ver = _extract_additional_version(text)

            remote_line, remote_date = "", ""
            remote_add_ver = ""

            def fetch_main():
                nonlocal remote_line, remote_date
                remote_line, remote_date = HttpClient.get_remote_main_line_cached()

            def fetch_add():
                nonlocal remote_add_ver
                remote_add_ver = HttpClient.get_remote_add_version_cached()

            t1 = threading.Thread(target=fetch_main, daemon=True)
            t2 = threading.Thread(target=fetch_add, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=15)
            t2.join(timeout=15)

            main_match = local_line == remote_line and local_line.startswith("#")
            add_match = (local_add_ver == remote_add_ver) if remote_add_ver else (local_add_ver == "")

            if main_match and add_match:
                return HostsStatusResult("up_to_date", "#43b581", remote_date)
            return HostsStatusResult("outdated", "#e06c75", remote_date)
        except Exception:
            logger.exception("Status check failed")
            return HostsStatusResult("outdated", "#e06c75", "")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
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


def _is_windows_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _safe_remove(path: str, retries: int = 3, delay: float = 0.3):
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


def _sanitize_backup_action(action: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in action.strip().lower())
    return cleaned or "manual"


def _extract_update_line(content: bytes) -> tuple[str, str]:
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


def _extract_additional_version(text: str) -> str:
    match = _ADDITIONAL_HOSTS_VERSION_RE.search(text)
    return match.group(1) if match else ""


# ----------------------------------------------------------------------
# Translations
# ----------------------------------------------------------------------
TRANSLATIONS = {
    "ru": {
        "backup_missing_title": "Backup не найден",
        "backup_missing_info": "Последний backup-файл отсутствует.\nОткрыть папку с backup-файлами?",
        "open_folder": "Открыть папку",
        "cancel": "Отмена",
        "author_label": "Автор: AvenCores",
        "back_to_menu": "В меню",
        "status_installed": "Установлен",
        "status_not_installed": "Не установлен",
        "unlock_status": "ㅤОбход блокировок - <span style='color:{color}; font-weight:bold;'>{status}</span>ㅤ",
        "version_checking": "Проверка версии…",
        "update_date_checking": "Дата обновления: проверка...",
        "install_button_install": " Установить обход блокировок",
        "install_button_update": " Обновить обход блокировок",
        "uninstall_button": " Удалить обход блокировок",
        "theme_button": " Сменить тему",
        "language_button": " English",
        "donate_button": " Донат",
        "about_button": " О программе",
        "update_button": " Проверить обновления",
        "open_hosts_button": " Открыть файл hosts",
        "backup_hosts_button": " Бэкапы hosts",
        "backup_menu_open_file": "Открыть последний backup-файл",
        "backup_menu_open_folder": "Открыть папку backup",
        "ok": "Окей",
        "installed_version": "ㅤУстановленная версия: <b>v{version}</b>ㅤ",
        "latest_version": "Последняя версия: <b>v{version}</b>",
        "latest_version_padded": "ㅤПоследняя версия: <b>v{version}</b>ㅤ",
        "new_version_available": "Доступна новая версия!",
        "download": "Скачать",
        "latest_version_installed": "ㅤУ вас установлена последняя версия.ㅤ",
        "update_url_missing": "URL обновления не найден.",
        "update_info_unavailable": "Не удалось получить информацию об обновлении.",
        "updates_check_failed": "Не удалось проверить обновления.",
        "processing_install": "Установка обхода...\nㅤПожалуйста, подождите.ㅤ",
        "processing_update": "Обновление обхода...\nㅤПожалуйста, подождите.ㅤ",
        "processing_uninstall": "Удаление обхода...\nㅤПожалуйста, подождите.ㅤ",
        "install_success": "Файл hosts успешно установлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "update_success": "Файл hosts успешно обновлён!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "uninstall_success": "Файл hosts успешно восстановлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "admin_hint_windows": "Запустите программу от имени Администратора.",
        "admin_hint_unix": "Введите пароль root при запросе.",
        "install_error": "Не удалось установить файл hosts.\nㅤ{hint}ㅤ",
        "update_error": "Не удалось обновить файл hosts.\nㅤ{hint}ㅤ",
        "uninstall_error": "Не удалось восстановить файл hosts.\nㅤ{hint}ㅤ",
        "donate_title": "Поддержать автора",
        "copy_card": "Скопировать номер карты",
        "copied": "Скопировано",
        "repository": "Репозиторий",
        "hosts_status_not_installed": "Не установлен",
        "hosts_status_up_to_date": "Актуально",
        "hosts_status_outdated": "Устарело",
        "hosts_version_status": "Версия hosts - <span style='color:{color}; font-weight:bold;'>{status}</span>",
        "hosts_update_date": "Дата обновления hosts: {date}",
        "hosts_update_date_unknown": "Дата обновления hosts: неизвестно",
    },
    "en": {
        "backup_missing_title": "Backup not found",
        "backup_missing_info": "The latest backup file is missing.\nOpen the backup folder?",
        "open_folder": "Open folder",
        "cancel": "Cancel",
        "author_label": "Author: AvenCores",
        "back_to_menu": "Back to menu",
        "status_installed": "Installed",
        "status_not_installed": "Not installed",
        "unlock_status": "ㅤBypass status - <span style='color:{color}; font-weight:bold;'>{status}</span>ㅤ",
        "version_checking": "Checking version…",
        "update_date_checking": "Update date: checking...",
        "install_button_install": " Install bypass",
        "install_button_update": " Update bypass",
        "uninstall_button": " Remove bypass",
        "theme_button": " Change theme",
        "language_button": " Русский",
        "donate_button": " Donate",
        "about_button": " About",
        "update_button": " Check for updates",
        "open_hosts_button": " Open hosts file",
        "backup_hosts_button": " Hosts backups",
        "backup_menu_open_file": "Open latest backup file",
        "backup_menu_open_folder": "Open backup folder",
        "ok": "OK",
        "installed_version": "ㅤInstalled version: <b>v{version}</b>ㅤ",
        "latest_version": "Latest version: <b>v{version}</b>",
        "latest_version_padded": "ㅤLatest version: <b>v{version}</b>ㅤ",
        "new_version_available": "A new version is available!",
        "download": "Download",
        "latest_version_installed": "ㅤYou already have the latest version.ㅤ",
        "update_url_missing": "Update URL not found.",
        "update_info_unavailable": "Failed to get update information.",
        "updates_check_failed": "Failed to check for updates.",
        "processing_install": "Installing bypass...\nㅤPlease wait.ㅤ",
        "processing_update": "Updating bypass...\nㅤPlease wait.ㅤ",
        "processing_uninstall": "Removing bypass...\nㅤPlease wait.ㅤ",
        "install_success": "The hosts file was installed successfully!\nㅤYou may need to restart your browser.ㅤ",
        "update_success": "The hosts file was updated successfully!\nㅤYou may need to restart your browser.ㅤ",
        "uninstall_success": "The hosts file was restored successfully!\nㅤYou may need to restart your browser.ㅤ",
        "admin_hint_windows": "Run the app as Administrator.",
        "admin_hint_unix": "Enter the root password when prompted.",
        "install_error": "Failed to install the hosts file.\nㅤ{hint}ㅤ",
        "update_error": "Failed to update the hosts file.\nㅤ{hint}ㅤ",
        "uninstall_error": "Failed to restore the hosts file.\nㅤ{hint}ㅤ",
        "donate_title": "Support the author",
        "copy_card": "Copy card number",
        "copied": "Copied",
        "repository": "Repository",
        "hosts_status_not_installed": "Not installed",
        "hosts_status_up_to_date": "Up to date",
        "hosts_status_outdated": "Outdated",
        "hosts_version_status": "Hosts version - <span style='color:{color}; font-weight:bold;'>{status}</span>",
        "hosts_update_date": "Hosts update date: {date}",
        "hosts_update_date_unknown": "Hosts update date: unknown",
    },
}


def normalize_language(language: str | None) -> str:
    if not language:
        return "ru"
    normalized = language.lower().replace("-", "_")
    if normalized.startswith("ru"):
        return "ru"
    if normalized.startswith("en"):
        return "en"
    return "en"


def detect_system_language() -> str:
    try:
        return normalize_language(QLocale.system().name())
    except Exception:
        return "ru"


def set_current_language(language: str | None) -> str:
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = normalize_language(language)
    return CURRENT_LANGUAGE


@lru_cache(maxsize=512)
def _tr_cached(key: str, lang: str, kwargs_tuple: tuple) -> str:
    bundle = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    template = bundle.get(key, TRANSLATIONS["ru"].get(key, key))
    if kwargs_tuple:
        return template.format(**dict(kwargs_tuple))
    return template


def tr(key: str, *, language: str | None = None, **kwargs) -> str:
    lang = normalize_language(language or CURRENT_LANGUAGE)
    kwargs_tuple = tuple(sorted(kwargs.items())) if kwargs else tuple()
    return _tr_cached(key, lang, kwargs_tuple)


def clean_message_line(text: str) -> str:
    return text.replace(_LAYOUT_FILLER, "").strip()


def localize_update_date(date_text: str, language: str | None = None) -> str:
    target = normalize_language(language or CURRENT_LANGUAGE)
    names = _MONTH_NAME_OUTPUTS.get(target, _MONTH_NAME_OUTPUTS["en"])

    def replace_month(match):
        idx = _MONTH_NAME_ALIASES.get(match.group(0).lower())
        return names[idx] if idx is not None else match.group(0)

    return _MONTH_NAME_RE.sub(replace_month, date_text)


set_current_language(detect_system_language())


# ----------------------------------------------------------------------
# Hosts file GUI helpers
# ----------------------------------------------------------------------
def _show_open_hosts_error(detail: str, _inline_callback=None):
    lang = str(globals().get("CURRENT_LANGUAGE", "ru")).lower().replace("-", "_")
    if lang.startswith("ru"):
        message = f"Не удалось открыть файл hosts с правами администратора.\n{detail}"
    else:
        message = f"Failed to open the hosts file with administrator privileges.\n{detail}"

    if _inline_callback is not None:
        try:
            QTimer.singleShot(0, lambda: _inline_callback(message, False))
        except Exception:
            print(message)
    else:
        try:
            app = QApplication.instance()
            parent = app.activeWindow() if app else None
            title = "Ошибка открытия hosts" if lang.startswith("ru") else "Hosts Open Error"
            QMessageBox.critical(parent, title, message)
        except Exception:
            print(message)


def _open_hosts_file_windows_as_admin() -> tuple[bool, str | None]:
    try:
        import ctypes
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "notepad.exe", str(HOSTS_PATH), None, 1
        )
        return result > 32, None
    except Exception as e:
        logger.error("Open hosts error: %s", e)
        return False, str(e)


def _open_hosts_file_linux_as_admin() -> tuple[bool, str | None]:
    editors = (
        "gnome-text-editor", "gedit", "xed", "pluma", "mousepad",
        "geany", "kate", "kwrite", "featherpad", "leafpad",
    )
    display_env = [
        f"{k}={v}" for k, v in os.environ.items()
        if k in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    ]

    if os.geteuid() == 0:
        for editor in editors:
            ep = shutil.which(editor)
            if ep:
                try:
                    subprocess.Popen([ep, str(HOSTS_PATH)], start_new_session=True)
                    return True, None
                except Exception:
                    continue
        try:
            open_target(str(HOSTS_PATH))
            return True, None
        except Exception as e:
            logger.error("Open error: %s", e)
            return False, str(e)

    launchers = []
    if shutil.which("pkexec"):
        launchers.append("pkexec")
    for su in ("gksudo", "kdesudo"):
        if shutil.which(su):
            launchers.append(su)

    for editor in editors:
        ep = shutil.which(editor)
        if not ep:
            continue
        for launcher in launchers:
            try:
                if launcher == "pkexec":
                    cmd = ["pkexec"]
                    if display_env:
                        cmd.extend(["env", *display_env])
                    cmd.extend([ep, str(HOSTS_PATH)])
                else:
                    cmd = [launcher, ep, str(HOSTS_PATH)]
                subprocess.Popen(cmd, start_new_session=True)
                return True, None
            except Exception:
                continue
    return False, "linux_admin_open_unavailable"


def open_hosts_file(_inline_callback=None):
    try:
        if sys.platform == "win32":
            opened, error_key = _open_hosts_file_windows_as_admin()
        elif sys.platform.startswith("linux"):
            opened, error_key = _open_hosts_file_linux_as_admin()
        else:
            open_target(str(HOSTS_PATH))
            return

        if opened:
            return

        if error_key == "admin_hint_windows":
            detail = tr("admin_hint_windows")
        elif error_key == "linux_admin_open_unavailable":
            detail = (
                "Установите pkexec и графический текстовый редактор или запустите приложение от имени root."
                if normalize_language(CURRENT_LANGUAGE) == "ru" else
                "Install pkexec and a graphical text editor, or run the app as root."
            )
        else:
            detail = error_key or tr("admin_hint_unix")

        _show_open_hosts_error(detail, _inline_callback=_inline_callback)
    except Exception as e:
        logger.error("Open hosts error: %s", e)
        _show_open_hosts_error(str(e), _inline_callback=_inline_callback)


def open_hosts_backup_folder():
    HOSTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    open_target(str(HOSTS_BACKUP_DIR))


def open_latest_hosts_backup_file():
    manager = HostsManager()
    latest = manager.get_latest_backup()
    if latest and latest.exists():
        open_target(str(latest))
    else:
        _show_backup_missing_dialog()


def _show_backup_missing_dialog():
    from PySide6.QtWidgets import QLabel
    app = QApplication.instance()
    parent = app.activeWindow() if app else None
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(tr("backup_missing_title"))
    dialog.setIcon(QMessageBox.Icon.NoIcon)
    dialog.setText(f"<b style='font-size:15px;'>{tr('backup_missing_title')}</b>")
    dialog.setInformativeText(tr("backup_missing_info"))
    dialog.setTextFormat(Qt.TextFormat.RichText)
    dialog.setStandardButtons(QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel)
    dialog.setDefaultButton(QMessageBox.StandardButton.Open)
    dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)

    open_btn = dialog.button(QMessageBox.StandardButton.Open)
    cancel_btn = dialog.button(QMessageBox.StandardButton.Cancel)
    if open_btn:
        open_btn.setText(tr("open_folder"))
        open_btn.setObjectName("backupOpenButton")
    if cancel_btn:
        cancel_btn.setText(tr("cancel"))
        cancel_btn.setObjectName("backupCancelButton")
    for lbl in dialog.findChildren(QLabel):
        if lbl.text().strip():
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    dark = bool(getattr(parent, "dark_theme", False))
    if dark:
        dialog.setStyleSheet("""
            QMessageBox { background-color: #1f242d; }
            QMessageBox QLabel { color: #f3f6fd; font-size: 13px; max-width: 250px; background: transparent; border: none; }
            QPushButton#backupOpenButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d7dff, stop:1 #2962d9);
                color: white; border: none; border-radius: 8px; padding: 7px 12px; min-width: 112px; font-weight: 600;
            }
            QPushButton#backupOpenButton:hover { background: #246cf0; }
            QPushButton#backupCancelButton {
                background: #e6e8ec; color: #222; border: 1px solid #cfd4db; border-radius: 8px; padding: 7px 12px; min-width: 96px;
            }
            QPushButton#backupCancelButton:hover { background: #d1d4d8; }
        """)
    else:
        dialog.setStyleSheet("""
            QMessageBox { background-color: #ffffff; }
            QMessageBox QLabel { color: #1a1a1a; font-size: 13px; max-width: 250px; background: transparent; border: none; }
            QPushButton#backupOpenButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078d4, stop:1 #0063b1);
                color: white; border: none; border-radius: 8px; padding: 7px 12px; min-width: 112px; font-weight: 600;
            }
            QPushButton#backupOpenButton:hover { background: #006cbd; }
            QPushButton#backupCancelButton {
                background: #f3f4f7; color: #1a1a1a; border: 1px solid #cfd4db; border-radius: 8px; padding: 7px 12px; min-width: 96px;
            }
            QPushButton#backupCancelButton:hover { background: #e6e8ec; }
        """)

    if dialog.exec() == QMessageBox.StandardButton.Open:
        open_hosts_backup_folder()


# ----------------------------------------------------------------------
# Styles
# ----------------------------------------------------------------------
def is_system_dark_theme():
    if sys.platform == "win32":
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except Exception:
            return False
    else:
        try:
            out = subprocess.check_output(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return "dark" in out.lower()
        except Exception:
            return False


_STYLESHEET_CACHE: dict[str, dict] = {}


def get_stylesheet(dark: bool, language: str | None = None) -> dict[str, str]:
    lang = normalize_language(language or CURRENT_LANGUAGE)
    key = f"{lang}_dark_{dark}"
    if key in _STYLESHEET_CACHE:
        return _STYLESHEET_CACHE[key]
    result = _build_stylesheet(dark, lang)
    _STYLESHEET_CACHE[key] = result
    return result


def _build_stylesheet(dark: bool, language: str) -> dict[str, str]:
    author_color = "#888" if dark else "#666666"
    link_color = "#2d7dff" if dark else "#0078d4"
    if dark:
        return {
            "main": """
                QMainWindow { background: #1e2228; border-radius: 16px; }
                QWidget { border-radius: 16px; background: #1e2228; }
                QWidget#titleBar { background: transparent; border-bottom: 1px solid #2d333b; }
            """,
            "label": "QLabel { font-size: 18px; padding: 16px 0 8px 0; color: #f3f6fd; font-weight: 500; }",
            "message_card": "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;",
            "message_label": "QLabel { font-size: 18px; padding: 8px 0 4px 0; color: #f3f6fd; font-weight: 500; background: transparent; }",
            "message_block_label": "QLabel { font-size: 18px; padding: 10px 12px; color: #f3f6fd; font-weight: 500; background: #363d46; border-radius: 8px; border: none; }",
            "button1": """
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d7dff, stop:1 #2962d9); color: white; border: none; border-radius: 8px; padding: 12px 0; font-size: 16px; font-weight: 600; }
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #246cf0, stop:1 #235bcc); }
                QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e5ed2, stop:1 #1c52b0); padding: 14px 0 10px 0; }
            """,
            "button2": """
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e06c75, stop:1 #d64c58); color: white; border: none; border-radius: 8px; padding: 12px 0; font-size: 16px; font-weight: 600; }
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b94a59, stop:1 #a43b47); }
                QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a84a57, stop:1 #973f4a); padding: 14px 0 10px 0; }
            """,
            "theme": """
                QPushButton, QToolButton { background: #e6e8ec; color: #222; border: 1.5px solid #cfd4db; border-radius: 8px; padding: 10px 0; font-size: 15px; font-weight: 500; }
                QPushButton:hover, QToolButton:hover { background: #d1d4d8; }
                QPushButton:pressed, QToolButton:pressed { background: #bfc3c9; padding: 12px 0 8px 0; }
            """,
            "theme_center_small": "QPushButton { background: #e6e8ec; color: #222; border: 1.5px solid #cfd4db; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500; min-width: 140px; text-align: center; }",
            "about_title_style": "font-size:25px; margin-bottom:4px;",
            "about_title_html": f"<b style='color:#f3f6fd;'>Goida AI Unlocker</b> <span style='font-size:15px; color:#bfc9db;'>(v{APP_VERSION})</span>",
            "about_info_html": f"<span style='font-size:11px; color:{author_color};'>{tr('author_label', language=language)}</span>",
            "about_link_html": f"<a href='#' style='color:{link_color}; text-decoration:none; font-size:13px;'>⟵ {tr('back_to_menu', language=language)}</a>",
        }
    else:
        return {
            "main": """
                QMainWindow { background: #ffffff; border-radius: 16px; }
                QWidget { border-radius: 16px; background: #ffffff; }
                QWidget#titleBar { background: transparent; border-bottom: 1px solid #e1e4e8; }
            """,
            "label": "QLabel { font-size: 18px; padding: 16px 0 8px 0; color: #1a1a1a; font-weight: 500; }",
            "message_card": "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;",
            "message_label": "QLabel { font-size: 18px; padding: 8px 0 4px 0; color: #1a1a1a; font-weight: 500; background: transparent; }",
            "message_block_label": "QLabel { font-size: 18px; padding: 10px 12px; color: #1a1a1a; font-weight: 500; background: #e6e8ec; border-radius: 8px; border: none; }",
            "button1": """
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078d4, stop:1 #0063b1); color: white; border: none; border-radius: 8px; padding: 12px 0; font-size: 16px; font-weight: 600; }
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #006cbd, stop:1 #005291); }
                QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005291, stop:1 #004677); padding: 14px 0 10px 0; }
            """,
            "button2": """
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e06c75, stop:1 #d64c58); color: white; border: none; border-radius: 8px; padding: 12px 0; font-size: 16px; font-weight: 600; }
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b94a59, stop:1 #a43b47); }
                QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9e3f4c, stop:1 #8f3640); padding: 14px 0 10px 0; }
            """,
            "theme": """
                QPushButton, QToolButton { background: #f3f4f7; color: #1a1a1a; border: 1.5px solid #cfd4db; border-radius: 8px; padding: 10px 0; font-size: 15px; font-weight: 500; }
                QPushButton:hover, QToolButton:hover { background: #e6e8ec; }
                QPushButton:pressed, QToolButton:pressed { background: #d1d5db; padding: 12px 0 8px 0; }
            """,
            "theme_center_small": "QPushButton { background: #f3f4f7; color: #1a1a1a; border: 1.5px solid #cfd4db; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500; min-width: 140px; text-align: center; }",
            "about_title_style": "font-size:25px; margin-bottom:4px;",
            "about_title_html": f"<b style='color:#1a1a1a;'>Goida AI Unlocker</b> <span style='font-size:15px; color:#555555;'>(v{APP_VERSION})</span>",
            "about_info_html": f"<span style='font-size:11px; color:{author_color};'>{tr('author_label', language=language)}</span>",
            "about_link_html": f"<a href='#' style='color:{link_color}; text-decoration:none; font-size:13px;'>⟵ {tr('back_to_menu', language=language)}</a>",
        }


def get_about_toolbutton_style(styles: dict[str, str]) -> str:
    return styles["theme"] + "\nQToolButton { font-size: 10pt; padding: 6px 12px; }"


# ----------------------------------------------------------------------
# Qt Workers (QThreadPool)
# ----------------------------------------------------------------------
class WorkerSignals(QObject):
    finished = Signal(str, bool, str)
    status_ready = Signal(object)
    update_ready = Signal(str, str, str)
    no_update = Signal(str, str)
    message = Signal(str, bool, bool)


class HostsWorker(QRunnable):
    def __init__(self, action: str, manager: HostsManager):
        super().__init__()
        self.action = action
        self.manager = manager
        self.signals = WorkerSignals()

    def run(self):
        try:
            if self.action in ("install", "update"):
                result = self.manager.update()
            else:
                result = self.manager.restore()
            self.signals.finished.emit(self.action, result, "")
        except Exception as e:
            logger.exception("Hosts operation failed")
            self.signals.finished.emit(self.action, False, str(e))


class VersionWorker(QRunnable):
    def __init__(self, manager: HostsManager):
        super().__init__()
        self.manager = manager
        self.signals = WorkerSignals()

    def run(self):
        status = self.manager.check_status()
        self.signals.status_ready.emit(status)


class AppUpdateWorker(QRunnable):
    def __init__(self, resource_path_func: Callable[[str], str]):
        super().__init__()
        self.resource_path = resource_path_func
        self.signals = WorkerSignals()

    def run(self):
        try:
            with open(self.resource_path("app_info.json"), "r", encoding="utf-8") as f:
                local = json.load(f)
            local_ver = local.get("version", "0.0.0")
            remote_url = local.get("update_info_url")
            if not remote_url:
                raise RuntimeError(tr("update_url_missing"))
            remote_content = HttpClient.fetch(remote_url)
            if not remote_content:
                raise RuntimeError(tr("update_info_unavailable"))
            remote_data = json.loads(remote_content)
            remote_ver = remote_data.get("version", "0.0.0")
            download_url = remote_data.get("download_url", "https://github.com/AvenCores/Goida-AI-Unlocker")

            def parse(v):
                return tuple(int(x) for x in v.strip("vV").split(".") if x.isdigit())

            if parse(remote_ver) > parse(local_ver):
                self.signals.update_ready.emit(local_ver, remote_ver, download_url)
            else:
                self.signals.no_update.emit(local_ver, remote_ver)
        except Exception as e:
            err = f"{tr('updates_check_failed')}\n{e}"
            self.signals.message.emit(err, False, True)


# ----------------------------------------------------------------------
# UI Classes
# ----------------------------------------------------------------------
class DraggableTitleBar(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self._main_window = main_window
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._main_window.start_system_move():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._main_window.move(self._main_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget: Optional[QStackedWidget] = None
        self._current_animation: Optional[QPropertyAnimation] = None
        self.dark_theme = False
        self.styles: dict[str, str] = {}
        self.title_bar: Optional[QWidget] = None
        self.language = CURRENT_LANGUAGE
        self.hosts_manager = HostsManager()
        self._check_updates_running = False
        self.home_page: Optional[QWidget] = None
        self.resource_path: Callable[[str], str] = lambda x: x
        self._processing_widget: Optional[QWidget] = None

    def start_system_move(self) -> bool:
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemMove())
        except Exception:
            return False

    def fix_widget_size(self, w: QWidget):
        h = self.height() - (self.title_bar.height() if self.title_bar else 32)
        w.setMinimumSize(self.width(), h)
        w.setMaximumSize(self.width(), h)

    def _clear_effects(self):
        """Remove all graphics effects from stacked widgets."""
        if not self.stacked_widget:
            return
        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w and w.graphicsEffect():
                w.setGraphicsEffect(None)

    def animate_switch(self, new_widget: QWidget, on_finish=None):
        if not self.stacked_widget:
            return
        current = self.stacked_widget.currentWidget()
        if not current or current == new_widget:
            self.stacked_widget.setCurrentWidget(new_widget)
            if on_finish:
                on_finish()
            return
        
        self.fix_widget_size(new_widget)
        
        if self._current_animation is not None:
            self._current_animation.stop()
            self._current_animation = None
        self._clear_effects()
        
        if current.graphicsEffect():
            current.setGraphicsEffect(None)
        
        effect_out = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect_out)
        fade_out = QPropertyAnimation(effect_out, b"opacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def do_switch():
            if self.stacked_widget is None:
                return
            self.stacked_widget.setCurrentWidget(new_widget)
            if current and current.graphicsEffect():
                current.setGraphicsEffect(None)
            
            if new_widget.graphicsEffect():
                new_widget.setGraphicsEffect(None)
                
            effect_in = QGraphicsOpacityEffect(new_widget)
            new_widget.setGraphicsEffect(effect_in)
            fade_in = QPropertyAnimation(effect_in, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)

            def cleanup():
                new_widget.setGraphicsEffect(None)
                self._current_animation = None
                if on_finish:
                    on_finish()

            fade_in.finished.connect(cleanup)
            self._current_animation = fade_in
            fade_in.start()

        fade_out.finished.connect(do_switch)
        self._current_animation = fade_out
        fade_out.start()

    def remove_widget(self, widget: QWidget):
        if self.stacked_widget:
            self.stacked_widget.removeWidget(widget)
        widget.deleteLater()

    def return_to_main(self, widget: QWidget):
        def cleanup():
            self.remove_widget(widget)
        self.animate_switch(self.home_page, on_finish=cleanup)

    def _add_and_switch(self, widget: QWidget):
        if self.stacked_widget:
            self.stacked_widget.addWidget(widget)
        self.update_subwindow_styles()
        self.animate_switch(widget)

    def _build_card(self, icon_name: str, max_width: int = 420) -> tuple[QWidget, QVBoxLayout, QWidget]:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        self.fix_widget_size(widget)

        card = QWidget()
        card.setObjectName("msg_card")
        card.setMinimumWidth(240)
        card.setMaximumWidth(max_width)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card.setStyleSheet(self.styles["message_card"])

        emoji = create_icon_label(icon_name, size=48)
        card_layout.addWidget(emoji)

        vbox.addWidget(card)
        return widget, card_layout, card

    def show_message(self, msg: str, success: bool = True, word_wrap: bool = False):
        widget, card_layout, card = self._build_card("check-circle.svg" if success else "x-circle.svg")

        if word_wrap:
            for raw_line in msg.split("\n"):
                line = clean_message_line(raw_line)
                if not line:
                    continue
                lbl = QLabel(line)
                lbl.setObjectName("message_block_label")
                lbl.setTextFormat(Qt.TextFormat.PlainText)
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                card_layout.addWidget(lbl)
        else:
            for raw_line in msg.split("\n"):
                line = clean_message_line(raw_line)
                if not line.strip():
                    continue
                lbl = QLabel(line)
                lbl.setObjectName("message_label")
                lbl.setTextFormat(Qt.TextFormat.PlainText)
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                card_layout.addWidget(lbl)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def show_processing(self, action: str) -> QWidget:
        if action == "install":
            msg = tr("processing_install")
        elif action == "update":
            msg = tr("processing_update")
        else:
            msg = tr("processing_uninstall")

        widget, card_layout, card = self._build_card("clock.svg")
        for raw_line in msg.split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            lbl = QLabel(line)
            lbl.setObjectName("message_label")
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(lbl)

        self._add_and_switch(widget)
        return widget

    def show_update_available(self, local_ver: str, latest_ver: str, dl_url: str):
        widget, card_layout, card = self._build_card("alert.svg", max_width=600)

        for text in (
            tr("installed_version", version=local_ver),
            tr("latest_version", version=latest_ver),
            tr("new_version_available")
        ):
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        dl_btn = QPushButton(tr("download"))
        dl_btn.setProperty("style_role", "button1")
        card_layout.addWidget(dl_btn)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        dl_btn.clicked.connect(lambda: open_target(dl_url))
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def show_no_update(self, local_ver: str, latest_ver: str):
        widget, card_layout, card = self._build_card("check-circle.svg", max_width=600)

        for text in (
            tr("installed_version", version=local_ver),
            tr("latest_version_padded", version=latest_ver),
            tr("latest_version_installed")
        ):
            lbl = QLabel(text)
            if "version" in text:
                lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def update_subwindow_styles(self):
        if not self.stacked_widget:
            return
        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w is self.home_page:
                continue
            w.setStyleSheet(self.styles["main"])
            for child in w.findChildren(QPushButton):
                role = child.property("style_role")
                if role == "button2":
                    child.setStyleSheet(self.styles["button2"])
                elif role == "theme":
                    child.setStyleSheet(self.styles["theme"])
                else:
                    child.setStyleSheet(self.styles["button1"])
            for child in w.findChildren(QToolButton):
                if child.property("style_role") == "about_tool":
                    child.setStyleSheet(get_about_toolbutton_style(self.styles))
            for child in w.findChildren(QLabel):
                name = child.objectName()
                if name == "about_title":
                    child.setText(self.styles["about_title_html"])
                    child.setStyleSheet(self.styles["about_title_style"])
                elif name == "about_info":
                    child.setText(self.styles["about_info_html"])
                elif name == "about_link":
                    child.setText(self.styles["about_link_html"])
                elif name == "message_label":
                    child.setStyleSheet(self.styles["message_label"])
                elif name == "message_block_label":
                    child.setStyleSheet(self.styles["message_block_label"])
                elif name == "message_emoji":
                    continue
                else:
                    child.setStyleSheet(self.styles["label"])
            for card in w.findChildren(QWidget, "msg_card"):
                card.setStyleSheet(self.styles["message_card"])
            if w is not self.home_page:
                refresh_icons(w)

    def animate_switch(self, new_widget: QWidget, on_finish=None):
        if not self.stacked_widget:
            return
        current = self.stacked_widget.currentWidget()
        if not current or current == new_widget:
            self.stacked_widget.setCurrentWidget(new_widget)
            if on_finish:
                on_finish()
            return
        
        self.fix_widget_size(new_widget)
        
        if self._current_animation is not None:
            self._current_animation.stop()
            self._current_animation = None
        self._clear_effects()
        
        if current.graphicsEffect():
            current.setGraphicsEffect(None)
        
        effect_out = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect_out)
        fade_out = QPropertyAnimation(effect_out, b"opacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def do_switch():
            if self.stacked_widget is None:
                return
            self.stacked_widget.setCurrentWidget(new_widget)
            if current and current.graphicsEffect():
                current.setGraphicsEffect(None)
            
            if new_widget.graphicsEffect():
                new_widget.setGraphicsEffect(None)
                
            effect_in = QGraphicsOpacityEffect(new_widget)
            new_widget.setGraphicsEffect(effect_in)
            fade_in = QPropertyAnimation(effect_in, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)

            def cleanup():
                new_widget.setGraphicsEffect(None)
                self._current_animation = None
                if on_finish:
                    on_finish()

            fade_in.finished.connect(cleanup)
            self._current_animation = fade_in
            fade_in.start()

        fade_out.finished.connect(do_switch)
        self._current_animation = fade_out
        fade_out.start()

    @Slot(str, bool, str)
    def on_hosts_finished(self, action: str, ok: bool, error: str):
        if ok:
            if action == "install":
                msg = tr("install_success")
            elif action == "update":
                msg = tr("update_success")
            else:
                msg = tr("uninstall_success")
            self.show_message(msg, success=True, word_wrap=True)
        else:
            hint = tr("admin_hint_windows") if sys.platform == "win32" else tr("admin_hint_unix")
            if action == "install":
                msg = tr("install_error", hint=hint)
            elif action == "update":
                msg = tr("update_error", hint=hint)
            else:
                msg = tr("uninstall_error", hint=hint)
            self.show_message(msg, success=False, word_wrap=True)

        # Не удаляем processing сразу — пусть animate_switch корректно отработает,
        # а виджет удалим после того, как переключение на message начнётся
        if self._processing_widget is not None:
            proc = self._processing_widget
            self._processing_widget = None
            QTimer.singleShot(400, lambda: self.remove_widget(proc))
        
        self.update_installation_status_label()
        self.check_version_status()

    def start_installation(self, action: str):
        self._processing_widget = self.show_processing(action)
        worker = HostsWorker(action, self.hosts_manager)
        worker.signals.finished.connect(self.on_hosts_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def update_installation_status_label(self):
        installed = self.hosts_manager.is_installed()
        color = "#43b581" if installed else "#e06c75"
        key = "status_installed" if installed else "status_not_installed"
        self.textinformer.setText(tr("unlock_status", status=tr(key), color=color))

    @Slot(object)
    def apply_hosts_version_status(self, status: HostsStatusResult):
        self.version_label.setProperty("status_key", status.key)
        self.version_label.setProperty("status_color", status.color)
        self.version_label.setProperty("update_date_value", status.date)

        self.version_label.setText(
            tr("hosts_version_status", color=status.color, status=tr(f"hosts_status_{status.key}"))
        )
        if status.date:
            self.update_date_label.setText(tr("hosts_update_date", date=localize_update_date(status.date)))
        else:
            self.update_date_label.setText(tr("hosts_update_date_unknown"))

        mode = "update" if status.key == "outdated" else "install"
        self.install_button.setProperty("install_mode", mode)
        self.install_button.setText(tr("install_button_update" if mode == "update" else "install_button_install"))

    def check_version_status(self):
        worker = VersionWorker(self.hosts_manager)
        worker.signals.status_ready.connect(self.apply_hosts_version_status, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def switch_theme(self):
        if self.is_animating:
            return
        self.is_animating = True
        steps, interval = 15, 20

        def fade_out(step=1.0):
            try:
                if step >= 0:
                    self.setWindowOpacity(step)
                    QTimer.singleShot(interval, lambda: fade_out(step - 1.0 / steps))
                else:
                    self.setWindowOpacity(0)
                    self.setUpdatesEnabled(False)
                    self.dark_theme = not self.dark_theme
                    self.styles = get_stylesheet(self.dark_theme, self.language)
                    self.setStyleSheet(self.styles["main"])
                    self.apply_main_texts()
                    self.apply_theme_styles()
                    self.setUpdatesEnabled(True)
                    fade_in()
            except Exception:
                self.setWindowOpacity(1.0)
                self.is_animating = False

        def fade_in(step=0.0):
            try:
                if step <= 1.0:
                    self.setWindowOpacity(step)
                    QTimer.singleShot(interval, lambda: fade_in(step + 1.0 / steps))
                else:
                    self.setWindowOpacity(1.0)
                    self.is_animating = False
            except Exception:
                self.setWindowOpacity(1.0)
                self.is_animating = False

        fade_out()

    def switch_language(self):
        global _STYLESHEET_CACHE
        next_lang = "en" if self.language == "ru" else "ru"
        self.language = set_current_language(next_lang)
        _STYLESHEET_CACHE.clear()
        self.apply_theme_styles()
        self.apply_main_texts()

    def apply_theme_styles(self):
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])
        self.textinformer.setStyleSheet(self.styles["label"])
        self.app_title_label.setStyleSheet(self.styles["about_title_style"])
        self.version_label.setStyleSheet(self.styles["label"])
        text_color = "#ffffff" if self.dark_theme else "#1a1a1a"
        self.update_date_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
        )
        self.install_button.setStyleSheet(self.styles["button1"])
        self.uninstall_button.setStyleSheet(self.styles["button2"])
        self.theme_button.setStyleSheet(self.styles["theme"])
        self.language_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        self.donate_button.setStyleSheet(self.styles["theme"])
        self.open_hosts_button.setStyleSheet(self.styles["theme"])
        self.backup_hosts_button.setStyleSheet(self.styles["theme"])
        self.update_button.setStyleSheet(self.styles["theme"])
        self.about_button.setStyleSheet(self.styles["theme"])
        self.refresh_status_container_style()
        self.update_subwindow_styles()
        refresh_icons(self)

    def refresh_status_container_style(self):
        light = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
        dark = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
        self.status_container.setStyleSheet(dark if self.dark_theme else light)

    def apply_main_texts(self):
        self.title_label.setText("Goida AI Unlocker")
        self.app_title_label.setText(self.styles["about_title_html"])
        self.update_installation_status_label()

        stored_key = self.version_label.property("status_key")
        if stored_key:
            status = HostsStatusResult(
                stored_key,
                self.version_label.property("status_color") or "#e06c75",
                self.version_label.property("update_date_value") or ""
            )
            self.apply_hosts_version_status(status)
        else:
            self.version_label.setText(tr("version_checking"))
            self.update_date_label.setText(tr("update_date_checking"))
            self.install_button.setProperty("install_mode", self.install_button.property("install_mode") or "install")

        self.uninstall_button.setText(tr("uninstall_button"))
        self.theme_button.setText(tr("theme_button"))
        self.language_button.setText("")
        self.language_button.setToolTip(tr("language_button"))
        self.language_button.setStatusTip(tr("language_button"))
        self.language_button.setAccessibleName(tr("language_button"))
        self.donate_button.setText(tr("donate_button"))
        self.about_button.setText(tr("about_button"))
        self.update_button.setText(tr("update_button"))
        self.open_hosts_button.setText(tr("open_hosts_button"))
        self.backup_hosts_button.setText(tr("backup_hosts_button"))

    def show_donate(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        self.fix_widget_size(widget)

        card = QWidget()
        card.setObjectName("donate_card")
        card.setMaximumWidth(380)
        card.setMinimumWidth(240)
        cl = QVBoxLayout(card)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(16)
        cl.setContentsMargins(32, 24, 32, 24)

        light = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card.setStyleSheet(dark if self.dark_theme else light)

        title = QLabel(tr("donate_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:600;")
        cl.addWidget(title)

        card_num = "2202 2050 1464 4675"
        card_lbl = QLabel(f"ㅤSBER: <b>{card_num}</b>ㅤ")
        card_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lbl.setStyleSheet("font-size:16px;")
        cl.addWidget(card_lbl)

        copy_btn = QPushButton(tr("copy_card"))
        copy_btn.setProperty("style_role", "button1")
        cl.addWidget(copy_btn)

        vbox.addWidget(card)

        back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setProperty("style_role", "theme")
        back_btn.setStyleSheet(self.styles["theme"])
        vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        def copy_card():
            QApplication.clipboard().setText(card_num)
            if getattr(copy_btn, "_animating", False):
                return
            setattr(copy_btn, "_animating", True)
            orig = tr("copy_card")
            succ = tr("copied")

            def anim():
                eff = QGraphicsOpacityEffect(copy_btn)
                copy_btn.setGraphicsEffect(eff)
                fo = QPropertyAnimation(eff, b"opacity", copy_btn)
                fo.setDuration(150)
                fo.setStartValue(1.0)
                fo.setEndValue(0.0)

                def change():
                    copy_btn.setText(succ)
                    fi = QPropertyAnimation(eff, b"opacity", copy_btn)
                    fi.setDuration(150)
                    fi.setStartValue(0.0)
                    fi.setEndValue(1.0)

                    def hold():
                        def revert():
                            fo2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                            fo2.setDuration(150)
                            fo2.setStartValue(1.0)
                            fo2.setEndValue(0.0)

                            def reset():
                                copy_btn.setText(orig)
                                fi2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                                fi2.setDuration(150)
                                fi2.setStartValue(0.0)
                                fi2.setEndValue(1.0)

                                def clear():
                                    copy_btn.setGraphicsEffect(None)
                                    setattr(copy_btn, "_animating", False)
                                fi2.finished.connect(clear)
                                fi2.start()
                            fo2.finished.connect(reset)
                            fo2.start()
                        QTimer.singleShot(1200, revert)
                    fi.finished.connect(hold)
                    fi.start()
                fo.finished.connect(change)
                fo.start()
            anim()

        copy_btn.clicked.connect(copy_card)
        back_btn.clicked.connect(lambda: self.return_to_main(widget))

        if self.stacked_widget:
            self.stacked_widget.addWidget(widget)
        self.update_subwindow_styles()
        self.animate_switch(widget)

    def show_about(self):
        about = QWidget()
        vbox = QVBoxLayout(about)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(8)
        vbox.setContentsMargins(12, 12, 12, 12)

        icon_label = create_icon_label("bulb.svg", size=32)
        vbox.addWidget(icon_label)

        label_ver = QLabel()
        label_ver.setObjectName("about_title")
        label_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(label_ver)

        info = QLabel()
        info.setObjectName("about_info")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(info)

        github_btn = QToolButton()
        github_btn.setText("GitHub")
        github_btn.setIcon(get_icon("github.svg", 24, force_dark=True))
        github_btn.setIconSize(QSize(24, 24))
        github_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setProperty("style_role", "about_tool")
        github_btn.setProperty("icon_name", "github.svg")
        github_btn.setProperty("icon_force_dark", True)
        github_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores"))

        repo_btn = QToolButton()
        repo_btn.setText(tr("repository"))
        repo_btn.setIcon(get_icon("github.svg", 24, force_dark=True))
        repo_btn.setIconSize(QSize(24, 24))
        repo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        repo_btn.setProperty("style_role", "about_tool")
        repo_btn.setProperty("icon_name", "github.svg")
        repo_btn.setProperty("icon_force_dark", True)
        repo_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(github_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)

        social = [
            ("Telegram", "https://t.me/avencoresyt", "send.svg"),
            ("YouTube", "https://youtube.com/@avencores", "play.svg"),
            ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"),
            ("Dzen", "https://dzen.ru/avencores", "book-open.svg"),
            ("VK", "https://vk.com/avencoresvk", "users.svg"),
        ]
        buttons = [github_btn, repo_btn]
        col_count = 3
        row, col = 0, 1
        for label, url, icon in social:
            btn = QToolButton()
            btn.setText(label)
            btn.setIcon(get_icon(icon, 24, force_dark=True))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setProperty("style_role", "about_tool")
            btn.setProperty("icon_name", icon)
            btn.setProperty("icon_force_dark", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, u=url: open_target(u))
            grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            buttons.append(btn)
            col += 1
            if col >= col_count:
                row += 1
                col = 0

        vbox.addLayout(grid)
        vbox.addSpacing(8)
        vbox.addWidget(repo_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addSpacing(8)

        def equalize():
            if not buttons:
                return
            try:
                ref = max(b.sizeHint().width() for b in buttons if b.sizeHint().width() > 0)
                for b in buttons:
                    b.setFixedWidth(ref)
            except Exception:
                pass

        back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setProperty("style_role", "theme")
        back_btn.setStyleSheet(self.styles["theme"])
        back_btn.clicked.connect(lambda: self.return_to_main(about))
        vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        if self.stacked_widget:
            self.stacked_widget.addWidget(about)
        self.update_subwindow_styles()
        QTimer.singleShot(150, equalize)
        self.animate_switch(about)

    def check_for_updates(self):
        if self._check_updates_running:
            return
        self._check_updates_running = True

        worker = AppUpdateWorker(self.resource_path)
        worker.signals.update_ready.connect(self.on_app_update_ready, Qt.ConnectionType.QueuedConnection)
        worker.signals.no_update.connect(self.on_app_up_to_date, Qt.ConnectionType.QueuedConnection)
        worker.signals.message.connect(self.on_app_update_message, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(str, str, str)
    def on_app_update_ready(self, local: str, remote: str, url: str):
        self.show_update_available(local, remote, url)
        self._check_updates_running = False

    @Slot(str, str)
    def on_app_up_to_date(self, local: str, remote: str):
        self.show_no_update(local, remote)
        self._check_updates_running = False

    @Slot(str, bool, bool)
    def on_app_update_message(self, msg: str, success: bool, word_wrap: bool):
        self.show_message(msg, success, word_wrap)
        self._check_updates_running = False


# ----------------------------------------------------------------------
# Icon helpers
# ----------------------------------------------------------------------
ICON_CACHE: dict = {}
RENDERER_CACHE: dict = {}


def _tint_pixmap(pix: QPixmap, color: QColor) -> QPixmap:
    if pix.isNull():
        return pix
    tinted = QPixmap(pix.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_icon(file_name: str, size_px: int | None = None, *, force_dark: bool = False, force_white: bool = False) -> QIcon:
    path = resource_path(os.path.join("icons", file_name))
    render_size = size_px or 48
    if force_white:
        tint = QColor("#ffffff")
    elif force_dark or not main_window.dark_theme:
        tint = QColor("#1a1a1a")
    else:
        tint = QColor("#ffffff")

    cache_key = (path, render_size, tint.name())
    cached = ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    renderer = RENDERER_CACHE.get(path)
    if renderer is None:
        renderer = QSvgRenderer(path)
        RENDERER_CACHE[path] = renderer
    pix = QPixmap(render_size, render_size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()

    tinted = _tint_pixmap(pix, tint)
    icon = QIcon(tinted)
    ICON_CACHE[cache_key] = icon
    return icon


def create_icon_label(file_name: str, size: int = 48) -> QLabel:
    icon = get_icon(file_name, size)
    label = QLabel()
    label.setPixmap(icon.pixmap(size, size))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setObjectName("message_emoji")
    label.setProperty("icon_name", file_name)
    return label


def refresh_icons(root_widget=None):
    if root_widget is None:
        root_widget = main_window
    buttons_with_icons = []
    labels_with_icons = []
    for btn in root_widget.findChildren(QAbstractButton):
        name = btn.property("icon_name")
        if name:
            buttons_with_icons.append((
                btn, name, btn.iconSize().width(),
                btn.property("icon_force_dark"), btn.property("icon_force_white")
            ))
    for lbl in root_widget.findChildren(QLabel):
        name = lbl.property("icon_name")
        if name:
            px = lbl.pixmap()
            sz = px.width() if px else 32
            labels_with_icons.append((
                lbl, name, sz,
                lbl.property("icon_force_dark"), lbl.property("icon_force_white")
            ))
    for btn, name, sz, fd, fw in buttons_with_icons:
        btn.setIcon(get_icon(name, sz, force_dark=bool(fd), force_white=bool(fw)))
    for lbl, name, sz, fd, fw in labels_with_icons:
        lbl.setPixmap(get_icon(name, sz, force_dark=bool(fd), force_white=bool(fw)).pixmap(sz, sz))


# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QPushButton:focus { outline: none; }")

    try:
        with open(resource_path("app_info.json"), "r", encoding="utf-8") as vf:
            APP_VERSION = json.load(vf).get("version", APP_VERSION)
    except Exception:
        pass

    icon_path = resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    main_window = MainWindow()
    main_window.stacked_widget = QStackedWidget()
    main_window.language = CURRENT_LANGUAGE
    main_window.setWindowTitle("Goida AI Unlocker")
    main_window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    main_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    main_window.dark_theme = is_system_dark_theme()
    main_window.styles = get_stylesheet(main_window.dark_theme, main_window.language)
    main_window.setStyleSheet(main_window.styles["main"])
    main_window.setWindowIcon(QIcon(icon_path))
    main_window.resource_path = resource_path

    main_container = QWidget()
    main_layout = QVBoxLayout(main_container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    title_bar = DraggableTitleBar(main_window)
    title_bar.setObjectName("titleBar")
    title_bar.setFixedHeight(32)
    main_window.title_bar = title_bar
    title_bar_layout = QHBoxLayout(title_bar)
    title_bar_layout.setContentsMargins(12, 0, 8, 0)
    title_bar_layout.setSpacing(0)

    title_label = QLabel("Goida AI Unlocker")
    title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    title_label.setStyleSheet("QLabel { color: #666666; font-size: 13px; font-weight: bold; background: transparent; }")
    title_bar_layout.addWidget(title_label)
    title_bar_layout.addStretch()

    minimize_button = QPushButton("─")
    minimize_button.setFixedSize(26, 26)
    minimize_button.clicked.connect(main_window.showMinimized)
    minimize_button.setStyleSheet(
        "QPushButton { background: transparent; color: #666666; border: none; font-size: 14px; font-weight: bold; } "
        "QPushButton:hover { color: #2d7dff; }"
    )
    close_button = QPushButton("×")
    close_button.setFixedSize(26, 26)
    close_button.clicked.connect(app.quit)
    close_button.setStyleSheet(
        "QPushButton { background: transparent; color: #666666; border: none; font-size: 18px; font-weight: bold; } "
        "QPushButton:hover { color: #e06c75; }"
    )
    title_bar_layout.addWidget(minimize_button)
    title_bar_layout.addWidget(close_button)
    main_layout.addWidget(title_bar)

    central_widget = QWidget()
    outer_layout = QVBoxLayout(central_widget)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)
    outer_layout.addStretch()

    layout = QVBoxLayout()
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setSpacing(24)
    layout.setContentsMargins(20, 20, 20, 20)
    outer_layout.addLayout(layout)
    outer_layout.addStretch()

    footer_layout = QHBoxLayout()
    footer_layout.setContentsMargins(20, 0, 20, 20)
    footer_layout.setSpacing(0)
    outer_layout.addLayout(footer_layout)

    main_window.resize(640, 640)

    def on_resize(event=None):
        main_window.fix_widget_size(central_widget)
        if main_window.stacked_widget:
            cur = main_window.stacked_widget.currentWidget()
            if cur:
                main_window.fix_widget_size(cur)

    orig_resize = main_window.resizeEvent

    def new_resize(event):
        orig_resize(event)
        on_resize(event)

    main_window.resizeEvent = new_resize

    app_title_label = QLabel()
    app_title_label.setObjectName("main_title")
    app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app_title_label.setTextFormat(Qt.TextFormat.RichText)
    app_title_label.setText(main_window.styles["about_title_html"])
    app_title_label.setStyleSheet(main_window.styles["about_title_style"])
    layout.addWidget(app_title_label)
    main_window.app_title_label = app_title_label

    installed = main_window.hosts_manager.is_installed()
    color = "#43b581" if installed else "#e06c75"
    status_key = "status_installed" if installed else "status_not_installed"
    textinformer = QLabel(tr("unlock_status", status=tr(status_key), color=color))
    textinformer.setTextFormat(Qt.TextFormat.RichText)
    textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    textinformer.setStyleSheet(main_window.styles["label"])
    main_window.textinformer = textinformer

    version_label = QLabel(tr("version_checking"))
    version_label.setTextFormat(Qt.TextFormat.RichText)
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setStyleSheet(main_window.styles["label"])
    main_window.version_label = version_label

    update_date_label = QLabel(tr("update_date_checking"))
    update_date_label.setTextFormat(Qt.TextFormat.RichText)
    update_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text_color = "#ffffff" if main_window.dark_theme else "#1a1a1a"
    update_date_label.setStyleSheet(
        f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
    )
    main_window.update_date_label = update_date_label

    status_container = QWidget()
    status_container.setObjectName("status_block")
    status_vbox = QVBoxLayout(status_container)
    status_vbox.setContentsMargins(16, 12, 16, 12)
    status_vbox.setSpacing(4)
    status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_vbox.addWidget(textinformer)
    status_vbox.addWidget(version_label)
    status_vbox.addWidget(update_date_label)

    light_block = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
    dark_block = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
    status_container.setStyleSheet(dark_block if main_window.dark_theme else light_block)
    main_window.status_container = status_container
    layout.addWidget(status_container)

    install_button = QPushButton(tr("install_button_install"))
    install_button.setIcon(get_icon("settings.svg", 18, force_white=True))
    install_button.setIconSize(QSize(18, 18))
    install_button.setProperty("icon_name", "settings.svg")
    install_button.setProperty("icon_force_white", True)
    install_button.setProperty("style_role", "button1")
    install_button.setProperty("install_mode", "install")
    install_button.setStyleSheet(main_window.styles["button1"])
    main_window.install_button = install_button

    uninstall_button = QPushButton(tr("uninstall_button"))
    uninstall_button.setIcon(get_icon("trash.svg", 18, force_white=True))
    uninstall_button.setIconSize(QSize(18, 18))
    uninstall_button.setProperty("icon_name", "trash.svg")
    uninstall_button.setProperty("icon_force_white", True)
    uninstall_button.setProperty("style_role", "button2")
    uninstall_button.setStyleSheet(main_window.styles["button2"])
    main_window.uninstall_button = uninstall_button

    theme_button = QPushButton(tr("theme_button"))
    theme_button.setIcon(get_icon("sun.svg", 18, force_dark=True))
    theme_button.setIconSize(QSize(18, 18))
    theme_button.setProperty("icon_name", "sun.svg")
    theme_button.setProperty("icon_force_dark", True)
    theme_button.setProperty("style_role", "theme")
    theme_button.setStyleSheet(main_window.styles["theme"])
    main_window.theme_button = theme_button

    language_button = QPushButton()
    language_button.setIcon(get_icon("language.svg", 20, force_dark=True))
    language_button.setIconSize(QSize(20, 20))
    language_button.setProperty("icon_name", "language.svg")
    language_button.setProperty("icon_force_dark", True)
    language_button.setProperty("style_role", "theme")
    language_button.setStyleSheet(
        main_window.styles["theme"] +
        "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
    )
    language_button.setFixedSize(44, 44)
    language_button.setCursor(Qt.CursorShape.PointingHandCursor)
    main_window.language_button = language_button

    donate_button = QPushButton(tr("donate_button"))
    donate_button.setIcon(get_icon("heart.svg", 18, force_dark=True))
    donate_button.setIconSize(QSize(18, 18))
    donate_button.setProperty("icon_name", "heart.svg")
    donate_button.setProperty("icon_force_dark", True)
    donate_button.setProperty("style_role", "theme")
    donate_button.setStyleSheet(main_window.styles["theme"])
    main_window.donate_button = donate_button

    about_button = QPushButton(tr("about_button"))
    about_button.setIcon(get_icon("info.svg", 18, force_dark=True))
    about_button.setIconSize(QSize(18, 18))
    about_button.setProperty("icon_name", "info.svg")
    about_button.setProperty("icon_force_dark", True)
    about_button.setProperty("style_role", "theme")
    about_button.setStyleSheet(main_window.styles["theme"])
    main_window.about_button = about_button

    update_button = QPushButton(tr("update_button"))
    update_button.setIcon(get_icon("refresh.svg", 18, force_dark=True))
    update_button.setIconSize(QSize(18, 18))
    update_button.setProperty("icon_name", "refresh.svg")
    update_button.setProperty("icon_force_dark", True)
    update_button.setProperty("style_role", "theme")
    update_button.setStyleSheet(main_window.styles["theme"])
    main_window.update_button = update_button

    open_hosts_button = QPushButton(tr("open_hosts_button"))
    open_hosts_button.setIcon(get_icon("book-open.svg", 18, force_dark=True))
    open_hosts_button.setIconSize(QSize(18, 18))
    open_hosts_button.setProperty("icon_name", "book-open.svg")
    open_hosts_button.setProperty("icon_force_dark", True)
    open_hosts_button.setProperty("style_role", "theme")
    open_hosts_button.setStyleSheet(main_window.styles["theme"])
    main_window.open_hosts_button = open_hosts_button

    backup_hosts_button = QPushButton(tr("backup_hosts_button"))
    backup_hosts_button.setIcon(get_icon("clock.svg", 18, force_dark=True))
    backup_hosts_button.setIconSize(QSize(18, 18))
    backup_hosts_button.setProperty("icon_name", "clock.svg")
    backup_hosts_button.setProperty("icon_force_dark", True)
    backup_hosts_button.setProperty("style_role", "theme")
    backup_hosts_button.setStyleSheet(main_window.styles["theme"])
    main_window.backup_hosts_button = backup_hosts_button

    install_button.clicked.connect(lambda: main_window.start_installation(install_button.property("install_mode") or "install"))
    uninstall_button.clicked.connect(lambda: main_window.start_installation("uninstall"))
    theme_button.clicked.connect(main_window.switch_theme)
    language_button.clicked.connect(main_window.switch_language)
    donate_button.clicked.connect(main_window.show_donate)
    about_button.clicked.connect(main_window.show_about)
    update_button.clicked.connect(main_window.check_for_updates)
    open_hosts_button.clicked.connect(
        lambda: open_hosts_file(_inline_callback=lambda msg, ok: main_window.show_message(msg, success=ok, word_wrap=True))
    )

    def show_backup_menu():
        menu = QMenu(main_window)
        if main_window.dark_theme:
            menu.setStyleSheet(
                "QMenu { background:#2d333b; color:#f3f6fd; border:1px solid #3c434d; border-radius:10px; padding:6px; }"
                "QMenu::item { padding:6px 16px; border-radius:8px; margin:2px 0; }"
                "QMenu::item:selected { background:#246cf0; color:#ffffff; border-radius:8px; }"
            )
        else:
            menu.setStyleSheet(
                "QMenu { background:#ffffff; color:#1a1a1a; border:1px solid #cfd4db; border-radius:10px; padding:6px; }"
                "QMenu::item { padding:6px 16px; border-radius:8px; margin:2px 0; }"
                "QMenu::item:selected { background:#0078d4; color:#ffffff; border-radius:8px; }"
            )
        act1 = menu.addAction(tr("backup_menu_open_file"))
        act2 = menu.addAction(tr("backup_menu_open_folder"))
        sel = menu.exec(backup_hosts_button.mapToGlobal(backup_hosts_button.rect().bottomLeft()))
        if sel == act1:
            open_latest_hosts_backup_file()
        elif sel == act2:
            open_hosts_backup_folder()

    backup_hosts_button.clicked.connect(show_backup_menu)

    layout.addWidget(install_button)
    layout.addWidget(uninstall_button)
    layout.addWidget(open_hosts_button)
    layout.addWidget(backup_hosts_button)

    controls_hbox = QHBoxLayout()
    controls_hbox.setSpacing(12)
    controls_hbox.addWidget(theme_button)
    controls_hbox.addWidget(donate_button)
    layout.addLayout(controls_hbox)
    layout.addStretch()
    layout.addWidget(update_button)
    layout.addWidget(about_button)

    footer_layout.addWidget(language_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    footer_layout.addStretch()

    main_window.home_page = central_widget
    main_window.title_label = title_label
    if main_window.stacked_widget:
        main_window.stacked_widget.addWidget(central_widget)
    main_layout.addWidget(main_window.stacked_widget)
    main_window.setCentralWidget(main_container)

    main_window.apply_main_texts()
    main_window.check_version_status()
    main_window.show()
    on_resize()
    sys.exit(app.exec())
