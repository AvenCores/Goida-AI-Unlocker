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

# --- Cross-platform helpers ---
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts" if sys.platform == 'win32' else "/etc/hosts"
HOSTS_BACKUP_DIR = os.path.join(os.path.expanduser("~"), ".goida-ai-unlocker", "hosts-backups")
HOSTS_BACKUP_PREFIX = "hosts_backup_"

def open_target(path: str):
    """Кроссплатформенное открытие файла или ссылки."""
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':  # MacOS
            subprocess.call(['open', path])
        else:  # Linux
            subprocess.call(['xdg-open', path])
    except Exception as e:
        print(f"Ошибка открытия {path}: {e}")

# --------------------------------

def _show_open_hosts_error(detail: str, _inline_callback=None):
    lang = str(globals().get("CURRENT_LANGUAGE", "ru")).lower().replace("-", "_")
    if lang.startswith("ru"):
        message = f"Не удалось открыть файл hosts с правами администратора.\n{detail}"
    else:
        message = f"Failed to open the hosts file with administrator privileges.\n{detail}"

    if _inline_callback is not None:
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: _inline_callback(message, False))
        except Exception:
            print(message)
    else:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
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
            None,
            "runas",
            "notepad.exe",
            HOSTS_PATH,
            None,
            1,
        )
        if result > 32:
            return True, None
        return False, "admin_hint_windows"
    except Exception as e:
        print(f"Open error {HOSTS_PATH}: {e}")
        return False, str(e)


def _open_hosts_file_linux_as_admin() -> tuple[bool, str | None]:
    editor_candidates = (
        "gnome-text-editor",
        "gedit",
        "xed",
        "pluma",
        "mousepad",
        "geany",
        "kate",
        "kwrite",
        "featherpad",
        "leafpad",
    )
    display_env = []
    for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        value = os.environ.get(key)
        if value:
            display_env.append(f"{key}={value}")

    if os.geteuid() == 0:
        for editor in editor_candidates:
            editor_path = shutil.which(editor)
            if not editor_path:
                continue
            try:
                subprocess.Popen([editor_path, HOSTS_PATH], start_new_session=True)
                return True, None
            except Exception:
                continue
        try:
            open_target(HOSTS_PATH)
            return True, None
        except Exception as e:
            print(f"Open error {HOSTS_PATH}: {e}")
            return False, str(e)

    launchers = []
    if shutil.which("pkexec"):
        launchers.append("pkexec")
    for su_tool in ("gksudo", "kdesudo"):
        if shutil.which(su_tool):
            launchers.append(su_tool)

    for editor in editor_candidates:
        editor_path = shutil.which(editor)
        if not editor_path:
            continue
        for launcher in launchers:
            try:
                if launcher == "pkexec":
                    command = ["pkexec"]
                    if display_env:
                        command.extend(["env", *display_env])
                    command.extend([editor_path, HOSTS_PATH])
                else:
                    command = [launcher, editor_path, HOSTS_PATH]
                subprocess.Popen(command, start_new_session=True)
                return True, None
            except Exception:
                continue

    return False, "linux_admin_open_unavailable"


def open_hosts_file(_inline_callback=None):
    """Open hosts with a sensible default editor."""
    try:
        if sys.platform == 'win32':
            opened, error_key = _open_hosts_file_windows_as_admin()
        elif sys.platform.startswith('linux'):
            opened, error_key = _open_hosts_file_linux_as_admin()
        else:
            open_target(HOSTS_PATH)
            return

        if opened:
            return

        if error_key == "admin_hint_windows":
            detail = tr("admin_hint_windows")
        elif error_key == "linux_admin_open_unavailable":
            if normalize_language(CURRENT_LANGUAGE) == "ru":
                detail = "Установите pkexec и графический текстовый редактор или запустите приложение от имени root."
            else:
                detail = "Install pkexec and a graphical text editor, or run the app as root."
        else:
            detail = error_key or tr("admin_hint_unix")

        _show_open_hosts_error(detail, _inline_callback=_inline_callback)
    except Exception as e:
        print(f"Open error {HOSTS_PATH}: {e}")
        _show_open_hosts_error(str(e), _inline_callback=_inline_callback)

def get_hosts_backup_dir() -> str:
    return HOSTS_BACKUP_DIR

def _get_hosts_backup_timestamp() -> str:
    return _time.strftime("%Y%m%d_%H%M%S")

def _sanitize_backup_action(action: str) -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in action.strip().lower())
    return cleaned or "manual"

def create_hosts_backup(action: str) -> str | None:
    try:
        with open(HOSTS_PATH, "rb") as src:
            previous_hosts = src.read()
    except Exception as e:
        print(f"Backup read error {HOSTS_PATH}: {e}")
        return None

    backup_dir = get_hosts_backup_dir()
    try:
        os.makedirs(backup_dir, exist_ok=True)
        action_tag = _sanitize_backup_action(action)
        backup_name = f"{HOSTS_BACKUP_PREFIX}{action_tag}_{_get_hosts_backup_timestamp()}_{_time.time_ns() % 1_000_000:06d}.txt"
        backup_path = os.path.join(backup_dir, backup_name)
        created_at = _time.strftime("%Y-%m-%d %H:%M:%S")
        header = (
            "# Goida AI Unlocker hosts backup\n"
            f"# action {action_tag}\n"
            f"# created_at {created_at}\n"
            f"# source {HOSTS_PATH}\n\n"
        ).encode("utf-8")
        with open(backup_path, "wb") as dst:
            dst.write(header)
            dst.write(previous_hosts)
        return backup_path
    except Exception as e:
        print(f"Backup write error {backup_dir}: {e}")
        return None

def get_latest_hosts_backup_file() -> str | None:
    backup_dir = get_hosts_backup_dir()
    if not os.path.isdir(backup_dir):
        return None
    files = []
    for name in os.listdir(backup_dir):
        lower_name = name.lower()
        if lower_name.startswith(HOSTS_BACKUP_PREFIX) and lower_name.endswith(".txt"):
            full_path = os.path.join(backup_dir, name)
            if os.path.isfile(full_path):
                files.append(full_path)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def open_hosts_backup_folder():
    backup_dir = get_hosts_backup_dir()
    os.makedirs(backup_dir, exist_ok=True)
    open_target(backup_dir)

