from functools import lru_cache
import json
from PySide6.QtCore import QLocale
from app.core.constants import _LAYOUT_FILLER, _MONTH_NAME_OUTPUTS, _MONTH_NAME_ALIASES, _MONTH_NAME_RE, resource_path

CURRENT_LANGUAGE = "ru"

def _load_translations() -> dict:
    try:
        path = resource_path("app/gui/translations.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading translations: {e}")
        return {
            "ru": {
                "language_name": "Русский",
                "language_button": "Сменить язык"
            },
            "en": {
                "language_name": "English",
                "language_button": "Change language"
            }
        }

TRANSLATIONS = _load_translations()

def normalize_language(language: str | None) -> str:
    if not language:
        return "ru"
    normalized = language.lower().replace("-", "_")
    if normalized in TRANSLATIONS:
        return normalized
    for lang_code in sorted(TRANSLATIONS.keys(), key=len, reverse=True):
        if normalized.startswith(lang_code):
            return lang_code
    return "en" if "en" in TRANSLATIONS else list(TRANSLATIONS.keys())[0]

def get_supported_languages() -> dict[str, str]:
    return {lang: TRANSLATIONS[lang].get("language_name", lang) for lang in TRANSLATIONS}

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
