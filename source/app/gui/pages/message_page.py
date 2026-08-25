from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt

from app.gui.localization import tr, clean_message_line
from app.gui.components.card import CardPage
from app.gui.components.busy_spinner import BusySpinner
from app.gui.scaling import ui_scaled
from app.utils.helpers import open_target


class MessagePage(CardPage):
    """Страница результата (успех/ошибка). Enter или кнопка «Окей» возвращает назад.

    Для ошибок с известным действием (retry_callback) добавляется кнопка
    «Повторить попытку» — она становится основной, «Вернуться в главное
    меню» — вторичной.
    """

    def __init__(self, msg: str, success: bool, word_wrap: bool,
                 styles: dict, dark_theme: bool, ok_callback=None,
                 retry_callback=None):
        super().__init__(styles, dark_theme)
        self._msg = msg
        self._word_wrap = word_wrap
        # Повтор показываем только для ошибок с известным действием
        self._retry_callback = retry_callback if (retry_callback and not success) else None

        icon_name = "check-circle.svg" if success else "x-circle.svg"
        self.icon_label = self.add_icon(icon_name)

        self._fill_messages()

        if self._retry_callback:
            self.retry_button = QPushButton(tr("retry"))
            self.retry_button.setProperty("style_role", "button1")
            self.retry_button.setDefault(True)
            self.retry_button.setFocus()
            self.retry_button.clicked.connect(self._retry_callback)
            self.card_layout.addWidget(self.retry_button)

        self.ok_button = QPushButton(tr("back_to_main_menu"))
        self.ok_button.setProperty("style_role", "theme" if self._retry_callback else "button1")
        self.ok_button.clicked.connect(ok_callback)
        self.card_layout.addWidget(self.ok_button)

        self.apply_theme(styles, dark_theme)

    def _fill_messages(self):
        for raw_line in self._msg.split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            self.add_message(line, block=self._word_wrap)

    def apply_texts(self):
        self.clear_messages()
        self._fill_messages()
        if self._retry_callback:
            self.retry_button.setText(tr("retry"))
        self.ok_button.setText(tr("back_to_main_menu"))

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        if self._retry_callback:
            self.retry_button.setStyleSheet(styles["button1"])
            self.ok_button.setStyleSheet(styles["theme"])
        else:
            self.ok_button.setStyleSheet(styles["button1"])

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._retry_callback:
                self.retry_button.click()
            elif self.ok_button.isEnabled():
                self.ok_button.click()
            event.accept()
            return
        super().keyPressEvent(event)


class UninstallChoicePage(CardPage):
    """Страница выбора способа восстановления hosts при удалении обхода."""

    def __init__(self, styles: dict, dark_theme: bool,
                 backup_callback=None, clean_callback=None, cancel_callback=None):
        super().__init__(styles, dark_theme)

        self.icon_label = self.add_icon("trash.svg")

        self.title_label = self.add_message("", rich=True, block=True, wrap=False)
        self.info_label = self.add_message("", block=True)
        self._fill_texts()

        self.backup_button = QPushButton(tr("uninstall_choice_backup"))
        self.backup_button.setProperty("style_role", "button1")
        self.backup_button.setDefault(True)
        self.backup_button.setFocus()
        if backup_callback:
            self.backup_button.clicked.connect(backup_callback)
        self.card_layout.addWidget(self.backup_button)

        self.clean_button = QPushButton(tr("uninstall_choice_clean"))
        self.clean_button.setProperty("style_role", "button2")
        if clean_callback:
            self.clean_button.clicked.connect(clean_callback)
        self.card_layout.addWidget(self.clean_button)

        self.cancel_button = QPushButton(tr("cancel"))
        self.cancel_button.setProperty("style_role", "theme")
        if cancel_callback:
            self.cancel_button.clicked.connect(cancel_callback)
        self.card_layout.addWidget(self.cancel_button)

        self.apply_theme(styles, dark_theme)

    def _fill_texts(self):
        self.title_label.setText(f"<b>{clean_message_line(tr('uninstall_choice_title'))}</b>")
        self.info_label.setText(clean_message_line(tr("uninstall_choice_info")))

    def apply_texts(self):
        self._fill_texts()
        self.backup_button.setText(tr("uninstall_choice_backup"))
        self.clean_button.setText(tr("uninstall_choice_clean"))
        self.cancel_button.setText(tr("cancel"))

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.backup_button.setStyleSheet(styles["button1"])
        self.clean_button.setStyleSheet(styles["button2"])
        self.cancel_button.setStyleSheet(styles["theme"])


