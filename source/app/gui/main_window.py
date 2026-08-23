import sys
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton
)
from PySide6.QtCore import Qt, QTimer, Slot, QThreadPool, QSize, QPropertyAnimation
from PySide6.QtGui import QIcon

from app.core.constants import resource_path
from app.core.hosts_manager import HostsManager
from app.core.dns_manager import DnsManager, DNS_PROVIDER_ID, DNS_PROVIDERS
from app.core.settings import get_setting, set_setting
from app.gui.localization import CURRENT_LANGUAGE, set_current_language, tr
from app.gui.styles import clear_stylesheet_cache, get_stylesheet, is_system_dark_theme
from app.gui.icons import get_icon
from app.gui.workers import HostsWorker, VersionWorker, AppUpdateWorker
from app.gui.components.title_bar import DraggableTitleBar, WINDOW_TITLE
from app.gui.components.page_navigator import PageNavigator
from app.gui.pages.home_page import HomePage
from app.gui.pages.about_page import AboutPage
from app.gui.pages.donate_page import DonatePage
from app.gui.pages.message_page import (
    MessagePage,
    NoUpdatePage,
    ProcessingPage,
    UpdateAvailablePage,
)
from app.gui.pages.hosts_editor_page import HostsBackupViewerPage, HostsEditorPage

