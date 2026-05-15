import os
import sys
import shutil
import subprocess
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer
from app.core.logger import logger
from app.core.constants import HOSTS_PATH, HOSTS_BACKUP_DIR
from app.core.hosts_manager import HostsManager
from app.utils.helpers import open_target
from app.gui.localization import tr, normalize_language, CURRENT_LANGUAGE

def _show_open_hosts_error(detail: str, _inline_callback=None):
    lang = CURRENT_LANGUAGE
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
