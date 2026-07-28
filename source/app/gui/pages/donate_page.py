from typing import Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QApplication, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QPropertyAnimation, QTimer
from app.gui.localization import tr
from app.gui.icons import create_icon_label


def build_donate_page(
    styles: dict,
    dark_theme: bool,
    return_callback: Callable[[], None],
) -> QWidget:
    """Build the Donate page widget.

    Args:
        styles: Current stylesheet dict.
        dark_theme: Whether dark theme is active.
        return_callback: Called when user clicks "Back to menu".

    Returns:
        The donate page QWidget.
    """
    widget = QWidget()
    vbox = QVBoxLayout(widget)
    vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vbox.setSpacing(24)
    vbox.setContentsMargins(20, 20, 20, 20)

    card = QWidget()
    card.setObjectName("donate_card")
    card.setMaximumWidth(380)
    card.setMinimumWidth(240)
    cl = QVBoxLayout(card)
    cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cl.setSpacing(16)
    cl.setContentsMargins(32, 24, 32, 24)

    light = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
    dark = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
    card.setStyleSheet(dark if dark_theme else light)

    title = QLabel(tr("donate_title"))
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size:22px; font-weight:600;")
    cl.addWidget(title)

    sber_icon_lbl = create_icon_label("sber.svg", 36, dark_theme=dark_theme)
    cl.addWidget(sber_icon_lbl)

    card_num = "2202 2050 1464 4675"
    card_lbl = QLabel(f"\u3164SBER: <b>{card_num}</b>\u3164")
    card_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_lbl.setStyleSheet("font-size:16px;")
    cl.addWidget(card_lbl)

    copy_btn = QPushButton(tr("copy_card"))
    copy_btn.setProperty("style_role", "button1")
    cl.addWidget(copy_btn)

    vbox.addWidget(card)

    back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
    back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    back_btn.setProperty("style_role", "theme")
    back_btn.setStyleSheet(styles["theme"])
    vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def copy_card():
        QApplication.clipboard().setText(card_num)
        if getattr(copy_btn, "_animating", False):
            return
        setattr(copy_btn, "_animating", True)
        orig = tr("copy_card")
        succ = tr("copied")

        def anim():
            eff = QGraphicsOpacityEffect(copy_btn)
            copy_btn.setGraphicsEffect(eff)
            fo = QPropertyAnimation(eff, b"opacity", copy_btn)
            fo.setDuration(150)
            fo.setStartValue(1.0)
            fo.setEndValue(0.0)

            def change():
                copy_btn.setText(succ)
                fi = QPropertyAnimation(eff, b"opacity", copy_btn)
                fi.setDuration(150)
                fi.setStartValue(0.0)
                fi.setEndValue(1.0)

                def hold():
                    def revert():
                        fo2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                        fo2.setDuration(150)
                        fo2.setStartValue(1.0)
                        fo2.setEndValue(0.0)

                        def reset():
                            copy_btn.setText(orig)
                            fi2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                            fi2.setDuration(150)
                            fi2.setStartValue(0.0)
                            fi2.setEndValue(1.0)

                            def clear():
                                copy_btn.setGraphicsEffect(None)
                                setattr(copy_btn, "_animating", False)
                            fi2.finished.connect(clear)
                            fi2.start()
                        fo2.finished.connect(reset)
                        fo2.start()
                    QTimer.singleShot(1200, revert)
                fi.finished.connect(hold)
                fi.start()
            fo.finished.connect(change)
            fo.start()
        anim()

    copy_btn.clicked.connect(copy_card)
    back_btn.clicked.connect(return_callback)

    return widget
