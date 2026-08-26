from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QApplication, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QPropertyAnimation, QSequentialAnimationGroup, QPauseAnimation

from app.gui.localization import tr
from app.gui.icons import get_icon_pixmap
from app.gui.scaling import ui_scaled

SBER_CARD_NUMBER = "2202 2050 1464 4675"
_FADE_MS = 150


class DonatePage(QWidget):
    """Страница поддержки автора: карточка с номером карты и копированием.

    Номер выделен полем на подложке (выделяется мышью), кнопки копирования
    и возврата — внутри карточки, как на странице «О программе».
    """

    def __init__(self, styles: dict, dark_theme: bool, return_callback):
        super().__init__()
        self.styles = styles
        self.dark_theme = dark_theme
        self._copy_animation: QSequentialAnimationGroup | None = None

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setContentsMargins(*(ui_scaled(20),) * 4)

        self.card = QWidget()
        self.card.setObjectName("donate_card")
        self.card.setMinimumWidth(ui_scaled(240))
        self.card.setMaximumWidth(ui_scaled(440))
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(ui_scaled(16))
        card_layout.setContentsMargins(
            ui_scaled(32), ui_scaled(24), ui_scaled(32), ui_scaled(24)
        )

        self.title_label = QLabel(tr("donate_title"))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)

        # Прозрачный фон: иначе QLabel наследует рамку карточки
        self.sber_icon_label = QLabel()
        self.sber_icon_label.setStyleSheet("background: transparent; border: none;")
        self.sber_icon_label.setPixmap(
            get_icon_pixmap("sber.svg", 48, dark_theme=dark_theme)
        )
        self.sber_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.sber_icon_label)

        self.card_number_label = QLabel(f"\u3164SBER: <b>{SBER_CARD_NUMBER}</b>\u3164")
        self.card_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_number_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        card_layout.addWidget(self.card_number_label)

        self.copy_button = QPushButton(tr("copy_card"))
        self.copy_button.setProperty("style_role", "button1")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy_card_number)
        card_layout.addWidget(self.copy_button)

        card_layout.addSpacing(ui_scaled(4))

        self.back_button = QPushButton(f"  {tr('back_to_menu')}  ")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(return_callback)
        card_layout.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(self.card)

        self.apply_theme(styles, dark_theme)

    # --- Копирование с плавной подсветкой статуса ---

    def _copy_card_number(self):
        group_state = (
            self._copy_animation.state() if self._copy_animation else None
        )
        if group_state == QSequentialAnimationGroup.State.Running:
            return
        QApplication.clipboard().setText(SBER_CARD_NUMBER)

        button = self.copy_button
        effect = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(effect)

        def fade(start: float, end: float) -> QPropertyAnimation:
            anim = QPropertyAnimation(effect, b"opacity")
            anim.setDuration(_FADE_MS)
            anim.setStartValue(start)
            anim.setEndValue(end)
            return anim

        # затемнение → «Скопировано» → проявление → пауза →
        # → затемнение → исходный текст → проявление
        show_copied = fade(1.0, 0.0)
        reveal_copied = fade(0.0, 1.0)
        hold_copied = QPauseAnimation(1200)
        hide_copied = fade(1.0, 0.0)
        reveal_restored = fade(0.0, 1.0)

        show_copied.finished.connect(lambda: button.setText(tr("copied")))
        hide_copied.finished.connect(lambda: button.setText(tr("copy_card")))
        reveal_restored.finished.connect(lambda: button.setGraphicsEffect(None))
        reveal_restored.finished.connect(self._finish_copy)

        group = QSequentialAnimationGroup(button)
        for step in (show_copied, reveal_copied, hold_copied, hide_copied, reveal_restored):
            group.addAnimation(step)

        self._copy_animation = group
        group.start(QSequentialAnimationGroup.DeletionPolicy.DeleteWhenStopped)

    def _finish_copy(self):
        self._copy_animation = None

    # --- Темизация / переводы ---

    def apply_texts(self):
        self.title_label.setText(tr("donate_title"))
        self.copy_button.setText(tr("copy_card"))
        self.back_button.setText(f"  {tr('back_to_menu')}  ")

    def apply_theme(self, styles: dict, dark_theme: bool):
        self.styles = styles
        self.dark_theme = dark_theme
        self.card.setStyleSheet(styles["message_card"])
        self.title_label.setStyleSheet(styles["donate_title"])
        self.card_number_label.setStyleSheet(styles["donate_card_number"])
        self.copy_button.setStyleSheet(styles["button1"])
        self.back_button.setStyleSheet(styles["theme"])
        self.sber_icon_label.setPixmap(
            get_icon_pixmap("sber.svg", 48, dark_theme=dark_theme)
        )