def _show_backup_missing_dialog():
    """Called only after Qt is fully initialised (from __main__ block)."""
    from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
    from PySide6.QtCore import Qt
    app = QApplication.instance()
    parent = app.activeWindow() if app else None
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(tr("backup_missing_title"))
    dialog.setIcon(QMessageBox.Icon.NoIcon)
    dialog.setText(f"<b style='font-size:15px;'>{tr('backup_missing_title')}</b>")
    dialog.setInformativeText(tr("backup_missing_info"))
    dialog.setTextFormat(Qt.TextFormat.RichText)
    dialog.setStandardButtons(
        QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel
    )
    dialog.setDefaultButton(QMessageBox.StandardButton.Open)
    dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)

    open_button = dialog.button(QMessageBox.StandardButton.Open)
    cancel_button = dialog.button(QMessageBox.StandardButton.Cancel)
    if open_button:
        open_button.setText(tr("open_folder"))
        open_button.setObjectName("backupOpenButton")
    if cancel_button:
        cancel_button.setText(tr("cancel"))
        cancel_button.setObjectName("backupCancelButton")
    for label in dialog.findChildren(QLabel):
        if label.text().strip():
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    dark_theme = bool(getattr(parent, "dark_theme", False))
    if dark_theme:
        dialog.setStyleSheet("""
            QMessageBox { background-color: #1f242d; }
            QMessageBox QLabel {
                color: #f3f6fd;
                font-size: 13px;
                max-width: 250px;
                background: transparent;
                border: none;
            }
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
            QMessageBox QLabel {
                color: #1a1a1a;
                font-size: 13px;
                max-width: 250px;
                background: transparent;
                border: none;
            }
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

    result = dialog.exec()
    if result == QMessageBox.StandardButton.Open:
        open_hosts_backup_folder()


def open_latest_hosts_backup_file():
    latest_backup = get_latest_hosts_backup_file()
    if latest_backup and os.path.exists(latest_backup):
        open_target(latest_backup)
    else:
        _show_backup_missing_dialog()

_ADDITIONAL_HOSTS_VERSION_RE = _re.compile(r'# additional_hosts_version\s+(\S+)')
_HOSTS_VERSION_BLOCK_RE = _re.compile(r'version_add\s*=\s*["\']([^"\']+)["\']')
_HOSTS_CONTENT_RE = _re.compile(r'hosts_add\s*=\s*"""(.*?)"""', _re.S)

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect, QStackedWidget, QSizePolicy, QToolButton, QAbstractButton, QGridLayout, QMenu, QMessageBox
    from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QSize, QLocale
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFontMetrics
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    print("Ошибка: библиотека PySide6 не установлена. Пожалуйста, установите ее командой: pip install PySide6")
    sys.exit(1)

from typing import Optional
import json
import textwrap as _tw

ADDITIONAL_HOSTS_URL = "https://raw.githubusercontent.com/AvenCores/Goida-AI-Unlocker/refs/heads/main/additional_hosts.py"
APP_VERSION = "0.0.0"
SUPPORTED_LANGUAGES = ("ru", "en")
CURRENT_LANGUAGE = "ru"

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

_MONTH_NAME_ALIASES = {
    "январь": 0,
    "января": 0,
    "january": 0,
    "февраль": 1,
    "февраля": 1,
    "february": 1,
    "март": 2,
    "марта": 2,
    "march": 2,
    "апрель": 3,
    "апреля": 3,
    "april": 3,
    "май": 4,
    "мая": 4,
    "may": 4,
    "июнь": 5,
    "июня": 5,
    "june": 5,
    "июль": 6,
    "июля": 6,
    "july": 6,
    "август": 7,
    "августа": 7,
    "august": 7,
    "сентябрь": 8,
    "сентября": 8,
    "september": 8,
    "октябрь": 9,
    "октября": 9,
    "october": 9,
    "ноябрь": 10,
    "ноября": 10,
    "november": 10,
    "декабрь": 11,
    "декабря": 11,
    "december": 11,
}

_MONTH_NAME_OUTPUTS = {
    "ru": [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
}

_MONTH_NAME_RE = _re.compile(
    r"\b(" + "|".join(sorted((_re.escape(name) for name in _MONTH_NAME_ALIASES), key=len, reverse=True)) + r")\b",
    _re.IGNORECASE,
)


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


def tr(key: str, *, language: str | None = None, **kwargs) -> str:
    lang = normalize_language(language or CURRENT_LANGUAGE)
    bundle = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    template = bundle.get(key, TRANSLATIONS["ru"].get(key, key))
    return template.format(**kwargs)


def localize_update_date(date_text: str, language: str | None = None) -> str:
    target_language = normalize_language(language or CURRENT_LANGUAGE)
    month_names = _MONTH_NAME_OUTPUTS.get(target_language, _MONTH_NAME_OUTPUTS["en"])

    def replace_month(match):
        month_index = _MONTH_NAME_ALIASES.get(match.group(0).lower())
        if month_index is None:
            return match.group(0)
        return month_names[month_index]

    return _MONTH_NAME_RE.sub(replace_month, date_text)


set_current_language(detect_system_language())

def _safe_remove(path: str, retries: int = 3, delay: float = 0.3):
    for _ in range(retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            _time.sleep(delay)
        except Exception:
            break
    try:
        if os.path.exists(path):
            atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    except Exception:
        pass

def _fetch_remote_additional() -> tuple[str, str]:
    import time as _t
    try:
        raw_txt = urllib.request.urlopen(f"{ADDITIONAL_HOSTS_URL}?t={int(_t.time())}", timeout=10).read().decode("utf-8", errors="ignore")
        ver_match = _HOSTS_VERSION_BLOCK_RE.search(raw_txt)
        hosts_match = _HOSTS_CONTENT_RE.search(raw_txt)
        version = ver_match.group(1) if ver_match else ""
        hosts_block = hosts_match.group(1).strip() if hosts_match else ""
        hosts_block = _tw.dedent(hosts_block)
        if not hosts_block:
            version = ""
        return version, hosts_block
    except Exception:
        return "", ""

def check_installation():
    try:
        with open(HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return "dns.malw.link" in content
    except Exception:
        return False

def _extract_additional_version(text: str) -> str:
    match = _ADDITIONAL_HOSTS_VERSION_RE.search(text)
    return match.group(1) if match else ""

def _get_remote_add_version() -> str:
    ver, _ = _fetch_remote_additional()
    return ver

_URL_CACHE: dict = {}
_URL_CACHE_TTL: float = 300.0
_REMOTE_CACHE_TTL: float = 60.0
_remote_main_line_cache: tuple | None = None
_remote_add_ver_cache: tuple | None = None

def _fetch_url_cached(url: str, timeout: int = 10, add_timestamp: bool = True) -> str:
    # Include add_timestamp flag in the cache key so that callers with
    # different bypass-cache intentions do not share a single entry.
    cache_key = (url, add_timestamp)
    now = _time.time()

    if cache_key in _URL_CACHE:
        cached_time, cached_content = _URL_CACHE[cache_key]
        if now - cached_time < _URL_CACHE_TTL:
            return cached_content

    try:
        full_url = f"{url}?t={int(now)}" if add_timestamp else url
        content = urllib.request.urlopen(full_url, timeout=timeout).read().decode("utf-8", errors="ignore")
        _URL_CACHE[cache_key] = (now, content)
        return content
    except Exception:
        return ""

def _apply_hosts_file(content: str) -> bool:
    """Write *content* to the system hosts file with privilege elevation.

    Returns True on success, False on failure.
    Temporary files are cleaned up in all cases.
    """
    temp_path: str | None = None
    ps_script_path: str | None = None

    try:
        temp_fd, temp_path = tempfile.mkstemp()
        os.close(temp_fd)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        if sys.platform == 'win32':
            # Escape single-quotes that could appear in Windows temp paths.
            safe_src = temp_path.replace("'", "''")
            safe_dst = HOSTS_PATH.replace("'", "''")
            ps_content = f"""
$source = '{safe_src}'
$dest = '{safe_dst}'
Copy-Item -LiteralPath $source -Destination $dest -Force
try {{ Clear-DnsClientCache }} catch {{}}
try {{ ipconfig /flushdns }} catch {{}}
"""
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.ps1', encoding='utf-8') as ps_file:
                ps_file.write(ps_content)
                ps_script_path = ps_file.name

            elevated = False
            # Try UAC elevation first
            try:
                command = [
                    "powershell", "-WindowStyle", "Hidden", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command",
                    f'Start-Process powershell -Verb runAs -WindowStyle Hidden -ArgumentList \'-NoProfile -ExecutionPolicy Bypass -File "{ps_script_path}"\' -Wait'
                ]
                result = subprocess.run(command, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
                elevated = (result.returncode == 0)
            except Exception:
                elevated = False

            # Fallback: maybe already running as admin
            if not elevated:
                try:
                    result2 = subprocess.run(
                        ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-ExecutionPolicy", "Bypass",
                         "-File", ps_script_path],
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=60
                    )
                    elevated = (result2.returncode == 0)
                except Exception:
                    elevated = False

            if not elevated:
                raise PermissionError("Не удалось получить права администратора. Запустите программу от имени Администратора.")

        else:
            flush_cmd = (
                "resolvectl flush-caches 2>/dev/null || "
                "systemd-resolve --flush-caches 2>/dev/null || "
                "/etc/init.d/nscd restart 2>/dev/null || "
                "killall -HUP dnsmasq 2>/dev/null || "
                "true"
            )
            if os.geteuid() == 0:
                shutil.copy(temp_path, HOSTS_PATH)
                os.chmod(HOSTS_PATH, 0o644)
                subprocess.run(flush_cmd, shell=True)
            else:
                # Escape single-quotes in paths for the shell command
                safe_src = temp_path.replace("'", "'\\''")
                safe_dst = HOSTS_PATH.replace("'", "'\\''")
                bash_cmd = f"cp '{safe_src}' '{safe_dst}' && chmod 644 '{safe_dst}' && {flush_cmd}"
                elevated = False

                if shutil.which("pkexec"):
                    try:
                        result = subprocess.run(["pkexec", "bash", "-c", bash_cmd], timeout=120)
                        elevated = (result.returncode == 0)
                    except Exception:
                        elevated = False

                if not elevated and shutil.which("sudo"):
                    try:
                        result = subprocess.run(["sudo", "bash", "-c", bash_cmd], timeout=120)
                        elevated = (result.returncode == 0)
                    except Exception:
                        elevated = False

                if not elevated:
                    for su_tool in ("gksudo", "kdesudo"):
                        if shutil.which(su_tool):
                            try:
                                result = subprocess.run([su_tool, "bash", "-c", bash_cmd], timeout=120)
                                elevated = (result.returncode == 0)
                                if elevated:
                                    break
                            except Exception:
                                continue

                if not elevated:
                    raise PermissionError("Не удалось получить права root. Введите пароль при запросе или запустите программу от имени root.")

        # Brief pause to let the OS flush the file to disk before we re-read it.
        _time.sleep(0.5)
        return True
    except Exception as e:
        print(f"Ошибка: {e}")
        return False
    finally:
        if temp_path:
            _safe_remove(temp_path)
        if ps_script_path:
            _safe_remove(ps_script_path)


def update_hosts_as_admin(action: str = "install") -> bool:
    url = "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts"
    if not create_hosts_backup(action):
        return False
    content = _fetch_url_cached(url)
    add_ver, add_hosts_remote = _fetch_remote_additional()
    if add_hosts_remote:
        extra_block = f"\n# additional_hosts_version {add_ver}\n{add_hosts_remote.strip()}\n"
        content += extra_block
    return _apply_hosts_file(content)

def is_system_dark_theme():
    if sys.platform == 'win32':
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except Exception:
            return False
    else:
        # Linux (попытка определить для GNOME/GTK)
        try:
            out = subprocess.check_output(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return 'dark' in out.lower()
        except Exception:
            return False # Fallback

_STYLESHEET_CACHE = {}

def get_stylesheet(dark, language: str | None = None):
    lang = normalize_language(language or CURRENT_LANGUAGE)
    cache_key = f"{lang}_dark_{dark}"
    if cache_key in _STYLESHEET_CACHE:
        return _STYLESHEET_CACHE[cache_key]
    result = _build_stylesheet(dark, lang)
    _STYLESHEET_CACHE[cache_key] = result
    return result

def _build_stylesheet(dark, language: str):
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
    # Keep an explicit point-sized font here: pixel-sized fonts can leave
    # pointSize() at -1 and spam Qt warnings on QToolButton hover.
    return styles["theme"] + "\nQToolButton { font-size: 10pt; padding: 6px 12px; }"

class DraggableTitleBar(QWidget):
    def __init__(self, main_window: "CustomWindow"):
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


class CustomWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget: Optional[QStackedWidget] = None
        self._current_animation: Optional[QPropertyAnimation] = None
        self.dark_theme = False
        self.styles = {}
        self.title_bar: Optional[QWidget] = None

    def start_system_move(self) -> bool:
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemMove())
        except Exception:
            return False

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

def get_hosts_version_status() -> tuple[str, str, str]:
    global _REMOTE_CACHE_TTL, _remote_main_line_cache, _remote_add_ver_cache

    def _get_remote_add_version_cached() -> str:
        global _remote_add_ver_cache
        now = _time.time()
        if (_remote_add_ver_cache is not None and isinstance(_remote_add_ver_cache, tuple) and now - _remote_add_ver_cache[0] < _REMOTE_CACHE_TTL):
            return _remote_add_ver_cache[1]
        try:
            ver = _get_remote_add_version()
        except Exception:
            ver = ""
        _remote_add_ver_cache = (now, ver)
        return ver

    if not (os.path.exists(HOSTS_PATH) and check_installation()):
        return "not_installed", "#e06c75", ""

    try:
        with open(HOSTS_PATH, "rb") as lf:
            raw_content = lf.read()
            local_line, local_date = _extract_update_line(raw_content)
            text_content = raw_content.decode("utf-8", errors="ignore")
            local_add_ver = _extract_additional_version(text_content)

        remote_line_result = [None]
        remote_add_ver_result = [None]
        remote_date_result = [None]

        def fetch_main():
            now = _time.time()
            # Use the module-level cache for the main hosts line too
            global _remote_main_line_cache
            if (_remote_main_line_cache is not None and isinstance(_remote_main_line_cache, tuple) and now - _remote_main_line_cache[0] < _REMOTE_CACHE_TTL):
                remote_line_result[0], remote_date_result[0] = _remote_main_line_cache[1]
                return
            try:
                remote_url = f"https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts?t={int(now)}"
                data = urllib.request.urlopen(remote_url, timeout=10).read()
                remote_line, remote_date = _extract_update_line(data)
            except Exception:
                remote_line, remote_date = "", ""
            _remote_main_line_cache = (now, (remote_line, remote_date))
            remote_line_result[0] = remote_line
            remote_date_result[0] = remote_date

        def fetch_add():
            remote_add_ver_result[0] = _get_remote_add_version_cached()

        t1 = threading.Thread(target=fetch_main, daemon=True)
        t2 = threading.Thread(target=fetch_add, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        remote_line = remote_line_result[0] or ""
        remote_date = remote_date_result[0] or ""
        remote_add_ver = remote_add_ver_result[0] or ""

        main_match = local_line == remote_line and local_line.startswith("#")
        add_match = (local_add_ver == remote_add_ver) if remote_add_ver else (local_add_ver == "")

        if main_match and add_match:
            return "up_to_date", "#43b581", remote_date
        else:
            return "outdated", "#e06c75", remote_date
    except Exception:
        return "outdated", "#e06c75", ""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QPushButton:focus { outline: none; }")

    def resource_path(relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    ICON_CACHE = {}
    RENDERER_CACHE = {}

    def _tint_pixmap(pix: QPixmap, color: QColor) -> QPixmap:
        if pix.isNull(): return pix
        tinted = QPixmap(pix.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def get_icon(file_name: str, size_px: int | None = None, *, force_dark: bool = False, force_white: bool = False) -> QIcon:
        path = resource_path(os.path.join("icons", file_name))
        render_size = size_px or 48
        if force_white: tint = QColor("#ffffff")
        elif force_dark or (not main_window.dark_theme): tint = QColor("#1a1a1a")
        else: tint = QColor("#ffffff")

        cache_key = (path, render_size, tint.name())
        cached_icon = ICON_CACHE.get(cache_key)
        if cached_icon is not None: return cached_icon

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
        if root_widget is None: root_widget = main_window
        buttons_with_icons = []
        labels_with_icons = []
        for btn in root_widget.findChildren(QAbstractButton):
            name = btn.property("icon_name")
            if name: buttons_with_icons.append((btn, name, btn.property("icon_force_dark"), btn.property("icon_force_white")))
        for lbl in root_widget.findChildren(QLabel):
            name = lbl.property("icon_name")
            if name:
                pixmap = lbl.pixmap()
                size = pixmap.width() if pixmap else 32
                labels_with_icons.append((lbl, name, size, lbl.property("icon_force_dark"), lbl.property("icon_force_white")))
        for btn, name, force_dark, force_white in buttons_with_icons:
            btn.setIcon(get_icon(name, btn.iconSize().width(), force_dark=bool(force_dark), force_white=bool(force_white)))
        for lbl, name, size, force_dark, force_white in labels_with_icons:
            lbl.setPixmap(get_icon(name, size, force_dark=bool(force_dark), force_white=bool(force_white)).pixmap(size, size))

    try:
        with open(resource_path("app_info.json"), "r", encoding="utf-8") as _vf:
            APP_VERSION = json.load(_vf).get("version", APP_VERSION)
    except Exception:
        pass

    icon_path = resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    main_window = CustomWindow()
    main_window.stacked_widget = QStackedWidget()
    main_window.language = CURRENT_LANGUAGE
    main_window.setWindowTitle("Goida AI Unlocker")
    main_window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    main_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    main_window.dark_theme = is_system_dark_theme()
    main_window.styles = get_stylesheet(main_window.dark_theme, main_window.language)
    main_window.setStyleSheet(main_window.styles["main"])
    main_window.setWindowIcon(QIcon(icon_path))

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
    minimize_button.setStyleSheet("QPushButton { background: transparent; color: #666666; border: none; font-size: 14px; font-weight: bold; } QPushButton:hover { color: #2d7dff; }")
    close_button = QPushButton("×")
    close_button.setFixedSize(26, 26)
    close_button.clicked.connect(app.quit)
    close_button.setStyleSheet("QPushButton { background: transparent; color: #666666; border: none; font-size: 18px; font-weight: bold; } QPushButton:hover { color: #e06c75; }")
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

    def fix_widget_size(w):
        w.setMinimumSize(main_window.width(), main_window.height() - title_bar.height())
        w.setMaximumSize(main_window.width(), main_window.height() - title_bar.height())

    main_window.resize(640, 640)

    def on_main_window_resize(event=None):
        fix_widget_size(central_widget)
        if main_window.stacked_widget:
            current = main_window.stacked_widget.currentWidget()
            if current: fix_widget_size(current)

    _original_resize_event = main_window.resizeEvent

    def new_resize_event(event):
        _original_resize_event(event)
        on_main_window_resize(event)

    main_window.resizeEvent = new_resize_event

    app_title_label = QLabel()
    app_title_label.setObjectName("main_title")
    app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app_title_label.setTextFormat(Qt.TextFormat.RichText)
    app_title_label.setText(main_window.styles["about_title_html"])
    app_title_label.setStyleSheet(main_window.styles["about_title_style"])
    layout.addWidget(app_title_label)

    installed = check_installation()
    color = "#43b581" if installed else "#e06c75"
    status_key = "status_installed" if installed else "status_not_installed"
    textinformer = QLabel(tr("unlock_status", status=tr(status_key), color=color))
    textinformer.setTextFormat(Qt.TextFormat.RichText)
    textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    textinformer.setStyleSheet(main_window.styles["label"])

    version_label = QLabel(tr("version_checking"))
    version_label.setTextFormat(Qt.TextFormat.RichText)
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setStyleSheet(main_window.styles["label"])

    update_date_label = QLabel(tr("update_date_checking"))
    update_date_label.setTextFormat(Qt.TextFormat.RichText)
    update_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text_color = "#ffffff" if main_window.dark_theme else "#1a1a1a"
    update_date_label.setStyleSheet(f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;")

    status_container = QWidget()
    status_container.setObjectName("status_block")
    status_vbox = QVBoxLayout(status_container)
    status_vbox.setContentsMargins(16, 12, 16, 12)
    status_vbox.setSpacing(4)
    status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_vbox.addWidget(textinformer)
    status_vbox.addWidget(version_label)
    status_vbox.addWidget(update_date_label)

    _light_block = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
    _dark_block = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
    status_container.setStyleSheet(_dark_block if main_window.dark_theme else _light_block)
    layout.addWidget(status_container)

    button = QPushButton(tr("install_button_install"))
    button.setIcon(get_icon("settings.svg", 18, force_white=True))
    button.setIconSize(QSize(18, 18))
    button.setProperty("icon_name", "settings.svg")
    button.setProperty("icon_force_white", True)
    button.setProperty("style_role", "button1")
    button.setProperty("install_mode", "install")
    button.setStyleSheet(main_window.styles["button1"])
    button2 = QPushButton(tr("uninstall_button"))
    button2.setIcon(get_icon("trash.svg", 18, force_white=True))
    button2.setIconSize(QSize(18, 18))
    button2.setProperty("icon_name", "trash.svg")
    button2.setProperty("icon_force_white", True)
    button2.setProperty("style_role", "button2")
    button2.setStyleSheet(main_window.styles["button2"])
    theme_button = QPushButton(tr("theme_button"))
    theme_button.setIcon(get_icon("sun.svg", 18, force_dark=True))
    theme_button.setIconSize(QSize(18, 18))
    theme_button.setProperty("icon_name", "sun.svg")
    theme_button.setProperty("icon_force_dark", True)
    theme_button.setProperty("style_role", "theme")
    theme_button.setStyleSheet(main_window.styles["theme"])
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
    donate_button = QPushButton(tr("donate_button"))
    donate_button.setIcon(get_icon("heart.svg", 18, force_dark=True))
    donate_button.setIconSize(QSize(18, 18))
    donate_button.setProperty("icon_name", "heart.svg")
    donate_button.setProperty("icon_force_dark", True)
    donate_button.setProperty("style_role", "theme")
    donate_button.setStyleSheet(main_window.styles["theme"])
    about_button = QPushButton(tr("about_button"))
    about_button.setIcon(get_icon("info.svg", 18, force_dark=True))
    about_button.setIconSize(QSize(18, 18))
    about_button.setProperty("icon_name", "info.svg")
    about_button.setProperty("icon_force_dark", True)
    about_button.setProperty("style_role", "theme")
    about_button.setStyleSheet(main_window.styles["theme"])

    update_button = QPushButton(tr("update_button"))
    update_button.setIcon(get_icon("refresh.svg", 18, force_dark=True))
    update_button.setIconSize(QSize(18, 18))
    update_button.setProperty("icon_name", "refresh.svg")
    update_button.setProperty("icon_force_dark", True)
    update_button.setProperty("style_role", "theme")
    update_button.setStyleSheet(main_window.styles["theme"])
    update_button.clicked.connect(lambda: check_for_updates())
    open_hosts_button = QPushButton(tr("open_hosts_button"))
    open_hosts_button.setIcon(get_icon("book-open.svg", 18, force_dark=True))
    open_hosts_button.setIconSize(QSize(18, 18))
    open_hosts_button.setProperty("icon_name", "book-open.svg")
    open_hosts_button.setProperty("icon_force_dark", True)
    open_hosts_button.setProperty("style_role", "theme")
    open_hosts_button.setStyleSheet(main_window.styles["theme"])
    open_hosts_button.clicked.connect(lambda: open_hosts_file(_inline_callback=lambda msg, ok: show_message_and_return(msg, ok, word_wrap=True)))
    backup_hosts_button = QPushButton(tr("backup_hosts_button"))
    backup_hosts_button.setIcon(get_icon("clock.svg", 18, force_dark=True))
    backup_hosts_button.setIconSize(QSize(18, 18))
    backup_hosts_button.setProperty("icon_name", "clock.svg")
    backup_hosts_button.setProperty("icon_force_dark", True)
    backup_hosts_button.setProperty("style_role", "theme")
    backup_hosts_button.setStyleSheet(main_window.styles["theme"])

    def show_hosts_backup_menu():
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
        open_file_action = menu.addAction(tr("backup_menu_open_file"))
        open_folder_action = menu.addAction(tr("backup_menu_open_folder"))
        selected_action = menu.exec(backup_hosts_button.mapToGlobal(backup_hosts_button.rect().bottomLeft()))
        if selected_action == open_file_action:
            open_latest_hosts_backup_file()
        elif selected_action == open_folder_action:
            open_hosts_backup_folder()

    backup_hosts_button.clicked.connect(show_hosts_backup_menu)

    def refresh_status_container_style():
        _light_block = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
        _dark_block = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
        status_container.setStyleSheet(_dark_block if main_window.dark_theme else _light_block)

    def set_install_button_mode(mode: str):
        """Set the install button to 'update' or 'install' mode."""
        effective_mode = "update" if mode == "update" else "install"
        button.setProperty("install_mode", effective_mode)
        button.setText(tr("install_button_update" if effective_mode == "update" else "install_button_install"))

    def update_installation_status_label():
        is_installed = check_installation()
        current_color = "#43b581" if is_installed else "#e06c75"
        current_status_key = "status_installed" if is_installed else "status_not_installed"
        textinformer.setText(tr("unlock_status", status=tr(current_status_key), color=current_color))

    def apply_hosts_version_status(status_key: str | None = None, color: str | None = None, update_date: str | None = None):
        if status_key is not None:
            version_label.setProperty("status_key", status_key)
        else:
            status_key = version_label.property("status_key") or "not_installed"

        if color is not None:
            version_label.setProperty("status_color", color)
        else:
            color = version_label.property("status_color") or "#e06c75"

        if update_date is not None:
            update_date_label.setProperty("update_date_value", update_date)
        else:
            update_date = update_date_label.property("update_date_value") or ""

        version_label.setText(
            tr(
                "hosts_version_status",
                color=color,
                status=tr(f"hosts_status_{status_key}"),
            )
        )
        if update_date:
            update_date_label.setText(tr("hosts_update_date", date=localize_update_date(update_date)))
        else:
            update_date_label.setText(tr("hosts_update_date_unknown"))
        set_install_button_mode("update" if status_key == "outdated" else "install")

    def apply_main_texts():
        title_label.setText("Goida AI Unlocker")
        app_title_label.setText(main_window.styles["about_title_html"])
        update_installation_status_label()

        stored_status_key = version_label.property("status_key")
        if stored_status_key:
            apply_hosts_version_status()
        else:
            version_label.setText(tr("version_checking"))
            update_date_label.setText(tr("update_date_checking"))
            set_install_button_mode(button.property("install_mode") or "install")

        button2.setText(tr("uninstall_button"))
        theme_button.setText(tr("theme_button"))
        language_button.setText("")
        language_button.setToolTip(tr("language_button"))
        language_button.setStatusTip(tr("language_button"))
        language_button.setAccessibleName(tr("language_button"))
        donate_button.setText(tr("donate_button"))
        about_button.setText(tr("about_button"))
        update_button.setText(tr("update_button"))
        open_hosts_button.setText(tr("open_hosts_button"))
        backup_hosts_button.setText(tr("backup_hosts_button"))

    def apply_theme_styles():
        main_window.styles = get_stylesheet(main_window.dark_theme, main_window.language)
        main_window.setStyleSheet(main_window.styles["main"])
        textinformer.setStyleSheet(main_window.styles["label"])
        app_title_label.setStyleSheet(main_window.styles["about_title_style"])
        version_label.setStyleSheet(main_window.styles["label"])
        text_color = "#ffffff" if main_window.dark_theme else "#1a1a1a"
        update_date_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
        )
        button.setStyleSheet(main_window.styles["button1"])
        button2.setStyleSheet(main_window.styles["button2"])
        theme_button.setStyleSheet(main_window.styles["theme"])
        language_button.setStyleSheet(
            main_window.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        donate_button.setStyleSheet(main_window.styles["theme"])
        open_hosts_button.setStyleSheet(main_window.styles["theme"])
        backup_hosts_button.setStyleSheet(main_window.styles["theme"])
        update_button.setStyleSheet(main_window.styles["theme"])
        about_button.setStyleSheet(main_window.styles["theme"])
        refresh_status_container_style()
        update_subwindow_styles()
        refresh_icons()

    def restore_original_hosts() -> bool:
        if not create_hosts_backup("uninstall"):
            return False

        default_hosts = '127.0.0.1       localhost\n::1             localhost\n'
        if sys.platform == 'win32':
            default_hosts = (
                '# Copyright (c) 1993-2009 Microsoft Corp.\n#\n'
                '# This is a sample HOSTS file used by Microsoft TCP/IP for Windows.\n#\n'
                '# This file contains the mappings of IP addresses to host names. Each\n'
                '# entry should be kept on an individual line. The IP address should\n'
                '# be placed in the first column followed by the corresponding host name.\n'
                '# The IP address and the host name should be separated by at least one\n# space.\n#\n'
                '# Additionally, comments (such as these) may be inserted on individual\n'
                '# lines or following the machine name denoted by a "#" symbol.\n#\n'
                '# For example:\n#\n#      102.54.94.97     rhino.acme.com          # source server\n'
                '#       38.25.63.10     x.acme.com              # x client host\n\n'
                '# localhost name resolution is handled within DNS itself.\n'
                '#   127.0.0.1       localhost\n#   ::1             localhost'
            )
        return _apply_hosts_file(default_hosts)

    if main_window.stacked_widget: main_window.stacked_widget.addWidget(central_widget)
    main_layout.addWidget(main_window.stacked_widget)
    main_window.setCentralWidget(main_container)

    def animate_widget_switch(new_widget, on_finish=None):
        if not main_window.stacked_widget: return
        current_widget = main_window.stacked_widget.currentWidget()
        if not current_widget or current_widget == new_widget:
            main_window.stacked_widget.setCurrentWidget(new_widget)
            if on_finish: on_finish()
            return
        fix_widget_size(new_widget)
        effect = QGraphicsOpacityEffect(current_widget)
        current_widget.setGraphicsEffect(effect)
        fade_out = QPropertyAnimation(effect, b"opacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        def after_fade_out():
            if main_window.stacked_widget is not None:
                main_window.stacked_widget.setCurrentWidget(new_widget)
                effect2 = QGraphicsOpacityEffect(new_widget)
                new_widget.setGraphicsEffect(effect2)
                fade_in = QPropertyAnimation(effect2, b"opacity")
                fade_in.setDuration(180)
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)
                def clear_anim():
                    new_widget.setGraphicsEffect(None)
                    main_window._current_animation = None
                fade_in.finished.connect(clear_anim)
                if on_finish: fade_in.finished.connect(on_finish)
                main_window._current_animation = fade_in
                fade_in.start()
        fade_out.finished.connect(after_fade_out)
        main_window._current_animation = fade_out
        fade_out.start()

    def update_subwindow_styles():
        if not main_window.stacked_widget: return
        buttons_to_update = []
        tool_buttons_to_update = []
        labels_to_update = []
        for i in range(main_window.stacked_widget.count()):
            w = main_window.stacked_widget.widget(i)
            if w is central_widget: continue
            w.setStyleSheet(main_window.styles["main"])
            for child in w.findChildren(QPushButton):
                role = child.property("style_role")
                if role == "button2":
                    buttons_to_update.append((child, main_window.styles["button2"]))
                elif role == "theme":
                    buttons_to_update.append((child, main_window.styles["theme"]))
                else:
                    buttons_to_update.append((child, main_window.styles["button1"]))
            for child in w.findChildren(QToolButton):
                if child.property("style_role") == "about_tool":
                    tool_buttons_to_update.append((child, get_about_toolbutton_style(main_window.styles)))
            for child in w.findChildren(QLabel):
                obj_name = child.objectName()
                if obj_name == "about_title": labels_to_update.append((child, "title", main_window.styles))
                elif obj_name == "about_info": labels_to_update.append((child, "info", main_window.styles))
                elif obj_name == "about_link": labels_to_update.append((child, "link", main_window.styles))
                elif obj_name == "message_emoji": continue
                else: labels_to_update.append((child, "label", main_window.styles))
        for btn, style in buttons_to_update: btn.setStyleSheet(style)
        for btn, style in tool_buttons_to_update: btn.setStyleSheet(style)
        for lbl, label_type, styles in labels_to_update:
            if label_type == "title":
                lbl.setText(styles["about_title_html"])
                lbl.setStyleSheet(styles["about_title_style"])
            elif label_type == "info": lbl.setText(styles["about_info_html"])
            elif label_type == "link": lbl.setText(styles["about_link_html"])
            else: lbl.setStyleSheet(styles["label"])
        for i in range(main_window.stacked_widget.count()):
            w = main_window.stacked_widget.widget(i)
            if w is not central_widget: refresh_icons(w)

    def show_message_and_return(msg, success=True, animate=True, word_wrap=False):
        message_widget = QWidget()
        vbox = QVBoxLayout(message_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(message_widget)
        card_container = QWidget()
        card_container.setObjectName("msg_card")
        card_container.setMinimumWidth(240)
        card_container.setMaximumWidth(380)
        card_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)
        icon_file = "check-circle.svg" if success else "x-circle.svg"
        emoji_label = create_icon_label(icon_file, size=48)
        card_layout.addWidget(emoji_label)
        if word_wrap:
            lines = [l for l in msg.split("\n") if l.strip()]
            for line in lines:
                block = QWidget()
                block.setStyleSheet("background:#363d46; border-radius:8px;")
                block_layout = QVBoxLayout(block)
                block_layout.setContentsMargins(12, 10, 12, 10)
                block_layout.setSpacing(0)
                lbl = QLabel(line)
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                lbl.setStyleSheet("border: none; background: transparent;")
                block_layout.addWidget(lbl)
                card_layout.addWidget(block)
        else:
            for line in msg.split("\n"):
                if not line.strip(): continue
                lbl = QLabel(line)
                lbl.setWordWrap(False)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                card_layout.addWidget(lbl)
        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)
        vbox.addWidget(card_container)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(message_widget)
        update_subwindow_styles()
        if animate and main_window.stacked_widget: animate_widget_switch(message_widget)
        elif main_window.stacked_widget: main_window.stacked_widget.setCurrentWidget(message_widget)
        def return_to_main():
            def do_remove_message_widget():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(message_widget)
                message_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_message_widget)
        ok_btn.clicked.connect(return_to_main)

    def show_update_available(local_version: str, latest_version: str, dl_url: str):
        update_widget = QWidget()
        vbox = QVBoxLayout(update_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(update_widget)
        card_container = QWidget()
        card_container.setObjectName("update_card")
        card_container.setMinimumWidth(240)
        card_container.setMaximumWidth(600)
        card_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)
        emoji_label = create_icon_label("alert.svg", size=48)
        emoji_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        emoji_label.setFixedHeight(48)
        card_layout.addWidget(emoji_label)
        installed_lbl = QLabel(tr("installed_version", version=local_version))
        installed_lbl.setTextFormat(Qt.TextFormat.RichText)
        installed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(installed_lbl)
        latest_lbl = QLabel(tr("latest_version", version=latest_version))
        latest_lbl.setTextFormat(Qt.TextFormat.RichText)
        latest_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(latest_lbl)
        label = QLabel(tr("new_version_available"))
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(label)
        download_btn = QPushButton(tr("download"))
        download_btn.setProperty("style_role", "button1")
        card_layout.addWidget(download_btn)
        ok_btn2 = QPushButton(tr("ok"))
        ok_btn2.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn2)
        vbox.addWidget(card_container)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(update_widget)
        update_subwindow_styles()
        animate_widget_switch(update_widget)
        download_btn.clicked.connect(lambda: open_target(dl_url))
        def return_to_main2():
            def do_remove_update_widget():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(update_widget)
                update_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_update_widget)
        ok_btn2.clicked.connect(return_to_main2)

    def show_no_update_needed(local_version: str, latest_version: str):
        done_widget = QWidget()
        vbox = QVBoxLayout(done_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(done_widget)
        card_container = QWidget()
        card_container.setObjectName("update_card")
        card_container.setMinimumWidth(240)
        card_container.setMaximumWidth(600)
        card_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)
        emoji_label = create_icon_label("check-circle.svg", size=40)
        emoji_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        emoji_label.setFixedHeight(48)
        emoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji_label.setObjectName("message_emoji")
        emoji_label.setStyleSheet("font-size: 48px;")
        card_layout.addWidget(emoji_label)
        installed_lbl = QLabel(tr("installed_version", version=local_version))
        installed_lbl.setTextFormat(Qt.TextFormat.RichText)
        installed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(installed_lbl)
        latest_lbl = QLabel(tr("latest_version_padded", version=latest_version))
        latest_lbl.setTextFormat(Qt.TextFormat.RichText)
        latest_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(latest_lbl)
        info_label = QLabel(tr("latest_version_installed"))
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(False)
        card_layout.addWidget(info_label)
        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)
        vbox.addWidget(card_container)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(done_widget)
        update_subwindow_styles()
        animate_widget_switch(done_widget)
        def return_to_main():
            def do_remove():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(done_widget)
                done_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove)
        ok_btn.clicked.connect(return_to_main)

    def check_for_updates():
        import json as _json
        if getattr(check_for_updates, "_running", False): return
        setattr(check_for_updates, "_running", True)
        def worker():
            try:
                with open(resource_path("app_info.json"), "r", encoding="utf-8") as _f:
                    _local = _json.load(_f)
                local_ver = _local.get("version", "0.0.0")
                remote_url = _local.get("update_info_url")
                if not remote_url: raise RuntimeError(tr("update_url_missing"))
                remote_content = _fetch_url_cached(remote_url)
                if not remote_content: raise RuntimeError(tr("update_info_unavailable"))
                remote_data = _json.loads(remote_content)
                remote_ver = remote_data.get("version", "0.0.0")
                download_url = remote_data.get("download_url", "https://github.com/AvenCores/Goida-AI-Unlocker")
                def _parse(v): return tuple(int(x) for x in v.strip("vV").split(".") if x.isdigit())
                newer = _parse(remote_ver) > _parse(local_ver)
                if newer: QTimer.singleShot(0, main_window, lambda lv=local_ver, rv=remote_ver, u=download_url: show_update_available(lv, rv, u))
                else: QTimer.singleShot(0, main_window, lambda lv=local_ver, rv=remote_ver: show_no_update_needed(lv, rv))
            except Exception as e:
                err = f"{tr('updates_check_failed')}\n{e}"
                QTimer.singleShot(0, main_window, lambda m=err: show_message_and_return(m, success=False, animate=True))
            finally: setattr(check_for_updates, "_running", False)
        threading.Thread(target=worker, daemon=True).start()

    def start_installation(action: str = "install"):
        processing_widget = QWidget()
        vbox = QVBoxLayout(processing_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(processing_widget)
        card_container = QWidget()
        card_container.setObjectName("wait_card")
        card_container.setMinimumWidth(220)
        card_container.setMaximumWidth(600)
        card_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)
        emoji_label = create_icon_label("clock.svg", size=48)
        card_layout.addWidget(emoji_label)
        if action == "install":
            msg_text = tr("processing_install")
        elif action == "update":
            msg_text = tr("processing_update")
        else:
            msg_text = tr("processing_uninstall")
        for line in msg_text.split("\n"):
            if not line.strip(): continue
            lbl = QLabel(line)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(False)
            card_layout.addWidget(lbl)
        vbox.addWidget(card_container)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(processing_widget)
        update_subwindow_styles()
        animate_widget_switch(processing_widget)
        def update_status_label():
            update_installation_status_label()
            update_version_label()
        def finish(ok_result):
            if ok_result:
                if action == "install":
                    success_msg = tr("install_success")
                elif action == "update":
                    success_msg = tr("update_success")
                else:
                    success_msg = tr("uninstall_success")
                show_message_and_return(success_msg, success=True, animate=True)
            else:
                admin_hint = tr("admin_hint_windows") if sys.platform == 'win32' else tr("admin_hint_unix")
                if action == "install":
                    error_msg = tr("install_error", hint=admin_hint)
                elif action == "update":
                    error_msg = tr("update_error", hint=admin_hint)
                else:
                    error_msg = tr("uninstall_error", hint=admin_hint)
                show_message_and_return(error_msg, success=False, animate=True)
            def remove_processing():
                if main_window.stacked_widget and processing_widget in [main_window.stacked_widget.widget(i) for i in range(main_window.stacked_widget.count())]:
                    main_window.stacked_widget.removeWidget(processing_widget)
                processing_widget.deleteLater()
            QTimer.singleShot(400, remove_processing)
            QTimer.singleShot(500, update_status_label)
        def worker():
            if action in ("install", "update"): result = update_hosts_as_admin()
            else: result = restore_original_hosts()
            QTimer.singleShot(0, main_window, lambda res=result: finish(res))
        threading.Thread(target=worker, daemon=True).start()

    def on_install_click():
        start_installation(button.property("install_mode") or "install")
    def on_uninstall_click(): start_installation("uninstall")
    button.clicked.connect(on_install_click)
    button2.clicked.connect(on_uninstall_click)

    def switch_theme():
        if main_window.is_animating: return
        main_window.is_animating = True
        animation_steps, time_interval = 15, 20
        def fade_out(step=1.0):
            try:
                if step >= 0:
                    main_window.setWindowOpacity(step)
                    QTimer.singleShot(time_interval, lambda: fade_out(step - 1.0 / animation_steps))
                else:
                    main_window.setWindowOpacity(0)
                    main_window.setUpdatesEnabled(False)
                    main_window.dark_theme = not main_window.dark_theme
                    apply_theme_styles()
                    apply_main_texts()
                    main_window.setUpdatesEnabled(True)
                    fade_in()
            except Exception:
                main_window.setWindowOpacity(1.0)
                main_window.is_animating = False
        def fade_in(step=0.0):
            try:
                if step <= 1.0:
                    main_window.setWindowOpacity(step)
                    QTimer.singleShot(time_interval, lambda: fade_in(step + 1.0 / animation_steps))
                else:
                    main_window.setWindowOpacity(1.0)
                    main_window.is_animating = False
            except Exception:
                main_window.setWindowOpacity(1.0)
                main_window.is_animating = False
        fade_out()
    theme_button.clicked.connect(switch_theme)

    def switch_language():
        global _STYLESHEET_CACHE
        next_language = "en" if main_window.language == "ru" else "ru"
        main_window.language = set_current_language(next_language)
        _STYLESHEET_CACHE.clear()
        apply_theme_styles()
        apply_main_texts()

    language_button.clicked.connect(switch_language)

    def show_donate_window():
        donate_widget = QWidget()
        donate_layout = QVBoxLayout(donate_widget)
        donate_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        donate_layout.setSpacing(24)
        donate_layout.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(donate_widget)
        card_container = QWidget()
        card_container.setObjectName("donate_card")
        card_container.setMaximumWidth(380)
        card_container.setMinimumWidth(240)
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        title_lbl = QLabel(tr("donate_title"))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size:22px; font-weight:600;")
        card_layout.addWidget(title_lbl)
        card = "2202 2050 1464 4675"
        card_lbl = QLabel(f"ㅤSBER: <b>{card}</b>ㅤ")
        card_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lbl.setStyleSheet("font-size:16px;")
        card_layout.addWidget(card_lbl)
        copy_btn = QPushButton(tr("copy_card"))
        copy_btn.setProperty("style_role", "button1")
        card_layout.addWidget(copy_btn)
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)
        donate_layout.addWidget(card_container)
        back_button = QPushButton(f"  {tr('back_to_menu')}  ")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.setProperty("style_role", "theme")
        back_button.setStyleSheet(main_window.styles["theme"])
        donate_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignCenter)
        copy_btn.setStyleSheet(main_window.styles["button1"])
        def copy_card():
            QApplication.clipboard().setText(card)
            if getattr(copy_btn, "_animating", False): return
            setattr(copy_btn, "_animating", True)
            original_text = tr("copy_card")
            success_text = tr("copied")
            def fade_out_then_change():
                effect = QGraphicsOpacityEffect(copy_btn)
                copy_btn.setGraphicsEffect(effect)
                fade_out = QPropertyAnimation(effect, b"opacity", copy_btn)
                fade_out.setDuration(150)
                fade_out.setStartValue(1.0)
                fade_out.setEndValue(0.0)
                def change_text_and_fade_in():
                    copy_btn.setText(success_text)
                    fade_in = QPropertyAnimation(effect, b"opacity", copy_btn)
                    fade_in.setDuration(150)
                    fade_in.setStartValue(0.0)
                    fade_in.setEndValue(1.0)
                    def hold_then_revert():
                        def fade_out2():
                            fade_out_back = QPropertyAnimation(effect, b"opacity", copy_btn)
                            fade_out_back.setDuration(150)
                            fade_out_back.setStartValue(1.0)
                            fade_out_back.setEndValue(0.0)
                            def reset_text():
                                copy_btn.setText(original_text)
                                fade_in_back = QPropertyAnimation(effect, b"opacity", copy_btn)
                                fade_in_back.setDuration(150)
                                fade_in_back.setStartValue(0.0)
                                fade_in_back.setEndValue(1.0)
                                def clear():
                                    copy_btn.setGraphicsEffect(None)
                                    setattr(copy_btn, "_animating", False)
                                fade_in_back.finished.connect(clear)
                                fade_in_back.start()
                            fade_out_back.finished.connect(reset_text)
                            fade_out_back.start()
                        QTimer.singleShot(1200, fade_out2)
                    fade_in.finished.connect(hold_then_revert)
                    fade_in.start()
                fade_out.finished.connect(change_text_and_fade_in)
                fade_out.start()
            fade_out_then_change()
        def return_to_main():
            def do_remove_donate_widget():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(donate_widget)
                donate_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_donate_widget)
        copy_btn.clicked.connect(copy_card)
        back_button.clicked.connect(return_to_main)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(donate_widget)
        update_subwindow_styles()
        animate_widget_switch(donate_widget)
    donate_button.clicked.connect(show_donate_window)

    layout.addWidget(button)
    layout.addWidget(button2)
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

    def show_about_window():
        about_widget = QWidget()
        vbox = QVBoxLayout(about_widget)
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
        github_btn.setStyleSheet(get_about_toolbutton_style(main_window.styles))
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
        repo_btn.setStyleSheet(get_about_toolbutton_style(main_window.styles))
        repo_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(github_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
        social_buttons = [("Telegram", "https://t.me/avencoresyt", "send.svg"), ("YouTube", "https://youtube.com/@avencores", "play.svg"), ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"), ("Dzen", "https://dzen.ru/avencores", "book-open.svg"), ("VK", "https://vk.com/avencoresvk", "users.svg")]
        about_buttons = [github_btn, repo_btn]
        col_count = 3
        row = 0
        col = 1
        for label, url, icon_file in social_buttons:
            btn = QToolButton()
            btn.setText(label)
            btn.setIcon(get_icon(icon_file, 24, force_dark=True))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setProperty("style_role", "about_tool")
            btn.setProperty("icon_name", icon_file)
            btn.setProperty("icon_force_dark", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(get_about_toolbutton_style(main_window.styles))
            btn.clicked.connect(lambda checked=False, u=url: open_target(u))
            grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            about_buttons.append(btn)
            col += 1
            if col >= col_count:
                row += 1
                col = 0
        vbox.addLayout(grid)
        vbox.addSpacing(8)
        vbox.addWidget(repo_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addSpacing(8)
        def _equalize_about_button_widths():
            if not about_buttons: return
            # Only use sizeHint() — it's reliable after the widget is shown.
            # Avoid QFontMetrics on not-yet-shown widgets: that triggers
            # "QFont::setPointSize: Point size <= 0" warnings.
            try:
                ref_w = max(b.sizeHint().width() for b in about_buttons if b.sizeHint().width() > 0)
                for b in about_buttons:
                    b.setFixedWidth(ref_w)
            except (ValueError, Exception):
                pass
        back_button = QPushButton(f"  {tr('back_to_menu')}  ")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.setProperty("style_role", "theme")
        back_button.setStyleSheet(main_window.styles["theme"])
        def return_to_main():
            def do_remove_about_widget():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(about_widget)
                about_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_about_widget)
        back_button.clicked.connect(return_to_main)
        vbox.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignCenter)
        if main_window.stacked_widget: main_window.stacked_widget.addWidget(about_widget)
        update_subwindow_styles()
        QTimer.singleShot(150, lambda: _equalize_about_button_widths())
        animate_widget_switch(about_widget)
    about_button.clicked.connect(show_about_window)

    def update_version_label():
        now_ts = _time.time()
        last_run = getattr(update_version_label, "_last_run", 0.0)
        if getattr(update_version_label, "_running", False) or (now_ts - last_run) < 1.0: return
        setattr(update_version_label, "_running", True)
        setattr(update_version_label, "_last_run", now_ts)
        def worker():
            status_key, clr, update_date = get_hosts_version_status()
            def apply():
                apply_hosts_version_status(status_key, clr, update_date)
            QTimer.singleShot(0, main_window, apply)
            setattr(update_version_label, "_running", False)
        threading.Thread(target=worker, daemon=True).start()

    apply_main_texts()
    update_version_label()
    main_window.show()
    on_main_window_resize()
    sys.exit(app.exec())
