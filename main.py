import sys
import tempfile
import urllib.request
import subprocess
import os
import threading  # Added for running blocking tasks in background
import atexit
import time as _time  # for retry sleeps
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect, QStackedWidget, QSizePolicy, QToolButton, QAbstractButton, QGridLayout
    from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QSize
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFontMetrics
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    print("Ошибка: библиотека PySide6 не установлена. Пожалуйста, установите ее командой: pip install PySide6")
    sys.exit(1)
from typing import Optional
import json
import textwrap as _tw # NEW: for dedent

# ---------------- additional hosts configs ----------------
# Raw URL to fetch latest additional hosts definition for update checks
ADDITIONAL_HOSTS_URL = "https://raw.githubusercontent.com/AvenCores/Goida-AI-Unlocker/refs/heads/main/additional_hosts.py"
# ----------------------------------------------------------

# Placeholder, real version will be loaded from app_info.json at runtime
APP_VERSION = "0.0.0"

# ----------------------- NEW: safe temp removal helper -----------------------
def _safe_remove(path: str, retries: int = 3, delay: float = 0.3):
    """Attempt to remove a temporary file. If immediate deletion fails,
    retry a few times and, as a fallback, register the file for deletion
    when the application exits."""
    for _ in range(retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            _time.sleep(delay)
        except Exception:
            break

    # If still not deleted, try again when the program terminates
    try:
        if os.path.exists(path):
            atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    except Exception:
        pass
# ---------------------------------------------------------------------------

# ----------- NEW: fetch remote additional hosts -------------------
def _fetch_remote_additional() -> tuple[str, str]:
    """Return (version, hosts_add) fetched from remote additional_hosts.py.
    On failure returns ("", "").
    If hosts_add is empty, version is also returned as empty."""
    import time as _t
    try:
        raw_txt = urllib.request.urlopen(f"{ADDITIONAL_HOSTS_URL}?t={int(_t.time())}", timeout=10).read().decode("utf-8", errors="ignore")
        import re as _re, textwrap as _tw
        ver_match = _re.search(r'version_add\s*=\s*["\']([^"\']+)["\']', raw_txt)
        hosts_match = _re.search(r'hosts_add\s*=\s*"""(.*?)"""', raw_txt, _re.S)
        version = ver_match.group(1) if ver_match else ""
        hosts_block = hosts_match.group(1).strip() if hosts_match else ""
        # Normalise line indentation
        hosts_block = _tw.dedent(hosts_block)
        # If hosts_add is empty, also return empty version
        if not hosts_block:
            version = ""
        return version, hosts_block
    except Exception:
        return "", ""
# -----------------------------------------------------------------

def check_installation():
    # Эта функция будет работать только на Windows
    if sys.platform != 'win32':
        return False
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    try:
        with open(hosts_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        return "# Блокировка реально плохих сайтов" in content
    except Exception as e:
        return False

def update_hosts_as_admin():
    """Скачивает и устанавливает актуальный hosts. Возвращает True при успехе.
    Даже при ошибке всегда пытается удалить созданные временные файлы."""
    if sys.platform != 'win32':
        print("Эта функция предназначена только для Windows.")
        return False

    url = "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts"
    temp_path: str | None = None
    ps_script_path: str | None = None
    try:
        # Скачиваем и сохраняем содержимое во временный файл
        temp_fd, temp_path = tempfile.mkstemp()
        os.close(temp_fd)

        # Скачиваем контент основного hosts-списка и декодируем в текст
        content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

        # --- Добавляем блок с дополнительными записями и меткой версии ---
        # Only add version marker if there's actual content (not empty hosts_add)
        add_ver, add_hosts_remote = _fetch_remote_additional()
        if add_hosts_remote:  # Only add if hosts_add is not empty
            extra_block = f"\n# additional_hosts_version {add_ver}\n{add_hosts_remote.strip()}\n"
            content += extra_block

        # Записываем во временный файл (уже обновлённый контент)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Создаём PowerShell-скрипт для копирования
        ps_content = f'''
$source = "{temp_path}"
$dest = "C:\\Windows\\System32\\drivers\\etc\\hosts"
Copy-Item -Path $source -Destination $dest -Force
Clear-DnsClientCache
ipconfig /flushdns
ipconfig /release
ipconfig /renew
netsh winsock reset
'''
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.ps1', encoding='utf-8') as ps_file:
            ps_file.write(ps_content)
            ps_script_path = ps_file.name

        command = [
            "powershell", "-WindowStyle", "Hidden", "-Command",
            f'Start-Process powershell -Verb runAs -WindowStyle Hidden -ArgumentList \'-NoProfile -ExecutionPolicy Bypass -File "{ps_script_path}"\' -Wait'
        ]
        subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

        # Даем время на обновление файла
        import time as _t; _t.sleep(1)
        return True
    except Exception as e:
        print(f"Ошибка: {e}")
        return False
    finally:
        if temp_path:
            _safe_remove(temp_path)
        if ps_script_path:
            _safe_remove(ps_script_path)

def is_windows_dark_theme():
    # Эта функция будет работать только на Windows
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(registry, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False

def get_stylesheet(dark):
    if dark:
        return {
            "main": """
                QMainWindow {
                    background: #1e2228;
                    border-radius: 16px;
                }
                QWidget {
                    border-radius: 16px;
                    background: #1e2228;
                }
                QWidget#titleBar {
                    background: transparent;
                    border-top-left-radius: 16px;
                    border-top-right-radius: 16px;
                    border-bottom-left-radius: 0;
                    border-bottom-right-radius: 0;
                    border-bottom: 1px solid #2d333b;
                }
            """,
            "label": """
                QLabel {
                    font-size: 18px;
                    padding: 16px 0 8px 0;
                    color: #f3f6fd;
                    font-weight: 500;
                }
            """,
            "button1": """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d7dff, stop:1 #2962d9);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 0;
                    font-size: 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #246cf0, stop:1 #235bcc);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e5ed2, stop:1 #1c52b0);
                    padding: 14px 0 10px 0;
                }
            """,
            "button2": """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e06c75, stop:1 #d64c58);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 0;
                    font-size: 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b94a59, stop:1 #a43b47);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a84a57, stop:1 #973f4a);
                    padding: 14px 0 10px 0;
                }
            """,
            "theme": """
                QPushButton, QToolButton {
                    background: #e6e8ec;
                    color: #222;
                    border: 1.5px solid #cfd4db;
                    border-radius: 8px;
                    padding: 10px 0;
                    font-size: 15px;
                    font-weight: 500;
                }
                QPushButton:hover, QToolButton:hover {
                    /* slightly darker on hover to simulate dimming */
                    background: #d1d4d8;
                }
                QPushButton:pressed, QToolButton:pressed {
                    background: #bfc3c9;
                    padding: 12px 0 8px 0;
                }
            """,
            "theme_center_small": """
                QPushButton {
                    background: #e6e8ec;
                    color: #222;
                    border: 1.5px solid #cfd4db;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 140px;
                    text-align: center;
                }
                QPushButton:hover {
                    background: #d1d4d8;
                }
                QPushButton:pressed {
                    background: #bfc3c9;
                    padding: 10px 16px 6px 16px;
                }
            """,
            "about_title_style": "font-size:25px; margin-bottom:4px;",
            "about_title_html": f"<b style='color:#f3f6fd;'>Goida AI Unlocker</b> <span style='font-size:15px; color:#bfc9db;'>(v{APP_VERSION})</span>",
            "about_info_html": "<span style='font-size:11px; color:#888;'>Автор: AvenCores</span>",
            "about_link_html": "<a href='#' style='color:#2d7dff; text-decoration:none; font-size:13px;'>⟵ В меню</a>",
        }
    else:
        return {
            "main": """
                QMainWindow {
                    background: #ffffff;
                    border-radius: 16px;
                }
                QWidget {
                    border-radius: 16px;
                    background: #ffffff;
                }
                QWidget#titleBar {
                    background: transparent;
                    border-top-left-radius: 16px;
                    border-top-right-radius: 16px;
                    border-bottom-left-radius: 0;
                    border-bottom-right-radius: 0;
                    border-bottom: 1px solid #e1e4e8;
                }
            """,
            "label": """
                QLabel {
                    font-size: 18px;
                    padding: 16px 0 8px 0;
                    color: #1a1a1a;
                    font-weight: 500;
                }
            """,
            "button1": """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078d4, stop:1 #0063b1);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 0;
                    font-size: 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #006cbd, stop:1 #005291);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005291, stop:1 #004677);
                    padding: 14px 0 10px 0;
                }
            """,
            "button2": """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e06c75, stop:1 #d64c58);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 0;
                    font-size: 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b94a59, stop:1 #a43b47);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9e3f4c, stop:1 #8f3640);
                    padding: 14px 0 10px 0;
                }
            """,
            "theme": """
                QPushButton, QToolButton {
                    background: #f3f4f7;
                    color: #1a1a1a;
                    border: 1.5px solid #cfd4db;
                    border-radius: 8px;
                    padding: 10px 0;
                    font-size: 15px;
                    font-weight: 500;
                }
                QPushButton:hover, QToolButton:hover {
                    background: #e6e8ec;
                }
                QPushButton:pressed, QToolButton:pressed {
                    background: #d1d5db;
                    padding: 12px 0 8px 0;
                }
            """,
            "theme_center_small": """
                QPushButton {
                    background: #f3f4f7;
                    color: #1a1a1a;
                    border: 1.5px solid #cfd4db;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 140px;
                    text-align: center;
                }
                QPushButton:hover {
                    background: #e6e8ec;
                }
                QPushButton:pressed {
                    background: #d1d5db;
                    padding: 10px 16px 6px 16px;
                }
            """,
            "about_title_style": "font-size:25px; margin-bottom:4px;",
            "about_title_html": f"<b style='color:#1a1a1a;'>Goida AI Unlocker</b> <span style='font-size:15px; color:#555555;'>(v{APP_VERSION})</span>",
            "about_info_html": "<span style='font-size:11px; color:#666666;'>Автор: AvenCores</span>",
            "about_link_html": "<a href='#' style='color:#0078d4; text-decoration:none; font-size:13px;'>⟵ В меню</a>",
        }

class CustomWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget: Optional[QStackedWidget] = None
        self._current_animation: Optional[QPropertyAnimation] = None
        self.dark_theme = False
        self.styles = {}
        self.title_bar: Optional[QWidget] = None

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.title_bar is not None
            and self.title_bar.underMouse()
        ):
            self.dragPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'dragPos') and self.dragPos:
            delta = event.globalPosition().toPoint() - self.dragPos
            self.move(self.pos() + delta)
            self.dragPos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.dragPos = None

# ----------------------- NEW: hosts version helpers -----------------------

def _extract_update_line(content: bytes) -> str:
    """Return the second line (index 1) from hosts content without leading/trailing spaces."""
    try:
        return content.decode("utf-8", errors="ignore").splitlines()[1].strip()
    except Exception:
        return ""


# ---------- NEW: helpers for additional hosts version ----------
def _extract_additional_version(text: str) -> str:
    """Return version string from line '# additional_hosts_version X'."""
    for line in text.splitlines():
        if line.lower().startswith("# additional_hosts_version"):
            parts = line.strip().split()
            if len(parts) >= 2:
                return parts[-1]
    return ""


def _get_remote_add_version() -> str:
    """Return remote version_add (wrapper around _fetch_remote_additional)."""
    ver, _ = _fetch_remote_additional()
    return ver
# --------------------------------------------------------------


def get_hosts_version_status() -> tuple[str, str]:
    """Return a tuple (status_word, color) describing hosts version state."""
    # --- BEGIN: short-lived cache for remote checks ---
    # Cache remote main hosts line and additional version to avoid frequent network IO
    # in quick successions (e.g., multiple UI-triggered checks). TTL ~60s is enough.
    global _REMOTE_CACHE_TTL, _remote_main_line_cache, _remote_add_ver_cache
    try:
        _REMOTE_CACHE_TTL
    except NameError:
        _REMOTE_CACHE_TTL = 60.0
    try:
        _remote_main_line_cache
    except NameError:
        _remote_main_line_cache = None  # type: ignore[assignment]
    try:
        _remote_add_ver_cache
    except NameError:
        _remote_add_ver_cache = None  # type: ignore[assignment]

    def _get_remote_main_hosts_line_cached() -> str:
        global _remote_main_line_cache
        now = _time.time()
        if (
            _remote_main_line_cache is not None
            and isinstance(_remote_main_line_cache, tuple)
            and now - _remote_main_line_cache[0] < _REMOTE_CACHE_TTL
        ):
            return _remote_main_line_cache[1]
        import time as _t
        remote_url = f"https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts?t={int(_t.time())}"
        try:
            line = _extract_update_line(urllib.request.urlopen(remote_url, timeout=10).read())
        except Exception:
            line = ""
        _remote_main_line_cache = (now, line)
        return line

    def _get_remote_add_version_cached() -> str:
        global _remote_add_ver_cache
        now = _time.time()
        if (
            _remote_add_ver_cache is not None
            and isinstance(_remote_add_ver_cache, tuple)
            and now - _remote_add_ver_cache[0] < _REMOTE_CACHE_TTL
        ):
            return _remote_add_ver_cache[1]
        try:
            ver = _get_remote_add_version()
        except Exception:
            ver = ""
        _remote_add_ver_cache = (now, ver)
        return ver
    # --- END: short-lived cache for remote checks ---

    if sys.platform != "win32":
        return "Не установлен", "#e06c75"

    hosts_path = r"C:\\Windows\\System32\\drivers\\etc\\hosts"
    # If hosts file missing or our block not installed -> treat as not installed
    if not (os.path.exists(hosts_path) and check_installation()):
        return "Не установлен", "#e06c75"

    try:
        with open(hosts_path, "rb") as lf:
            raw_content = lf.read()
            local_line = _extract_update_line(raw_content)
            text_content = raw_content.decode("utf-8", errors="ignore")
            local_add_ver = _extract_additional_version(text_content)

        remote_line = _get_remote_main_hosts_line_cached()
        remote_add_ver = _get_remote_add_version_cached()

        # Up-to-date only if the main hosts list matches.
        # For additional hosts: if remote version is not empty, local must match it.
        # If remote version is empty (no additional hosts content), local can be anything.
        main_match = local_line == remote_line and local_line.startswith("#")
        
        # Additional hosts match: either both empty, or both have same version
        # (This accounts for when hosts_add is empty - no version line added)
        if remote_add_ver:
            # Remote has additional content - require versions to match
            add_match = (local_add_ver == remote_add_ver)
        else:
            # Remote has no additional content - local should also have none
            add_match = (local_add_ver == "")
        
        up_to_date = main_match and add_match
        
        if up_to_date:
            return "Актуально", "#43b581"
        else:
            return "Устарело", "#e06c75"
    except Exception:
        # Any error counts as outdated
        return "Устарело", "#e06c75"
# --------------------- END NEW helpers ---------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Убираем фокус-обводку (dotted outline) у всех кнопок
    app.setStyleSheet("QPushButton:focus { outline: none; }")

    # --- Установка иконки приложения ---
    def resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS  # type: ignore[attr-defined]
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # ------------------ NEW: SVG icon helpers ------------------
    # Cache already-rendered & tinted icons to avoid expensive re-rendering on every
    # button click / theme refresh. Keyed by (file_path, size_px, tint_hex).
    ICON_CACHE: dict[tuple[str, int, str], QIcon] = {}
    # Cache QSvgRenderer per source path to avoid re-parsing the SVG data each time
    RENDERER_CACHE: dict[str, QSvgRenderer] = {}

    def _tint_pixmap(pix: QPixmap, color: QColor) -> QPixmap:
        """Re-color a pixmap while preserving alpha."""
        if pix.isNull():
            return pix
        tinted = QPixmap(pix.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode_Source)  # type: ignore[attr-defined]
        painter.drawPixmap(0, 0, pix)  # original alpha
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)  # type: ignore[attr-defined]
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def get_icon(file_name: str, size_px: int | None = None, *, force_dark: bool = False, force_white: bool = False) -> QIcon:
        """Load an SVG from ./icons and tint it depending on current theme.
        Returned icons are cached for faster subsequent access."""
        path = resource_path(os.path.join("icons", file_name))
        # Render SVG directly at target size for crisp edges
        render_size = size_px or 48
        # Determine tint colour first to form cache key
        if force_white:
            tint = QColor("#ffffff")
        elif force_dark or (not main_window.dark_theme):
            tint = QColor("#1a1a1a")
        else:
            tint = QColor("#ffffff")

        cache_key = (path, render_size, tint.name())
        cached_icon = ICON_CACHE.get(cache_key)
        if cached_icon is not None:
            return cached_icon

        # Not cached -> render & store
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
        """Return QLabel with a tinted icon pixmap."""
        icon = get_icon(file_name, size)
        label = QLabel()
        label.setPixmap(icon.pixmap(size, size))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName("message_emoji")
        label.setProperty("icon_name", file_name)
        return label

    def refresh_icons(root_widget=None):
        """Re-tint all buttons/labels that carry 'icon_name' property."""
        if root_widget is None:
            root_widget = main_window
        # Update button icons (QPushButton/QToolButton)
        for btn in root_widget.findChildren(QAbstractButton):
            name = btn.property("icon_name")
            if not name:
                continue
            force_dark = bool(btn.property("icon_force_dark"))
            force_white = bool(btn.property("icon_force_white"))
            btn.setIcon(get_icon(name, btn.iconSize().width(), force_dark=force_dark, force_white=force_white))
        # Update QLabel icons
        for lbl in root_widget.findChildren(QLabel):
            name = lbl.property("icon_name")
            if not name:
                continue
            size = lbl.pixmap().width() if lbl.pixmap() else 32
            force_dark = bool(lbl.property("icon_force_dark"))
            force_white = bool(lbl.property("icon_force_white"))
            lbl.setPixmap(get_icon(name, size, force_dark=force_dark, force_white=force_white).pixmap(size, size))
        # function ends implicitly
    # ------------------------------------------------------------

    # --------- Load application version from app_info.json ---------
    try:
        with open(resource_path("app_info.json"), "r", encoding="utf-8") as _vf:
            APP_VERSION = json.load(_vf).get("version", APP_VERSION)
    except Exception:
        # If file missing or malformed, keep placeholder
        pass
    # --------------------------------------------------------------

    icon_path = resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    main_window = CustomWindow()
    main_window.stacked_widget = QStackedWidget()
    main_window.setWindowTitle("Goida AI Unlocker")
    main_window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    main_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    main_window.dark_theme = is_windows_dark_theme()
    main_window.styles = get_stylesheet(main_window.dark_theme)
    main_window.setStyleSheet(main_window.styles["main"])
    main_window.setWindowIcon(QIcon(icon_path))

    # --- Главный контейнер ---
    main_container = QWidget()
    main_layout = QVBoxLayout(main_container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # Title bar (вынесен отдельно, всегда сверху)
    title_bar = QWidget()
    title_bar.setObjectName("titleBar")
    title_bar.setFixedHeight(32)
    main_window.title_bar = title_bar # Для доступа в mousePressEvent
    title_bar_layout = QHBoxLayout(title_bar)
    title_bar_layout.setContentsMargins(12, 0, 8, 0)
    title_bar_layout.setSpacing(0)
    title_label = QLabel("Goida AI Unlocker")
    title_label.setStyleSheet("""
        QLabel {
            color: #666666;
            font-size: 13px;
            font-weight: bold;
            background: transparent;
        }
    """)
    title_bar_layout.addWidget(title_label)
    title_bar_layout.addStretch()
    minimize_button = QPushButton("─")
    minimize_button.setFixedSize(26, 26)
    minimize_button.clicked.connect(main_window.showMinimized)
    minimize_button.setStyleSheet("""
        QPushButton { background: transparent; color: #666666; border: none; font-size: 14px; font-weight: bold; }
        QPushButton:hover { color: #2d7dff; }
    """)
    close_button = QPushButton("×")
    close_button.setFixedSize(26, 26)
    close_button.clicked.connect(app.quit)
    close_button.setStyleSheet("""
        QPushButton { background: transparent; color: #666666; border: none; font-size: 18px; font-weight: bold; }
        QPushButton:hover { color: #e06c75; }
    """)
    title_bar_layout.addWidget(minimize_button)
    title_bar_layout.addWidget(close_button)
    main_layout.addWidget(title_bar)

    # --- Центральный виджет (меняется в стеке) ---
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

    def fix_widget_size(w):
        w.setMinimumSize(main_window.width(), main_window.height() - title_bar.height())
        w.setMaximumSize(main_window.width(), main_window.height() - title_bar.height())

    # изменяем размер окна
    main_window.resize(640, 640)

    def on_main_window_resize(event=None):
        fix_widget_size(central_widget)
        if main_window.stacked_widget:
            current = main_window.stacked_widget.currentWidget()
            if current:
                fix_widget_size(current)

    old_resize_event = main_window.resizeEvent
    def new_resize_event(self, event):
        old_resize_event(event)
        on_main_window_resize(event)
    main_window.resizeEvent = new_resize_event.__get__(main_window, CustomWindow)

    # --- Новый заголовок приложения
    app_title_label = QLabel()
    app_title_label.setObjectName("main_title")
    app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app_title_label.setTextFormat(Qt.TextFormat.RichText)
    app_title_label.setText(main_window.styles["about_title_html"])
    app_title_label.setStyleSheet(main_window.styles["about_title_style"])
    layout.addWidget(app_title_label)

    status = "Установлен" if check_installation() else "Не установлен"
    color = "#43b581" if status == "Установлен" else "#e06c75"
    textinformer = QLabel(f"ㅤОбход блокировок - <span style='color:{color}; font-weight:bold;'>{status}</span>ㅤ")
    textinformer.setTextFormat(Qt.TextFormat.RichText)
    textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    textinformer.setStyleSheet(main_window.styles["label"])

    # ----------------------- NEW: version label -----------------------
    version_label = QLabel("Проверка версии…")
    version_label.setTextFormat(Qt.TextFormat.RichText)
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setStyleSheet(main_window.styles["label"])
    # -----------------------------------------------------------------

    # Группируем две надписи для компактного вида
    status_container = QWidget()
    status_container.setObjectName("status_block")
    status_vbox = QVBoxLayout(status_container)
    status_vbox.setContentsMargins(16, 12, 16, 12)  # inner padding for card feel
    status_vbox.setSpacing(4)
    status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_vbox.addWidget(textinformer)
    status_vbox.addWidget(version_label)

    # Apply initial block style depending on theme
    _light_block = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
    _dark_block = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
    status_container.setStyleSheet(_dark_block if main_window.dark_theme else _light_block)

    layout.addWidget(status_container)

    button = QPushButton(" Установить обход блокировок")
    button.setIcon(get_icon("settings.svg", 18, force_white=True))
    button.setIconSize(QSize(18, 18))
    button.setProperty("icon_name", "settings.svg")
    button.setProperty("icon_force_white", True)
    button.setStyleSheet(main_window.styles["button1"])
    button2 = QPushButton(" Удалить обход блокировок")
    button2.setIcon(get_icon("trash.svg", 18, force_white=True))
    button2.setIconSize(QSize(18, 18))
    button2.setProperty("icon_name", "trash.svg")
    button2.setProperty("icon_force_white", True)
    button2.setStyleSheet(main_window.styles["button2"])
    theme_button = QPushButton(" Сменить тему")
    theme_button.setIcon(get_icon("sun.svg", 18, force_dark=True))
    theme_button.setIconSize(QSize(18, 18))
    theme_button.setProperty("icon_name", "sun.svg")
    theme_button.setProperty("icon_force_dark", True)
    theme_button.setStyleSheet(main_window.styles["theme"])
    donate_button = QPushButton(" Донат")
    donate_button.setIcon(get_icon("heart.svg", 18, force_dark=True))
    donate_button.setIconSize(QSize(18, 18))
    donate_button.setProperty("icon_name", "heart.svg")
    donate_button.setProperty("icon_force_dark", True)
    donate_button.setStyleSheet(main_window.styles["theme"])
    about_button = QPushButton(" О программе")
    about_button.setIcon(get_icon("info.svg", 18, force_dark=True))
    about_button.setIconSize(QSize(18, 18))
    about_button.setProperty("icon_name", "info.svg")
    about_button.setProperty("icon_force_dark", True)
    about_button.setStyleSheet(main_window.styles["theme"])

    update_button = QPushButton(" Проверить обновления")
    update_button.setIcon(get_icon("refresh.svg", 18, force_dark=True))
    update_button.setIconSize(QSize(18, 18))
    update_button.setProperty("icon_name", "refresh.svg")
    update_button.setProperty("icon_force_dark", True)
    update_button.setStyleSheet(main_window.styles["theme"])
    update_button.clicked.connect(lambda: check_for_updates())

    def restore_original_hosts():
        """Восстанавливает стандартный hosts. Чистит временные файлы в любом случае."""
        if sys.platform != 'win32':
            print("Эта функция предназначена только для Windows.")
            return False

        temp_path: str | None = None
        ps_script_path: str | None = None
        try:
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

            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
                temp_file.write(default_hosts)
                temp_path = temp_file.name

            ps_content = f'''
$source = "{temp_path}"
$dest = "C:\\Windows\\System32\\drivers\\etc\\hosts"
Copy-Item -Path $source -Destination $dest -Force
Clear-DnsClientCache
ipconfig /flushdns
ipconfig /release
ipconfig /renew
netsh winsock reset
'''
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.ps1', encoding='utf-8') as ps_file:
                ps_file.write(ps_content)
                ps_script_path = ps_file.name

            command = [
                "powershell", "-WindowStyle", "Hidden", "-Command",
                f'Start-Process powershell -Verb runAs -WindowStyle Hidden -ArgumentList \'-NoProfile -ExecutionPolicy Bypass -File "{ps_script_path}"\' -Wait'
            ]
            subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

            import time as _t; _t.sleep(1)
            return True
        except Exception as e:
            print(f"Ошибка: {e}")
            return False
        finally:
            if temp_path:
                _safe_remove(temp_path)
            if ps_script_path:
                _safe_remove(ps_script_path)

    if main_window.stacked_widget:
        main_window.stacked_widget.addWidget(central_widget)
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
        for i in range(main_window.stacked_widget.count()):
            w = main_window.stacked_widget.widget(i)
            if w is central_widget: continue
            w.setStyleSheet(main_window.styles["main"])
            for child in w.findChildren(QPushButton):
                text = child.text().lower()
                if any(keyword in text for keyword in ["донат", "о программе", "github", "вернуться", "меню", "telegram", "youtube", "rutube", "дзен", "dzen", "vk"]):
                    child.setStyleSheet(main_window.styles["theme"])
                elif "копировать" in text or "окей" in text:
                    child.setStyleSheet(main_window.styles["button1"])
                elif "удалить" in text:
                    child.setStyleSheet(main_window.styles["button2"])
                else: child.setStyleSheet(main_window.styles["button1"])

            for child in w.findChildren(QLabel):
                obj_name = child.objectName()
                if obj_name == "about_title":
                    child.setText(main_window.styles["about_title_html"])
                    child.setStyleSheet(main_window.styles["about_title_style"])
                elif obj_name == "about_info":
                    child.setText(main_window.styles["about_info_html"])
                elif obj_name == "about_link":
                    child.setText(main_window.styles["about_link_html"])
                elif obj_name == "message_emoji": continue
                else: child.setStyleSheet(main_window.styles["label"])

            # Re-tint icons for this subwindow once after styles are updated
            refresh_icons(w)

    def show_message_and_return(msg, success=True, animate=True):
        message_widget = QWidget()
        vbox = QVBoxLayout(message_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(message_widget)

        # ---- Карточка сообщения ----
        card_container = QWidget()
        card_container.setObjectName("msg_card")
        # Позволяем карточке расширяться при необходимости, но не более 600px
        card_container.setMinimumWidth(220)
        card_container.setMaximumWidth(600)
        card_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)

        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)

        # Replace emoji label with SVG icon label
        icon_file = "check-circle.svg" if success else "x-circle.svg"
        emoji_label = create_icon_label(icon_file, size=48)
        card_layout.addWidget(emoji_label)

        # Show each line of the incoming message on its own QLabel instead of using \n within a single label
        for line in msg.split("\n"):
            if not line.strip():
                continue  # skip empty lines for cleaner look
            lbl = QLabel(line)
            lbl.setWordWrap(False)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(lbl)

        ok_btn = QPushButton("Окей")
        card_layout.addWidget(ok_btn)

        vbox.addWidget(card_container)

        if main_window.stacked_widget:
            main_window.stacked_widget.addWidget(message_widget)
        update_subwindow_styles()

        # Переключение либо с анимацией, либо мгновенно
        if animate and main_window.stacked_widget:
            animate_widget_switch(message_widget)
        elif main_window.stacked_widget:
            main_window.stacked_widget.setCurrentWidget(message_widget)

        def return_to_main():
            def do_remove_message_widget():
                if main_window.stacked_widget: main_window.stacked_widget.removeWidget(message_widget)
                message_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_message_widget)
        ok_btn.clicked.connect(return_to_main)

    # --- Окно уведомления об обновлении ---
    def show_update_available(local_version: str, latest_version: str, dl_url: str):
        update_widget = QWidget()
        vbox = QVBoxLayout(update_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(update_widget)

        # ---- Создаём карточку с рамкой ----
        card_container = QWidget()
        card_container.setObjectName("update_card")
        # Динамическая ширина: от 240 до 600 px
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

        # ---- Содержимое карточки ----
        emoji_label = create_icon_label("alert.svg", size=48)
        emoji_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        emoji_label.setFixedHeight(48)
        card_layout.addWidget(emoji_label)

        # ---- Версии без вложенных блоков ----
        installed_lbl = QLabel(f"ㅤУстановленная версия: <b>v{local_version}</b>ㅤ")
        installed_lbl.setTextFormat(Qt.TextFormat.RichText)
        installed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(installed_lbl)

        latest_lbl = QLabel(f"Последняя версия: <b>v{latest_version}</b>")
        latest_lbl.setTextFormat(Qt.TextFormat.RichText)
        latest_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(latest_lbl)

        # Заголовок о доступности обновления
        label = QLabel("Доступна новая версия!")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(label)

        download_btn = QPushButton("Скачать")
        card_layout.addWidget(download_btn)

        ok_btn2 = QPushButton("Окей")
        card_layout.addWidget(ok_btn2)

        # Добавляем карточку на основной макет
        vbox.addWidget(card_container)

        if main_window.stacked_widget:
            main_window.stacked_widget.addWidget(update_widget)
        update_subwindow_styles()
        animate_widget_switch(update_widget)

        # Открываем ссылку на загрузку
        download_btn.clicked.connect(lambda: os.startfile(dl_url))

        def return_to_main2():
            def do_remove_update_widget():
                if main_window.stacked_widget:
                    main_window.stacked_widget.removeWidget(update_widget)
                update_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove_update_widget)
        ok_btn2.clicked.connect(return_to_main2)

    # --- Окно «версия актуальна» ---
    def show_no_update_needed(local_version: str, latest_version: str):
        done_widget = QWidget()
        vbox = QVBoxLayout(done_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(done_widget)

        card_container = QWidget()
        card_container.setObjectName("update_card")
        # Динамическая ширина: от 240 до 600 px
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

        # Replace emoji label with SVG
        emoji_label = create_icon_label("check-circle.svg", size=40)
        emoji_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        emoji_label.setFixedHeight(48)
        emoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji_label.setObjectName("message_emoji")
        emoji_label.setStyleSheet("font-size: 48px;")
        card_layout.addWidget(emoji_label)

        installed_lbl = QLabel(f"ㅤУстановленная версия: <b>v{local_version}</b>ㅤ")
        installed_lbl.setTextFormat(Qt.TextFormat.RichText)
        installed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(installed_lbl)

        latest_lbl = QLabel(f"ㅤПоследняя версия: <b>v{latest_version}</b>ㅤ")
        latest_lbl.setTextFormat(Qt.TextFormat.RichText)
        latest_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(latest_lbl)

        info_label = QLabel("ㅤУ вас установлена последняя версия.ㅤ")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(False)
        card_layout.addWidget(info_label)

        ok_btn = QPushButton("Окей")
        card_layout.addWidget(ok_btn)

        vbox.addWidget(card_container)

        if main_window.stacked_widget:
            main_window.stacked_widget.addWidget(done_widget)
        update_subwindow_styles()
        animate_widget_switch(done_widget)

        def return_to_main():
            def do_remove():
                if main_window.stacked_widget:
                    main_window.stacked_widget.removeWidget(done_widget)
                done_widget.deleteLater()
            animate_widget_switch(central_widget, on_finish=do_remove)
        ok_btn.clicked.connect(return_to_main)

    # --- Функция проверки обновлений ---
    def check_for_updates():
        import json as _json  # локальный импорт, чтобы не конфликтовать
        # Prevent parallel runs
        if getattr(check_for_updates, "_running", False):
            return
        setattr(check_for_updates, "_running", True)

        def worker():
            try:
                # Используем resource_path, чтобы корректно находить файл как при разработке, так и внутри собранного exe
                with open(resource_path("app_info.json"), "r", encoding="utf-8") as _f:
                    _local = _json.load(_f)
                local_ver = _local.get("version", "0.0.0")
                import time as _t
                remote_url = _local.get("update_info_url")
                if not remote_url:
                    raise RuntimeError("URL обновления не найден.")
                remote_data = _json.loads(urllib.request.urlopen(f"{remote_url}?t={int(_t.time())}", timeout=10).read().decode("utf-8"))
                remote_ver = remote_data.get("version", "0.0.0")
                download_url = remote_data.get("download_url", "https://github.com/AvenCores/Goida-AI-Unlocker")

                def _parse(v):
                    return tuple(int(x) for x in v.strip("vV").split(".") if x.isdigit())
                newer = _parse(remote_ver) > _parse(local_ver)
                if newer:
                    QTimer.singleShot(0, main_window, lambda lv=local_ver, rv=remote_ver, u=download_url: show_update_available(lv, rv, u))
                else:
                    QTimer.singleShot(0, main_window, lambda lv=local_ver, rv=remote_ver: show_no_update_needed(lv, rv))
            except Exception as e:
                err = f"Не удалось проверить обновления.\n{e}"
                QTimer.singleShot(0, main_window, lambda m=err: show_message_and_return(m, success=False, animate=True))
            finally:
                setattr(check_for_updates, "_running", False)
        threading.Thread(target=worker, daemon=True).start()
    # --------------------------------------------------------------

    # --- Новая функция: промежуточное окно установки/удаления/обновления ---
    def start_installation(action: str = "install"):
        """Показывает окно ожидания и выполняет установку / обновление / удаление в фоне.
        action: 'install' | 'update' | 'uninstall'
        """
        # Создаём виджет ожидания
        processing_widget = QWidget()
        vbox = QVBoxLayout(processing_widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        fix_widget_size(processing_widget)

        # ---- Карточка ожидания ----
        card_container = QWidget()
        card_container.setObjectName("wait_card")
        # Позволяем карточке расширяться при необходимости, но не более 600px
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
            msg_text = "Установка обхода...\nㅤПожалуйста, подождите.ㅤ"
        elif action == "update":
            msg_text = "Обновление обхода...\nㅤПожалуйста, подождите.ㅤ"
        else:  # uninstall
            msg_text = "Удаление обхода...\nㅤПожалуйста, подождите.ㅤ"

        # Отображаем каждую строку текста отдельным QLabel, чтобы не использовать \n внутри одного блока
        for line in msg_text.split("\n"):
            if not line.strip():
                continue  # пропускаем пустые строки
            lbl = QLabel(line)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(False)
            card_layout.addWidget(lbl)

        vbox.addWidget(card_container)

        # Добавляем на стек и показываем
        if main_window.stacked_widget:
            main_window.stacked_widget.addWidget(processing_widget)
        update_subwindow_styles()
        animate_widget_switch(processing_widget)

        # Функция для обновления статуса строки состояния
        def update_status_label():
            current_status = "Установлен" if check_installation() else "Не установлен"
            current_color = "#43b581" if current_status == "Установлен" else "#e06c75"
            textinformer.setText(f"ㅤОбход блокировок - <span style='color:{current_color}; font-weight:bold;'>{current_status}</span>ㅤ")
            # -------- NEW: refresh hosts version label --------
            update_version_label()
            # ---------------------------------------------------

        # Завершение процесса: скрыть окно ожидания и показать итоговое сообщение
        def finish(ok_result):
            # Сначала показываем итоговое сообщение с анимацией
            if ok_result:
                if action == "install":
                    success_msg = "Файл hosts успешно установлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ"
                elif action == "update":
                    success_msg = "Файл hosts успешно обновлён!\nㅤВозможно потребуется перезапустить браузер.ㅤ"
                else:  # uninstall
                    success_msg = "Файл hosts успешно восстановлен!\nㅤВозможно потребуется перезапустить браузер.ㅤ"
                show_message_and_return(success_msg, success=True, animate=True)
            else:
                if action == "install":
                    error_msg = "Не удалось установить файл hosts.\nㅤЗапустите программу от имени Администратора.ㅤ"
                elif action == "update":
                    error_msg = "Не удалось обновить файл hosts.\nㅤЗапустите программу от имени Администратора.ㅤ"
                else:
                    error_msg = "Не удалось восстановить файл hosts.\nㅤЗапустите программу от имени Администратора.ㅤ"
                show_message_and_return(error_msg, success=False, animate=True)

            # После завершения анимации (≈400 мс) убираем виджет ожидания
            def remove_processing():
                if main_window.stacked_widget and processing_widget in [main_window.stacked_widget.widget(i) for i in range(main_window.stacked_widget.count())]:
                    main_window.stacked_widget.removeWidget(processing_widget)
                processing_widget.deleteLater()
            QTimer.singleShot(400, remove_processing)

            # Обновляем индикатор состояния чуть позже, чтобы окно успело появиться
            QTimer.singleShot(500, update_status_label)

        # Запускаем блокирующую операцию в отдельном потоке
        def worker():
            if action in ("install", "update"):
                result = update_hosts_as_admin()
            else:
                result = restore_original_hosts()
            # Публикуем результат в главный поток через таймер, привязанный к main_window
            QTimer.singleShot(0, main_window, lambda res=result: finish(res))

        threading.Thread(target=worker, daemon=True).start()

    def on_install_click():
        # Определяем действие по тексту кнопки
        if "Обновить" in button.text():
            start_installation("update")
        else:
            start_installation("install")

    def on_uninstall_click():
        start_installation("uninstall")

    button.clicked.connect(on_install_click)
    button2.clicked.connect(on_uninstall_click)

    def switch_theme():
        if main_window.is_animating: return
        main_window.is_animating = True
        animation_steps, time_interval = 15, 20

        def fade_out(step=1.0):
            if step >= 0:
                main_window.setWindowOpacity(step)
                QTimer.singleShot(time_interval, lambda: fade_out(step - 1.0 / animation_steps))
            else:
                main_window.setWindowOpacity(0)
                # Temporarily disable updates to reduce overdraw while changing many styles
                main_window.setUpdatesEnabled(False)
                main_window.dark_theme = not main_window.dark_theme
                main_window.styles = get_stylesheet(main_window.dark_theme)
                main_window.setStyleSheet(main_window.styles["main"])
                textinformer.setStyleSheet(main_window.styles["label"])
                # Обновляем заголовок согласно теме
                app_title_label.setText(main_window.styles["about_title_html"])
                app_title_label.setStyleSheet(main_window.styles["about_title_style"])
                # -------- NEW: update version label style --------
                version_label.setStyleSheet(main_window.styles["label"])
                # --------------------------------------------------
                button.setStyleSheet(main_window.styles["button1"])
                button2.setStyleSheet(main_window.styles["button2"])
                theme_button.setStyleSheet(main_window.styles["theme"])
                donate_button.setStyleSheet(main_window.styles["theme"])
                about_button.setStyleSheet(main_window.styles["theme"])
                # --- Update status block style on theme change ---
                _light_block = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
                _dark_block = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
                status_container.setStyleSheet(_dark_block if main_window.dark_theme else _light_block)
                update_subwindow_styles()
                # --- NEW: refresh icons tint ---
                refresh_icons()
                # Re-enable updates now that styles are applied
                main_window.setUpdatesEnabled(True)
                fade_in()

        def fade_in(step=0.0):
            if step <= 1.0:
                main_window.setWindowOpacity(step)
                QTimer.singleShot(time_interval, lambda: fade_in(step + 1.0 / animation_steps))
            else:
                main_window.setWindowOpacity(1.0)
                main_window.is_animating = False

        fade_out()
    theme_button.clicked.connect(switch_theme)

    def show_donate_window():
        # --- Re-designed Donate window ---
        donate_widget = QWidget()
        donate_layout = QVBoxLayout(donate_widget)
        donate_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        donate_layout.setSpacing(24)
        # Leave some breathing room around the content – values scale with window size for rudimentary adaptivity
        donate_layout.setContentsMargins(20, 20, 20, 20)

        fix_widget_size(donate_widget)

        # The main content block (card look)
        card_container = QWidget()
        card_container.setObjectName("donate_card")
        card_container.setMaximumWidth(380)  # Prevent the card from becoming too wide on large windows
        card_container.setMinimumWidth(240)

        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)

        title_lbl = QLabel("Поддержать автора")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size:22px; font-weight:600;")
        card_layout.addWidget(title_lbl)

        card = "2202 2050 7215 4401"
        card_lbl = QLabel(f"ㅤSBER: <b>{card}</b>ㅤ")
        card_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lbl.setStyleSheet("font-size:16px;")
        card_layout.addWidget(card_lbl)

        copy_btn = QPushButton("Скопировать номер карты")
        card_layout.addWidget(copy_btn)

        # Style card depending on theme
        light_style = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark_style = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card_container.setStyleSheet(dark_style if main_window.dark_theme else light_style)

        donate_layout.addWidget(card_container)

        # Back button below the card
        back_button = QPushButton("  В меню  ")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.setStyleSheet(main_window.styles["theme"])
        donate_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Apply button style only to copy button
        copy_btn.setStyleSheet(main_window.styles["button1"])

        def copy_card():
            QApplication.clipboard().setText(card)

            # Prevent multiple animations
            if getattr(copy_btn, "_animating", False):
                return
            setattr(copy_btn, "_animating", True)

            original_text = "Скопировать номер карты"
            success_text = "Скопировано"

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
                                    copy_btn.setGraphicsEffect(None)  # type: ignore[arg-type]
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

        if main_window.stacked_widget:
            main_window.stacked_widget.addWidget(donate_widget)
        update_subwindow_styles()
        animate_widget_switch(donate_widget)
    donate_button.clicked.connect(show_donate_window)

    layout.addWidget(button)
    layout.addWidget(button2)
    theme_donate_hbox = QHBoxLayout()
    theme_donate_hbox.setSpacing(12)
    theme_donate_hbox.addWidget(theme_button)
    theme_donate_hbox.addWidget(donate_button)
    layout.addLayout(theme_donate_hbox)
    layout.addStretch()
    # Кнопка проверки обновлений выводится вертикально перед кнопкой «О программе»
    layout.addWidget(update_button)
    layout.addWidget(about_button)

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
        github_btn.setStyleSheet(main_window.styles["theme"] + "\nQToolButton { font-size:13px; padding:6px 12px; }")  # compact text under icon
        github_btn.setProperty("icon_name", "github.svg")
        github_btn.setProperty("icon_force_dark", True)
        github_btn.clicked.connect(lambda: os.startfile("https://github.com/AvenCores"))

        # Highlighted repository button
        repo_btn = QToolButton()
        repo_btn.setText("Репозиторий")
        repo_btn.setIcon(get_icon("github.svg", 24, force_dark=True))
        repo_btn.setIconSize(QSize(24, 24))
        repo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        repo_btn.setProperty("icon_name", "github.svg")
        repo_btn.setProperty("icon_force_dark", True)
        repo_btn.setStyleSheet(
            main_window.styles["theme"] +
            "\nQToolButton { font-size:13px; padding:6px 12px; background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e06c75, stop:1 #d64c58); color:white; border:1px solid #b94852; border-radius:8px; }\nQToolButton:pressed { background:#c94c57; }"
        )
        repo_btn.clicked.connect(lambda: os.startfile("https://github.com/AvenCores/Goida-AI-Unlocker"))
        # Grid for buttons in multiple rows
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Put GitHub profile first
        grid.addWidget(github_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)

        social_buttons = [
            ("Telegram", "https://t.me/avencoresyt", "send.svg"),
            ("YouTube", "https://youtube.com/@avencores", "play.svg"),
            ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"),
            ("Dzen", "https://dzen.ru/avencores", "book-open.svg"),
            ("VK", "https://vk.com/avencoresvk", "users.svg"),
        ]
        about_buttons = [github_btn, repo_btn]
        col_count = 3  # number of columns in the grid
        row = 0
        col = 1  # start after GitHub in (0,0)
        for label, url, icon_file in social_buttons:
            btn = QToolButton()
            btn.setText(label)
            btn.setIcon(get_icon(icon_file, 24, force_dark=True))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setProperty("icon_name", icon_file)
            btn.setProperty("icon_force_dark", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(main_window.styles["theme"] + "\nQToolButton { font-size:13px; padding:6px 12px; }")  # compact text under icon
            btn.clicked.connect(lambda checked=False, u=url: os.startfile(u))
            grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            about_buttons.append(btn)
            col += 1
            if col >= col_count:
                row += 1
                col = 0

        vbox.addLayout(grid)
        # Separate repo button below the grid, above the menu button
        repo_btn.setStyleSheet(main_window.styles["theme"] + "\nQToolButton { font-size:13px; padding:6px 12px; }")
        vbox.addSpacing(8)
        vbox.addWidget(repo_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        # Match Donate's 24px gap (About vbox spacing is 8px → add remaining extra)
        vbox.addSpacing(8)

        # Defer width equalization until styles are applied
        def _equalize_about_button_widths():
            if not about_buttons:
                return
            # Compute required width per button using font metrics (text or icon, whichever wider)
            def _req_w(b):
                fm = b.fontMetrics() if hasattr(b, "fontMetrics") else QFontMetrics(b.font())
                text_w = fm.horizontalAdvance(b.text())
                icon_w = b.iconSize().width() if hasattr(b, "iconSize") else 24
                base = max(text_w, icon_w)
                return base + 24  # horizontal padding allowance
            ref_w = max(max(b.sizeHint().width(), _req_w(b)) for b in about_buttons)
            for b in about_buttons:
                b.setFixedWidth(ref_w)

        back_button = QPushButton("  В меню  ")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
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
        # Equalize widths after styles are applied
        QTimer.singleShot(0, lambda: _equalize_about_button_widths())
        animate_widget_switch(about_widget)
    about_button.clicked.connect(show_about_window)

    # ----------------------- NEW: async updater -----------------------
    def update_version_label():
        """Refresh version_label text and adapt the install button caption depending on hosts version."""
        now_ts = _time.time()
        last_run = getattr(update_version_label, "_last_run", 0.0)
        if getattr(update_version_label, "_running", False) or (now_ts - last_run) < 1.0:
            return
        setattr(update_version_label, "_running", True)
        setattr(update_version_label, "_last_run", now_ts)

        def worker():
            word, clr = get_hosts_version_status()
            def apply():
                version_label.setText(
                    f"Версия hosts - <span style='color:{clr}; font-weight:bold;'>{word}</span>")
                # Изменяем надпись кнопки в зависимости от актуальности
                if word == "Устарело":
                    button.setText(" Обновить обход блокировок")
                else:
                    button.setText(" Установить обход блокировок")
            QTimer.singleShot(0, main_window, apply)
            setattr(update_version_label, "_running", False)
        threading.Thread(target=worker, daemon=True).start()
    # -----------------------------------------------------------------

    # Initial version check
    update_version_label()

    main_window.show()
    on_main_window_resize()

    sys.exit(app.exec())