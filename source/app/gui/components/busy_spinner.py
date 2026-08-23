from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor


class BusySpinner(QWidget):
    """Компактный вращающийся индикатор занятости."""

    def __init__(self, color: str = "#2d7dff", diameter: int = 40, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._angle = 0
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def _tick(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = pen.width()
        rect = QRectF(
            margin, margin,
            self._diameter - margin * 2,
            self._diameter - margin * 2,
        )
        painter.drawArc(rect, -self._angle * 16, 90 * 16)
        painter.end()
