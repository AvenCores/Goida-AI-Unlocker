from typing import Callable, Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from app.core.hosts_manager import HostsManager
from app.core.constants import HOSTS_PATH
from app.gui.localization import tr
from app.gui.icons import create_icon_label


def _editor_stylesheet(dark_theme: bool) -> str:
    if dark_theme:
        return (
            "QPlainTextEdit {"
            "  background: #1a1e24; color: #e6edf3;"
            "  border: 1.5px solid #3c434d; border-radius: 10px;"
            "  padding: 12px; font-size: 13px;"
            "  selection-background-color: #264f78;"
            "}"
            "QPlainTextEdit:focus { border-color: #2d7dff; }"
        )
    return (
        "QPlainTextEdit {"
        "  background: #fafbfc; color: #1a1a1a;"
        "  border: 1.5px solid #cfd4db; border-radius: 10px;"
        "  padding: 12px; font-size: 13px;"
        "  selection-background-color: #add6ff;"
        "}"
        "QPlainTextEdit:focus { border-color: #0078d4; }"
    )


def build_hosts_editor_page(
    hosts_manager: HostsManager,
    styles: dict,
    dark_theme: bool,
    return_callback: Callable[[], None],
    save_callback: Optional[Callable[[str], None]] = None,
    fix_size_fn: Optional[Callable[[QWidget], None]] = None,
) -> QWidget:
    """Build the in-app hosts file editor page.

    Args:
        hosts_manager: HostsManager instance for reading/saving.
        styles: Current stylesheet dict.
        dark_theme: Whether dark theme is active.
        return_callback: Called when user clicks "Back".
        save_callback: Called with new content on save (runs in worker).
        fix_size_fn: Optional size constraint function.

    Returns:
        The editor page QWidget.
    """
    page = QWidget()
    vbox = QVBoxLayout(page)
    vbox.setSpacing(12)
    vbox.setContentsMargins(20, 16, 20, 16)
    if fix_size_fn:
        fix_size_fn(page)

    # Header
    header_hbox = QHBoxLayout()
    header_hbox.setSpacing(8)

    icon_label = create_icon_label("book-open.svg", size=24, dark_theme=dark_theme)
    header_hbox.addWidget(icon_label)

    title = QLabel(tr("hosts_editor_title"))
    title.setStyleSheet(
        f"font-size: 18px; font-weight: 600; color: {'#f3f6fd' if dark_theme else '#1a1a1a'}; background: transparent;"
    )
    header_hbox.addWidget(title)
    header_hbox.addStretch()

    path_label = QLabel(str(HOSTS_PATH))
    path_label.setStyleSheet(
        f"font-size: 11px; color: {'#8b949e' if dark_theme else '#666666'}; background: transparent;"
    )
    header_hbox.addWidget(path_label)
    vbox.addLayout(header_hbox)

    # Text editor
    editor = QPlainTextEdit()
    editor.setPlainText(hosts_manager.read())
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    editor.setStyleSheet(_editor_stylesheet(dark_theme))
    font = QFont("Consolas", 11)
    font.setStyleHint(QFont.StyleHint.Monospace)
    editor.setFont(font)
    editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    vbox.addWidget(editor, 1)

    # Buttons
    btn_hbox = QHBoxLayout()
    btn_hbox.setSpacing(12)

    back_btn = QPushButton(tr("back_to_menu"))
    back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    back_btn.setProperty("style_role", "theme")
    back_btn.setStyleSheet(styles["theme"])
    back_btn.clicked.connect(return_callback)
    btn_hbox.addWidget(back_btn)

    btn_hbox.addStretch()

    save_btn = QPushButton(tr("hosts_editor_save"))
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn.setProperty("style_role", "button1")
    save_btn.setStyleSheet(styles["button1"])
    btn_hbox.addWidget(save_btn)

    vbox.addLayout(btn_hbox)

    # Save logic
    def _on_save():
        content = editor.toPlainText()
        if save_callback:
            save_callback(content)

    save_btn.clicked.connect(_on_save)

    return page


