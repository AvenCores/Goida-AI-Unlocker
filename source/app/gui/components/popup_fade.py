"""Плавные fade-переходы для всплывающих меню настроек."""

from PySide6.QtCore import QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget

FADE_MS = 120


def fade_in_popup(widget: QWidget, duration: int = FADE_MS):
    """Показывает попап с проявлением (прозрачность задаётся до показа — без вспышки)."""
    widget.setWindowOpacity(0.0)
    widget.show()
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def fade_out_popup(widget: QWidget, duration: int = FADE_MS, on_finished=None):
    """Затухание с закрытием; on_finished вызывается после close().

    Если попап уже закрыт (клик мимо во время анимации), on_finished
    не вызывается — вложенное меню открывать не нужно.
    """

    def _finish():
        if not widget.isVisible():
            return
        widget.close()
        if on_finished:
            on_finished()

    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.windowOpacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(_finish)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
