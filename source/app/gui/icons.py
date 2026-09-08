import os
from collections import OrderedDict

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from app.core.constants import resource_path
from app.core.logger import logger
from app.gui.scaling import ui_scaled

_MAX_CACHE = 256
ICON_CACHE: OrderedDict = OrderedDict()
RENDERER_CACHE: dict = {}


def _cache_get(cache: OrderedDict, key):
    try:
        val = cache.pop(key)
        cache[key] = val
        return val
    except KeyError:
        return None


def _cache_put(cache: OrderedDict, key, val):
    cache[key] = val
    while len(cache) > _MAX_CACHE:
        cache.popitem(last=False)


def clear_icon_cache():
    ICON_CACHE.clear()
    RENDERER_CACHE.clear()


def _tint_pixmap(pix: QPixmap, color: QColor) -> QPixmap:
    if pix.isNull():
        return pix
    tinted = QPixmap(pix.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    try:
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
    finally:
        painter.end()
    return tinted


def get_icon(file_name: str, size_px: int | None = None, *,
             dark_theme: bool = False,
             force_dark: bool = False,
             force_white: bool = False) -> QIcon:
    """Загружает SVG-иконку, окрашенную под тему (с LRU-кэшированием).

    Базовый размер из вызова масштабируется под разрешение экрана,
    поэтому все места вызова остаются с исходными «дизайнерскими» px.
    """
    path = resource_path(os.path.join("assets", "icons", file_name))
    render_size = ui_scaled(size_px or 48)
    if force_white:
        tint = QColor("#ffffff")
    elif force_dark or not dark_theme:
        tint = QColor("#1a1a1a")
    else:
        tint = QColor("#ffffff")

    cache_key = (path, render_size, tint.name())
    cached = _cache_get(ICON_CACHE, cache_key)
    if cached is not None:
        return cached

    if not os.path.exists(path):
        logger.error("Icon not found: %s", path)
        empty = QIcon()
        _cache_put(ICON_CACHE, cache_key, empty)
        return empty

    renderer = RENDERER_CACHE.get(path)
    if renderer is None:
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            logger.error("Invalid SVG icon: %s", path)
            empty = QIcon()
            _cache_put(ICON_CACHE, cache_key, empty)
            return empty
        RENDERER_CACHE[path] = renderer

    pix = QPixmap(render_size, render_size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    if pix.isNull():
        logger.error("Failed to render icon: %s", path)
        empty = QIcon()
        _cache_put(ICON_CACHE, cache_key, empty)
        return empty

    icon = QIcon(_tint_pixmap(pix, tint))
    _cache_put(ICON_CACHE, cache_key, icon)
    return icon


def get_icon_pixmap(file_name: str, size_px: int, **kwargs) -> QPixmap:
    """Пиксмап иконки нужного (уже масштабированного) размера для QLabel."""
    scaled = ui_scaled(size_px)
    return get_icon(file_name, size_px, **kwargs).pixmap(scaled, scaled)


def create_icon_label(file_name: str, size: int = 48, dark_theme: bool = False) -> QLabel:
    label = QLabel()
    pixmap = get_icon_pixmap(file_name, size, dark_theme=dark_theme)
    label.setPixmap(pixmap)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label
