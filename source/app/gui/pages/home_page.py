from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox
)
from PySide6.QtCore import Qt, Signal, QSize
from app.core.hosts_manager import HostsManager, HostsStatusResult
from app.utils.helpers import open_target
from app.gui.localization import tr, localize_update_date
from app.gui.icons import get_icon


class HomePage(QWidget):
    """Main application home page with status, provider selection, and action buttons."""

    # Signals emitted to MainWindow for orchestration
    install_requested = Signal(str)       # action: "install" | "update" | "uninstall"
    donate_requested = Signal()
    about_requested = Signal()
    update_check_requested = Signal()
    provider_changed = Signal(str)        # provider id
    open_hosts_requested = Signal()       # open built-in hosts editor
    view_backups_requested = Signal()     # open built-in backup viewer

    def __init__(self, hosts_manager: HostsManager, styles: dict, dark_theme: bool, current_provider: str):
        super().__init__()
        self.hosts_manager = hosts_manager
        self.styles = styles
        self.dark_theme = dark_theme
        self.current_provider = current_provider

        # UI references
        self.app_title_label: Optional[QLabel] = None
        self.textinformer: Optional[QLabel] = None
        self.version_label: Optional[QLabel] = None
        self.update_date_label: Optional[QLabel] = None
        self.status_container: Optional[QWidget] = None
        self.install_button: Optional[QPushButton] = None
        self.uninstall_button: Optional[QPushButton] = None
        self.donate_button: Optional[QPushButton] = None
        self.about_button: Optional[QPushButton] = None
        self.update_button: Optional[QPushButton] = None
        self.open_hosts_button: Optional[QPushButton] = None
        self.backup_hosts_button: Optional[QPushButton] = None
        self.provider_combo: Optional[QComboBox] = None
        self.provider_repo_button: Optional[QPushButton] = None

        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addStretch()

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)
        layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.addLayout(layout)
        outer_layout.addStretch()

        # App title
        app_title_label = QLabel()
        app_title_label.setObjectName("main_title")
        app_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_title_label.setTextFormat(Qt.TextFormat.RichText)
        app_title_label.setText(self.styles["about_title_html"])
        app_title_label.setStyleSheet(self.styles["about_title_style"])
        layout.addWidget(app_title_label)
        self.app_title_label = app_title_label

        # Status labels
        textinformer = QLabel(tr("unlock_status", status=tr("version_checking"), color="#666666"))
        textinformer.setTextFormat(Qt.TextFormat.RichText)
        textinformer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        textinformer.setStyleSheet(self.styles["label"])
        self.textinformer = textinformer

        version_label = QLabel(tr("version_checking"))
        version_label.setTextFormat(Qt.TextFormat.RichText)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet(self.styles["label"])
        self.version_label = version_label

        update_date_label = QLabel(tr("update_date_checking"))
        update_date_label.setTextFormat(Qt.TextFormat.RichText)
        update_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_color = "#ffffff" if self.dark_theme else "#1a1a1a"
        update_date_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
        )
        self.update_date_label = update_date_label

        # Provider combo
        provider_combo = QComboBox()
        provider_combo.addItem(tr("provider_malw"), "dns.malw.link")
        provider_combo.addItem(tr("provider_geohide"), "geohide")
        provider_combo.setStyleSheet(self.styles["combo"])
        provider_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.provider_combo = provider_combo

        provider_repo_button = QPushButton()
        provider_repo_button.setIcon(get_icon("globe.svg", 18, dark_theme=self.dark_theme))
        provider_repo_button.setIconSize(QSize(18, 18))
        provider_repo_button.setProperty("icon_name", "globe.svg")
        provider_repo_button.setProperty("icon_force_dark", False)
        provider_repo_button.setProperty("style_role", "provider_repo")
        provider_repo_button.setFixedSize(32, 32)
        provider_repo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        provider_repo_button.setToolTip(tr("provider_repo_tooltip"))
        provider_repo_button.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 4px; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(128,128,128,0.15); }"
        )
        provider_repo_button.clicked.connect(self._open_provider_repo)
        self.provider_repo_button = provider_repo_button

        provider_hbox = QHBoxLayout()
        provider_hbox.setSpacing(6)
        provider_hbox.setContentsMargins(0, 0, 0, 0)
        provider_hbox.addWidget(provider_combo)
        provider_hbox.addWidget(provider_repo_button)

        # Status container
        status_container = QWidget()
        status_vbox = QVBoxLayout(status_container)
        status_vbox.setContentsMargins(16, 12, 16, 12)
        status_vbox.setSpacing(8)
        status_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_vbox.addLayout(provider_hbox)
        status_vbox.addWidget(textinformer)
        status_vbox.addWidget(version_label)
        status_vbox.addWidget(update_date_label)
        self.status_container = status_container
        self.refresh_status_container_style()
        layout.addWidget(status_container)

        initial_idx = 1 if self.current_provider == "geohide" else 0
        provider_combo.setCurrentIndex(initial_idx)
        provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        # Action buttons
        install_button = QPushButton(tr("install_button_install"))
        install_button.setIcon(get_icon("settings.svg", 18, dark_theme=self.dark_theme, force_white=True))
        install_button.setIconSize(QSize(18, 18))
        install_button.setProperty("icon_name", "settings.svg")
        install_button.setProperty("icon_force_white", True)
        install_button.setProperty("style_role", "button1")
        install_button.setProperty("install_mode", "install")
        install_button.setStyleSheet(self.styles["button1"])
        self.install_button = install_button

        uninstall_button = QPushButton(tr("uninstall_button"))
        uninstall_button.setIcon(get_icon("trash.svg", 18, dark_theme=self.dark_theme, force_white=True))
        uninstall_button.setIconSize(QSize(18, 18))
        uninstall_button.setProperty("icon_name", "trash.svg")
        uninstall_button.setProperty("icon_force_white", True)
        uninstall_button.setProperty("style_role", "button2")
        uninstall_button.setStyleSheet(self.styles["button2"])
        self.uninstall_button = uninstall_button

        donate_button = QPushButton(tr("donate_button"))
        donate_button.setIcon(get_icon("heart.svg", 18, dark_theme=self.dark_theme, force_dark=True))
        donate_button.setIconSize(QSize(18, 18))
        donate_button.setProperty("icon_name", "heart.svg")
        donate_button.setProperty("icon_force_dark", True)
        donate_button.setProperty("style_role", "theme")
        donate_button.setStyleSheet(self.styles["theme"])
        self.donate_button = donate_button

        about_button = QPushButton(tr("about_button"))
        about_button.setIcon(get_icon("info.svg", 18, dark_theme=self.dark_theme, force_dark=True))
        about_button.setIconSize(QSize(18, 18))
        about_button.setProperty("icon_name", "info.svg")
        about_button.setProperty("icon_force_dark", True)
        about_button.setProperty("style_role", "theme")
        about_button.setStyleSheet(self.styles["theme"])
        self.about_button = about_button

        update_button = QPushButton(tr("update_button"))
        update_button.setIcon(get_icon("refresh.svg", 18, dark_theme=self.dark_theme, force_dark=True))
        update_button.setIconSize(QSize(18, 18))
        update_button.setProperty("icon_name", "refresh.svg")
        update_button.setProperty("icon_force_dark", True)
        update_button.setProperty("style_role", "theme")
        update_button.setStyleSheet(self.styles["theme"])
        self.update_button = update_button

        open_hosts_button = QPushButton(tr("open_hosts_button"))
        open_hosts_button.setIcon(get_icon("book-open.svg", 18, dark_theme=self.dark_theme, force_dark=True))
        open_hosts_button.setIconSize(QSize(18, 18))
        open_hosts_button.setProperty("icon_name", "book-open.svg")
        open_hosts_button.setProperty("icon_force_dark", True)
        open_hosts_button.setProperty("style_role", "theme")
        open_hosts_button.setStyleSheet(self.styles["theme"])
        self.open_hosts_button = open_hosts_button

        backup_hosts_button = QPushButton(tr("backup_hosts_button"))
        backup_hosts_button.setIcon(get_icon("clock.svg", 18, dark_theme=self.dark_theme, force_dark=True))
        backup_hosts_button.setIconSize(QSize(18, 18))
        backup_hosts_button.setProperty("icon_name", "clock.svg")
        backup_hosts_button.setProperty("icon_force_dark", True)
        backup_hosts_button.setProperty("style_role", "theme")
        backup_hosts_button.setStyleSheet(self.styles["theme"])
        self.backup_hosts_button = backup_hosts_button

        # Connect signals
        install_button.clicked.connect(lambda: self.install_requested.emit(install_button.property("install_mode") or "install"))
        uninstall_button.clicked.connect(lambda: self.install_requested.emit("uninstall"))
        donate_button.clicked.connect(self.donate_requested.emit)
        about_button.clicked.connect(self.about_requested.emit)
        update_button.clicked.connect(self.update_check_requested.emit)
        open_hosts_button.clicked.connect(self.open_hosts_requested.emit)
        backup_hosts_button.clicked.connect(self.view_backups_requested.emit)

        # Layout
        layout.addWidget(install_button)
        layout.addWidget(uninstall_button)
        layout.addWidget(open_hosts_button)
        layout.addWidget(backup_hosts_button)

        controls_hbox = QHBoxLayout()
        controls_hbox.setSpacing(12)
        controls_hbox.addWidget(donate_button)
        layout.addLayout(controls_hbox)
        layout.addStretch()
        layout.addWidget(update_button)
        layout.addWidget(about_button)

    # --- Public API ---

    def update_status_label(self):
        installed = self.hosts_manager.is_installed(self.current_provider)
        color = "#43b581" if installed else "#e06c75"
        key = "status_installed" if installed else "status_not_installed"
        self.textinformer.setText(tr("unlock_status", status=tr(key), color=color))

    def apply_hosts_version_status(self, status: HostsStatusResult):
        self.version_label.setProperty("status_key", status.key)
        self.version_label.setProperty("status_color", status.color)
        self.version_label.setProperty("update_date_value", status.date)

        self.version_label.setText(
            tr("hosts_version_status", color=status.color, status=tr(f"hosts_status_{status.key}"))
        )
        if status.date:
            self.update_date_label.setText(tr("hosts_update_date", date=localize_update_date(status.date)))
        else:
            self.update_date_label.setText(tr("hosts_update_date_unknown"))

        mode = "update" if status.key == "outdated" else "install"
        self.install_button.setProperty("install_mode", mode)
        self.install_button.setText(tr("install_button_update" if mode == "update" else "install_button_install"))

    def apply_texts(self):
        self.app_title_label.setText(self.styles["about_title_html"])
        self.update_status_label()

        if self.provider_combo:
            self.provider_combo.blockSignals(True)
            self.provider_combo.setItemText(0, tr("provider_malw"))
            self.provider_combo.setItemText(1, tr("provider_geohide"))
            self.provider_combo.blockSignals(False)
        if self.provider_repo_button:
            self.provider_repo_button.setToolTip(tr("provider_repo_tooltip"))

        stored_key = self.version_label.property("status_key")
        if stored_key:
            status = HostsStatusResult(
                stored_key,
                self.version_label.property("status_color") or "#e06c75",
                self.version_label.property("update_date_value") or ""
            )
            self.apply_hosts_version_status(status)
        else:
            self.version_label.setText(tr("version_checking"))
            self.update_date_label.setText(tr("update_date_checking"))
            self.install_button.setProperty("install_mode", self.install_button.property("install_mode") or "install")

        self.uninstall_button.setText(tr("uninstall_button"))
        self.donate_button.setText(tr("donate_button"))
        self.about_button.setText(tr("about_button"))
        self.update_button.setText(tr("update_button"))
        self.open_hosts_button.setText(tr("open_hosts_button"))
        self.backup_hosts_button.setText(tr("backup_hosts_button"))

    def apply_theme_styles(self):
        self.app_title_label.setStyleSheet(self.styles["about_title_style"])
        self.textinformer.setStyleSheet(self.styles["label"])
        self.version_label.setStyleSheet(self.styles["label"])
        text_color = "#ffffff" if self.dark_theme else "#1a1a1a"
        self.update_date_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
        )
        self.install_button.setStyleSheet(self.styles["button1"])
        self.uninstall_button.setStyleSheet(self.styles["button2"])
        if self.provider_combo:
            self.provider_combo.setStyleSheet(self.styles["combo"])
        self.donate_button.setStyleSheet(self.styles["theme"])
        self.open_hosts_button.setStyleSheet(self.styles["theme"])
        self.backup_hosts_button.setStyleSheet(self.styles["theme"])
        self.update_button.setStyleSheet(self.styles["theme"])
        self.about_button.setStyleSheet(self.styles["theme"])
        self.refresh_status_container_style()

    def refresh_status_container_style(self):
        light = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
        dark = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
        self.status_container.setStyleSheet(dark if self.dark_theme else light)

    # --- Private ---

    def _on_provider_changed(self):
        selected_provider = self.provider_combo.currentData()
        if selected_provider:
            self.current_provider = selected_provider
            self.update_status_label()
            self.provider_changed.emit(selected_provider)

    def _open_provider_repo(self):
        urls = {
            "dns.malw.link": "https://github.com/ImMALWARE/dns.malw.link",
            "geohide": "https://github.com/Internet-Helper/GeoHideDNS",
        }
        url = urls.get(self.current_provider)
        if url:
            open_target(url)
