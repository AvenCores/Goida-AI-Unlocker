import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from app.core.constants import APP_VERSION
from app.gui.localization import normalize_language, tr, CURRENT_LANGUAGE
from app.gui.scaling import get_ui_scale

# Палитры тем: единый источник цветов для всех стилей
_PALETTES: dict[bool, dict] = {
    True: {  # dark
        "bg": "#1e2228",
        "border": "#2d333b",
        "card_bg": "#2d333b",
        "card_border": "#3c434d",
        "field_bg": "#363d46",
        "text": "#f3f6fd",
        "text_muted": "#8b949e",
        "text_dim": "#bfc9db",
        "btn_bg": "#e6e8ec",
        "btn_border": "#cfd4db",
        "btn_hover": "#d1d4d8",
        "btn_pressed": "#bfc3c9",
        "btn_text": "#222222",
        "accent_start": "#2d7dff",
        "accent_end": "#2962d9",
        "accent_hover_start": "#246cf0",
        "accent_hover_end": "#235bcc",
        "accent_pressed_start": "#1e5ed2",
        "accent_pressed_end": "#1c52b0",
        "combo_sel": "#246cf0",
        "editor_bg": "#1a1e24",
        "editor_text": "#e6edf3",
        "editor_sel": "#264f78",
        "title_text": "#8b949e",
        "title_hover": "#2d7dff",
        "close_hover": "#e06c75",
        "author_color": "#888888",
    },
    False: {  # light
        "bg": "#ffffff",
        "border": "#e1e4e8",
        "card_bg": "#f3f4f7",
        "card_border": "#cfd4db",
        "field_bg": "#e6e8ec",
        "text": "#1a1a1a",
        "text_muted": "#666666",
        "text_dim": "#555555",
        "btn_bg": "#f3f4f7",
        "btn_border": "#cfd4db",
        "btn_hover": "#e6e8ec",
        "btn_pressed": "#d1d5db",
        "btn_text": "#1a1a1a",
        "accent_start": "#0078d4",
        "accent_end": "#0063b1",
        "accent_hover_start": "#006cbd",
        "accent_hover_end": "#005291",
        "accent_pressed_start": "#005291",
        "accent_pressed_end": "#004677",
        "combo_sel": "#0078d4",
        "editor_bg": "#fafbfc",
        "editor_text": "#1a1a1a",
        "editor_sel": "#add6ff",
        "title_text": "#666666",
        "title_hover": "#0078d4",
        "close_hover": "#e06c75",
        "author_color": "#666666",
    },
}

# Общие для обеих тем градиенты опасной кнопки
_DANGER_START, _DANGER_END = "#e06c75", "#d64c58"
_DANGER_HOVER_START, _DANGER_HOVER_END = "#b94a59", "#a43b47"
_DANGER_PRESSED_START, _DANGER_PRESSED_END = "#a4414d", "#93383f"

_STYLESHEET_CACHE: dict[str, dict[str, str]] = {}


def is_system_dark_theme() -> bool:
    """Определяет системную тему средствами Qt (без winreg/gsettings-костылей)."""
    app = QGuiApplication.instance()
    if app is None:
        return False
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def get_stylesheet(dark: bool, language: str | None = None) -> dict[str, str]:
    lang = normalize_language(language or CURRENT_LANGUAGE)
    key = f"{lang}_dark_{dark}"
    if key not in _STYLESHEET_CACHE:
        _STYLESHEET_CACHE[key] = _build_stylesheet(dark, lang)
    return _STYLESHEET_CACHE[key]


def _grad(start: str, end: str) -> str:
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {start}, stop:1 {end})"


_PX_VALUE_RE = re.compile(r"(-?\d+(?:\.\d+)?)px")


def _apply_ui_scale(styles: dict[str, str]) -> dict[str, str]:
    """Пропорционально увеличивает все px-размеры готовых CSS/HTML строк.

    Регэксп проходит по каждому значению «Npx» (шрифты, отступы, радиусы,
    min/max-width), поэтому масштабирование не рассинхронизируется при
    добавлении новых правил. Ширины границ тоже растут — на больших
    экранах это сохраняет визуальный баланс.
    """
    factor = get_ui_scale()
    if factor == 1.0:
        return styles

    def repl(match: re.Match) -> str:
        scaled = max(1, round(float(match.group(1)) * factor))
        return f"{scaled}px"

    return {key: _PX_VALUE_RE.sub(repl, value) for key, value in styles.items()}


