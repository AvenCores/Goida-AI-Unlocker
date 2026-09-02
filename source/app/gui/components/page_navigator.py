from typing import Callable, Optional

from PySide6.QtWidgets import QWidget, QStackedWidget, QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation


class PageNavigator:
    """Переключение страниц QStackedWidget с анимацией затухания."""

    FADE_DURATION_MS = 180

    def __init__(self, stacked_widget: QStackedWidget):
        self._stacked = stacked_widget
        self._current_animation: Optional[QPropertyAnimation] = None

    def _clear_effects(self):
        for i in range(self._stacked.count()):
            w = self._stacked.widget(i)
            if w and w.graphicsEffect():
                w.setGraphicsEffect(None)

    @staticmethod
    def _fade(widget: QWidget, start: float, end: float) -> QPropertyAnimation:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(PageNavigator.FADE_DURATION_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        return anim

    def animate_switch(
        self, new_widget: QWidget, on_finish: Optional[Callable] = None,
        on_start: Optional[Callable] = None,
    ):
        if on_start:
            on_start()
        current = self._stacked.currentWidget()
        if not current or current == new_widget:
            self._stacked.setCurrentWidget(new_widget)
            if on_finish:
                on_finish()
            return

        if self._current_animation is not None:
            self._current_animation.stop()
            self._current_animation = None
        self._clear_effects()

        fade_out = self._fade(current, 1.0, 0.0)

        def do_switch():
            self._stacked.setCurrentWidget(new_widget)
            current.setGraphicsEffect(None)

            fade_in = self._fade(new_widget, 0.0, 1.0)

            def cleanup():
                new_widget.setGraphicsEffect(None)
                self._current_animation = None
                if on_finish:
                    on_finish()

            fade_in.finished.connect(cleanup)
            self._current_animation = fade_in
            fade_in.start()

        fade_out.finished.connect(do_switch)
        self._current_animation = fade_out
        fade_out.start()

    def add_page(self, widget: QWidget):
        self._stacked.addWidget(widget)

    def remove_widget(self, widget: QWidget):
        self._stacked.removeWidget(widget)
        widget.deleteLater()

    def return_to_main(self, home_wrapper: QWidget, widget: QWidget):
        self.animate_switch(home_wrapper, on_finish=lambda: self.remove_widget(widget))
