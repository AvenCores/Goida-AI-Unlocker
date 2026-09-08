from typing import Callable, Optional

from PySide6.QtWidgets import QWidget, QStackedWidget, QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation


class PageNavigator:
    """Переключение страниц QStackedWidget с анимацией затухания."""

    FADE_DURATION_MS = 180

    def __init__(self, stacked_widget: QStackedWidget):
        self._stacked = stacked_widget
        self._current_animation: Optional[QPropertyAnimation] = None
        self._busy = False
        self._pending: list = []

    def _clear_effects(self):
        for i in range(self._stacked.count()):
            try:
                w = self._stacked.widget(i)
                if w and w.graphicsEffect():
                    w.setGraphicsEffect(None)
            except RuntimeError:
                pass

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
        # Быстрые клики: складываем в очередь, ничего не теряем
        if self._busy:
            self._pending.append((new_widget, on_finish, on_start))
            # Защита от бесконечного роста при спаме
            if len(self._pending) > 5:
                dropped = self._pending.pop(0)
                try:
                    from app.core.logger import logger

                    logger.debug("PageNavigator: dropped queued switch")
                except Exception:
                    pass
            return
        self._busy = True
        if on_start:
            try:
                on_start()
            except Exception:
                pass
        current = self._stacked.currentWidget()
        if not current or current == new_widget:
            try:
                self._stacked.setCurrentWidget(new_widget)
            except RuntimeError:
                pass
            self._busy = False
            if on_finish:
                try:
                    on_finish()
                except Exception:
                    pass
            self._drain_pending()
            return

        try:
            if self._current_animation is not None:
                try:
                    self._current_animation.stop()
                except Exception:
                    pass
                self._current_animation = None
            self._clear_effects()
        except Exception:
            pass

        try:
            fade_out = self._fade(current, 1.0, 0.0)
        except RuntimeError:
            self._busy = False
            return

        def do_switch():
            try:
                self._stacked.setCurrentWidget(new_widget)
            except RuntimeError:
                self._busy = False
                return
            try:
                current.setGraphicsEffect(None)
            except RuntimeError:
                pass

            try:
                fade_in = self._fade(new_widget, 0.0, 1.0)
            except RuntimeError:
                self._busy = False
                return

            def cleanup():
                try:
                    new_widget.setGraphicsEffect(None)
                except RuntimeError:
                    pass
                self._current_animation = None
                self._busy = False
                if on_finish:
                    try:
                        on_finish()
                    except Exception:
                        pass
                self._drain_pending()

            try:
                fade_in.finished.connect(cleanup)
            except RuntimeError:
                self._busy = False
                return
            self._current_animation = fade_in
            fade_in.start()

        try:
            fade_out.finished.connect(do_switch)
        except RuntimeError:
            self._busy = False
            return
        self._current_animation = fade_out
        fade_out.start()

    def _drain_pending(self):
        if self._pending:
            item = self._pending.pop(0)
            self.animate_switch(item[0], on_finish=item[1], on_start=item[2])

    def add_page(self, widget: QWidget):
        self._stacked.addWidget(widget)

    def remove_widget(self, widget: QWidget):
        try:
            if self._current_animation is not None:
                try:
                    self._current_animation.stop()
                except Exception:
                    pass
                self._current_animation = None
            self._clear_effects()
        except Exception:
            pass
        try:
            self._stacked.removeWidget(widget)
        except RuntimeError:
            return
        try:
            widget.deleteLater()
        except RuntimeError:
            pass

    def return_to_main(self, home_wrapper: QWidget, widget: QWidget):
        self.animate_switch(home_wrapper, on_finish=lambda: self.remove_widget(widget))