class ProcessingPage(CardPage):
    """Страница выполнения операции с анимированным индикатором занятости."""

    _ACTION_KEYS = {
        "install": "processing_install",
        "update": "processing_update",
        "uninstall": "processing_uninstall",
        "save": "processing_save",
        "open": "processing_open",
        "check_updates": "processing_check_updates",
    }

    def __init__(self, action: str, styles: dict, dark_theme: bool):
        super().__init__(styles, dark_theme)
        self._action = action

        # Индикатор занятости вместо статичной иконки (центрируется явно:
        # виджет фиксированного размера в layout растягивается влево)
        self.spinner = BusySpinner("#2d7dff" if dark_theme else "#0078d4", diameter=40)
        self.card_layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)

        self._fill_messages()

        self.apply_theme(styles, dark_theme)

    def _message_key(self) -> str:
        return self._ACTION_KEYS.get(self._action, "processing_uninstall")

    def _fill_messages(self):
        for raw_line in tr(self._message_key()).split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            # Блоки-подложки — как на страницах результата
            self.add_message(line, block=True)

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.spinner.set_color("#2d7dff" if dark_theme else "#0078d4")

    def apply_texts(self):
        self.clear_messages()
        self._fill_messages()


class UpdateAvailablePage(CardPage):
    """Сообщение о доступном обновлении приложения."""

    def __init__(self, local_ver: str, latest_ver: str, dl_url: str,
                 styles: dict, dark_theme: bool, ok_callback=None):
        super().__init__(styles, dark_theme, max_width=460)
        self._local_ver = local_ver
        self._latest_ver = latest_ver
        self._dl_url = dl_url
        self.card.setMinimumWidth(ui_scaled(420))

        self.icon_label = self.add_icon("alert.svg")
        self.info_labels = [
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", block=True, wrap=False),
        ]
        self._fill_texts()

        self.download_button = QPushButton(tr("download"))
        self.download_button.setProperty("style_role", "button1")
        self.download_button.clicked.connect(lambda: open_target(dl_url))
        self.card_layout.addWidget(self.download_button)

        self.ok_button = QPushButton(tr("back_to_main_menu"))
        self.ok_button.setProperty("style_role", "button1")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(ok_callback)
        self.card_layout.addWidget(self.ok_button)

        self.apply_theme(styles, dark_theme)

    def _fill_texts(self):
        texts = (
            tr("installed_version", version=self._local_ver),
            tr("latest_version", version=self._latest_ver),
            tr("new_version_available"),
        )
        for label, text in zip(self.info_labels, texts):
            label.setText(clean_message_line(text))

    def apply_texts(self):
        self._fill_texts()

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.download_button.setStyleSheet(styles["button1"])
        self.ok_button.setStyleSheet(styles["button1"])


class NoUpdatePage(CardPage):
    """Сообщение «обновления нет»."""

    def __init__(self, local_ver: str, latest_ver: str,
                 styles: dict, dark_theme: bool, ok_callback=None):
        super().__init__(styles, dark_theme, max_width=460)
        self._local_ver = local_ver
        self._latest_ver = latest_ver
        self.card.setMinimumWidth(ui_scaled(420))

        self.icon_label = self.add_icon("check-circle.svg")
        self.info_labels = [
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", block=True, wrap=False),
        ]
        self._fill_texts()

        self.ok_button = QPushButton(tr("back_to_main_menu"))
        self.ok_button.setProperty("style_role", "button1")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(ok_callback)
        self.card_layout.addWidget(self.ok_button)

        self.apply_theme(styles, dark_theme)

    def _fill_texts(self):
        texts = (
            tr("installed_version", version=self._local_ver),
            tr("latest_version_padded", version=self._latest_ver),
            tr("latest_version_installed"),
        )
        for label, text in zip(self.info_labels, texts):
            label.setText(clean_message_line(text))

    def apply_texts(self):
        self._fill_texts()

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.ok_button.setStyleSheet(styles["button1"])
