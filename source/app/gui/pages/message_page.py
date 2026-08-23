from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt

from app.gui.localization import tr, clean_message_line
from app.gui.components.card import CardPage
from app.gui.components.busy_spinner import BusySpinner
from app.utils.helpers import open_target


class MessagePage(CardPage):
    """Страница результата (успех/ошибка). Enter или кнопка «Окей» возвращает назад."""

    def __init__(self, msg: str, success: bool, word_wrap: bool,
                 styles: dict, dark_theme: bool, ok_callback=None):
        super().__init__(styles, dark_theme)
        self._msg = msg
        self._word_wrap = word_wrap

        icon_name = "check-circle.svg" if success else "x-circle.svg"
        self.icon_label = self.add_icon(icon_name)

        self._fill_messages()

        self.ok_button = QPushButton(tr("ok"))
        self.ok_button.setProperty("style_role", "button1")
        self.ok_button.setDefault(True)
        self.ok_button.setFocus()
        self.card_layout.addWidget(self.ok_button)

        if ok_callback:
            self.ok_button.clicked.connect(ok_callback)

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
        self.ok_button.setText(tr("ok"))

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.ok_button.setStyleSheet(styles["button1"])

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.ok_button.isEnabled():
                self.ok_button.click()
            event.accept()
            return
        super().keyPressEvent(event)


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

        for raw_line in tr(self._message_key()).split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            self.add_message(line)

        self.apply_theme(styles, dark_theme)

    def _message_key(self) -> str:
        return self._ACTION_KEYS.get(self._action, "processing_uninstall")

    def apply_theme(self, styles: dict, dark_theme: bool):
        super().apply_theme(styles, dark_theme)
        self.spinner.set_color("#2d7dff" if dark_theme else "#0078d4")

    def apply_texts(self):
        self.clear_messages()
        for raw_line in tr(self._message_key()).split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            self.add_message(line)


class UpdateAvailablePage(CardPage):
    """Сообщение о доступном обновлении приложения."""

    def __init__(self, local_ver: str, latest_ver: str, dl_url: str,
                 styles: dict, dark_theme: bool, ok_callback=None):
        super().__init__(styles, dark_theme, max_width=460)
        self._local_ver = local_ver
        self._latest_ver = latest_ver
        self._dl_url = dl_url
        self.card.setMinimumWidth(420)

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

        self.ok_button = QPushButton(tr("ok"))
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
        self.card.setMinimumWidth(420)

        self.icon_label = self.add_icon("check-circle.svg")
        self.info_labels = [
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", rich=True, block=True, wrap=False),
            self.add_message("", block=True, wrap=False),
        ]
        self._fill_texts()

        self.ok_button = QPushButton(tr("ok"))
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
