import sys
import os
import json
import re as _re
from pathlib import Path

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
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

ADDITIONAL_HOSTS_URL = "https://raw.githubusercontent.com/AvenCores/Goida-AI-Unlocker/refs/heads/main/additional_hosts.json"

APP_VERSION = "0.0.0"
try:
    with open(resource_path("app_info.json"), "r", encoding="utf-8") as _vf:
        APP_VERSION = json.load(_vf).get("version", APP_VERSION)
except Exception:
    pass

_LAYOUT_FILLER = "\u3164"

# Regex
_ADDITIONAL_HOSTS_VERSION_RE = _re.compile(r"# additional_hosts_version\s+(\S+)")

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
