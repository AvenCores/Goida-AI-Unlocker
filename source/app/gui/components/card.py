from typing import Callable
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt
from app.gui.icons import create_icon_label


def build_card(
    icon_name: str,
    dark_theme: bool,
    styles: dict,
    max_width: int = 420,
    fix_size_fn: Callable[[QWidget], None] | None = None,
) -> tuple[QWidget, QVBoxLayout, QWidget]:
    """Build a centered card widget with an icon.

    Returns:
        (outer_widget, card_layout, card_widget) tuple.
    """
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vbox.setSpacing(24)
    vbox.setContentsMargins(20, 20, 20, 20)
    if fix_size_fn:
        fix_size_fn(widget)

    card = QWidget()
    card.setObjectName("msg_card")
    card.setMinimumWidth(240)
    card.setMaximumWidth(max_width)
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    card_layout = QVBoxLayout(card)
    card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.setSpacing(16)
    card_layout.setContentsMargins(32, 24, 32, 24)
    card.setStyleSheet(styles["message_card"])

    emoji = create_icon_label(icon_name, size=48, dark_theme=dark_theme)
    card_layout.addWidget(emoji)

    vbox.addWidget(card)
    return widget, card_layout, card
