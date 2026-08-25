from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

from app.gui.icons import get_icon_pixmap
from app.gui.localization import tr
from app.gui.scaling import get_ui_scale, ui_scaled


class SettingsPopup(QWidget):
    """Меню настроек: смена темы, языка и масштаба интерфейса.

    Пункты языка и масштаба открывают вложенные попапы — о них
    напоминает шеврон «›» справа.
    """

    action_selected = Signal(str)

    THEME = "theme"
    LANGUAGE = "language"
    SCALE = "scale"

    def __init__(self, dark_theme: bool, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dark_theme = dark_theme
        self._hover_index = -1
        self._items: list[tuple[str, str, bool]] = [
            (self.THEME, tr("theme_button").strip(), False),
            (self.LANGUAGE, tr("language_button").strip(), True),
            (self.SCALE, tr("scale_button").strip(), True),
        ]
        self._item_height = ui_scaled(32)
        self._padding = ui_scaled(6)
        self._radius = ui_scaled(12)
        self._margin = ui_scaled(10)  # место под ручную тень

        total_height = self._margin * 2 + self._padding * 2 + self._item_height * len(self._items)
        self._width = ui_scaled(200) + self._margin * 2
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
        icon_px = ui_scaled(16)
        for i, (action, label, has_submenu) in enumerate(self._items):
            y = m + self._padding + i * self._item_height
            item_rect_x = m + self._padding
            item_rect_w = self.width() - 2 * m - self._padding * 2
            item_rect_h = self._item_height - gap

            is_hovered = i == self._hover_index
            if is_hovered:
                hover_bg = QColor("#363d46") if self.dark_theme else QColor("#f0f2f5")
                hover_path = QPainterPath()
                hover_path.addRoundedRect(item_rect_x, y + gap, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(hover_path, hover_bg)
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")
            else:
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")

            # Иконка пункта (тема показывает целевое состояние, как футер-кнопка раньше)
            icon_x = item_rect_x + ui_scaled(10)
            icon_y = y + gap + (item_rect_h - icon_px) // 2
            if action == self.THEME:
                icon_name = "sun.svg" if self.dark_theme else "moon.svg"
                painter.drawPixmap(icon_x, icon_y, get_icon_pixmap(icon_name, 16, dark_theme=self.dark_theme))
            elif action == self.LANGUAGE:
                painter.drawPixmap(icon_x, icon_y, get_icon_pixmap("language.svg", 16, dark_theme=self.dark_theme))
            else:  # SCALE — глиф «развернуть»: диагональ со стрелками на концах
                painter.setPen(QPen(
                    text_color, 1.6,
                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
                ))
                inset = ui_scaled(3)
                x0, y0 = icon_x + inset, icon_y + icon_px - inset
                x1, y1 = icon_x + icon_px - inset, icon_y + inset
                arrow = ui_scaled(5)
                painter.drawLine(x0, y0, x1, y1)
                painter.drawLine(x1, y1, x1 - arrow, y1)
                painter.drawLine(x1, y1, x1, y1 + arrow)
                painter.drawLine(x0, y0, x0 + arrow, y0)
                painter.drawLine(x0, y0, x0, y0 - arrow)

            painter.setFont(self._item_font())
            painter.setPen(text_color)
            text_rect = QRect(
                item_rect_x + ui_scaled(34), y + gap,
                item_rect_w - ui_scaled(52), item_rect_h,
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

            if has_submenu:
                painter.setPen(QPen(
                    QColor("#8b949e"), 1.8,
                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
                ))
                cx = item_rect_x + item_rect_w - ui_scaled(16)
                cy = y + gap + item_rect_h // 2
                painter.drawLine(cx - 3, cy - 4, cx + 1, cy)
                painter.drawLine(cx + 1, cy, cx - 3, cy + 4)

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
            action, _label, _submenu = self._items[idx]
            # Закрытие с анимацией и открытие вложенного попапа выполняет
            # MainWindow (см. _on_settings_action): меню затухает и только
            # после close() показывается вложенное — иначе popup-grab Qt
            # закрывает его сразу после показа
            self.action_selected.emit(action)
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
        if idx >= len(self._items):
            return -1
        offset_in_item = rel - idx * self._item_height
        if offset_in_item > self._item_height - ui_scaled(4):
            return -1
        return idx
