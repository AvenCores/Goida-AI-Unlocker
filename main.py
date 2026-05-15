import sys
import json
import os
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from app.core.logger import logger
from app.core.constants import APP_VERSION
from app.utils.helpers import resource_path
from app.gui.localization import tr, CURRENT_LANGUAGE, detect_system_language, set_current_language
from app.gui.styles import is_system_dark_theme, get_stylesheet
from app.gui.icons import get_icon
from app.gui.main_window import MainWindow, DraggableTitleBar
from app.gui.hosts_helpers import open_hosts_file, open_latest_hosts_backup_file, open_hosts_backup_folder

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("QPushButton:focus { outline: none; }")

    # Load app version
    global_app_version = APP_VERSION
    try:
        with open(resource_path("app_info.json"), "r", encoding="utf-8") as vf:
            global_app_version = json.load(vf).get("version", global_app_version)
    except Exception:
        pass

    icon_path = resource_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    # Detect language
    set_current_language(detect_system_language())

    main_window = MainWindow()
    main_window.stacked_widget = QStackedWidget()
    from app.gui.localization import CURRENT_LANGUAGE
    main_window.language = CURRENT_LANGUAGE
    main_window.setWindowTitle("Goida AI Unlocker")
    main_window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    main_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    main_window.dark_theme = is_system_dark_theme()
    main_window.styles = get_stylesheet(main_window.dark_theme, main_window.language)
    main_window.setStyleSheet(main_window.styles["main"])
    main_window.setWindowIcon(QIcon(icon_path))
    main_window.resource_path = resource_path

    main_container = QWidget()
    main_layout = QVBoxLayout(main_container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    title_bar = DraggableTitleBar(main_window)
    title_bar.setObjectName("titleBar")
    title_bar.setFixedHeight(32)
    main_window.title_bar = title_bar
    title_bar_layout = QHBoxLayout(title_bar)
    title_bar_layout.setContentsMargins(12, 0, 8, 0)
    title_bar_layout.setSpacing(0)

    title_label = QLabel("Goida AI Unlocker")
    title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    title_label.setStyleSheet("QLabel { color: #666666; font-size: 13px; font-weight: bold; background: transparent; }")
    title_bar_layout.addWidget(title_label)
    title_bar_layout.addStretch()

    minimize_button = QPushButton("─")
    minimize_button.setFixedSize(26, 26)
    minimize_button.clicked.connect(main_window.showMinimized)
    minimize_button.setStyleSheet(
        "QPushButton { background: transparent; color: #666666; border: none; font-size: 14px; font-weight: bold; } "
        "QPushButton:hover { color: #2d7dff; }"
    )
    close_button = QPushButton("×")
    close_button.setFixedSize(26, 26)
    close_button.clicked.connect(app.quit)
    close_button.setStyleSheet(
        "QPushButton { background: transparent; color: #666666; border: none; font-size: 18px; font-weight: bold; } "
        "QPushButton:hover { color: #e06c75; }"
    )
    title_bar_layout.addWidget(minimize_button)
    title_bar_layout.addWidget(close_button)
    main_layout.addWidget(title_bar)

    central_widget = QWidget()
    outer_layout = QVBoxLayout(central_widget)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)
    outer_layout.addStretch()

    layout = QVBoxLayout()
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.setSpacing(24)
    layout.setContentsMargins(20, 20, 20, 20)
    outer_layout.addLayout(layout)
    outer_layout.addStretch()

    footer_layout = QHBoxLayout()
    footer_layout.setContentsMargins(20, 0, 20, 20)
    footer_layout.setSpacing(0)
    outer_layout.addLayout(footer_layout)

    main_window.resize(640, 640)

    def on_resize(event=None):
        main_window.fix_widget_size(central_widget)
        if main_window.stacked_widget:
            cur = main_window.stacked_widget.currentWidget()
            if cur:
                main_window.fix_widget_size(cur)

    orig_resize = main_window.resizeEvent

    def new_resize(event):
        orig_resize(event)
        on_resize(event)

    main_window.resizeEvent = new_resize

    app_title_label = QLabel()
    app_title_label.setObjectName("main_title")
    app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app_title_label.setTextFormat(Qt.TextFormat.RichText)
    app_title_label.setText(main_window.styles["about_title_html"])
    app_title_label.setStyleSheet(main_window.styles["about_title_style"])
    layout.addWidget(app_title_label)
    main_window.app_title_label = app_title_label

    installed = main_window.hosts_manager.is_installed()
    color = "#43b581" if installed else "#e06c75"
    status_key = "status_installed" if installed else "status_not_installed"
    textinformer = QLabel(tr("unlock_status", status=tr(status_key), color=color))
    textinformer.setTextFormat(Qt.TextFormat.RichText)
    textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    textinformer.setStyleSheet(main_window.styles["label"])
    main_window.textinformer = textinformer

    version_label = QLabel(tr("version_checking"))
    version_label.setTextFormat(Qt.TextFormat.RichText)
    version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    version_label.setStyleSheet(main_window.styles["label"])
    main_window.version_label = version_label

    update_date_label = QLabel(tr("update_date_checking"))
    update_date_label.setTextFormat(Qt.TextFormat.RichText)
    update_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    text_color = "#ffffff" if main_window.dark_theme else "#1a1a1a"
    update_date_label.setStyleSheet(
        f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
    )
    main_window.update_date_label = update_date_label

    status_container = QWidget()
    status_vbox = QVBoxLayout(status_container)
    status_vbox.setContentsMargins(16, 12, 16, 12)
    status_vbox.setSpacing(4)
    status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_vbox.addWidget(textinformer)
    status_vbox.addWidget(version_label)
    status_vbox.addWidget(update_date_label)

    main_window.status_container = status_container
    main_window.refresh_status_container_style()
    layout.addWidget(status_container)

    install_button = QPushButton(tr("install_button_install"))
    install_button.setIcon(get_icon("settings.svg", 18, dark_theme=main_window.dark_theme, force_white=True))
    install_button.setIconSize(QSize(18, 18))
    install_button.setProperty("icon_name", "settings.svg")
    install_button.setProperty("icon_force_white", True)
    install_button.setProperty("style_role", "button1")
    install_button.setProperty("install_mode", "install")
    install_button.setStyleSheet(main_window.styles["button1"])
    main_window.install_button = install_button

    uninstall_button = QPushButton(tr("uninstall_button"))
    uninstall_button.setIcon(get_icon("trash.svg", 18, dark_theme=main_window.dark_theme, force_white=True))
    uninstall_button.setIconSize(QSize(18, 18))
    uninstall_button.setProperty("icon_name", "trash.svg")
    uninstall_button.setProperty("icon_force_white", True)
    uninstall_button.setProperty("style_role", "button2")
    uninstall_button.setStyleSheet(main_window.styles["button2"])
    main_window.uninstall_button = uninstall_button

    theme_button = QPushButton(tr("theme_button"))
    theme_button.setIcon(get_icon("sun.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    theme_button.setIconSize(QSize(18, 18))
    theme_button.setProperty("icon_name", "sun.svg")
    theme_button.setProperty("icon_force_dark", True)
    theme_button.setProperty("style_role", "theme")
    theme_button.setStyleSheet(main_window.styles["theme"])
    main_window.theme_button = theme_button

    language_button = QPushButton()
    language_button.setIcon(get_icon("language.svg", 20, dark_theme=main_window.dark_theme, force_dark=True))
    language_button.setIconSize(QSize(20, 20))
    language_button.setProperty("icon_name", "language.svg")
    language_button.setProperty("icon_force_dark", True)
    language_button.setProperty("style_role", "theme")
    language_button.setStyleSheet(
        main_window.styles["theme"] +
        "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
    )
    language_button.setFixedSize(44, 44)
    language_button.setCursor(Qt.CursorShape.PointingHandCursor)
    main_window.language_button = language_button

    donate_button = QPushButton(tr("donate_button"))
    donate_button.setIcon(get_icon("heart.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    donate_button.setIconSize(QSize(18, 18))
    donate_button.setProperty("icon_name", "heart.svg")
    donate_button.setProperty("icon_force_dark", True)
    donate_button.setProperty("style_role", "theme")
    donate_button.setStyleSheet(main_window.styles["theme"])
    main_window.donate_button = donate_button

    about_button = QPushButton(tr("about_button"))
    about_button.setIcon(get_icon("info.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    about_button.setIconSize(QSize(18, 18))
    about_button.setProperty("icon_name", "info.svg")
    about_button.setProperty("icon_force_dark", True)
    about_button.setProperty("style_role", "theme")
    about_button.setStyleSheet(main_window.styles["theme"])
    main_window.about_button = about_button

    update_button = QPushButton(tr("update_button"))
    update_button.setIcon(get_icon("refresh.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    update_button.setIconSize(QSize(18, 18))
    update_button.setProperty("icon_name", "refresh.svg")
    update_button.setProperty("icon_force_dark", True)
    update_button.setProperty("style_role", "theme")
    update_button.setStyleSheet(main_window.styles["theme"])
    main_window.update_button = update_button

    open_hosts_button = QPushButton(tr("open_hosts_button"))
    open_hosts_button.setIcon(get_icon("book-open.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    open_hosts_button.setIconSize(QSize(18, 18))
    open_hosts_button.setProperty("icon_name", "book-open.svg")
    open_hosts_button.setProperty("icon_force_dark", True)
    open_hosts_button.setProperty("style_role", "theme")
    open_hosts_button.setStyleSheet(main_window.styles["theme"])
    main_window.open_hosts_button = open_hosts_button

    backup_hosts_button = QPushButton(tr("backup_hosts_button"))
    backup_hosts_button.setIcon(get_icon("clock.svg", 18, dark_theme=main_window.dark_theme, force_dark=True))
    backup_hosts_button.setIconSize(QSize(18, 18))
    backup_hosts_button.setProperty("icon_name", "clock.svg")
    backup_hosts_button.setProperty("icon_force_dark", True)
    backup_hosts_button.setProperty("style_role", "theme")
    backup_hosts_button.setStyleSheet(main_window.styles["theme"])
    main_window.backup_hosts_button = backup_hosts_button

    install_button.clicked.connect(lambda: main_window.start_installation(install_button.property("install_mode") or "install"))
    uninstall_button.clicked.connect(lambda: main_window.start_installation("uninstall"))
    theme_button.clicked.connect(main_window.switch_theme)
    language_button.clicked.connect(main_window.switch_language)
    donate_button.clicked.connect(main_window.show_donate)
    about_button.clicked.connect(main_window.show_about)
    update_button.clicked.connect(main_window.check_for_updates)
    open_hosts_button.clicked.connect(
        lambda: open_hosts_file(_inline_callback=lambda msg, ok: main_window.show_message(msg, success=ok, word_wrap=True))
    )

    def show_backup_menu():
        menu = QMenu(main_window)
        if main_window.dark_theme:
            menu.setStyleSheet(
                "QMenu { background:#2d333b; color:#f3f6fd; border:1px solid #3c434d; border-radius:10px; padding:6px; }"
                "QMenu::item { padding:6px 16px; border-radius:8px; margin:2px 0; }"
                "QMenu::item:selected { background:#246cf0; color:#ffffff; border-radius:8px; }"
            )
        else:
            menu.setStyleSheet(
                "QMenu { background:#ffffff; color:#1a1a1a; border:1px solid #cfd4db; border-radius:10px; padding:6px; }"
                "QMenu::item { padding:6px 16px; border-radius:8px; margin:2px 0; }"
                "QMenu::item:selected { background:#0078d4; color:#ffffff; border-radius:8px; }"
            )
        act1 = menu.addAction(tr("backup_menu_open_file"))
        act2 = menu.addAction(tr("backup_menu_open_folder"))
        sel = menu.exec(backup_hosts_button.mapToGlobal(backup_hosts_button.rect().bottomLeft()))
        if sel == act1:
            open_latest_hosts_backup_file()
        elif sel == act2:
            open_hosts_backup_folder()

    backup_hosts_button.clicked.connect(show_backup_menu)

    layout.addWidget(install_button)
    layout.addWidget(uninstall_button)
    layout.addWidget(open_hosts_button)
    layout.addWidget(backup_hosts_button)

    controls_hbox = QHBoxLayout()
    controls_hbox.setSpacing(12)
    controls_hbox.addWidget(theme_button)
    controls_hbox.addWidget(donate_button)
    layout.addLayout(controls_hbox)
    layout.addStretch()
    layout.addWidget(update_button)
    layout.addWidget(about_button)

    footer_layout.addWidget(language_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    footer_layout.addStretch()

    main_window.home_page = central_widget
    main_window.title_label = title_label
    if main_window.stacked_widget:
        main_window.stacked_widget.addWidget(central_widget)
    main_layout.addWidget(main_window.stacked_widget)
    main_window.setCentralWidget(main_container)

    main_window.apply_main_texts()
    main_window.check_version_status()
    main_window.show()
    on_resize()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
