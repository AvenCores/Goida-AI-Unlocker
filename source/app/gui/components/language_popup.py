from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

from app.gui.scaling import get_ui_scale, ui_scaled

# Flag definitions: horizontal/vertical stripes, cross, circle, or custom types
_FLAGS: dict[str, dict] = {
    "ru": {"stripes": [("#ffffff", 1/3), ("#0039a6", 1/3), ("#d52b1e", 1/3)]},
    "en": {"type": "cross", "bg": "#012169", "cross": "#c8102e", "fimb": "#ffffff"},
    "de": {"stripes": [("#000000", 1/3), ("#dd0000", 1/3), ("#ffcc00", 1/3)]},
    "uk": {"stripes": [("#0057b7", 0.5), ("#ffd700", 0.5)]},
    "be": {"stripes": [("#d52b1e", 2/3), ("#009639", 1/3)]},
    "kk": {"type": "kazakhstan", "bg": "#00afca", "gold": "#fec50c"},
    "fr": {"vertical": True, "stripes": [("#002395", 1/3), ("#ffffff", 1/3), ("#ed2939", 1/3)]},
    "pl": {"stripes": [("#ffffff", 0.5), ("#dc143c", 0.5)]},
    "es": {"stripes": [("#c60b1e", 0.25), ("#ffc400", 0.5), ("#c60b1e", 0.25)]},
    "pt": {"type": "portugal"},
    "it": {"vertical": True, "stripes": [("#009246", 1/3), ("#ffffff", 1/3), ("#ce2b37", 1/3)]},
    "tr": {"type": "crescent"},
    "zh": {"type": "circle", "bg": "#de2910", "circle": "#ffde00"},
    "ja": {"type": "circle", "bg": "#ffffff", "circle": "#bc002d"},
    "ko": {"type": "taegeuk", "bg": "#ffffff"},
    "cs": {"type": "czech"},
    "nl": {"stripes": [("#ae1c28", 1/3), ("#ffffff", 1/3), ("#21468b", 1/3)]},
    "sv": {"type": "nordic", "bg": "#006aa7", "cross": "#fecc00"},
}


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
        self._item_height = ui_scaled(32)
        self._padding = ui_scaled(6)
        self._radius = ui_scaled(12)

        self._margin = ui_scaled(10)  # space for manual shadow
        total_height = self._margin * 2 + self._padding * 2 + self._item_height * len(self._items)
        self._width = ui_scaled(190) + self._margin * 2
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
        painter.setFont(self._item_font())
        for i, (code, name) in enumerate(self._items):
            y = m + self._padding + i * self._item_height
            item_rect_x = m + self._padding
            item_rect_w = self.width() - 2 * m - self._padding * 2
            item_rect_h = self._item_height - ui_scaled(4)
            gap = ui_scaled(2)

            is_selected = code == self.current_lang
            is_hovered = i == self._hover_index

            # Hover / selected background
            if is_selected:
                accent = QColor("#246cf0") if self.dark_theme else QColor("#0078d4")
                hover_path = QPainterPath()
                hover_path.addRoundedRect(item_rect_x, y + gap, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(hover_path, accent)
                text_color = QColor("#ffffff")
            elif is_hovered:
                hover_bg = QColor("#363d46") if self.dark_theme else QColor("#f0f2f5")
                hover_path = QPainterPath()
                hover_path.addRoundedRect(item_rect_x, y + gap, item_rect_w, item_rect_h, 8, 8)
                painter.fillPath(hover_path, hover_bg)
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")
            else:
                text_color = QColor("#f3f6fd") if self.dark_theme else QColor("#1a1a1a")

            # Flag
            flag_def = _FLAGS.get(code)
            if flag_def:
                flag_w, flag_h = ui_scaled(18), ui_scaled(12)
                flag_y = y + gap + (item_rect_h - flag_h) // 2
                self._draw_flag(painter, flag_def, item_rect_x + ui_scaled(8), flag_y, flag_w, flag_h)

            # Text
            painter.setFont(self._item_font())
            painter.setPen(text_color)
            text_rect = QRect(
                item_rect_x + ui_scaled(32), y + gap,
                item_rect_w - ui_scaled(54), item_rect_h,
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

            # Checkmark for selected
            if is_selected:
                painter.setPen(QPen(QColor("#ffffff"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                cx = item_rect_x + item_rect_w - ui_scaled(20)
                cy = y + gap + item_rect_h // 2
                painter.drawLine(cx - 4, cy, cx - 1, cy + 3)
                painter.drawLine(cx - 1, cy + 3, cx + 5, cy - 3)

        painter.end()

    def _item_font(self) -> QFont:
        font = QFont("Segoe UI")
        font.setPointSizeF(round(9.5 * get_ui_scale(), 1))
        font.setWeight(QFont.Weight.Medium)
        return font

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

    def _draw_flag(self, painter: QPainter, flag_def: dict, x: int, y: int, w: int, h: int):
        """Draw a small rounded flag."""
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(x, y, w, h), 3, 3)
        painter.setClipPath(clip_path)

        flag_type = flag_def.get("type", "stripes")

        if flag_type == "cross":
            # UK-style: blue bg + white fimbriation + red cross (centered)
            painter.fillRect(x, y, w, h, QColor(flag_def["bg"]))
            fimb = QColor(flag_def["fimb"])
            cross = QColor(flag_def["cross"])
            cx, cy = x + w // 2, y + h // 2
            painter.fillRect(cx - 3, y, 6, h, fimb)
            painter.fillRect(x, cy - 3, w, 6, fimb)
            painter.fillRect(cx - 2, y, 4, h, cross)
            painter.fillRect(x, cy - 2, w, 4, cross)

        elif flag_type == "nordic":
            # Nordic cross (Sweden): vertical bar offset to the left
            painter.fillRect(x, y, w, h, QColor(flag_def["bg"]))
            cross_color = QColor(flag_def["cross"])
            vx = x + int(w * 0.35)  # vertical bar at ~1/3 from left
            cy = y + h // 2
            painter.fillRect(vx - 2, y, 4, h, cross_color)
            painter.fillRect(x, cy - 2, w, 4, cross_color)

        elif flag_type == "kazakhstan":
            # Sky-blue field + gold ornament stripe on left + gold sun in center
            painter.fillRect(x, y, w, h, QColor(flag_def["bg"]))
            gold = QColor(flag_def["gold"])
            painter.fillRect(x, y, 3, h, gold)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gold)
            sun_cx = x + w // 2 + 1
            sun_cy = y + h // 2 - 1
            painter.drawEllipse(sun_cx - 3, sun_cy - 3, 6, 6)

        elif flag_type == "circle":
            # Solid bg + centered circle (Japan, China)
            painter.fillRect(x, y, w, h, QColor(flag_def["bg"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(flag_def["circle"]))
            r = min(w, h) // 3
            cx, cy = x + w // 2, y + h // 2
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        elif flag_type == "crescent":
            # Turkey: red bg + white crescent + white star
            painter.fillRect(x, y, w, h, QColor("#e30a17"))
            painter.setPen(Qt.PenStyle.NoPen)
            cx, cy = x + w // 2 - 1, y + h // 2
            r = min(w, h) // 3
            # White circle
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            # Red circle offset right to create crescent
            painter.setBrush(QColor("#e30a17"))
            offset = r // 2
            painter.drawEllipse(cx - r + offset + 1, cy - r + 1, r * 2 - 2, r * 2 - 2)
            # Small white star (dot) to the right
            star_x = cx + r + 2
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(star_x - 1, cy - 1, 3, 3)

        elif flag_type == "portugal":
            # Portugal: green left (2/5) + red right (3/5) + yellow sphere at boundary
            gw = int(w * 0.4)
            painter.fillRect(x, y, gw, h, QColor("#046a38"))
            painter.fillRect(x + gw, y, w - gw, h, QColor("#da291c"))
            # Yellow armillary sphere at boundary
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffe900"))
            sr = min(w, h) // 4
            painter.drawEllipse(x + gw - sr, y + h // 2 - sr, sr * 2, sr * 2)

        elif flag_type == "taegeuk":
            # South Korea: white bg + red(top)/blue(bottom) taegeuk circle
            painter.fillRect(x, y, w, h, QColor(flag_def["bg"]))
            cx, cy = x + w // 2, y + h // 2
            r = min(w, h) // 3
            painter.setPen(Qt.PenStyle.NoPen)
            # Top half red (180° span from 9 o'clock going up)
            painter.setBrush(QColor("#cd2e3a"))
            painter.drawPie(cx - r, cy - r, r * 2, r * 2, 180 * 16, 180 * 16)
            # Bottom half blue (180° span from 3 o'clock going down)
            painter.setBrush(QColor("#0047a0"))
            painter.drawPie(cx - r, cy - r, r * 2, r * 2, 0, 180 * 16)

        elif flag_type == "czech":
            # Czech Republic: white top, red bottom, blue triangle on left
            half_h = h // 2
            painter.fillRect(x, y, w, half_h, QColor("#ffffff"))
            painter.fillRect(x, y + half_h, w, h - half_h, QColor("#d7141a"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#11457e"))
            tri = QPainterPath()
            tri.moveTo(x, y)
            tri.lineTo(x + w // 2, y + h // 2)
            tri.lineTo(x, y + h)
            tri.closeSubpath()
            painter.drawPath(tri)

        else:
            # Stripes (horizontal or vertical)
            vertical = flag_def.get("vertical", False)
            stripes = flag_def["stripes"]
            offset = 0.0
            for color_hex, fraction in stripes:
                color = QColor(color_hex)
                if vertical:
                    sx = x + int(offset * w)
                    sw = int((offset + fraction) * w) - int(offset * w)
                    painter.fillRect(sx, y, sw + 1, h, color)
                else:
                    sy = y + int(offset * h)
                    sh = int((offset + fraction) * h) - int(offset * h)
                    painter.fillRect(x, sy, w, sh + 1, color)
                offset += fraction

        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 40), 0.8))
        painter.drawRoundedRect(QRectF(x, y, w, h), 3, 3)
        painter.restore()

    def _index_at(self, y: float) -> int:
        rel = y - self._margin - self._padding
        if rel < 0:
            return -1
        idx = int(rel // self._item_height)
        if idx >= len(self._items):
            return -1
        # Check if within item bounds (not in gap)
        offset_in_item = rel - idx * self._item_height
        if offset_in_item > self._item_height - ui_scaled(4):
            return -1
        return idx
