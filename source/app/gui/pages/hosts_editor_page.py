from pathlib import Path
import re
import time
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QSizePolicy, QLineEdit, QApplication
)
from PySide6.QtCore import Qt, QRect, QSize, QTimer
from PySide6.QtGui import (
    QFont, QKeySequence, QShortcut, QPainter, QColor,
    QTextCharFormat, QTextCursor, QSyntaxHighlighter
)

from app.core.hosts_manager import HostsManager
from app.core.constants import HOSTS_PATH
from app.core.logger import logger
from app.gui.localization import tr
from app.gui.icons import get_icon

# Максимум подсвечиваемых совпадений поиска (защита от тормозов на больших файлах)
_MAX_SEARCH_HIGHLIGHTS = 2000

_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_DOMAIN_TOKEN_RE = re.compile(r"(?<=\s)[A-Za-z0-9_.\-]+\.[A-Za-z]{2,}(?=\s|$|#)")


def _monospace_font() -> QFont:
    font = QFont("Consolas", 11)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class _HostsHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса hosts: комментарии, IPv4-адреса, домены."""

    def __init__(self, document, dark_theme: bool):
        super().__init__(document)
        self._dark = dark_theme
        self._build_rules()

    def set_dark_theme(self, dark_theme: bool):
        if dark_theme == self._dark:
            return
        self._dark = dark_theme
        self._build_rules()
        self.rehighlight()

    def _build_rules(self):
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6f7a8a" if self._dark else "#9aa0aa"))
        comment_fmt.setFontItalic(True)

        ip_fmt = QTextCharFormat()
        ip_fmt.setForeground(QColor("#5aa2ff" if self._dark else "#0063b1"))
        ip_fmt.setFontWeight(QFont.Weight.Bold)

        domain_fmt = QTextCharFormat()
        domain_fmt.setForeground(QColor("#79c37a" if self._dark else "#1e7d32"))

        self._rules = (
            (re.compile(r"\d{1,3}(?:\.\d{1,3}){3}"), ip_fmt),
            (_DOMAIN_TOKEN_RE, domain_fmt),
        )
        self._comment_fmt = comment_fmt

    def highlightBlock(self, text):
        hash_pos = text.find("#")
        code = text[:hash_pos] if hash_pos >= 0 else text
        for pattern, fmt in self._rules:
            for match in pattern.finditer(code):
                self.setFormat(match.start(), len(match.group()), fmt)
        if hash_pos >= 0:
            self.setFormat(hash_pos, len(text) - hash_pos, self._comment_fmt)


class _LineNumberArea(QWidget):
    """Панель слева от редактора, на которой рисуются номера строк."""

    def __init__(self, editor: "_LineNumbersEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class _LineNumbersEditor(QPlainTextEdit):
    """QPlainTextEdit с панелью нумерации строк (текущая строка подсвечивается)."""

    def __init__(self):
        super().__init__()
        self._dark_theme = True
        self._line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width()

    def set_line_number_theme(self, dark_theme: bool):
        self._dark_theme = dark_theme
        self._line_number_area.update()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _count: int = 0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)
        if self._dark_theme:
            bg, fg, current_fg = QColor("#232a35"), QColor("#7d8593"), QColor("#e6e9f0")
        else:
            bg, fg, current_fg = QColor("#f0f2f6"), QColor("#9aa0aa"), QColor("#1a1a1a")
        painter.fillRect(event.rect(), bg)

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                painter.setPen(current_fg if number == current else fg)
                painter.drawText(
                    0, top, self._line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1


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
    """Встроенный редактор hosts: нумерация строк, подсветка синтаксиса,
    поиск, валидация перед сохранением и подтверждение выхода с правками."""

    MAX_SHOWN_ISSUES = 3

    def __init__(self, hosts_manager: HostsManager, styles: dict, dark_theme: bool,
                 return_callback: Callable[[], None],
                 save_callback: Optional[Callable[[str], None]] = None):
        super().__init__(styles, dark_theme, "book-open.svg", return_callback)
        self._return_callback = return_callback
        self._save_callback = save_callback
        self._last_issues: list = []
        self._matches: list[tuple[int, int]] = []
        self._search_index = -1

        # --- Редактор ---
        self.editor = _LineNumbersEditor()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(_monospace_font())
        self._highlighter = _HostsHighlighter(self.editor.document(), dark_theme)
        self._original_content = hosts_manager.read()
        self._vbox.addWidget(self.editor, 1)

        # --- Статус: строки/символы/изменён ---
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._vbox.addWidget(self.status_label)

        # --- Панель поиска (скрыта, открывается по Ctrl+F) ---
        self.search_bar = QWidget()
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh_search)
        self.search_edit.returnPressed.connect(self._find_next)
        search_layout.addWidget(self.search_edit, 1)
        self.search_count_label = QLabel()
        search_layout.addWidget(self.search_count_label)
        self.search_close_button = QPushButton("✕")
        self.search_close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_close_button.setFixedWidth(36)
        self.search_close_button.clicked.connect(lambda: self._toggle_search(False))
        search_layout.addWidget(self.search_close_button)
        self.search_bar.setVisible(False)
        self._vbox.addWidget(self.search_bar)

        # --- Панель подтверждения выхода с несохранёнными правками ---
        self.confirm_panel = QWidget()
        confirm_layout = QHBoxLayout(self.confirm_panel)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.setSpacing(8)
        self.confirm_label = QLabel()
        self.confirm_label.setWordWrap(True)
        confirm_layout.addWidget(self.confirm_label, 1)
        self.confirm_exit_button = QPushButton()
        self.confirm_exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_exit_button.clicked.connect(self._leave)
        confirm_layout.addWidget(self.confirm_exit_button)
        self.confirm_stay_button = QPushButton()
        self.confirm_stay_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_stay_button.clicked.connect(self.confirm_panel.hide)
        confirm_layout.addWidget(self.confirm_stay_button)
        self.confirm_panel.setVisible(False)
        self._vbox.addWidget(self.confirm_panel)

        # --- Панель проблем валидации ---
        self.validation_panel = QWidget()
        validation_layout = QHBoxLayout(self.validation_panel)
        validation_layout.setContentsMargins(0, 0, 0, 0)
        validation_layout.setSpacing(8)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        validation_layout.addWidget(self.validation_label, 1)
        self.validation_save_button = QPushButton()
        self.validation_save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.validation_save_button.clicked.connect(self._do_save)
        validation_layout.addWidget(self.validation_save_button)
        self.validation_back_button = QPushButton()
        self.validation_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.validation_back_button.clicked.connect(self.validation_panel.hide)
        validation_layout.addWidget(self.validation_back_button)
        self.validation_panel.setVisible(False)
        self._vbox.addWidget(self.validation_panel)

        # --- Кнопки инструментов ---
        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)
        tools_row.addWidget(self.back_button)

        self.undo_button = QPushButton("↶")
        self.undo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_button.setToolTip("Ctrl+Z")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.editor.undo)
        self.editor.undoAvailable.connect(self.undo_button.setEnabled)
        tools_row.addWidget(self.undo_button)

        self.redo_button = QPushButton("↷")
        self.redo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.redo_button.setToolTip("Ctrl+Y")
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self.editor.redo)
        self.editor.redoAvailable.connect(self.redo_button.setEnabled)
        tools_row.addWidget(self.redo_button)

        self.wrap_button = QPushButton()
        self.wrap_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wrap_button.setCheckable(True)
        self.wrap_button.toggled.connect(self._toggle_wrap)
        tools_row.addWidget(self.wrap_button)

        tools_row.addStretch()

        self.copy_path_button = QPushButton()
        self.copy_path_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_path_button.clicked.connect(self._copy_path)
        tools_row.addWidget(self.copy_path_button)
        self._vbox.addLayout(tools_row)

        # --- Кнопки действий ---
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()

        self.reset_button = QPushButton()
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._reset_to_original)
        buttons.addWidget(self.reset_button)

        self.save_button = QPushButton()
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._request_save)
        buttons.addWidget(self.save_button)
        self._vbox.addLayout(buttons)

        # Кнопка «В меню» из _HeaderedPage ведёт через подтверждение
        self.back_button.clicked.disconnect()
        self.back_button.clicked.connect(self._request_return)

        # Горячие клавиши
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.activated.connect(self._request_save)
        self._find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._find_shortcut.activated.connect(lambda: self._toggle_search(True))
        self._find_next_shortcut = QShortcut(QKeySequence("F3"), self)
        self._find_next_shortcut.activated.connect(self._find_next)

        # Подключение после создания всех виджетов: setPlainText
        # триггерит textChanged, который их использует
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.setPlainText(self._original_content)

        self.apply_theme(styles, dark_theme)
        self.apply_texts()

    # ------------------------------------------------------------------
    # Изменения / статус
    # ------------------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        return self.editor.toPlainText() != self._original_content

    def _on_text_changed(self):
        modified = self._has_unsaved_changes()
        self.save_button.setEnabled(modified)
        self.reset_button.setEnabled(modified)
        self._update_status()
        if self.search_bar.isVisible():
            self._refresh_search()

    def _update_status(self):
        state_key = (
            "hosts_editor_modified" if self._has_unsaved_changes()
            else "hosts_editor_unmodified"
        )
        self.status_label.setText(tr(
            "hosts_editor_stats",
            lines=self.editor.blockCount(),
            chars=len(self.editor.toPlainText()),
            state=tr(state_key),
        ))

    # ------------------------------------------------------------------
    # Поиск (Ctrl+F, Enter/F3 — следующее совпадение)
    # ------------------------------------------------------------------

    def _toggle_search(self, visible: Optional[bool] = None):
        show = not self.search_bar.isVisible() if visible is None else visible
        self.search_bar.setVisible(show)
        if show:
            self.search_edit.setFocus()
            self.search_edit.selectAll()
        else:
            self._matches.clear()
            self._search_index = -1
            self.editor.setExtraSelections([])
            self.search_count_label.clear()
            self.editor.setFocus()

    def _refresh_search(self):
        self._matches.clear()
        query = self.search_edit.text()
        if query:
            lowered = self.editor.toPlainText().lower()
            q = query.lower()
            pos = 0
            while len(self._matches) < _MAX_SEARCH_HIGHLIGHTS:
                idx = lowered.find(q, pos)
                if idx < 0:
                    break
                self._matches.append((idx, idx + len(query)))
                pos = idx + max(1, len(query))
        self._search_index = -1
        self._apply_search_highlights()
        self._update_search_count()

    def _find_next(self):
        if not self._matches:
            return
        pos = self.editor.textCursor().position()
        for i, (start, _end) in enumerate(self._matches):
            if start >= pos:
                self._search_index = i
                break
        else:
            self._search_index = 0
        self._goto_match(self._search_index)

    def _goto_match(self, index: int):
        start, end = self._matches[index]
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self._apply_search_highlights()
        self._update_search_count()

    def _apply_search_highlights(self):
        if not self.search_bar.isVisible():
            return
        selections = []
        for i, (start, end) in enumerate(self._matches):
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(45, 125, 255, 150 if i == self._search_index else 70))
            cursor = self.editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            sel = QPlainTextEdit.ExtraSelection()
            sel.format = fmt
            sel.cursor = cursor
            selections.append(sel)
        self.editor.setExtraSelections(selections)

    def _update_search_count(self):
        total = len(self._matches)
        if not self.search_edit.text():
            self.search_count_label.setText("")
        elif total == 0:
            self.search_count_label.setText("0")
        elif self._search_index >= 0:
            self.search_count_label.setText(f"{self._search_index + 1}/{total}")
        else:
            self.search_count_label.setText(str(total))

    # ------------------------------------------------------------------
    # Валидация перед сохранением
    # ------------------------------------------------------------------

    def _collect_issues(self) -> list[tuple[int, str]]:
        issues: list[tuple[int, str]] = []
        seen_domains: dict[str, int] = {}
        for n, raw in enumerate(self.editor.toPlainText().splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            code = line.split("#", 1)[0].strip()
            tokens = code.split()
            if not tokens:
                continue
            ip = tokens[0]
            if ":" not in ip:
                if _IPV4_RE.match(ip):
                    if any(int(octet) > 255 for octet in ip.split(".")):
                        issues.append((n, tr("hosts_editor_issue_bad_ip")))
                else:
                    issues.append((n, tr("hosts_editor_issue_no_ip")))
            if len(tokens) < 2:
                issues.append((n, tr("hosts_editor_issue_no_domain")))
            else:
                domain = tokens[1].lower()
                if domain in seen_domains:
                    issues.append((n, f"{tr('hosts_editor_issue_duplicate')} ({domain})"))
                else:
                    seen_domains[domain] = n
        return issues

    def _request_save(self):
        if not self.save_button.isEnabled():
            return
        issues = self._collect_issues()
        if issues:
            self._show_validation(issues)
            return
        self._do_save()

    def _show_validation(self, issues: list[tuple[int, str]]):
        self._last_issues = issues
        lines = [
            tr("hosts_editor_issue_line", n=n, issue=msg)
            for n, msg in issues[: self.MAX_SHOWN_ISSUES]
        ]
        hidden = len(issues) - len(lines)
        if hidden > 0:
            lines.append(f"… +{hidden}")
        self.validation_label.setText(
            tr("hosts_editor_validation_title") + "\n" + "\n".join(lines)
        )
        self.validation_panel.show()

    def _do_save(self):
        self.validation_panel.hide()
        self.confirm_panel.hide()
        if self._save_callback:
            self._save_callback(self.editor.toPlainText())

    # ------------------------------------------------------------------
    # Выход с подтверждением / сброс / прочие действия
    # ------------------------------------------------------------------

    def _request_return(self):
        if self._has_unsaved_changes():
            self.confirm_label.setText(tr("hosts_editor_unsaved_warning"))
            self.confirm_panel.show()
            return
        self._leave()

    def _leave(self):
        self.confirm_panel.hide()
        if self._return_callback:
            self._return_callback()

    def _reset_to_original(self):
        self.editor.setPlainText(self._original_content)
        self.validation_panel.hide()
        self.confirm_panel.hide()

    def _toggle_wrap(self, checked: bool):
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def _copy_path(self):
        QApplication.clipboard().setText(str(HOSTS_PATH))
        self.copy_path_button.setText(tr("copied"))
        QTimer.singleShot(1500, lambda: self.copy_path_button.setText(tr("hosts_editor_copy_path")))

    def keyPressEvent(self, event):
        # Esc закрывает панели, затем спрашивает про несохранённые правки,
        # и только потом уходит со страницы
        if event.key() == Qt.Key.Key_Escape:
            if self.search_bar.isVisible():
                self._toggle_search(False)
                event.accept()
                return
            if self.confirm_panel.isVisible():
                self.confirm_panel.hide()
                event.accept()
                return
            if self.validation_panel.isVisible():
                self.validation_panel.hide()
                event.accept()
                return
            if self._has_unsaved_changes():
                self._request_return()
                event.accept()
                return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Тексты и тема
    # ------------------------------------------------------------------

    def _fill_validation_label(self):
        if self._last_issues:
            self._show_validation(self._last_issues)

    def apply_texts(self):
        self.title_label.setText(tr("hosts_editor_title"))
        self.subtitle_label.setText(str(HOSTS_PATH))
        self.back_button.setText(tr("back_to_menu"))
        self.save_button.setText(f"  {tr('hosts_editor_save')}  ")
        self.reset_button.setText(tr("hosts_editor_reset"))
        self.copy_path_button.setText(tr("hosts_editor_copy_path"))
        self.wrap_button.setText(tr("hosts_editor_wrap_lines"))
        self.search_edit.setPlaceholderText(tr("hosts_editor_search_placeholder"))
        self.confirm_label.setText(tr("hosts_editor_unsaved_warning"))
        self.confirm_exit_button.setText(tr("hosts_editor_exit_without_save"))
        self.confirm_stay_button.setText(tr("hosts_editor_stay"))
        self.validation_save_button.setText(tr("hosts_editor_save_anyway"))
        self.validation_back_button.setText(tr("hosts_editor_back_to_edit"))
        if self.validation_panel.isVisible():
            self._fill_validation_label()
        self._update_status()

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.editor.setStyleSheet(styles["editor"])
        self.editor.set_line_number_theme(dark_theme)
        self._highlighter.set_dark_theme(dark_theme)
        self.save_button.setStyleSheet(styles["button1"])
        self.reset_button.setStyleSheet(styles["button2"])
        self.undo_button.setStyleSheet(styles["theme"])
        self.redo_button.setStyleSheet(styles["theme"])
        self.wrap_button.setStyleSheet(styles["theme"])
        self.copy_path_button.setStyleSheet(styles["theme"])
        self.search_edit.setStyleSheet(styles["combo"])
        self.search_count_label.setStyleSheet(styles["page_subtitle"])
        self.search_close_button.setStyleSheet(styles["theme"])
        self.status_label.setStyleSheet(styles["page_subtitle"])
        self.confirm_label.setStyleSheet(styles["page_text"])
        self.confirm_exit_button.setStyleSheet(styles["button2"])
        self.confirm_stay_button.setStyleSheet(styles["theme"])
        self.validation_label.setStyleSheet(styles["page_text"])
        self.validation_save_button.setStyleSheet(styles["button1"])
        self.validation_back_button.setStyleSheet(styles["theme"])
        self.icon_label.setPixmap(
            get_icon("book-open.svg", 24, dark_theme=dark_theme).pixmap(24, 24)
        )


class HostsBackupViewerPage(_HeaderedPage):
    """Просмотрщик резервных копий hosts (только чтение)."""

    def __init__(self, hosts_manager: HostsManager, styles: dict, dark_theme: bool,
                 return_callback: Callable[[], None]):
        super().__init__(styles, dark_theme, "clock.svg", return_callback)
        self._hosts_manager = hosts_manager

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

        self.delete_button = QPushButton()
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._delete_selected_backup)
        buttons.addWidget(self.delete_button)
        self._vbox.addLayout(buttons)

        self.backup_combo.currentIndexChanged.connect(self._load_selected_backup)
        self._populate(hosts_manager)
        self.apply_theme(styles, dark_theme)
        self.apply_texts()

    def _populate(self, hosts_manager: HostsManager):
        self.backup_combo.blockSignals(True)
        self.backup_combo.clear()
        backups: list[Path] = hosts_manager.get_backups_list()
        if not backups:
            self.backup_combo.addItem(tr("hosts_backup_none"), None)
            self.viewer.setPlainText(tr("hosts_backup_none_info"))
            self.delete_button.setEnabled(False)
        else:
            for bp in backups:
                try:
                    mtime = bp.stat().st_mtime
                    date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
                except Exception:
                    date_str = bp.name
                self.backup_combo.addItem(f"{date_str}  ({bp.name})", str(bp))
            self.delete_button.setEnabled(True)
        self.backup_combo.blockSignals(False)
        self._load_selected_backup(self.backup_combo.currentIndex())

    def _delete_selected_backup(self):
        path_str = self.backup_combo.currentData()
        if not path_str:
            return
        try:
            Path(path_str).unlink()
            logger.info("Deleted hosts backup: %s", path_str)
        except Exception as e:
            logger.error("Failed to delete hosts backup %s: %s", path_str, e)
        self._populate(self._hosts_manager)

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
        self.delete_button.setText(tr("hosts_backup_delete"))

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.viewer.setStyleSheet(styles["editor"])
        self.backup_combo.setStyleSheet(styles["combo"])
        self.select_label.setStyleSheet(styles["page_text"])
        self.delete_button.setStyleSheet(styles["button2"])
        self.icon_label.setPixmap(
            get_icon("clock.svg", 24, dark_theme=dark_theme).pixmap(24, 24)
        )
