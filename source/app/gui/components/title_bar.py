from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

from app.gui.scaling import ui_scaled

WINDOW_TITLE = "Goida AI Unlocker"


class DraggableTitleBar(QWidget):
    """Заголовок безрамочного окна: перетаскивание + кнопки свернуть/закрыть."""

    TITLE_BAR_HEIGHT = 32
    BUTTON_SIZE = 26

    def __init__(self, main_window: "QMainWindow"):
        super().__init__(main_window)
        self._main_window = main_window
        self._drag_pos = None

        self.bar_height = ui_scaled(self.TITLE_BAR_HEIGHT)
        button_size = ui_scaled(self.BUTTON_SIZE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(ui_scaled(12), 0, ui_scaled(8), 0)
        layout.setSpacing(0)

        self.title_label = QLabel(WINDOW_TITLE)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.minimize_button = QPushButton("\u2500")
        self.minimize_button.setFixedSize(button_size, button_size)
        self.minimize_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize_button.clicked.connect(self._main_window.showMinimized)
        layout.addWidget(self.minimize_button)

        self.close_button = QPushButton("\u00d7")
        self.close_button.setFixedSize(button_size, button_size)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # close() корректнее quit(): срабатывают closeEvent и завершение по последнему окну
        self.close_button.clicked.connect(self._main_window.close)
        layout.addWidget(self.close_button)

    def apply_theme(self, styles: dict):
        self.title_label.setStyleSheet(styles["title_label"])
        self.minimize_button.setStyleSheet(styles["title_button"])
        self.close_button.setStyleSheet(styles["title_close_button"])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._main_window.start_system_move():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._main_window.move(self._main_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
