from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QToolButton, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt, QSize

from app.gui.localization import tr
from app.gui.icons import get_icon
from app.utils.helpers import open_target


class AboutPage(QWidget):
    """Страница «О программе»: версия, автор и ссылки."""

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
        self._icon_buttons: list[tuple[QToolButton, str]] = []

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(8)
        vbox.setContentsMargins(12, 12, 12, 12)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(get_icon("bulb.svg", 32, dark_theme=dark_theme).pixmap(32, 32))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.title_label)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.info_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._tool_buttons: list[QToolButton] = []
        self.repo_button = self._make_tool_button(tr("repository"), "github.svg")
        self.repo_button.clicked.connect(
            lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker")
        )

        entries = [
            ("GitHub", "https://github.com/AvenCores", "github.svg"),
            *self._SOCIAL_LINKS,
        ]
        for index, (label, url, icon) in enumerate(entries):
            btn = self._make_tool_button(label, icon)
            btn.clicked.connect(lambda checked=False, u=url: open_target(u))
            grid.addWidget(btn, index // 3, index % 3, alignment=Qt.AlignmentFlag.AlignHCenter)

        vbox.addLayout(grid)
        vbox.addSpacing(8)
        vbox.addWidget(self.repo_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addSpacing(8)

        self.back_button = QPushButton(f"  {tr('back_to_menu')}  ")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(return_callback)
        vbox.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.apply_theme(styles, dark_theme)

    def _make_tool_button(self, text: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(get_icon(icon_name, 24, dark_theme=self.dark_theme, force_dark=True))
        btn.setIconSize(QSize(24, 24))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_buttons.append(btn)
        self._icon_buttons.append((btn, icon_name))
        return btn

    def _equalize_button_widths(self):
        # sizeHint доступен сразу после задания текста/иконки — таймер не нужен
        widths = [b.sizeHint().width() for b in self._tool_buttons]
        ref = max((w for w in widths if w > 0), default=0)
        for b in self._tool_buttons:
            b.setFixedWidth(ref)

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
        self.title_label.setStyleSheet(styles["about_title_style"])
        self.back_button.setStyleSheet(styles["theme"])
        self.repo_button.setStyleSheet(styles["tool_button"])
        for btn, icon_name in self._icon_buttons:
            btn.setStyleSheet(styles["tool_button"])
            btn.setIcon(get_icon(icon_name, 24, dark_theme=dark_theme, force_dark=True))
        self._fill_html()
        self._equalize_button_widths()

    def _fill_html(self):
        self.title_label.setText(self.styles["about_title_html"])
        self.info_label.setText(self.styles["about_info_html"])
