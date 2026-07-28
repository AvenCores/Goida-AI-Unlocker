from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QStackedWidget
from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect


class PageNavigator:
    """Manages stacked-widget page transitions with fade animations."""

    def __init__(self, stacked_widget: QStackedWidget, title_bar_height: int = 32):
        self._stacked = stacked_widget
        self._title_bar_height = title_bar_height
        self._current_animation: Optional[QPropertyAnimation] = None
        self._parent_window: Optional[QWidget] = None

    def set_parent_window(self, window: QWidget):
        self._parent_window = window

    def fix_widget_size(self, w: QWidget, width: int, height: int):
        h = height - self._title_bar_height
        w.setMinimumSize(width, h)
        w.setMaximumSize(width, h)

    def _clear_effects(self):
        if not self._stacked:
            return
        for i in range(self._stacked.count()):
            w = self._stacked.widget(i)
            if w and w.graphicsEffect():
                w.setGraphicsEffect(None)

    def animate_switch(self, new_widget: QWidget, on_finish: Optional[Callable] = None):
        if not self._stacked:
            return
        current = self._stacked.currentWidget()
        if not current or current == new_widget:
            self._stacked.setCurrentWidget(new_widget)
            if on_finish:
                on_finish()
            return

        if self._parent_window:
            self.fix_widget_size(new_widget, self._parent_window.width(), self._parent_window.height())

        if self._current_animation is not None:
            self._current_animation.stop()
            self._current_animation = None
        self._clear_effects()

        if current.graphicsEffect():
            current.setGraphicsEffect(None)

        effect_out = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect_out)
        fade_out = QPropertyAnimation(effect_out, b"opacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def do_switch():
            if self._stacked is None:
                return
            self._stacked.setCurrentWidget(new_widget)
            if current and current.graphicsEffect():
                current.setGraphicsEffect(None)

            if new_widget.graphicsEffect():
                new_widget.setGraphicsEffect(None)

            effect_in = QGraphicsOpacityEffect(new_widget)
            new_widget.setGraphicsEffect(effect_in)
            fade_in = QPropertyAnimation(effect_in, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)

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

    def remove_widget(self, widget: QWidget):
        if self._stacked:
            self._stacked.removeWidget(widget)
        widget.deleteLater()

    def return_to_main(self, home_page: QWidget, widget: QWidget):
        def cleanup():
            self.remove_widget(widget)
        self.animate_switch(home_page, on_finish=cleanup)

    def add_and_switch(self, widget: QWidget):
        if self._stacked:
            self._stacked.addWidget(widget)
        self.animate_switch(widget)
