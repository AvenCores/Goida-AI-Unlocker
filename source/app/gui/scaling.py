"""Адаптивное масштабирование интерфейса под большие разрешения экрана.

Приоритет источника фактора:
1) переменная окружения GOIDA_UI_SCALE (для отладки и форсирования);
2) настройка пользователя «ui_scale» (переключатель в приложении);
3) автоопределение по логической высоте основного экрана относительно
   базовых 1080p: логические пиксели Qt уже учитывают масштаб ОС, поэтому
   на экранах с системным масштабом >100% двойного увеличения не
   происходит, а на больших мониторах со 100% масштабом интерфейс
   увеличивается.

Сверху фактор ограничивается «экранным потолком» (fit-лимит): если окно
в выбранном масштабе не помещается на экране, фактор уменьшается — иначе
футер с переключателем масштаба оказался бы за пределами экрана и вернуться
к меньшему масштабу было бы невозможно.
"""

import os

from PySide6.QtGui import QGuiApplication

from app.core.settings import get_setting, set_setting

BASE_LOGICAL_HEIGHT = 1080.0
MIN_SCALE = 1.0
MAX_SCALE = 2.0
SCALE_STEP = 0.05

SCALE_SETTINGS_KEY = "ui_scale"
SCALE_AUTO = "auto"

_SCALE_ENV_VAR = "GOIDA_UI_SCALE"

_scale_cache: float | None = None
_fit_limited_scale: float | None = None


def _parse_env_override() -> float | None:
    raw = os.environ.get(_SCALE_ENV_VAR)
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return max(MIN_SCALE, min(MAX_SCALE * 1.25, value))


def get_ui_scale_setting() -> str:
    """Сохранённый выбор пользователя: SCALE_AUTO или строка-число."""
    raw = get_setting(SCALE_SETTINGS_KEY, SCALE_AUTO)
    return str(raw)


def apply_ui_scale_setting(value: str) -> float:
    """Сохраняет выбор пользователя и применяет его без перезапуска процесса.

    Возвращает новый фактор. Виджеты пересобирает вызывающая сторона
    (MainWindow испускает restart_requested).
    """
    global _scale_cache
    normalized = SCALE_AUTO
    if value != SCALE_AUTO:
        try:
            numeric = float(str(value).replace(",", "."))
        except ValueError:
            numeric = None
        if numeric is not None and MIN_SCALE <= numeric <= MAX_SCALE:
            normalized = f"{round(numeric, 2):g}"
        else:
            normalized = SCALE_AUTO
    set_setting(SCALE_SETTINGS_KEY, normalized)
    _scale_cache = None
    return get_ui_scale()


def set_fit_limited_scale(factor: float | None):
    """Задает «экранный потолок» фактора (None — снять ограничение).

    Потолок не поднимает масштаб, а только ограничивает сверху любой
    источник (окружение, настройку, авто), поэтому выбор пользователя
    на меньший масштаб всегда работает.
    """
    global _fit_limited_scale, _scale_cache
    if factor is None:
        _fit_limited_scale = None
    else:
        _fit_limited_scale = max(MIN_SCALE, min(MAX_SCALE, factor))
    _scale_cache = None


def _compute_scale() -> float:
    override = _parse_env_override()

    saved = get_ui_scale_setting()
    manual = None
    if override is None and saved != SCALE_AUTO:
        try:
            candidate = float(saved.replace(",", "."))
        except ValueError:
            candidate = None
        if candidate is not None and MIN_SCALE <= candidate <= MAX_SCALE:
            manual = candidate

    if override is not None:
        factor = override
    elif manual is not None:
        factor = manual
    else:
        factor = _auto_screen_scale()

    # Потолок «по размеру экрана» применяется к любому источнику:
    # иначе при слишком большом масштабе переключатель возврата
    # оказывается недоступен
    if _fit_limited_scale is not None:
        factor = min(factor, _fit_limited_scale)
    return factor


def _auto_screen_scale() -> float:
    app = QGuiApplication.instance()
    if app is None:
        return MIN_SCALE
    screen = app.primaryScreen()
    if screen is None:
        return MIN_SCALE
    height = screen.availableGeometry().height()
    if height <= 0:
        return MIN_SCALE
    raw = height / BASE_LOGICAL_HEIGHT
    stepped = round(raw / SCALE_STEP) * SCALE_STEP
    return max(MIN_SCALE, min(MAX_SCALE, stepped))


def get_ui_scale() -> float:
    """Возвращает текущий коэффициент масштабирования интерфейса."""
    global _scale_cache
    if _scale_cache is None:
        _scale_cache = _compute_scale()
    return _scale_cache


def ui_scaled(value: int | float) -> int | float:
    """Увеличивает размер в пикселях под текущий фактор; int остаётся int."""
    factor = get_ui_scale()
    result = value * factor
    if isinstance(value, int):
        return max(1, int(round(result)))
    return round(result, 2)
