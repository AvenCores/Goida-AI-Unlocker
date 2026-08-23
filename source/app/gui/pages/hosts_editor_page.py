from pathlib import Path
import time
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from app.core.hosts_manager import HostsManager
from app.core.constants import HOSTS_PATH
from app.gui.localization import tr
from app.gui.icons import get_icon


def _monospace_font() -> QFont:
    font = QFont("Consolas", 11)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class _HeaderedPage(QWidget):
    """Общая основа страниц с заголовком (иконка + название + подпись)."""

    def __init__(self, styles: dict, dark_theme: bool,
                 icon_name: str, return_callback: Callable[[], None]):
        super().__init__()
        self.styles = styles
        self.dark_theme = dark_theme

        self._vbox = QVBoxLayout(self)
        self._vbox.setSpacing(12)
        self._vbox.setContentsMargins(20, 16, 20, 16)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(
            get_icon(icon_name, 24, dark_theme=dark_theme).pixmap(24, 24)
        )
        header.addWidget(self.icon_label)

        self.title_label = QLabel()
        header.addWidget(self.title_label)
        header.addStretch()

        self.subtitle_label = QLabel()
        header.addWidget(self.subtitle_label)
        self._vbox.addLayout(header)

        self.back_button = QPushButton(tr("back_to_menu"))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(return_callback)

    def _make_code_view(self) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFont(_monospace_font())
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return view

    def apply_texts(self):
        pass

    def apply_theme(self, styles: dict, dark_theme: bool):
        self.styles = styles
        self.dark_theme = dark_theme
        self.title_label.setStyleSheet(styles["page_title"])
        self.subtitle_label.setStyleSheet(styles["page_subtitle"])
        self.back_button.setStyleSheet(styles["theme"])


class HostsEditorPage(_HeaderedPage):
    """Встроенный редактор hosts. Сохранение активно только при изменениях."""

    def __init__(self, hosts_manager: HostsManager, styles: dict, dark_theme: bool,
                 return_callback: Callable[[], None],
                 save_callback: Optional[Callable[[str], None]] = None):
        super().__init__(styles, dark_theme, "book-open.svg", return_callback)

        self.editor = self._make_code_view()
        original = hosts_manager.read()
        self.editor.setPlainText(original)
        self._original_content = original
        self.editor.textChanged.connect(self._on_text_changed)
        self._vbox.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(self.back_button)
        buttons.addStretch()

        self.save_button = QPushButton(f"  {tr('hosts_editor_save')}  ")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setProperty("style_role", "button1")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._request_save)
        buttons.addWidget(self.save_button)
        self._vbox.addLayout(buttons)

        # Ctrl+S — сохранить
        shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        shortcut.activated.connect(self._request_save)

        self._save_callback = save_callback
        self.apply_theme(styles, dark_theme)
        self.apply_texts()

    def _on_text_changed(self):
        modified = self.editor.toPlainText() != self._original_content
        self.save_button.setEnabled(modified)

    def _request_save(self):
        if not self.save_button.isEnabled():
            return
        if self._save_callback:
            self._save_callback(self.editor.toPlainText())

    def apply_texts(self):
        self.title_label.setText(tr("hosts_editor_title"))
        self.subtitle_label.setText(str(HOSTS_PATH))
        self.back_button.setText(tr("back_to_menu"))
        self.save_button.setText(f"  {tr('hosts_editor_save')}  ")

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.editor.setStyleSheet(styles["editor"])
        self.save_button.setStyleSheet(styles["button1"])
        self.icon_label.setPixmap(
            get_icon("book-open.svg", 24, dark_theme=dark_theme).pixmap(24, 24)
        )


class HostsBackupViewerPage(_HeaderedPage):
    """Просмотрщик резервных копий hosts (только чтение)."""

    def __init__(self, hosts_manager: HostsManager, styles: dict, dark_theme: bool,
                 return_callback: Callable[[], None]):
        super().__init__(styles, dark_theme, "clock.svg", return_callback)

        selector = QHBoxLayout()
        selector.setSpacing(8)

        self.select_label = QLabel()
        selector.addWidget(self.select_label)

        self.backup_combo = QComboBox()
        self.backup_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_combo.setMinimumWidth(300)
        selector.addWidget(self.backup_combo, 1)
        self._vbox.addLayout(selector)

        self.viewer = self._make_code_view()
        self.viewer.setReadOnly(True)
        self._vbox.addWidget(self.viewer, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(self.back_button)
        buttons.addStretch()
        self._vbox.addLayout(buttons)

        self._populate(hosts_manager)
        self.apply_theme(styles, dark_theme)
        self.apply_texts()

    def _populate(self, hosts_manager: HostsManager):
        backups: list[Path] = hosts_manager.get_backups_list()
        if not backups:
            self.backup_combo.addItem(tr("hosts_backup_none"), None)
            self.viewer.setPlainText(tr("hosts_backup_none_info"))
            return

        for bp in backups:
            try:
                mtime = bp.stat().st_mtime
                date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            except Exception:
                date_str = bp.name
            self.backup_combo.addItem(f"{date_str}  ({bp.name})", str(bp))

        self.backup_combo.currentIndexChanged.connect(self._load_selected_backup)
        self._load_selected_backup(0)

    def _load_selected_backup(self, index: int):
        path_str = self.backup_combo.itemData(index)
        if not path_str:
            self.viewer.setPlainText(tr("hosts_backup_none_info"))
            return
        try:
            content = Path(path_str).read_text(encoding="utf-8", errors="ignore")
            self.viewer.setPlainText(content)
        except Exception as e:
            self.viewer.setPlainText(f"Error: {e}")

    def apply_texts(self):
        self.title_label.setText(tr("hosts_backup_viewer_title"))
        self.select_label.setText(tr("hosts_backup_select"))
        self.back_button.setText(tr("back_to_menu"))

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.viewer.setStyleSheet(styles["editor"])
        self.backup_combo.setStyleSheet(styles["combo"])
        self.select_label.setStyleSheet(styles["page_text"])
        self.icon_label.setPixmap(
            get_icon("clock.svg", 24, dark_theme=dark_theme).pixmap(24, 24)
        )
