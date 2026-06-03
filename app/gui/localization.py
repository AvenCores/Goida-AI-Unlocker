from functools import lru_cache
from PySide6.QtCore import QLocale
from app.core.constants import _LAYOUT_FILLER, _MONTH_NAME_OUTPUTS, _MONTH_NAME_ALIASES, _MONTH_NAME_RE

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
        "open_hosts_error_title": "Ошибка открытия hosts",
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
        "processing_open": "Открытие файла hosts...\nㅤПожалуйста, подождите.ㅤ",
        "install_success": "Файл hosts успешно установлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "update_success": "Файл hosts успешно обновлён!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "uninstall_success": "Файл hosts успешно восстановлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ",
        "admin_hint_windows": "Запустите программу от имени Администратора.",
        "admin_hint_unix": "Введите пароль root при запросе.",
        "install_error": "Не удалось установить файл hosts.\nㅤ{hint}ㅤ",
        "update_error": "Не удалось обновить файл hosts.\nㅤ{hint}ㅤ",
        "uninstall_error": "Не удалось восстановить файл hosts.\nㅤ{hint}ㅤ",
        "open_hosts_error": "Не удалось открыть файл hosts.\nㅤ{hint}ㅤ",
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
        "provider_malw": "dns.malw.link (Основной)",
        "provider_geohide": "GeoHideDNS (Резервный)",
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
        "open_hosts_error_title": "Hosts Open Error",
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
        "processing_open": "Opening hosts file...\nㅤPlease wait.ㅤ",
        "install_success": "The hosts file was installed successfully!\nㅤYou may need to restart your browser.ㅤ",
        "update_success": "The hosts file was updated successfully!\nㅤYou may need to restart your browser.ㅤ",
        "uninstall_success": "The hosts file was restored successfully!\n!ㅤYou may need to restart your browser.ㅤ",
        "admin_hint_windows": "Run the app as Administrator.",
        "admin_hint_unix": "Enter the root password when prompted.",
        "install_error": "Failed to install the hosts file.\nㅤ{hint}ㅤ",
        "update_error": "Failed to update the hosts file.\nㅤ{hint}ㅤ",
        "uninstall_error": "Failed to restore the hosts file.\nㅤ{hint}ㅤ",
        "open_hosts_error": "Failed to open the hosts file.\nㅤ{hint}ㅤ",
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
        "provider_malw": "dns.malw.link (Primary)",
        "provider_geohide": "GeoHideDNS (Backup)",
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
