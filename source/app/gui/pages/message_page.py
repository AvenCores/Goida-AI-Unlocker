from typing import Callable
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt
from app.gui.localization import tr, clean_message_line
from app.gui.components.card import build_card
from app.utils.helpers import open_target


def build_message_page(
    msg: str,
    success: bool,
    word_wrap: bool,
    styles: dict,
    dark_theme: bool,
    fix_size_fn: Callable[[QWidget], None] | None = None,
    ok_callback: Callable[[], None] | None = None,
) -> QWidget:
    """Build a message result page (success or error).

    Returns:
        The message page QWidget.
    """
    icon = "check-circle.svg" if success else "x-circle.svg"
    widget, card_layout, card = build_card(icon, dark_theme, styles, fix_size_fn=fix_size_fn)

    if word_wrap:
        for raw_line in msg.split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            lbl = QLabel(line)
            lbl.setObjectName("message_block_label")
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(lbl)
    else:
        for raw_line in msg.split("\n"):
            line = clean_message_line(raw_line)
            if not line.strip():
                continue
            lbl = QLabel(line)
            lbl.setObjectName("message_label")
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(lbl)

    ok_btn = QPushButton(tr("ok"))
    ok_btn.setProperty("style_role", "button1")
    card_layout.addWidget(ok_btn)

    if ok_callback:
        ok_btn.clicked.connect(ok_callback)

    return widget


def build_processing_page(
    action: str,
    styles: dict,
    dark_theme: bool,
    fix_size_fn: Callable[[QWidget], None] | None = None,
) -> QWidget:
    """Build a processing/in-progress page.

    Returns:
        The processing page QWidget.
    """
    if action == "install":
        msg = tr("processing_install")
    elif action == "update":
        msg = tr("processing_update")
    elif action == "save":
        msg = tr("processing_save")
    elif action == "open":
        msg = tr("processing_open")
    else:
        msg = tr("processing_uninstall")

    widget, card_layout, card = build_card("clock.svg", dark_theme, styles, fix_size_fn=fix_size_fn)
    for raw_line in msg.split("\n"):
        line = clean_message_line(raw_line)
        if not line:
            continue
        lbl = QLabel(line)
        lbl.setObjectName("message_label")
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout.addWidget(lbl)

    return widget


def build_update_available_page(
    local_ver: str,
    latest_ver: str,
    dl_url: str,
    styles: dict,
    dark_theme: bool,
    fix_size_fn: Callable[[QWidget], None] | None = None,
    ok_callback: Callable[[], None] | None = None,
) -> QWidget:
    """Build the 'update available' page.

    Returns:
        The update-available page QWidget.
    """
    widget, card_layout, card = build_card("alert.svg", dark_theme, styles, max_width=600, fix_size_fn=fix_size_fn)
    card.setMinimumWidth(420)

    for text in (
        tr("installed_version", version=local_ver),
        tr("latest_version", version=latest_ver),
        tr("new_version_available")
    ):
        line = clean_message_line(text)
        if not line:
            continue
        lbl = QLabel(line)
        lbl.setObjectName("message_block_label")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(False)
        card_layout.addWidget(lbl)

    dl_btn = QPushButton(tr("download"))
    dl_btn.setProperty("style_role", "button1")
    card_layout.addWidget(dl_btn)

    ok_btn = QPushButton(tr("ok"))
    ok_btn.setProperty("style_role", "button1")
    card_layout.addWidget(ok_btn)

    dl_btn.clicked.connect(lambda: open_target(dl_url))
    if ok_callback:
        ok_btn.clicked.connect(ok_callback)

    return widget


def build_no_update_page(
    local_ver: str,
    latest_ver: str,
    styles: dict,
    dark_theme: bool,
    fix_size_fn: Callable[[QWidget], None] | None = None,
    ok_callback: Callable[[], None] | None = None,
) -> QWidget:
    """Build the 'already up to date' page.

    Returns:
        The no-update page QWidget.
    """
    widget, card_layout, card = build_card("check-circle.svg", dark_theme, styles, max_width=600, fix_size_fn=fix_size_fn)
    card.setMinimumWidth(420)

    for text in (
        tr("installed_version", version=local_ver),
        tr("latest_version_padded", version=latest_ver),
        tr("latest_version_installed")
    ):
        line = clean_message_line(text)
        if not line:
            continue
        lbl = QLabel(line)
        lbl.setObjectName("message_block_label")
        if "version" in text:
            lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(False)
        card_layout.addWidget(lbl)

    ok_btn = QPushButton(tr("ok"))
    ok_btn.setProperty("style_role", "button1")
    card_layout.addWidget(ok_btn)

    if ok_callback:
        ok_btn.clicked.connect(ok_callback)

    return widget