def build_hosts_backup_viewer_page(
    hosts_manager: HostsManager,
    styles: dict,
    dark_theme: bool,
    return_callback: Callable[[], None],
    fix_size_fn: Optional[Callable[[QWidget], None]] = None,
) -> QWidget:
    """Build the in-app hosts backup viewer page.

    Args:
        hosts_manager: HostsManager instance for reading backups.
        styles: Current stylesheet dict.
        dark_theme: Whether dark theme is active.
        return_callback: Called when user clicks "Back".
        fix_size_fn: Optional size constraint function.

    Returns:
        The backup viewer page QWidget.
    """
    page = QWidget()
    vbox = QVBoxLayout(page)
    vbox.setSpacing(12)
    vbox.setContentsMargins(20, 16, 20, 16)
    if fix_size_fn:
        fix_size_fn(page)

    # Header
    header_hbox = QHBoxLayout()
    header_hbox.setSpacing(8)

    icon_label = create_icon_label("clock.svg", size=24, dark_theme=dark_theme)
    header_hbox.addWidget(icon_label)

    title = QLabel(tr("hosts_backup_viewer_title"))
    title.setStyleSheet(
        f"font-size: 18px; font-weight: 600; color: {'#f3f6fd' if dark_theme else '#1a1a1a'}; background: transparent;"
    )
    header_hbox.addWidget(title)
    header_hbox.addStretch()
    vbox.addLayout(header_hbox)

    # Backup selector
    selector_hbox = QHBoxLayout()
    selector_hbox.setSpacing(8)

    selector_label = QLabel(tr("hosts_backup_select"))
    selector_label.setStyleSheet(
        f"font-size: 13px; color: {'#e6edf3' if dark_theme else '#1a1a1a'}; background: transparent;"
    )
    selector_hbox.addWidget(selector_label)

    combo = QComboBox()
    combo.setStyleSheet(styles["combo"])
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    combo.setMinimumWidth(300)
    selector_hbox.addWidget(combo, 1)
    vbox.addLayout(selector_hbox)

    # Text viewer (read-only)
    viewer = QPlainTextEdit()
    viewer.setReadOnly(True)
    viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    viewer.setStyleSheet(_editor_stylesheet(dark_theme))
    font = QFont("Consolas", 11)
    font.setStyleHint(QFont.StyleHint.Monospace)
    viewer.setFont(font)
    viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    vbox.addWidget(viewer, 1)

    # Buttons
    btn_hbox = QHBoxLayout()
    btn_hbox.setSpacing(12)

    back_btn = QPushButton(tr("back_to_menu"))
    back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    back_btn.setProperty("style_role", "theme")
    back_btn.setStyleSheet(styles["theme"])
    back_btn.clicked.connect(return_callback)
    btn_hbox.addWidget(back_btn)

    btn_hbox.addStretch()
    vbox.addLayout(btn_hbox)

    # Populate backups
    backups: list[Path] = hosts_manager.get_backups_list()

    if not backups:
        combo.addItem(tr("hosts_backup_none"), None)
        viewer.setPlainText(tr("hosts_backup_none_info"))
    else:
        for bp in backups:
            try:
                mtime = bp.stat().st_mtime
                import time as _time
                date_str = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(mtime))
            except Exception:
                date_str = bp.name
            combo.addItem(f"{date_str}  ({bp.name})", str(bp))

        # Load first backup
        def _load_backup(index: int):
            path_str = combo.itemData(index)
            if not path_str:
                viewer.setPlainText(tr("hosts_backup_none_info"))
                return
            try:
                content = Path(path_str).read_text(encoding="utf-8", errors="ignore")
                viewer.setPlainText(content)
            except Exception as e:
                viewer.setPlainText(f"Error: {e}")

        combo.currentIndexChanged.connect(_load_backup)
        _load_backup(0)

    return page
