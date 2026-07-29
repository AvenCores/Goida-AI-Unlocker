import sys
import os
import re as _re
from pathlib import Path

def resource_path(relative_path: str) -> str:
    candidates = []

    try:
        if getattr(sys, "_MEIPASS", None):
            candidates.append(os.path.join(sys._MEIPASS, relative_path))
    except Exception:
        pass

    base_path = os.path.abspath(".")
    candidates.append(os.path.join(base_path, relative_path))

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if os.path.exists(repo_root):
        candidates.append(os.path.join(repo_root, relative_path))

    source_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if os.path.exists(source_dir):
        candidates.append(os.path.join(source_dir, relative_path))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return os.path.join(base_path, relative_path)

def _get_backup_dir() -> Path:
    try:
        # Try to use the user's home directory
        return Path.home() / ".goida-ai-unlocker" / "hosts-backups"
    except Exception:
        # Fallback to a temporary directory if home is not accessible
        import tempfile
        return Path(tempfile.gettempdir()) / "goida-ai-unlocker" / "hosts-backups"

def _get_settings_path() -> Path:
    try:
        return Path.home() / ".goida-ai-unlocker" / "settings.json"
    except Exception:
        import tempfile
        return Path(tempfile.gettempdir()) / "goida-ai-unlocker" / "settings.json"

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts") if sys.platform == "win32" else Path("/etc/hosts")
HOSTS_BACKUP_DIR = _get_backup_dir()
HOSTS_BACKUP_PREFIX = "hosts_backup_"
SETTINGS_PATH = _get_settings_path()

GITHUB_RELEASES_API_URL = "https://api.github.com/repos/AvenCores/Goida-AI-Unlocker/releases/latest"
GITHUB_RELEASES_PAGE_URL = "https://github.com/AvenCores/Goida-AI-Unlocker/releases/latest"

APP_VERSION = "1.3.3"

_LAYOUT_FILLER = "\u3164"

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
    "de": [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ],
    "uk": [
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
    ],
    "be": [
        "студзеня", "лютага", "сакавіка", "красавіка", "траўня", "чэрвеня",
        "ліпеня", "жніўня", "верасня", "кастрычніка", "лістапада", "снежня",
    ],
    "kk": [
        "қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
        "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан",
    ],
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ],
    "pl": [
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
        "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
    ],
    "es": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ],
    "pt": [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ],
    "it": [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ],
    "tr": [
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    ],
    "zh": [
        "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
    ],
    "ja": [
        "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
    ],
    "ko": [
        "1월", "2월", "3월", "4월", "5월", "6월",
        "7월", "8월", "9월", "10월", "11월", "12월",
    ],
    "cs": [
        "ledna", "února", "března", "dubna", "května", "června",
        "července", "srpna", "září", "října", "listopadu", "prosince",
    ],
    "nl": [
        "januari", "februari", "maart", "april", "mei", "juni",
        "juli", "augustus", "september", "oktober", "november", "december",
    ],
    "sv": [
        "januari", "februari", "mars", "april", "maj", "juni",
        "juli", "augusti", "september", "oktober", "november", "december",
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
