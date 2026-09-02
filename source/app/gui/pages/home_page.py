from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox
)
from PySide6.QtCore import Qt, Signal, QSize

from app.core.constants import COLOR_ERROR, COLOR_SUCCESS
from app.core.hosts_manager import HostsManager, HostsStatusResult
from app.core.dns_manager import (
    DNS_PROVIDER_ID,
    DnsManager,
    get_dns_provider_site_url,
    get_dns_providers,
)
from app.utils.helpers import open_target
from app.gui.localization import localize_update_date, tr
from app.gui.icons import get_icon
from app.gui.scaling import ui_scaled

# Ширина колонки контента главной страницы (карточка статуса + кнопки)
COLUMN_MAX_WIDTH = 420


class HomePage(QWidget):
    """Главная страница: статус обхода, выбор механизма/провайдера и действия."""

    # Сигналы для MainWindow (оркестрация)
    install_requested = Signal(str)       # action: "install" | "update" | "uninstall"
    donate_requested = Signal()
    about_requested = Signal()
    update_check_requested = Signal()
    provider_changed = Signal(str)        # id hosts-провайдера
    mechanism_changed = Signal(str)       # "hosts" | "xbox-dns"
    dns_provider_changed = Signal(str)    # id DNS-провайдера
    open_hosts_requested = Signal()       # открыть редактор hosts
    view_backups_requested = Signal()     # открыть просмотрщик бэкапов
    # Клик по бейджу «доступна новая версия»
    update_badge_clicked = Signal()
    # Текст статуса изменился — высоте окна может потребоваться пересчёт
    home_content_changed = Signal()

    def __init__(self, hosts_manager: HostsManager, dns_manager: DnsManager,
                 styles: dict, dark_theme: bool, current_provider: str,
                 current_mechanism: str = "hosts",
                 current_dns_provider: str = DNS_PROVIDER_ID):
        super().__init__()
        self.hosts_manager = hosts_manager
        self.dns_manager = dns_manager
        self.styles = styles
        self.dark_theme = dark_theme
        self.current_provider = current_provider
        self.current_mechanism = current_mechanism
        self.current_dns_provider = current_dns_provider

        # Последний полученный асинхронно статус (вместо свойств на QLabel)
        self._status: Optional[HostsStatusResult] = None
        # Версия доступного обновления (бейдж на главной), None — обновление не найдено
        self._update_badge_version: Optional[str] = None
        # (кнопка, имя_иконки, force_white, force_dark) для перетемизации иконок
        self._icon_buttons: list[tuple[QPushButton, str, bool, bool]] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(ui_scaled(24))
        layout.setContentsMargins(*(ui_scaled(20),) * 4)

        # Колонка контента ограничена по ширине: rich-text QLabel'ы дают
        # завышенный sizeHint, из-за чего без ограничения колонка
        # растягивается на всю ширину окна
        column = QWidget()
        column.setMaximumWidth(ui_scaled(COLUMN_MAX_WIDTH))
        column.setLayout(layout)

        # Заголовок приложения
        self.app_title_label = QLabel()
        self.app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app_title_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.app_title_label)

        # Статусная карточка: механизм + провайдеры + статусы
        self.mechanism_combo = QComboBox()
        self.mechanism_combo.addItem(tr("mechanism_hosts"), "hosts")
        self.mechanism_combo.addItem(tr("mechanism_dns"), DNS_PROVIDER_ID)
        self.mechanism_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mechanism_combo.currentIndexChanged.connect(self._on_mechanism_changed)

        self.provider_combo, self.provider_repo_button = self._make_provider_row(
            [(tr("provider_malw"), "dns.malw.link"), (tr("provider_geohide"), "geohide")],
            self._open_provider_repo,
        )
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        self.dns_provider_combo, self.dns_site_button = self._make_provider_row(
            get_dns_providers(), self._open_dns_provider_site,
        )
        self.dns_provider_combo.currentIndexChanged.connect(self._on_dns_provider_changed)

        self.textinformer = QLabel()
        self.textinformer.setTextFormat(Qt.TextFormat.RichText)
        self.textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.version_label = QLabel(tr("version_checking"))
        self.version_label.setTextFormat(Qt.TextFormat.RichText)
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setWordWrap(True)

        self.update_date_label = QLabel(tr("update_date_checking"))
        self.update_date_label.setTextFormat(Qt.TextFormat.RichText)
        self.update_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Длинные строки (например, список DNS-серверов) переносятся,
        # а не обрезаются границей карточки
        self.update_date_label.setWordWrap(True)

        self.status_container = QWidget()
        status_vbox = QVBoxLayout(self.status_container)
        status_vbox.setContentsMargins(
            ui_scaled(16), ui_scaled(12), ui_scaled(16), ui_scaled(12)
        )
        status_vbox.setSpacing(ui_scaled(8))
        status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_vbox.addWidget(self.mechanism_combo)
        # Кнопка открытия сайта/репозитория — справа от комбобокса провайдера
        status_vbox.addLayout(self._row_with_button(self.provider_combo, self.provider_repo_button))
        status_vbox.addLayout(self._row_with_button(self.dns_provider_combo, self.dns_site_button))
        status_vbox.addWidget(self.textinformer)
        status_vbox.addWidget(self.version_label)
        status_vbox.addWidget(self.update_date_label)

        layout.addWidget(self.status_container)

        # Действия
        self.install_button = self._make_action_button(
            "settings.svg", force_white=True,
            clicked=lambda: self.install_requested.emit(
                self.install_button.property("install_mode") or "install"
            ),
        )
        self.install_button.setProperty("install_mode", "install")
        self.install_button.setText(tr("install_button_install"))
        self.uninstall_button = self._make_action_button(
            "trash.svg", force_white=True,
            clicked=lambda: self.install_requested.emit("uninstall"),
        )
        self.uninstall_button.setText(tr("uninstall_button"))
        self.open_hosts_button = self._make_tool_button(
            "book-open.svg", tr("open_hosts_button"), self.open_hosts_requested.emit
        )
        self.backup_hosts_button = self._make_tool_button(
            "clock.svg", tr("backup_hosts_button"), self.view_backups_requested.emit
        )

        layout.addWidget(self.install_button)
        layout.addWidget(self.uninstall_button)
        layout.addWidget(self.open_hosts_button)
        layout.addWidget(self.backup_hosts_button)
        layout.addStretch()

        self.donate_button = self._make_tool_button(
            "heart.svg", tr("donate_button"), self.donate_requested.emit
        )
        layout.addWidget(self.donate_button)
        layout.addStretch()

        self.update_button = self._make_tool_button(
            "refresh.svg", tr("update_button"), self.update_check_requested.emit
        )
        self.about_button = self._make_tool_button(
            "info.svg", tr("about_button"), self.about_requested.emit
        )
        # Компактный бейдж «доступна новая версия». Не добавляется в layout:
        # MainWindow переносит его в контейнер окна и позиционирует
        # наложением по центру внизу, чтобы он не влиял на размеры окна
        self.update_badge = QPushButton(self)
        badge_px = ui_scaled(14)
        self.update_badge.setIconSize(QSize(badge_px, badge_px))
        self.update_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_badge.clicked.connect(self.update_badge_clicked.emit)
        self.update_badge.setVisible(False)
        self._icon_buttons.append((self.update_badge, "alert.svg", False, True))

        layout.addWidget(self.update_button)
        layout.addWidget(self.about_button)

        outer_layout.addStretch()
        outer_layout.addWidget(column, 0, Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch()

        # Начальные значения без эмита сигналов
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(1 if self.current_provider == "geohide" else 0)
        self.provider_combo.blockSignals(False)

        self.mechanism_combo.blockSignals(True)
        idx = self.mechanism_combo.findData(self.current_mechanism)
        self.mechanism_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.mechanism_combo.blockSignals(False)

        self.dns_provider_combo.blockSignals(True)
        idx = self.dns_provider_combo.findData(self.current_dns_provider)
        self.dns_provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.dns_provider_combo.blockSignals(False)

        self._update_mechanism_controls_visibility()

        # Применяем стили и тексты после сборки всех виджетов
        self.apply_theme_styles()
        self.apply_texts()

    @staticmethod
    def _row_with_button(combo: QComboBox, button: QPushButton) -> QHBoxLayout:
        """Строка «комбобокс провайдера + кнопка открытия сайта справа».

        Без stretch-фактора у комбобокса: stretch делает строку expanding,
        и тогда растягивается вся колонка главной страницы.
        """
        row = QHBoxLayout()
        row.setSpacing(ui_scaled(6))
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(combo)
        row.addWidget(button)
        return row

    def _make_provider_row(self, items: list, open_callback: Callable) -> tuple[QComboBox, QPushButton]:
        """Комбобокс выбора провайдера + кнопка открытия сайта/репозитория."""
        combo = QComboBox()
        for name, data in items:
            combo.addItem(name, data)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)

        site_button = QPushButton()
        site_button.setIcon(get_icon("globe.svg", 18, dark_theme=self.dark_theme))
        site_button.setIconSize(QSize(ui_scaled(18), ui_scaled(18)))
        site_button.setFixedSize(ui_scaled(32), ui_scaled(32))
        site_button.setCursor(Qt.CursorShape.PointingHandCursor)
        site_button.setToolTip(tr("provider_repo_tooltip"))
        site_button.clicked.connect(open_callback)
        self._icon_buttons.append((site_button, "globe.svg", False, False))
        return combo, site_button

    def _make_action_button(self, icon_name: str, *, force_white: bool,
                            clicked: Callable) -> QPushButton:
        button = QPushButton()
        icon_px = ui_scaled(18)
        button.setIconSize(QSize(icon_px, icon_px))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(clicked)
        self._icon_buttons.append((button, icon_name, force_white, False))
        return button

    def _make_tool_button(self, icon_name: str, text: str, slot: Callable) -> QPushButton:
        button = QPushButton(text)
        icon_px = ui_scaled(18)
        button.setIconSize(QSize(icon_px, icon_px))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        self._icon_buttons.append((button, icon_name, False, True))
        return button

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def sync_status_label_heights(self):
        """Фиксирует минимальную высоту статусных меток под реальный перенос.

        sizeHint у QLabel с wordWrap завышен, а minimumSizeHint занижен:
        при нехватке высоты лейаут сжимает метки ниже размера текста и
        глифы обрезаются. Явный минимум = heightForWidth() делает такое
        сжатие невозможным.

        Ширина для замера берётся детерминированная (колонка минус поля
        страницы и карточки), а не фактическая lbl.width(): при раннем
        замере (showEvent на Wayland/X11) ширины ещё не устоялись, и
        heightForWidth по «широкой» метке считает на строку меньше — окно
        открывается заниженным и растягивается позже, когда приходит
        асинхронный статус. Итоговая ширина метки всегда одна и та же:
        ширина окна фиксирована, колонка ограничена COLUMN_MAX_WIDTH.

        Вызывается при смене текста статусов и из MainWindow
        перед замером высоты окна (метрики шрифтов актуальны только
        после полировки стилей при показе).
        """
        for lbl in (self.textinformer, self.version_label, self.update_date_label):
            lbl.setMinimumHeight(0)
            if not lbl.isVisibleTo(self):
                continue
            width = ui_scaled(COLUMN_MAX_WIDTH) - ui_scaled(72)
            need = lbl.heightForWidth(width) if lbl.wordWrap() else lbl.sizeHint().height()
            lbl.setMinimumHeight(need)

    def update_status_label(self):
        if self.current_mechanism == DNS_PROVIDER_ID:
            # Неблокирующий вариант: только кэш, без запуска PowerShell.
            # Свежая проверка выполняется асинхронно через VersionWorker.
            installed = self.dns_manager.get_cached_install_state(self.current_dns_provider)
        else:
            installed = self.hosts_manager.is_installed(self.current_provider)
        color = COLOR_SUCCESS if installed else COLOR_ERROR
        key = "status_installed" if installed else "status_not_installed"
        self.textinformer.setText(tr("unlock_status", status=tr(key), color=color))
        self.sync_status_label_heights()
        self.home_content_changed.emit()

    def set_update_badge(self, version: str):
        """Заполняет бейдж «доступна новая версия».

        Видимость и fade-анимация — ответственность MainWindow
        (бейдж виден только на главной странице).
        """
        self._update_badge_version = version
        self.update_badge.setText(tr("update_badge_text", version=version))
        self.update_badge.setToolTip(tr("update_badge_tooltip"))

    def clear_update_badge(self):
        self._update_badge_version = None

    def apply_hosts_version_status(self, status: HostsStatusResult):
        self._status = status

        if self.current_mechanism == DNS_PROVIDER_ID:
            # Для DNS-механизма строка версии hosts не нужна
            self.version_label.hide()
            self.update_date_label.setText(tr(
                "dns_servers_status_label",
                servers=status.date, color=COLOR_SUCCESS if status.key == "installed" else COLOR_ERROR,
                status=tr("status_installed" if status.key == "installed" else "status_not_installed"),
            ))
            mode = "install"
        else:
            self.version_label.show()
            self.version_label.setText(
                tr("hosts_version_status", color=status.color, status=tr(f"hosts_status_{status.key}"))
            )
            if status.date:
                self.update_date_label.setText(
                    tr("hosts_update_date", date=localize_update_date(status.date))
                )
            else:
                self.update_date_label.setText(tr("hosts_update_date_unknown"))
            mode = "update" if status.key == "outdated" else "install"

        self.install_button.setProperty("install_mode", mode)
        self.install_button.setText(
            tr("install_button_update" if mode == "update" else "install_button_install")
        )
        # Статус пришёл асинхронно — обновляем общий статус свежим значением
        self.update_status_label()

    def apply_texts(self):
        self.app_title_label.setText(self.styles["about_title_html"])
        self.update_status_label()

        self._set_combo_items(self.provider_combo, [
            (tr("provider_malw"), "dns.malw.link"),
            (tr("provider_geohide"), "geohide"),
        ])
        self._set_combo_items(self.mechanism_combo, [
            (tr("mechanism_hosts"), "hosts"),
            (tr("mechanism_dns"), DNS_PROVIDER_ID),
        ])

        current_dns = self.dns_provider_combo.currentData()
        self.provider_combo.blockSignals(True)
        self.mechanism_combo.blockSignals(True)
        self.dns_provider_combo.blockSignals(True)
        while self.dns_provider_combo.count():
            self.dns_provider_combo.removeItem(0)
        for name, pid in get_dns_providers():
            self.dns_provider_combo.addItem(name, pid)
        idx = self.dns_provider_combo.findData(current_dns)
        self.dns_provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.dns_provider_combo.blockSignals(False)
        self.mechanism_combo.blockSignals(False)
        self.provider_combo.blockSignals(False)

        self.provider_repo_button.setToolTip(tr("provider_repo_tooltip"))
        self.dns_site_button.setToolTip(tr("provider_repo_tooltip"))

        if self._status is not None:
            self.apply_hosts_version_status(self._status)
        elif self.current_mechanism == DNS_PROVIDER_ID:
            self.version_label.hide()
            self._show_instant_dns_status()
        else:
            self.version_label.show()
            self.version_label.setText(tr("version_checking"))
            self.update_date_label.setText(tr("update_date_checking"))

        self.uninstall_button.setText(tr("uninstall_button"))
        self.donate_button.setText(tr("donate_button"))
        self.about_button.setText(tr("about_button"))
        self.update_button.setText(tr("update_button"))
        if self._update_badge_version is not None:
            self.update_badge.setText(
                tr("update_badge_text", version=self._update_badge_version)
            )
            self.update_badge.setToolTip(tr("update_badge_tooltip"))
        self.open_hosts_button.setText(tr("open_hosts_button"))
        self.backup_hosts_button.setText(tr("backup_hosts_button"))

    def apply_theme_styles(self):
        self.app_title_label.setStyleSheet(self.styles["about_title_style"])
        self.app_title_label.setText(self.styles["about_title_html"])
        self.textinformer.setStyleSheet(self.styles["label"])
        self.version_label.setStyleSheet(self.styles["label"])
        self.update_date_label.setStyleSheet(self.styles["update_date_label"])
        self.status_container.setStyleSheet(self.styles["status_card"])

        for combo in (self.mechanism_combo, self.provider_combo, self.dns_provider_combo):
            combo.setStyleSheet(self.styles["combo"])

        for button, icon_name, force_white, force_dark in self._icon_buttons:
            if button is self.provider_repo_button or button is self.dns_site_button:
                button.setStyleSheet(self.styles["icon_button"])
            elif button is self.install_button:
                button.setStyleSheet(self.styles["button1"])
            elif button is self.uninstall_button:
                button.setStyleSheet(self.styles["button2"])
            elif button is self.update_badge:
                button.setStyleSheet(self.styles["update_badge"])
            else:
                button.setStyleSheet(self.styles["theme"])
            button.setIcon(get_icon(
                icon_name, 18,
                dark_theme=self.dark_theme,
                force_white=force_white,
                force_dark=force_dark,
            ))

    @staticmethod
    def _set_combo_items(combo: QComboBox, items: list):
        """Обновляет подписи элементов, сохраняя выбранные данные."""
        current = combo.currentData()
        combo.blockSignals(True)
        for i, (name, data) in enumerate(items):
            if i < combo.count():
                combo.setItemText(i, name)
                combo.setItemData(i, data)
            else:
                combo.addItem(name, data)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Обработчики
    # ------------------------------------------------------------------

    def _on_provider_changed(self):
        selected = self.provider_combo.currentData()
        if selected:
            self.current_provider = selected
            self.update_status_label()
            self.provider_changed.emit(selected)

    def _on_mechanism_changed(self):
        selected = self.mechanism_combo.currentData()
        if selected:
            self.current_mechanism = selected
            self._update_mechanism_controls_visibility()
            self.update_status_label()
            self.mechanism_changed.emit(selected)

    def _on_dns_provider_changed(self):
        selected = self.dns_provider_combo.currentData()
        if selected:
            self.current_dns_provider = selected
            self._show_instant_dns_status()
            self.update_status_label()
            self.dns_provider_changed.emit(selected)

    def _update_mechanism_controls_visibility(self):
        """Показывает контролы, соответствующие текущему механизму.

        Обычный setVisible достаточен: у страницы корректные size policy,
        и лейаут сам пересчитывается без ручных хаков с высотой.
        """
        is_dns = self.current_mechanism == DNS_PROVIDER_ID
        self.provider_combo.setVisible(not is_dns)
        self.provider_repo_button.setVisible(not is_dns)
        self.dns_provider_combo.setVisible(is_dns)
        self.dns_site_button.setVisible(is_dns)
        self.open_hosts_button.setVisible(not is_dns)
        self.backup_hosts_button.setVisible(not is_dns)
        # Строка «Версия hosts» имеет смысл только для hosts-механизма
        self.version_label.setVisible(not is_dns)
        if is_dns:
            self._show_instant_dns_status()
        else:
            self.sync_status_label_heights()

    def _show_instant_dns_status(self):
        """Мгновенно показывает статус DNS-серверов из кэша (без PowerShell)."""
        from app.core.dns_manager import get_dns_provider_servers

        ipv4_servers, _ = get_dns_provider_servers(self.current_dns_provider)
        installed = self.dns_manager.get_cached_install_state(self.current_dns_provider)
        color = COLOR_SUCCESS if installed else COLOR_ERROR
        key = "status_installed" if installed else "status_not_installed"
        self.update_date_label.setText(tr(
            "dns_servers_status_label",
            servers=", ".join(ipv4_servers), color=color, status=tr(key),
        ))
        self.sync_status_label_heights()
        self.home_content_changed.emit()

    def _open_provider_repo(self):
        urls = {
            "dns.malw.link": "https://github.com/ImMALWARE/dns.malw.link",
            "geohide": "https://github.com/Internet-Helper/GeoHideDNS",
        }
        url = urls.get(self.current_provider)
        if url:
            open_target(url)

    def _open_dns_provider_site(self):
        url = get_dns_provider_site_url(self.current_dns_provider)
        if url:
            open_target(url)
