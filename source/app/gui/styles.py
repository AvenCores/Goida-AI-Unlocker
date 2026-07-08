import sys
import subprocess
from functools import lru_cache
from app.core.constants import APP_VERSION
from app.gui.localization import normalize_language, tr, CURRENT_LANGUAGE

@lru_cache(maxsize=1)
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
    elif sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            return out.lower() == "dark"
        except Exception:
            return False
    else:
        try:
            out = subprocess.check_output(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                stderr=subprocess.DEVNULL,
                timeout=5,
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
            "combo": """
                QComboBox {
                    background: #2d333b;
                    color: #f3f6fd;
                    border: 1.5px solid #3c434d;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 11pt;
                    font-weight: 500;
                    min-width: 200px;
                }
                QComboBox:hover {
                    background: #363d46;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 25px;
                    border-left-width: 0px;
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;
                }
                QComboBox QAbstractItemView {
                    background: #2d333b;
                    color: #f3f6fd;
                    border: 1.5px solid #3c434d;
                    selection-background-color: #246cf0;
                    selection-color: #ffffff;
                }
            """,
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
            "combo": """
                QComboBox {
                    background: #f3f4f7;
                    color: #1a1a1a;
                    border: 1.5px solid #cfd4db;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 11pt;
                    font-weight: 500;
                    min-width: 200px;
                }
                QComboBox:hover {
                    background: #e6e8ec;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 25px;
                    border-left-width: 0px;
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;
                }
                QComboBox QAbstractItemView {
                    background: #ffffff;
                    color: #1a1a1a;
                    border: 1.5px solid #cfd4db;
                    selection-background-color: #0078d4;
                    selection-color: #ffffff;
                }
            """,
        }

def get_about_toolbutton_style(styles: dict[str, str]) -> str:
    return styles["theme"] + "\nQToolButton { font-size: 10pt; padding: 6px 12px; }"

def clear_stylesheet_cache():
    _STYLESHEET_CACHE.clear()
