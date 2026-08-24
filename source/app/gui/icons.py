import os

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from app.core.constants import resource_path

ICON_CACHE: dict = {}
RENDERER_CACHE: dict = {}


def _tint_pixmap(pix: QPixmap, color: QColor) -> QPixmap:
    if pix.isNull():
        return pix
    tinted = QPixmap(pix.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


def get_icon(file_name: str, size_px: int | None = None, *,
             dark_theme: bool = False,
             force_dark: bool = False,
             force_white: bool = False) -> QIcon:
    """Загружает SVG-иконку, окрашенную под тему (с кэшированием)."""
    path = resource_path(os.path.join("assets", "icons", file_name))
    render_size = size_px or 48
    if force_white:
        tint = QColor("#ffffff")
    elif force_dark or not dark_theme:
        tint = QColor("#1a1a1a")
    else:
        tint = QColor("#ffffff")

    cache_key = (path, render_size, tint.name())
    cached = ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    renderer = RENDERER_CACHE.get(path)
    if renderer is None:
        renderer = QSvgRenderer(path)
        RENDERER_CACHE[path] = renderer

    pix = QPixmap(render_size, render_size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()

    icon = QIcon(_tint_pixmap(pix, tint))
    ICON_CACHE[cache_key] = icon
    return icon


def create_icon_label(file_name: str, size: int = 48, dark_theme: bool = False) -> QLabel:
    label = QLabel()
    label.setPixmap(get_icon(file_name, size, dark_theme=dark_theme).pixmap(size, size))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label
