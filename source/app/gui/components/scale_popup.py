from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

from app.gui.localization import tr
from app.gui.scaling import SCALE_AUTO, get_ui_scale, ui_scaled


class ScalePopup(QWidget):
    """Всплывающий список выбора масштаба интерфейса (стиль LanguagePopup)."""

    scale_selected = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str,
                 dark_theme: bool, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dark_theme = dark_theme
        self.current_value = current
        self._hover_index = -1
        self._options: list[tuple[str, str]] = list(options)
        self._item_height = ui_scaled(32)
        self._padding = ui_scaled(6)
        self._radius = ui_scaled(12)
        self._margin = ui_scaled(10)  # место под ручную тень

        total_height = self._margin * 2 + self._padding * 2 + self._item_height * len(self._options)
        self._width = ui_scaled(170) + self._margin * 2
        self.setFixedSize(self._width, total_height)
        self.setMouseTracking(True)

    def _item_font(self) -> QFont:
        font = QFont("Segoe UI")
        font.setPointSizeF(round(9.5 * get_ui_scale(), 1))
        font.setWeight(QFont.Weight.Medium)
        return font

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        m = self._margin
        shadow_color = QColor(0, 0, 0, 18) if not self.dark_theme else QColor(0, 0, 0, 40)
        for i in range(m, 0, -1):
            alpha_factor = (m - i + 1) / m
            c = QColor(shadow_color)
            c.setAlpha(int(shadow_color.alpha() * alpha_factor))
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                m - i, m - i + 2,
                self.width() - 2 * (m - i), self.height() - 2 * (m - i),
                self._radius + i, self._radius + i,
            )
            painter.fillPath(shadow_path, c)

        bg_color = QColor("#2d333b") if self.dark_theme else QColor("#ffffff")
        border_color = QColor("#3c434d") if self.dark_theme else QColor("#e1e4e8")

        path = QPainterPath()
        path.addRoundedRect(m, m, self.width() - 2 * m, self.height() - 2 * m, self._radius, self._radius)

        painter.fillPath(path, bg_color)
        painter.setPen(QPen(border_color, 1.2))
        painter.drawPath(path)

        painter.setFont(self._item_font())
        gap = ui_scaled(2)
        for i, (value, label) in enumerate(self._options):
            y = m + self._padding + i * self._item_height
            item_rect_x = m + self._padding
            item_rect_w = self.width() - 2 * m - self._padding * 2
            item_rect_h = self._item_height - gap

            is_selected = value == self.current_value
            is_hovered = i == self._hover_index

            if is_selected:
                accent = QColor("#246cf0") if self.dark_theme else QColor("#0078d4")
                highlight_path = QPainterPath()
                highlight_path.addRoundedRect(item_rect_x, y + gap, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(highlight_path, accent)
                text_color = QColor("#ffffff")
            elif is_hovered:
                hover_bg = QColor("#363d46") if self.dark_theme else QColor("#f0f2f5")
                highlight_path = QPainterPath()
                highlight_path.addRoundedRect(item_rect_x, y + gap, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(highlight_path, hover_bg)
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")
            else:
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")

            painter.setFont(self._item_font())
            painter.setPen(text_color)
            text_rect = QRect(
                item_rect_x + ui_scaled(12), y + gap,
                item_rect_w - ui_scaled(34), item_rect_h,
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

            if is_selected:
                painter.setPen(QPen(
                    QColor("#ffffff"), 1.8,
                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
                ))
                cx = item_rect_x + item_rect_w - ui_scaled(20)
                cy = y + gap + item_rect_h // 2
                painter.drawLine(cx - 4, cy, cx - 1, cy + 3)
                painter.drawLine(cx - 1, cy + 3, cx + 5, cy - 3)

        painter.end()

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position().toPoint().y())
        if idx != self._hover_index:
            self._hover_index = idx
            self.update()
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if idx >= 0 else Qt.CursorShape.ArrowCursor
            )
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        idx = self._index_at(event.position().toPoint().y())
        if idx >= 0:
            value, _label = self._options[idx]
            self.scale_selected.emit(value)
            self.close()
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def _index_at(self, y: float) -> int:
        rel = y - self._margin - self._padding
        if rel < 0:
            return -1
        idx = int(rel // self._item_height)
        if idx >= len(self._options):
            return -1
        offset_in_item = rel - idx * self._item_height
        if offset_in_item > self._item_height - ui_scaled(4):
            return -1
        return idx


def get_scale_options() -> list[tuple[str, str]]:
    """Пункты меню масштаба: «Авто» и фиксированные проценты."""
    options = [(SCALE_AUTO, tr("scale_auto"))]
    for percent in (100, 125, 150, 175, 200):
        options.append((f"{percent / 100:g}", f"{percent}%"))
    return options