# Геометрия окна: фиксированная ширина, высота подстраивается под главную
# страницу (высота меняется только при смене механизма Hosts/DNS)
WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 560
MIN_WINDOW_WIDTH = 480


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget = QStackedWidget()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        icon_file = "icon.icns" if sys.platform == "darwin" else "icon.ico"
        self.setWindowIcon(QIcon(resource_path(icon_file)))
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        # Тема: сохранённая или системная
        saved_theme = get_setting("theme")
        if saved_theme == "dark":
            self.dark_theme = True
        elif saved_theme == "light":
            self.dark_theme = False
        else:
            self.dark_theme = is_system_dark_theme()

        self.language = CURRENT_LANGUAGE
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])

        self.hosts_manager = HostsManager()
        self.dns_manager = DnsManager()
        self.current_provider = self._detect_installed_provider()
        self.current_mechanism = get_setting("mechanism", "hosts")
        if self.current_mechanism not in ("hosts", DNS_PROVIDER_ID):
            self.current_mechanism = "hosts"
        self.current_dns_provider = get_setting("dns_provider", DNS_PROVIDER_ID)
        if self.current_dns_provider not in DNS_PROVIDERS:
            self.current_dns_provider = DNS_PROVIDER_ID

        self._check_updates_running = False
        self._version_status_check_running = False
        self._processing_widget: Optional[QWidget] = None

        self.title_bar: Optional[DraggableTitleBar] = None
        self.home_page: Optional[HomePage] = None
        self.theme_button: Optional[QPushButton] = None
        self.language_button: Optional[QPushButton] = None

        self._setup_ui()
        self._apply_theme_styles()

        self.resize(WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.check_version_status()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _setup_ui(self):
        main_container = QWidget()
        # Правило QWidget#mainContainer в main-стиле красит только контейнер
        # окна (скруглённый фон); дочерние виджеты остаются прозрачными
        main_container.setObjectName("mainContainer")
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        title_bar = DraggableTitleBar(self)
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(DraggableTitleBar.TITLE_BAR_HEIGHT)
        self.title_bar = title_bar
        main_layout.addWidget(title_bar)

        home_page = HomePage(
            self.hosts_manager, self.dns_manager, self.styles,
            self.dark_theme, self.current_provider, self.current_mechanism,
            self.current_dns_provider,
        )
        self.home_page = home_page
        self.home_wrapper = self._wrap_with_footer(home_page)

        self._navigator = PageNavigator(self.stacked_widget)

        self.stacked_widget.addWidget(self.home_wrapper)
        main_layout.addWidget(self.stacked_widget)
        self.setCentralWidget(main_container)

        # Страницы обновляют себя сами (apply_theme/apply_texts),
        # поэтому ручной обход findChildren больше не нужен
        home_page.install_requested.connect(self.start_installation)
        home_page.donate_requested.connect(self.show_donate)
        home_page.about_requested.connect(self.show_about)
        home_page.update_check_requested.connect(self.check_for_updates)
        home_page.provider_changed.connect(self._on_provider_changed)
        home_page.mechanism_changed.connect(self._on_mechanism_changed)
        home_page.dns_provider_changed.connect(self._on_dns_provider_changed)
        # Текст статуса (например, список DNS-серверов) может стать длиннее —
        # окно подстраивается, чтобы карточка статуса не обрезалась
        home_page.home_content_changed.connect(
            lambda: QTimer.singleShot(0, self._adjust_window_to_content)
        )
        home_page.open_hosts_requested.connect(self.show_hosts_editor)
        home_page.view_backups_requested.connect(self.show_hosts_backup_viewer)

    def _make_footer_button(self, icon_name: str, clicked: Callable) -> QPushButton:
        button = QPushButton()
        button.setIconSize(QSize(20, 20))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(clicked)
        self._footer_buttons.append((button, icon_name))
        return button

    def _wrap_with_footer(self, page: QWidget) -> QWidget:
        """Главная страница + футер с кнопками языка/темы."""
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 0, 20, 20)
        footer.setSpacing(0)

        self._footer_buttons: list[tuple[QPushButton, str]] = []

        self.language_button = self._make_footer_button("language.svg", self.switch_language)
        self.theme_button = self._make_footer_button(
            "sun.svg" if self.dark_theme else "moon.svg", self.switch_theme
        )

        footer.addWidget(
            self.language_button,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        )
        footer.addStretch()
        footer.addWidget(
            self.theme_button,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(page, 1)
        wrapper_layout.addLayout(footer)
        return wrapper

    # ------------------------------------------------------------------
    # Размер окна
    # ------------------------------------------------------------------

    def _adjust_window_to_content(self):
        """Подстраивает высоту окна под контент главной страницы.

        Важно: sizeHint корректен только после показа окна (при показе
        применяются стили — шрифты и отступы). Поэтому замер выполняется
        через QTimer.singleShot(0) из showEvent, а не в конструкторе.
        К высоте обёртки (страница + футер) добавляется заголовок окна.

        minimumSizeHint, а не heightForWidth: цепочка hfw через вложенные
        выровненные лейауты считает высоту меток не по той ширине и занижает
        окно, из-за чего карточка статуса сжимается и обрезает текст.
        minimumSizeHint включает явные минимумы статусных меток (см.
        HomePage._sync_status_label_heights) и потому точен.
        """
        if self.home_wrapper is None:
            return
        wrapper = self.home_wrapper
        wrapper.ensurePolished()
        # Актуальные минимумы статусных меток: при показе окна стили
        # полируются, и минимумы, посчитанные в конструкторе, устаревают
        self.home_page.sync_status_label_heights()
        layout = wrapper.layout()
        if layout is not None:
            # Сбрасываем кэш геометрии лейаута, иначе minimumSizeHint
            # вернёт заниженную высоту до следующей раскладки
            layout.invalidate()
            layout.activate()
        content_h = wrapper.minimumSizeHint().height()
        target_h = max(MIN_WINDOW_HEIGHT, content_h + DraggableTitleBar.TITLE_BAR_HEIGHT)
        if abs(self.height() - target_h) > 4:
            self.resize(WINDOW_WIDTH, target_h)

    # ------------------------------------------------------------------
    # Навигация по страницам
    # ------------------------------------------------------------------

    def _add_and_switch(self, widget: QWidget):
        self._navigator.add_page(widget)
        self._navigator.animate_switch(widget)

    def _return_to_main(self, widget: QWidget):
        self._navigator.return_to_main(self.home_wrapper, widget)

    def showEvent(self, event):
        super().showEvent(event)
        # Первый показ: стили применены, лейауты посчитаны — можно точно
        # подогнать высоту окна под контент
        if not getattr(self, "_initial_size_done", False):
            self._initial_size_done = True
            QTimer.singleShot(0, self._adjust_window_to_content)

    def keyPressEvent(self, event):
        # Esc возвращает на главную из любой вложенной страницы
        if event.key() == Qt.Key.Key_Escape and self.stacked_widget.currentWidget() is not self.home_wrapper:
            self._return_to_main(self.stacked_widget.currentWidget())
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Страницы
    # ------------------------------------------------------------------

    def show_message(self, msg: str, success: bool = True, word_wrap: bool = False):
        widget = MessagePage(
            msg, success, word_wrap, self.styles, self.dark_theme,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_processing(self, action: str) -> QWidget:
        widget = ProcessingPage(action, self.styles, self.dark_theme)
        self._add_and_switch(widget)
        return widget

    def _dismiss_processing(self):
        """Убирает страницу обработки (с небольшой задержкой для плавности)."""
        if self._processing_widget is None:
            return
        proc = self._processing_widget
        self._processing_widget = None
        QTimer.singleShot(400, lambda: self._navigator.remove_widget(proc))

    def show_update_available(self, local_ver: str, latest_ver: str, dl_url: str):
        widget = UpdateAvailablePage(
            local_ver, latest_ver, dl_url, self.styles, self.dark_theme,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_no_update(self, local_ver: str, latest_ver: str):
        widget = NoUpdatePage(
            local_ver, latest_ver, self.styles, self.dark_theme,
            ok_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_donate(self):
        widget = DonatePage(
            self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_about(self):
        widget = AboutPage(
            self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    def show_hosts_editor(self):
        def on_save(content: str):
            self._processing_widget = self.show_processing("save")
            worker = HostsWorker("save", self.hosts_manager, self.current_provider, self)
            worker.save_content = content
            worker.signals.finished.connect(self._on_hosts_save_finished, Qt.ConnectionType.QueuedConnection)
            QThreadPool.globalInstance().start(worker)

        widget = HostsEditorPage(
            self.hosts_manager, self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
            save_callback=on_save,
        )
        self._add_and_switch(widget)

    def show_hosts_backup_viewer(self):
        widget = HostsBackupViewerPage(
            self.hosts_manager, self.styles, self.dark_theme,
            return_callback=lambda: self._return_to_main(widget),
        )
        self._add_and_switch(widget)

    @Slot(str, bool, str, bool)
    def _on_hosts_save_finished(self, action: str, ok: bool, error: str, backup_failed: bool = False):
        self._dismiss_processing()
        if ok:
            self.show_message(tr("hosts_editor_save_success"), success=True, word_wrap=True)
        else:
            hint = self._get_error_hint(error)
            self.show_message(tr("hosts_editor_save_error", hint=hint), success=False, word_wrap=True)

        self.home_page.update_status_label()
        self.check_version_status()

    def _get_error_hint(self, error: str) -> str:
        """Подсказка по ошибке с учётом фактических привилегий."""
        import os

        from app.utils.helpers import is_windows_admin

        if error:
            return error

        if sys.platform == "win32":
            if is_windows_admin():
                return tr("hosts_locked_hint_windows")
            return tr("admin_hint_windows")

        is_root = False
        try:
            is_root = os.geteuid() == 0
        except AttributeError:
            pass
        if is_root:
            return tr("hosts_locked_hint_unix")
        return tr("admin_hint_unix")

    # ------------------------------------------------------------------
    # Установка / воркеры
    # ------------------------------------------------------------------

    def start_installation(self, action: str):
        self._processing_widget = self.show_processing(action)
        if self.current_mechanism == DNS_PROVIDER_ID:
            worker = HostsWorker(action, self.dns_manager, self.current_dns_provider, self)
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

        self._dismiss_processing()
        self.home_page.update_status_label()
        self.check_version_status()

    # ------------------------------------------------------------------
    # Статус версии hosts / DNS
    # ------------------------------------------------------------------

    def check_version_status(self):
        if self._version_status_check_running:
            return
        self._version_status_check_running = True
        if self.current_mechanism == DNS_PROVIDER_ID:
            worker = VersionWorker(self.dns_manager, self.current_dns_provider, self)
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
        # Контент разной высоты — подстраиваем окно после пересчёта лейаута
        QTimer.singleShot(0, self._adjust_window_to_content)
        self.check_version_status()

    def _on_dns_provider_changed(self, provider: str):
        self.current_dns_provider = provider
        set_setting("dns_provider", provider)
        self.check_version_status()

    # ------------------------------------------------------------------
    # Обновления приложения
    # ------------------------------------------------------------------

    def check_for_updates(self):
        if self._check_updates_running:
            return
        self._check_updates_running = True
        # Видимый фидбек вместо «молчаливой» проверки
        self._processing_widget = self.show_processing("check_updates")

        worker = AppUpdateWorker(self)
        worker.signals.update_ready.connect(self.on_app_update_ready, Qt.ConnectionType.QueuedConnection)
        worker.signals.no_update.connect(self.on_app_up_to_date, Qt.ConnectionType.QueuedConnection)
        worker.signals.message.connect(self.on_app_update_message, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(str, str, str)
    def on_app_update_ready(self, local: str, remote: str, url: str):
        self._dismiss_processing()
        self.show_update_available(local, remote, url)
        self._check_updates_running = False

    @Slot(str, str)
    def on_app_up_to_date(self, local: str, remote: str):
        self._dismiss_processing()
        self.show_no_update(local, remote)
        self._check_updates_running = False

    @Slot(str, bool, bool)
    def on_app_update_message(self, msg: str, success: bool, word_wrap: bool):
        self._dismiss_processing()
        self.show_message(msg, success, word_wrap)
        self._check_updates_running = False

    # ------------------------------------------------------------------
    # Тема / язык
    # ------------------------------------------------------------------

    def _animate_transition(self, update_func: Callable):
        """Затемняет окно, применяет изменения и проявляет окно обратно."""
        if self.is_animating:
            return
        self.is_animating = True

        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def apply_changes():
            self.setUpdatesEnabled(False)
            update_func()
            self.setUpdatesEnabled(True)

            fade_in = QPropertyAnimation(self, b"windowOpacity", self)
            fade_in.setDuration(150)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.finished.connect(lambda: setattr(self, "is_animating", False))
            fade_in.start()

        fade_out.finished.connect(apply_changes)
        fade_out.start()

    def switch_theme(self):
        def update():
            self.dark_theme = not self.dark_theme
            set_setting("theme", "dark" if self.dark_theme else "light")
            self._apply_theme_styles()
            self._apply_texts()
        self._animate_transition(update)

    def switch_language(self):
        from app.gui.localization import get_supported_languages
        from app.gui.components.language_popup import LanguagePopup

        supported = get_supported_languages()
        popup = LanguagePopup(supported, self.language, self.dark_theme, self)
        popup.language_selected.connect(self.change_language_to)

        pos = self.language_button.mapToGlobal(self.language_button.rect().topLeft())
        pos.setX(pos.x() - 14)
        pos.setY(pos.y() - popup.height() + 6)
        popup.move(pos)
        popup.show()

    def change_language_to(self, new_lang: str):
        if new_lang == self.language or self.is_animating:
            return

        def update():
            self.language = set_current_language(new_lang)
            set_setting("language", new_lang)
            clear_stylesheet_cache()
            self._apply_theme_styles()
            self._apply_texts()
        self._animate_transition(update)

    def _apply_theme_styles(self):
        """Перетемизирует окно, главную страницу и все открытые страницы."""
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])

        self.title_bar.apply_theme(self.styles)
        for button, icon_name in self._footer_buttons:
            button.setStyleSheet(self.styles["footer_button"])
            button.setIcon(get_icon(icon_name, 20, dark_theme=self.dark_theme, force_dark=True))
        self.theme_button.setIcon(get_icon(
            "sun.svg" if self.dark_theme else "moon.svg",
            20, dark_theme=self.dark_theme, force_dark=True,
        ))

        self.home_page.styles = self.styles
        self.home_page.dark_theme = self.dark_theme
        self.home_page.apply_theme_styles()

        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w is self.home_wrapper:
                continue
            apply_theme = getattr(w, "apply_theme", None)
            if callable(apply_theme):
                apply_theme(self.styles, self.dark_theme)

    def _apply_texts(self):
        """Переводит заголовок, главную страницу и все открытые страницы."""
        self.setWindowTitle(WINDOW_TITLE)
        tooltip_theme = tr("theme_button").strip()
        tooltip_lang = tr("language_button").strip()
        self.theme_button.setToolTip(tooltip_theme)
        self.theme_button.setStatusTip(tooltip_theme)
        self.theme_button.setAccessibleName(tooltip_theme)
        self.language_button.setToolTip(tooltip_lang)
        self.language_button.setStatusTip(tooltip_lang)
        self.language_button.setAccessibleName(tooltip_lang)

        self.home_page.apply_texts()

        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w is self.home_wrapper:
                continue
            apply_texts = getattr(w, "apply_texts", None)
            if callable(apply_texts):
                apply_texts()

    def start_system_move(self) -> bool:
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemMove())
        except Exception:
            return False

    def closeEvent(self, event):
        # Даём фоновым воркерам (проверка статуса, установка, обновление)
        # корректно завершиться: защищает от обрыва записи hosts на середине
        # и от гонки «сигнал из удалённого объекта» при выходе.
        QThreadPool.globalInstance().waitForDone(5000)
        super().closeEvent(event)
