from typing import Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QToolButton, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QSize
from app.gui.localization import tr
from app.gui.icons import get_icon, create_icon_label
from app.utils.helpers import open_target


def build_about_page(
    styles: dict,
    dark_theme: bool,
    return_callback: Callable[[], None],
) -> QWidget:
    """Build the About page widget.

    Args:
        styles: Current stylesheet dict.
        dark_theme: Whether dark theme is active.
        return_callback: Called when user clicks "Back to menu".

    Returns:
        The about page QWidget.
    """
    about = QWidget()
    vbox = QVBoxLayout(about)
    vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vbox.setSpacing(8)
    vbox.setContentsMargins(12, 12, 12, 12)

    icon_label = create_icon_label("bulb.svg", size=32, dark_theme=dark_theme)
    vbox.addWidget(icon_label)

    label_ver = QLabel()
    label_ver.setObjectName("about_title")
    label_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vbox.addWidget(label_ver)

    info = QLabel()
    info.setObjectName("about_info")
    info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vbox.addWidget(info)

    github_btn = QToolButton()
    github_btn.setText("GitHub")
    github_btn.setIcon(get_icon("github.svg", 24, dark_theme=dark_theme, force_dark=True))
    github_btn.setIconSize(QSize(24, 24))
    github_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    github_btn.setProperty("style_role", "about_tool")
    github_btn.setProperty("icon_name", "github.svg")
    github_btn.setProperty("icon_force_dark", True)
    github_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores"))

    repo_btn = QToolButton()
    repo_btn.setText(tr("repository"))
    repo_btn.setIcon(get_icon("github.svg", 24, dark_theme=dark_theme, force_dark=True))
    repo_btn.setIconSize(QSize(24, 24))
    repo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    repo_btn.setProperty("style_role", "about_tool")
    repo_btn.setProperty("icon_name", "github.svg")
    repo_btn.setProperty("icon_force_dark", True)
    repo_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker"))

    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    grid.addWidget(github_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)

    social = [
        ("Telegram", "https://t.me/avencoresyt", "send.svg"),
        ("YouTube", "https://youtube.com/@avencores", "play.svg"),
        ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"),
        ("Dzen", "https://dzen.ru/avencores", "book-open.svg"),
        ("VK", "https://vk.com/avencoresreuploads", "users.svg"),
    ]
    buttons = [github_btn, repo_btn]
    col_count = 3
    row, col = 0, 1
    for label, url, icon in social:
        btn = QToolButton()
        btn.setText(label)
        btn.setIcon(get_icon(icon, 24, dark_theme=dark_theme, force_dark=True))
        btn.setIconSize(QSize(24, 24))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setProperty("style_role", "about_tool")
        btn.setProperty("icon_name", icon)
        btn.setProperty("icon_force_dark", True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, u=url: open_target(u))
        grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignHCenter)
        buttons.append(btn)
        col += 1
        if col >= col_count:
            row += 1
            col = 0

    vbox.addLayout(grid)
    vbox.addSpacing(8)
    vbox.addWidget(repo_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
    vbox.addSpacing(8)

    def equalize():
        if not buttons:
            return
        try:
            ref = max(b.sizeHint().width() for b in buttons if b.sizeHint().width() > 0)
            for b in buttons:
                b.setFixedWidth(ref)
        except Exception:
            pass

    back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
    back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    back_btn.setProperty("style_role", "theme")
    back_btn.setStyleSheet(styles["theme"])
    back_btn.clicked.connect(return_callback)
    vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    QTimer.singleShot(150, equalize)
    return about
