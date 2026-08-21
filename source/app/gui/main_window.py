import sys
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton, QToolButton, QComboBox, QApplication
)
from PySide6.QtCore import Qt, QTimer, Slot, QThreadPool, QSize
from PySide6.QtGui import QIcon

from app.core.constants import resource_path
from app.core.hosts_manager import HostsManager, HostsStatusResult
from app.core.dns_manager import DnsManager, DNS_PROVIDER_ID
from app.core.settings import get_setting, set_setting
from app.gui.localization import tr, set_current_language
from app.gui.styles import get_stylesheet, get_about_toolbutton_style, clear_stylesheet_cache, is_system_dark_theme
from app.gui.icons import get_icon, refresh_icons
from app.gui.workers import HostsWorker, VersionWorker, AppUpdateWorker
from app.gui.components.title_bar import DraggableTitleBar
from app.gui.components.page_navigator import PageNavigator
from app.gui.pages.home_page import HomePage
from app.gui.pages.about_page import build_about_page
from app.gui.pages.donate_page import build_donate_page
from app.gui.pages.message_page import (
    build_message_page,
    build_processing_page,
    build_update_available_page,
    build_no_update_page,
)
from app.gui.pages.hosts_editor_page import build_hosts_editor_page, build_hosts_backup_viewer_page


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget = QStackedWidget()

        # Window settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        icon_file = "icon.icns" if sys.platform == "darwin" else "icon.ico"
        self.setWindowIcon(QIcon(resource_path(icon_file)))
        self.setWindowTitle("Goida AI Unlocker")

        # Load theme setting
        from app.core.settings import get_setting
        saved_theme = get_setting("theme")
        if saved_theme == "dark":
            self.dark_theme = True
        elif saved_theme == "light":
            self.dark_theme = False
        else:
            self.dark_theme = is_system_dark_theme()

        from app.gui.localization import CURRENT_LANGUAGE
        self.language = CURRENT_LANGUAGE
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])

        self.hosts_manager = HostsManager()
        self.dns_manager = DnsManager()
        self.current_provider = self._detect_installed_provider()
        self.current_mechanism = get_setting("mechanism", "hosts")
        if self.current_mechanism not in ("hosts", DNS_PROVIDER_ID):
            self.current_mechanism = "hosts"
        self._check_updates_running = False
        self._version_status_check_running = False
        self._processing_widget: Optional[QWidget] = None
        self._lang_popup: Optional[QWidget] = None

        # UI components
        self.title_bar: Optional[QWidget] = None
        self.title_label: Optional[QLabel] = None
        self.home_page: Optional[HomePage] = None

        # Theme/language footer buttons
        self.theme_button: Optional[QPushButton] = None
        self.language_button: Optional[QPushButton] = None

        self._setup_ui()
        self._apply_main_texts()
        self.check_version_status()

    def _setup_ui(self):
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        title_bar = DraggableTitleBar(self)
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(32)
        self.title_bar = title_bar
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(12, 0, 8, 0)
        title_bar_layout.setSpacing(0)

        title_label = QLabel("Goida AI Unlocker")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_label.setStyleSheet("QLabel { color: #666666; font-size: 13px; font-weight: bold; background: transparent; }")
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        minimize_button = QPushButton("\u2500")
        minimize_button.setFixedSize(26, 26)
        minimize_button.clicked.connect(self.showMinimized)
        minimize_button.setStyleSheet(
            "QPushButton { background: transparent; color: #666666; border: none; font-size: 14px; font-weight: bold; } "
            "QPushButton:hover { color: #2d7dff; }"
        )
        close_button = QPushButton("\u00d7")
        close_button.setFixedSize(26, 26)
        close_button.clicked.connect(QApplication.instance().quit)
        close_button.setStyleSheet(
            "QPushButton { background: transparent; color: #666666; border: none; font-size: 18px; font-weight: bold; } "
            "QPushButton:hover { color: #e06c75; }"
        )
        title_bar_layout.addWidget(minimize_button)
        title_bar_layout.addWidget(close_button)
        main_layout.addWidget(title_bar)
        self.title_label = title_label

        # Home page
        home_page = HomePage(
            self.hosts_manager, self.dns_manager, self.styles,
            self.dark_theme, self.current_provider, self.current_mechanism
        )
        self.home_page = home_page

        # Footer with language/theme buttons
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(20, 0, 20, 20)
        footer_layout.setSpacing(0)

        language_button = QPushButton()
        language_button.setIcon(get_icon("language.svg", 20, dark_theme=self.dark_theme, force_dark=True))
        language_button.setIconSize(QSize(20, 20))
        language_button.setProperty("icon_name", "language.svg")
        language_button.setProperty("icon_force_dark", True)
        language_button.setProperty("style_role", "theme")
        language_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        language_button.setFixedSize(44, 44)
        language_button.setCursor(Qt.CursorShape.PointingHandCursor)
        language_button.clicked.connect(self.switch_language)
        self.language_button = language_button

        theme_button = QPushButton()
        initial_theme_icon = "sun.svg" if self.dark_theme else "moon.svg"
        theme_button.setIcon(get_icon(initial_theme_icon, 20, dark_theme=self.dark_theme, force_dark=True))
        theme_button.setIconSize(QSize(20, 20))
        theme_button.setProperty("icon_name", initial_theme_icon)
        theme_button.setProperty("icon_force_dark", True)
        theme_button.setProperty("style_role", "theme")
        theme_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        theme_button.setFixedSize(44, 44)
        theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        theme_button.clicked.connect(self.switch_theme)
        self.theme_button = theme_button

        footer_layout.addWidget(language_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        footer_layout.addStretch()
        footer_layout.addWidget(theme_button, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        # Assemble: home_page + footer in a wrapper
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(home_page, 1)
        central_layout.addLayout(footer_layout)

        self.resize(640, 640)

        # Page navigator
        self._navigator = PageNavigator(self.stacked_widget, title_bar_height=32)
        self._navigator.set_parent_window(self)

        self.stacked_widget.addWidget(central_widget)
        self._home_wrapper = central_widget
        main_layout.addWidget(self.stacked_widget)
        self.setCentralWidget(main_container)

        # Connect home page signals
        home_page.install_requested.connect(self.start_installation)
        home_page.donate_requested.connect(self.show_donate)
        home_page.about_requested.connect(self.show_about)
        home_page.update_check_requested.connect(self.check_for_updates)
        home_page.provider_changed.connect(self._on_provider_changed)
        home_page.mechanism_changed.connect(self._on_mechanism_changed)
        home_page.open_hosts_requested.connect(self.show_hosts_editor)
        home_page.view_backups_requested.connect(self.show_hosts_backup_viewer)

    # --- Window helpers ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fix_widget_size(self._home_wrapper)
        if self.stacked_widget:
            cur = self.stacked_widget.currentWidget()
            if cur:
                self._fix_widget_size(cur)

    def start_system_move(self) -> bool:
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemMove())
        except Exception:
            return False

    def _fix_widget_size(self, w: QWidget):
        h = self.height() - (self.title_bar.height() if self.title_bar else 32)
        w.setMinimumSize(self.width(), h)
        w.setMaximumSize(self.width(), h)

    # --- Page navigation ---

    def _add_and_switch(self, widget: QWidget):
        if self.stacked_widget:
            self.stacked_widget.addWidget(widget)
        self.update_subwindow_styles()
        self._navigator.animate_switch(widget)

    def _return_to_main(self, widget: QWidget):
        self._navigator.return_to_main(self._home_wrapper, widget)

    def _remove_widget(self, widget: QWidget):
        self._navigator.remove_widget(widget)

    # --- Pages ---

    def show_message(self, msg: str, success: bool = True, word_wrap: bool = False):
        widget = build_message_page(
            msg, success, word_wrap, self.styles, self.dark_theme,
            fix_size_fn=self._fix_widget_size,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_processing(self, action: str) -> QWidget:
        widget = build_processing_page(
            action, self.styles, self.dark_theme,
            fix_size_fn=self._fix_widget_size,
        )
        self._add_and_switch(widget)
        return widget

    def show_update_available(self, local_ver: str, latest_ver: str, dl_url: str):
        widget = build_update_available_page(
            local_ver, latest_ver, dl_url, self.styles, self.dark_theme,
            fix_size_fn=self._fix_widget_size,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_no_update(self, local_ver: str, latest_ver: str):
        widget = build_no_update_page(
            local_ver, latest_ver, self.styles, self.dark_theme,
            fix_size_fn=self._fix_widget_size,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_donate(self):
        widget = build_donate_page(
            self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
        )
        self._fix_widget_size(widget)
        self._add_and_switch(widget)

    def show_about(self):
        widget = build_about_page(
            self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_hosts_editor(self):
        def _on_save(content: str):
            self._processing_widget = self.show_processing("save")
            worker = HostsWorker("save", self.hosts_manager, self.current_provider, self)
            worker.save_content = content
            worker.signals.finished.connect(self._on_hosts_save_finished, Qt.ConnectionType.QueuedConnection)
            QThreadPool.globalInstance().start(worker)

        widget = build_hosts_editor_page(
            self.hosts_manager, self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
            save_callback=_on_save,
            fix_size_fn=self._fix_widget_size,
        )
        self._add_and_switch(widget)

    def show_hosts_backup_viewer(self):
        widget = build_hosts_backup_viewer_page(
            self.hosts_manager, self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
            fix_size_fn=self._fix_widget_size,
        )
        self._add_and_switch(widget)

    @Slot(str, bool, str, bool)
    def _on_hosts_save_finished(self, action: str, ok: bool, error: str, backup_failed: bool = False):
        if self._processing_widget is not None:
            proc = self._processing_widget
            self._processing_widget = None
            QTimer.singleShot(400, lambda: self._remove_widget(proc))

        if ok:
            self.show_message(tr("hosts_editor_save_success"), success=True, word_wrap=True)
        else:
            hint = self._get_error_hint(error)
            self.show_message(tr("hosts_editor_save_error", hint=hint), success=False, word_wrap=True)

        self.home_page.update_status_label()
        self.check_version_status()

    def _get_error_hint(self, error: str) -> str:
        """Determine the error hint to show based on the actual error and privileges."""
        import os
        from app.utils.helpers import is_windows_admin

        # If we have a specific error message from the worker, show it
        if error:
            return error

        # Fallback heuristic when no specific error is available
        if sys.platform == "win32":
            if is_windows_admin():
                return tr("hosts_locked_hint_windows")
            return tr("admin_hint_windows")
        else:
            is_root = False
            try:
                is_root = os.geteuid() == 0
            except AttributeError:
                pass
            if is_root:
                return tr("hosts_locked_hint_unix")
            return tr("admin_hint_unix")

    # --- Installation / Workers ---

    def start_installation(self, action: str):
        if action == "open":
            self.show_hosts_editor()
            return
        self._processing_widget = self.show_processing(action)
        if self.current_mechanism == DNS_PROVIDER_ID:
            worker = HostsWorker(action, self.dns_manager, DNS_PROVIDER_ID, self)
        else:
            worker = HostsWorker(action, self.hosts_manager, self.current_provider, self)
        worker.signals.finished.connect(self.on_hosts_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(str, bool, str, bool)
    def on_hosts_finished(self, action: str, ok: bool, error: str, backup_failed: bool = False):
        is_dns = self.current_mechanism == DNS_PROVIDER_ID
        if ok:
            if action == "install":
                msg = tr("dns_install_success" if is_dns else "install_success")
            elif action == "update":
                msg = tr("dns_install_success" if is_dns else "update_success")
            else:
                msg = tr("dns_uninstall_success" if is_dns else "uninstall_success")
            self.show_message(msg, success=True, word_wrap=True)
        else:
            hint = self._get_error_hint(error)

            if action == "install":
                msg = tr("dns_install_error" if is_dns else "install_error", hint=hint)
            elif action == "update":
                msg = tr("dns_install_error" if is_dns else "update_error", hint=hint)
            else:
                msg = tr("dns_uninstall_error" if is_dns else "uninstall_error", hint=hint)
            self.show_message(msg, success=False, word_wrap=True)

        if self._processing_widget is not None:
            proc = self._processing_widget
            self._processing_widget = None
            QTimer.singleShot(400, lambda: self._remove_widget(proc))

        self.home_page.update_status_label()
        self.check_version_status()

    # --- Version status ---

    def check_version_status(self):
        if self._version_status_check_running:
            return
        self._version_status_check_running = True
        if self.current_mechanism == DNS_PROVIDER_ID:
            worker = VersionWorker(self.dns_manager, DNS_PROVIDER_ID, self)
        else:
            worker = VersionWorker(self.hosts_manager, self.current_provider, self)
        worker.signals.status_ready.connect(
            self._on_version_status_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_version_status_ready(self, status):
        self._version_status_check_running = False
        self.home_page.apply_hosts_version_status(status)

    def _detect_installed_provider(self) -> str:
        content = self.hosts_manager.read()
        if "dns.geohide.ru" in content:
            return "geohide"
        return "dns.malw.link"

    def _on_provider_changed(self, provider: str):
        self.current_provider = provider
        self.check_version_status()

    def _on_mechanism_changed(self, mechanism: str):
        self.current_mechanism = mechanism
        set_setting("mechanism", mechanism)
        self.check_version_status()

    # --- App updates ---

    def check_for_updates(self):
        if self._check_updates_running:
            return
        self._check_updates_running = True

        worker = AppUpdateWorker(self)
        worker.signals.update_ready.connect(self.on_app_update_ready, Qt.ConnectionType.QueuedConnection)
        worker.signals.no_update.connect(self.on_app_up_to_date, Qt.ConnectionType.QueuedConnection)
        worker.signals.message.connect(self.on_app_update_message, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(str, str, str)
    def on_app_update_ready(self, local: str, remote: str, url: str):
        self.show_update_available(local, remote, url)
        self._check_updates_running = False

    @Slot(str, str)
    def on_app_up_to_date(self, local: str, remote: str):
        self.show_no_update(local, remote)
        self._check_updates_running = False

    @Slot(str, bool, bool)
    def on_app_update_message(self, msg: str, success: bool, word_wrap: bool):
        self.show_message(msg, success, word_wrap)
        self._check_updates_running = False

    # --- Theme / Language ---

    def _animate_transition(self, update_func: Callable):
        if self.is_animating:
            return
        self.is_animating = True
        steps, interval = 15, 20

        def fade_out(step=1.0):
            try:
                if step >= 0:
                    self.setWindowOpacity(step)
                    QTimer.singleShot(interval, lambda: fade_out(step - 1.0 / steps))
                else:
                    self.setWindowOpacity(0)
                    self.setUpdatesEnabled(False)
                    update_func()
                    self.setUpdatesEnabled(True)
                    fade_in()
            except Exception:
                self.setWindowOpacity(1.0)
                self.is_animating = False

        def fade_in(step=0.0):
            try:
                if step <= 1.0:
                    self.setWindowOpacity(step)
                    QTimer.singleShot(interval, lambda: fade_in(step + 1.0 / steps))
                else:
                    self.setWindowOpacity(1.0)
                    self.is_animating = False
            except Exception:
                self.setWindowOpacity(1.0)
                self.is_animating = False

        fade_out()

    def switch_theme(self):
        def update():
            self.dark_theme = not self.dark_theme
            from app.core.settings import set_setting
            set_setting("theme", "dark" if self.dark_theme else "light")
            self._apply_theme_styles()
            self._apply_main_texts()
        self._animate_transition(update)

    def change_language_to(self, new_lang):
        def update():
            self.language = set_current_language(new_lang)
            from app.core.settings import set_setting
            set_setting("language", new_lang)
            clear_stylesheet_cache()
            self._apply_theme_styles()
            self._apply_main_texts()
        self._animate_transition(update)

    def switch_language(self):
        from app.gui.localization import get_supported_languages
        from app.gui.components.language_popup import LanguagePopup

        supported = get_supported_languages()
        popup = LanguagePopup(supported, self.language, self.dark_theme, self)
        popup.language_selected.connect(self._on_language_popup_selected)

        pos = self.language_button.mapToGlobal(self.language_button.rect().topLeft())
        pos.setX(pos.x() - 14)
        pos.setY(pos.y() - popup.height() + 6)
        popup.move(pos)
        popup.show()
        self._lang_popup = popup

    def _on_language_popup_selected(self, code: str):
        if code != self.language:
            self.change_language_to(code)

    def _apply_theme_styles(self):
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])

        # Update home page
        self.home_page.styles = self.styles
        self.home_page.dark_theme = self.dark_theme
        self.home_page.apply_theme_styles()

        # Footer buttons
        self.theme_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        self.theme_button.setProperty("icon_name", "sun.svg" if self.dark_theme else "moon.svg")
        self.language_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )

        self.update_subwindow_styles()
        refresh_icons(self, self.dark_theme)

    def _apply_main_texts(self):
        self.title_label.setText("Goida AI Unlocker")
        self.home_page.apply_texts()
        self.theme_button.setText("")
        self.theme_button.setToolTip(tr("theme_button").strip())
        self.theme_button.setStatusTip(tr("theme_button").strip())
        self.theme_button.setAccessibleName(tr("theme_button").strip())
        self.language_button.setText("")
        self.language_button.setToolTip(tr("language_button").strip())
        self.language_button.setStatusTip(tr("language_button").strip())
        self.language_button.setAccessibleName(tr("language_button").strip())

    # --- Subwindow styling ---

    def update_subwindow_styles(self):
        if not self.stacked_widget:
            return
        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w is self._home_wrapper:
                continue
            w.setStyleSheet(self.styles["main"])
            for child in w.findChildren(QPushButton):
                role = child.property("style_role")
                if role == "button2":
                    child.setStyleSheet(self.styles["button2"])
                elif role == "theme":
                    child.setStyleSheet(self.styles["theme"])
                else:
                    child.setStyleSheet(self.styles["button1"])
            for child in w.findChildren(QComboBox):
                child.setStyleSheet(self.styles["combo"])
            for child in w.findChildren(QToolButton):
                if child.property("style_role") == "about_tool":
                    child.setStyleSheet(get_about_toolbutton_style(self.styles))
            for child in w.findChildren(QLabel):
                name = child.objectName()
                if name == "about_title":
                    child.setText(self.styles["about_title_html"])
                    child.setStyleSheet(self.styles["about_title_style"])
                elif name == "about_info":
                    child.setText(self.styles["about_info_html"])
                elif name == "about_link":
                    child.setText(self.styles["about_link_html"])
                elif name == "message_label":
                    child.setStyleSheet(self.styles["message_label"])
                elif name == "message_block_label":
                    child.setStyleSheet(self.styles["message_block_label"])
                elif name == "message_emoji":
                    continue
                else:
                    child.setStyleSheet(self.styles["label"])
            for card in w.findChildren(QWidget, "msg_card"):
                card.setStyleSheet(self.styles["message_card"])
            if w is not self._home_wrapper:
                refresh_icons(w, self.dark_theme)
