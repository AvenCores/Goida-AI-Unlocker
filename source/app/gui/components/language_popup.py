from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont


class LanguagePopup(QWidget):
    """Modern floating popup for language selection."""

    language_selected = Signal(str)

    def __init__(self, languages: dict[str, str], current_lang: str, dark_theme: bool, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dark_theme = dark_theme
        self.current_lang = current_lang
        self._hover_index = -1
        self._items: list[tuple[str, str]] = list(languages.items())
        self._item_height = 40
        self._padding = 8
        self._radius = 12

        self._margin = 10  # space for manual shadow
        total_height = self._margin * 2 + self._padding * 2 + self._item_height * len(self._items)
        self._width = 190 + self._margin * 2
        self.setFixedSize(self._width, total_height)

        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        m = self._margin
        # Manual soft shadow (layered rects)
        shadow_color = QColor(0, 0, 0, 18) if not self.dark_theme else QColor(0, 0, 0, 40)
        for i in range(m, 0, -1):
            alpha_factor = (m - i + 1) / m
            c = QColor(shadow_color)
            c.setAlpha(int(shadow_color.alpha() * alpha_factor))
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(m - i, m - i + 2, self.width() - 2 * (m - i), self.height() - 2 * (m - i), self._radius + i, self._radius + i)
            painter.fillPath(shadow_path, c)

        # Background
        bg_color = QColor("#2d333b") if self.dark_theme else QColor("#ffffff")
        border_color = QColor("#3c434d") if self.dark_theme else QColor("#e1e4e8")

        path = QPainterPath()
        path.addRoundedRect(m, m, self.width() - 2 * m, self.height() - 2 * m, self._radius, self._radius)

        painter.fillPath(path, bg_color)
        painter.setPen(QPen(border_color, 1.2))
        painter.drawPath(path)

        # Items
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        for i, (code, name) in enumerate(self._items):
            y = m + self._padding + i * self._item_height
            item_rect_x = m + self._padding
            item_rect_w = self.width() - 2 * m - self._padding * 2
            item_rect_h = self._item_height - 4

            is_selected = code == self.current_lang
            is_hovered = i == self._hover_index

            # Hover / selected background
            if is_selected:
                accent = QColor("#246cf0") if self.dark_theme else QColor("#0078d4")
                hover_path = QPainterPath()
                hover_path.addRoundedRect(item_rect_x, y + 2, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(hover_path, accent)
                text_color = QColor("#ffffff")
            elif is_hovered:
                hover_bg = QColor("#363d46") if self.dark_theme else QColor("#f0f2f5")
                hover_path = QPainterPath()
                hover_path.addRoundedRect(item_rect_x, y + 2, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(hover_path, hover_bg)
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")
            else:
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")

            # Text
            painter.setPen(text_color)
            text_rect = QRect(item_rect_x + 14, y + 2, item_rect_w - 40, item_rect_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

            # Checkmark for selected
            if is_selected:
                painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                cx = item_rect_x + item_rect_w - 24
                cy = y + 2 + item_rect_h // 2
                painter.drawLine(cx - 5, cy, cx - 1, cy + 4)
                painter.drawLine(cx - 1, cy + 4, cx + 6, cy - 4)

        painter.end()

    def mouseMoveEvent(self, event):
        idx = self._index_at(event.position().toPoint().y())
        if idx != self._hover_index:
            self._hover_index = idx
            self.update()
            if idx >= 0:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        idx = self._index_at(event.position().toPoint().y())
        if idx >= 0:
            code, _ = self._items[idx]
            self.language_selected.emit(code)
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
        if idx >= len(self._items):
            return -1
        # Check if within item bounds (not in gap)
        offset_in_item = rel - idx * self._item_height
        if offset_in_item > self._item_height - 4:
            return -1
        return idx