def _build_stylesheet(dark: bool, language: str) -> dict[str, str]:
    p = _PALETTES[dark]
    link_color = "#2d7dff" if dark else "#0078d4"

    main = f"""
        QMainWindow, QWidget#mainContainer {{
            background: {p['bg']}; border-radius: 16px;
        }}
        QWidget#titleBar {{ background: transparent; border-bottom: 1px solid {p['border']}; }}
    """

    button1 = f"""
        QPushButton {{ background: {_grad(p['accent_start'], p['accent_end'])}; color: white; border: none; border-radius: 8px; padding: 12px 22px; font-size: 16px; font-weight: 600; }}
        QPushButton:hover {{ background: {_grad(p['accent_hover_start'], p['accent_hover_end'])}; }}
        QPushButton:pressed {{ background: {_grad(p['accent_pressed_start'], p['accent_pressed_end'])}; padding: 14px 22px 10px 22px; }}
    """
    button2 = f"""
        QPushButton {{ background: {_grad(_DANGER_START, _DANGER_END)}; color: white; border: none; border-radius: 8px; padding: 12px 22px; font-size: 16px; font-weight: 600; }}
        QPushButton:hover {{ background: {_grad(_DANGER_HOVER_START, _DANGER_HOVER_END)}; }}
        QPushButton:pressed {{ background: {_grad(_DANGER_PRESSED_START, _DANGER_PRESSED_END)}; padding: 14px 22px 10px 22px; }}
    """
    theme = f"""
        QPushButton, QToolButton {{ background: {p['btn_bg']}; color: {p['btn_text']}; border: 1.5px solid {p['btn_border']}; border-radius: 8px; padding: 10px 16px; font-size: 15px; font-weight: 500; }}
        QPushButton:hover, QToolButton:hover {{ background: {p['btn_hover']}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {p['btn_pressed']}; padding: 12px 16px 8px 16px; }}
    """
    combo = f"""
        QComboBox {{
            background: {p['card_bg']};
            color: {p['text']};
            border: 1.5px solid {p['card_border']};
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 15px;
            font-weight: 500;
            min-width: 200px;
        }}
        QComboBox:hover {{ background: {p['field_bg']}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left-width: 0px;
            border-top-right-radius: 8px;
            border-bottom-right-radius: 8px;
        }}
        QComboBox QAbstractItemView {{
            background: {p['card_bg']};
            color: {p['text']};
            border: 1.5px solid {p['card_border']};
            selection-background-color: {p['combo_sel']};
            selection-color: #ffffff;
        }}
    """
    editor = f"""
        QPlainTextEdit {{
            background: {p['editor_bg']}; color: {p['editor_text']};
            border: 1.5px solid {p['card_border']}; border-radius: 10px;
            padding: 12px; font-size: 13px;
            selection-background-color: {p['editor_sel']};
        }}
        QPlainTextEdit:focus {{ border-color: {p['accent_start']}; }}
    """
    # Квадратная кнопка в футере (язык/тема)
    footer_button = (
        theme
        + "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px;"
        " min-height: 44px; max-height: 44px; }"
    )
    # Прозрачная иконка-кнопка рядом с комбобоксами
    icon_button = (
        "QPushButton { background: transparent; border: none; padding: 4px; border-radius: 6px; }"
        "QPushButton:hover { background: rgba(128,128,128,0.15); }"
    )
    title_button = f"""
        QPushButton {{ background: transparent; color: {p['title_text']}; border: none; font-size: 14px; font-weight: bold; }}
        QPushButton:hover {{ color: {p['title_hover']}; }}
    """
    title_close_button = f"""
        QPushButton {{ background: transparent; color: {p['title_text']}; border: none; font-size: 18px; font-weight: bold; }}
        QPushButton:hover {{ color: {p['close_hover']}; }}
    """
    title_label = (
        f"QLabel {{ color: {p['title_text']}; font-size: 13px;"
        " font-weight: bold; background: transparent; }"
    )
    status_card = (
        f"background:{p['card_bg']}; border:1.5px solid {p['card_border']};"
        " border-radius:12px;"
    )
    update_date_label = (
        f"font-size: 14px; color: {p['text']};"
        " border-radius: 8px; padding: 4px 8px; margin: 2px;"
    )

    result = {
        "main": main,
        "outline_reset": "QPushButton:focus { outline: none; }",
        "label": (
            f"QLabel {{ font-size: 18px; padding: 16px 0 8px 0;"
            f" color: {p['text']}; font-weight: 500; }}"
        ),
        "message_card": (
            f"background:{p['card_bg']}; border:2.5px solid {p['card_border']};"
            "border-radius:12px;"
        ),
        "message_label": (
            f"QLabel {{ font-size: 18px; padding: 8px 0 4px 0; color: {p['text']};"
            " font-weight: 500; background: transparent; border: none; }"
        ),
        "message_block_label": (
            f"QLabel {{ font-size: 18px; padding: 10px 12px; color: {p['text']};"
            f" font-weight: 500; background: {p['field_bg']};"
            " border-radius: 8px; border: none; }"
        ),
        "button1": button1,
        "button2": button2,
        "theme": theme,
        # Компактная кнопка для маленьких фиксированных размеров (крестик поиска)
        "small_button": theme + "\nQPushButton { padding: 4px 6px; font-size: 13px; }",
        "tool_button": theme + "\nQToolButton { font-size: 13px; padding: 6px 12px; }",
        "footer_button": footer_button,
        "icon_button": icon_button,
        "title_button": title_button,
        "title_close_button": title_close_button,
        "title_label": title_label,
        "status_card": status_card,
        "update_date_label": update_date_label,
        "editor": editor,
        "page_title": (
            f"font-size: 18px; font-weight: 600; color: {p['text']}; background: transparent;"
        ),
        "page_subtitle": (
            f"font-size: 11px; color: {p['text_muted']}; background: transparent;"
        ),
        "page_text": f"font-size: 13px; color: {p['text']}; background: transparent;",
        "donate_title": (
            f"font-size: 22px; font-weight: 600; color: {p['text']};"
            " background: transparent;"
        ),
        "donate_card_number": (
            f"font-size: 16px; color: {p['text']}; background: transparent;"
        ),
        "about_title_style": "font-size:25px; margin-bottom:4px;",
        "about_title_html": (
            f"<b style='color:{p['text']};'>Goida AI Unlocker</b>"
            f" <span style='font-size:15px; color:{p['text_dim']};'>(v{APP_VERSION})</span>"
        ),
        "about_info_html": (
            f"<span style='font-size:11px; color:{p['author_color']};'>"
            f"{tr('author_label', language=language)}</span>"
        ),
        "about_link_html": (
            f"<a href='#' style='color:{link_color}; text-decoration:none;"
            f" font-size:13px;'>⟵ {tr('back_to_menu', language=language)}</a>"
        ),
        "combo": combo,
    }
    return _apply_ui_scale(result)


def clear_stylesheet_cache():
    _STYLESHEET_CACHE.clear()
