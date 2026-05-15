import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QAbstractButton
from PySide6.QtCore import Qt, QSize
from app.utils.helpers import resource_path

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

def get_icon(file_name: str, size_px: int | None = None, *, dark_theme: bool = False, force_dark: bool = False, force_white: bool = False) -> QIcon:
    path = resource_path(os.path.join("icons", file_name))
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

    tinted = _tint_pixmap(pix, tint)
    icon = QIcon(tinted)
    ICON_CACHE[cache_key] = icon
    return icon

def create_icon_label(file_name: str, size: int = 48, dark_theme: bool = False) -> QLabel:
    icon = get_icon(file_name, size, dark_theme=dark_theme)
    label = QLabel()
    label.setPixmap(icon.pixmap(size, size))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setObjectName("message_emoji")
    label.setProperty("icon_name", file_name)
    return label

def refresh_icons(root_widget, dark_theme: bool):
    buttons_with_icons = []
    labels_with_icons = []
    for btn in root_widget.findChildren(QAbstractButton):
        name = btn.property("icon_name")
        if name:
            buttons_with_icons.append((
                btn, name, btn.iconSize().width(),
                btn.property("icon_force_dark"), btn.property("icon_force_white")
            ))
    for lbl in root_widget.findChildren(QLabel):
        name = lbl.property("icon_name")
        if name:
            px = lbl.pixmap()
            sz = px.width() if px else 32
            labels_with_icons.append((
                lbl, name, sz,
                lbl.property("icon_force_dark"), lbl.property("icon_force_white")
            ))
    for btn, name, sz, fd, fw in buttons_with_icons:
        btn.setIcon(get_icon(name, sz, dark_theme=dark_theme, force_dark=bool(fd), force_white=bool(fw)))
    for lbl, name, sz, fd, fw in labels_with_icons:
        lbl.setPixmap(get_icon(name, sz, dark_theme=dark_theme, force_dark=bool(fd), force_white=bool(fw)).pixmap(sz, sz))
