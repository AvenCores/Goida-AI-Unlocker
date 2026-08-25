from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from app.gui.icons import get_icon_pixmap
from app.gui.scaling import ui_scaled


class CardPage(QWidget):
    """Базовая страница по центру окна с тематизированной карточкой.

    Все дочерние страницы наследуют apply_theme()/apply_texts(), поэтому
    MainWindow не приходится вручную обходить findChildren и переустанавливать
    стили/тексты — каждая страница обновляет себя сама.
    """

    def __init__(self, styles: dict, dark_theme: bool, max_width: int = 420):
        super().__init__()
        self.styles = styles
        self.dark_theme = dark_theme
        self._icon_labels: list[tuple[QLabel, str, int]] = []
        self._message_labels: list[tuple[QLabel, bool, bool]] = []  # (label, rich, block)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(ui_scaled(24))
        vbox.setContentsMargins(*(ui_scaled(20),) * 4)

        self.card = QWidget()
        self.card.setObjectName("msg_card")
        self.card.setMinimumWidth(ui_scaled(240))
        self.card.setMaximumWidth(ui_scaled(max_width))
        self.card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_layout.setSpacing(ui_scaled(16))
        self.card_layout.setContentsMargins(
            ui_scaled(32), ui_scaled(24), ui_scaled(32), ui_scaled(24)
        )

        vbox.addWidget(self.card)

    # --- Хелперы для наследников ---

    def add_icon(self, file_name: str, size: int = 48) -> QLabel:
        label = QLabel()
        label.setPixmap(get_icon_pixmap(file_name, size, dark_theme=self.dark_theme))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Прозрачный фон: иначе глобальное правило QWidget {} рисует
        # под иконкой тёмную плашку с закруглёнными углами
        label.setStyleSheet("background: transparent; border: none;")
        self._icon_labels.append((label, file_name, size))
        self.card_layout.addWidget(label)
        return label

    def set_page_icon(self, label: QLabel, file_name: str, size: int = 48):
        """Заменяет картинку у ранее добавленной иконки (например success → error)."""
        for entry in self._icon_labels:
            if entry[0] is label:
                self._icon_labels.remove(entry)
                break
        label.setPixmap(get_icon_pixmap(file_name, size, dark_theme=self.dark_theme))
        self._icon_labels.append((label, file_name, size))

    def add_message(
        self,
        text: str,
        *,
        rich: bool = False,
        block: bool = False,
        wrap: bool = True,
    ) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
        label.setWordWrap(wrap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._message_labels.append((label, rich, block))
        self.card_layout.addWidget(label)
        return label

    def clear_messages(self):
        for label, _, _ in self._message_labels:
            self.card_layout.removeWidget(label)
            label.deleteLater()
        self._message_labels.clear()

    # --- Темизация ---

    def apply_theme(self, styles: dict, dark_theme: bool):
        self.styles = styles
        self.dark_theme = dark_theme
        self.card.setStyleSheet(styles["message_card"])
        for label, file_name, size in self._icon_labels:
            label.setPixmap(get_icon_pixmap(file_name, size, dark_theme=dark_theme))
        for label, _, block in self._message_labels:
            key = "message_block_label" if block else "message_label"
            label.setStyleSheet(styles[key])
