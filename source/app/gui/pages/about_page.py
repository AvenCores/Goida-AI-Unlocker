from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QAbstractButton, QToolButton, QGridLayout,
    QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, QSize

from app.gui.localization import tr
from app.gui.icons import get_icon, get_icon_pixmap
from app.gui.scaling import ui_scaled
from app.utils.helpers import open_target

_GRID_COLUMNS = 3


class AboutPage(QWidget):
    """Страница «О программе»: карточка с версией, автором и ссылками.

    Контент собран в тематизированную карточку (как страницы результата
    и донатов): шапка с иконкой и версией, ровная сетка соцсетей и
    широкая кнопка репозитория под ней.
    """

    _SOCIAL_LINKS = [
        ("Telegram", "https://t.me/avencoresyt", "send.svg"),
        ("YouTube", "https://youtube.com/@avencores", "play.svg"),
        ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"),
        ("Dzen", "https://dzen.ru/avencores", "book-open.svg"),
        ("VK", "https://vk.com/avencoresreuploads", "users.svg"),
    ]

    def __init__(self, styles: dict, dark_theme: bool, return_callback):
        super().__init__()
        self.styles = styles
        self.dark_theme = dark_theme
        self._icon_buttons: list[tuple[QAbstractButton, str]] = []
        self._tool_buttons: list[QToolButton] = []
        self._grid_hspacing = ui_scaled(12)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setContentsMargins(*(ui_scaled(20),) * 4)

        self.card = QWidget()
        self.card.setObjectName("about_card")
        self.card.setMinimumWidth(ui_scaled(240))
        self.card.setMaximumWidth(ui_scaled(500))
        self.card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(ui_scaled(16))
        card_layout.setContentsMargins(
            ui_scaled(24), ui_scaled(24), ui_scaled(24), ui_scaled(24)
        )

        # Без явной прозрачности QLabel наследуют background/border
        # карточки (декларации setStyleSheet распространяются на детей)
        transparent = "background: transparent; border: none;"
        self.icon_label = QLabel()
        self.icon_label.setStyleSheet(transparent)
        self.icon_label.setPixmap(get_icon_pixmap("bulb.svg", 40, dark_theme=dark_theme))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setStyleSheet(transparent)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)

        self.info_label = QLabel()
        self.info_label.setStyleSheet(transparent)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.info_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(self._grid_hspacing)
        grid.setVerticalSpacing(ui_scaled(10))
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # QPushButton, а не QToolButton: на широкой кнопке он центрирует
        # связку «иконка + текст», QToolButton прижимает её влево
        self.repo_button = QPushButton(tr("repository"))
        self.repo_button.setIcon(
            get_icon("github.svg", 24, dark_theme=dark_theme, force_dark=True)
        )
        self.repo_button.setIconSize(QSize(ui_scaled(24), ui_scaled(24)))
        self.repo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repo_button.clicked.connect(
            lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker")
        )
        self._icon_buttons.append((self.repo_button, "github.svg"))

        entries = [
            ("GitHub", "https://github.com/AvenCores", "github.svg"),
            *self._SOCIAL_LINKS,
        ]
        for index, (label, url, icon) in enumerate(entries):
            btn = self._make_tool_button(label, icon)
            btn.clicked.connect(lambda checked=False, u=url: open_target(u))
            grid.addWidget(
                btn, index // _GRID_COLUMNS, index % _GRID_COLUMNS,
                alignment=Qt.AlignmentFlag.AlignHCenter,
            )

        card_layout.addSpacing(ui_scaled(4))
        card_layout.addLayout(grid)
        card_layout.addSpacing(ui_scaled(4))
        card_layout.addWidget(self.repo_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        card_layout.addSpacing(ui_scaled(4))

        self.back_button = QPushButton(f"  {tr('back_to_menu')}  ")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(return_callback)
        card_layout.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(self.card)

        self.apply_theme(styles, dark_theme)

    def _make_tool_button(self, text: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(get_icon(icon_name, 24, dark_theme=self.dark_theme, force_dark=True))
        btn.setIconSize(QSize(ui_scaled(24), ui_scaled(24)))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_buttons.append(btn)
        self._icon_buttons.append((btn, icon_name))
        return btn

    def _equalize_button_widths(self):
        """Ровная сетка плиток; репозиторий — одной шириной с сеткой.

        Ширина берётся по соцкнопкам: подсказка «Репозитория» шире и
        раздувала бы плитки за пределы карточки.
        """
        # sizeHint доступен сразу после задания текста/иконки — таймер не нужен
        social = [b for b in self._tool_buttons if b is not self.repo_button]
        widths = [b.sizeHint().width() for b in social]
        ref = max((w for w in widths if w > 0), default=0)
        if ref <= 0:
            return
        ref = min(ref, ui_scaled(130))
        for btn in social:
            btn.setFixedWidth(ref)
        grid_width = ref * _GRID_COLUMNS + self._grid_hspacing * (_GRID_COLUMNS - 1)
        self.repo_button.setFixedWidth(
            max(grid_width, self.repo_button.sizeHint().width())
        )

    def apply_texts(self):
        labels = ["GitHub"] + [name for name, _, _ in self._SOCIAL_LINKS]
        for btn, label in zip(self._tool_buttons, labels):
            btn.setText(label)
            btn.ensurePolished()
        self.repo_button.setText(tr("repository"))
        self.back_button.setText(f"  {tr('back_to_menu')}  ")
        self._equalize_button_widths()
        self._fill_html()

    def apply_theme(self, styles: dict, dark_theme: bool):
        self.styles = styles
        self.dark_theme = dark_theme
        self.card.setStyleSheet(styles["message_card"])
        # Прозрачность перекрывает наследуемый от карточки фон/рамку
        self.title_label.setStyleSheet(
            "background: transparent; border: none;" + styles["about_title_style"]
        )
        self.back_button.setStyleSheet(styles["theme"])
        self.repo_button.setStyleSheet(styles["tool_button"])
        for btn, icon_name in self._icon_buttons:
            btn.setStyleSheet(styles["tool_button"])
            btn.setIcon(get_icon(icon_name, 24, dark_theme=dark_theme, force_dark=True))
        self.icon_label.setPixmap(get_icon_pixmap("bulb.svg", 40, dark_theme=dark_theme))
        self._fill_html()
        self._equalize_button_widths()

    def _fill_html(self):
        self.title_label.setText(self.styles["about_title_html"])
        self.info_label.setText(self.styles["about_info_html"])
