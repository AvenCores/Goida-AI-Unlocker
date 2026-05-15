from typing import Optional, Callable
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QStackedWidget,
    QSizePolicy, QPushButton, QToolButton, QGridLayout, QApplication,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QSize, Slot, QThreadPool
from PySide6.QtGui import QClipboard

from app.core.logger import logger
from app.core.hosts_manager import HostsManager, HostsStatusResult
from app.utils.helpers import open_target
from app.gui.localization import tr, set_current_language, localize_update_date, clean_message_line
from app.gui.styles import get_stylesheet, get_about_toolbutton_style, clear_stylesheet_cache
from app.gui.icons import get_icon, create_icon_label, refresh_icons
from app.gui.workers import HostsWorker, VersionWorker, AppUpdateWorker

class DraggableTitleBar(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self._main_window = main_window
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._main_window.start_system_move():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._main_window.move(self._main_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_animating = False
        self.stacked_widget: Optional[QStackedWidget] = None
        self._current_animation: Optional[QPropertyAnimation] = None
        self.dark_theme = False
        self.styles: dict[str, str] = {}
        self.title_bar: Optional[QWidget] = None
        from app.gui.localization import CURRENT_LANGUAGE
        self.language = CURRENT_LANGUAGE
        self.hosts_manager = HostsManager()
        self._check_updates_running = False
        self.home_page: Optional[QWidget] = None
        self.resource_path: Callable[[str], str] = lambda x: x
        self._processing_widget: Optional[QWidget] = None

    def start_system_move(self) -> bool:
        handle = self.windowHandle()
        if handle is None:
            return False
        try:
            return bool(handle.startSystemMove())
        except Exception:
            return False

    def fix_widget_size(self, w: QWidget):
        h = self.height() - (self.title_bar.height() if self.title_bar else 32)
        w.setMinimumSize(self.width(), h)
        w.setMaximumSize(self.width(), h)

    def _clear_effects(self):
        if not self.stacked_widget:
            return
        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w and w.graphicsEffect():
                w.setGraphicsEffect(None)

    def animate_switch(self, new_widget: QWidget, on_finish=None):
        if not self.stacked_widget:
            return
        current = self.stacked_widget.currentWidget()
        if not current or current == new_widget:
            self.stacked_widget.setCurrentWidget(new_widget)
            if on_finish:
                on_finish()
            return
        
        self.fix_widget_size(new_widget)
        
        if self._current_animation is not None:
            self._current_animation.stop()
            self._current_animation = None
        self._clear_effects()
        
        if current.graphicsEffect():
            current.setGraphicsEffect(None)
        
        effect_out = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect_out)
        fade_out = QPropertyAnimation(effect_out, b"opacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def do_switch():
            if self.stacked_widget is None:
                return
            self.stacked_widget.setCurrentWidget(new_widget)
            if current and current.graphicsEffect():
                current.setGraphicsEffect(None)
            
            if new_widget.graphicsEffect():
                new_widget.setGraphicsEffect(None)
                
            effect_in = QGraphicsOpacityEffect(new_widget)
            new_widget.setGraphicsEffect(effect_in)
            fade_in = QPropertyAnimation(effect_in, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)

            def cleanup():
                new_widget.setGraphicsEffect(None)
                self._current_animation = None
                if on_finish:
                    on_finish()

            fade_in.finished.connect(cleanup)
            self._current_animation = fade_in
            fade_in.start()

        fade_out.finished.connect(do_switch)
        self._current_animation = fade_out
        fade_out.start()

    def remove_widget(self, widget: QWidget):
        if self.stacked_widget:
            self.stacked_widget.removeWidget(widget)
        widget.deleteLater()

    def return_to_main(self, widget: QWidget):
        def cleanup():
            self.remove_widget(widget)
        self.animate_switch(self.home_page, on_finish=cleanup)

    def _add_and_switch(self, widget: QWidget):
        if self.stacked_widget:
            self.stacked_widget.addWidget(widget)
        self.update_subwindow_styles()
        self.animate_switch(widget)

    def _build_card(self, icon_name: str, max_width: int = 420) -> tuple[QWidget, QVBoxLayout, QWidget]:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        self.fix_widget_size(widget)

        card = QWidget()
        card.setObjectName("msg_card")
        card.setMinimumWidth(240)
        card.setMaximumWidth(max_width)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card.setStyleSheet(self.styles["message_card"])

        emoji = create_icon_label(icon_name, size=48, dark_theme=self.dark_theme)
        card_layout.addWidget(emoji)

        vbox.addWidget(card)
        return widget, card_layout, card

    def show_message(self, msg: str, success: bool = True, word_wrap: bool = False):
        widget, card_layout, card = self._build_card("check-circle.svg" if success else "x-circle.svg")

        if word_wrap:
            for raw_line in msg.split("\n"):
                line = clean_message_line(raw_line)
                if not line:
                    continue
                lbl = QLabel(line)
                lbl.setObjectName("message_block_label")
                lbl.setTextFormat(Qt.TextFormat.PlainText)
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                card_layout.addWidget(lbl)
        else:
            for raw_line in msg.split("\n"):
                line = clean_message_line(raw_line)
                if not line.strip():
                    continue
                lbl = QLabel(line)
                lbl.setObjectName("message_label")
                lbl.setTextFormat(Qt.TextFormat.PlainText)
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                card_layout.addWidget(lbl)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def show_processing(self, action: str) -> QWidget:
        if action == "install":
            msg = tr("processing_install")
        elif action == "update":
            msg = tr("processing_update")
        else:
            msg = tr("processing_uninstall")

        widget, card_layout, card = self._build_card("clock.svg")
        for raw_line in msg.split("\n"):
            line = clean_message_line(raw_line)
            if not line:
                continue
            lbl = QLabel(line)
            lbl.setObjectName("message_label")
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(lbl)

        self._add_and_switch(widget)
        return widget

    def show_update_available(self, local_ver: str, latest_ver: str, dl_url: str):
        widget, card_layout, card = self._build_card("alert.svg", max_width=600)

        for text in (
            tr("installed_version", version=local_ver),
            tr("latest_version", version=latest_ver),
            tr("new_version_available")
        ):
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        dl_btn = QPushButton(tr("download"))
        dl_btn.setProperty("style_role", "button1")
        card_layout.addWidget(dl_btn)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        dl_btn.clicked.connect(lambda: open_target(dl_url))
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def show_no_update(self, local_ver: str, latest_ver: str):
        widget, card_layout, card = self._build_card("check-circle.svg", max_width=600)

        for text in (
            tr("installed_version", version=local_ver),
            tr("latest_version_padded", version=latest_ver),
            tr("latest_version_installed")
        ):
            lbl = QLabel(text)
            if "version" in text:
                lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        ok_btn = QPushButton(tr("ok"))
        ok_btn.setProperty("style_role", "button1")
        card_layout.addWidget(ok_btn)

        self._add_and_switch(widget)
        ok_btn.clicked.connect(lambda: self.return_to_main(widget))

    def update_subwindow_styles(self):
        if not self.stacked_widget:
            return
        for i in range(self.stacked_widget.count()):
            w = self.stacked_widget.widget(i)
            if w is self.home_page:
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
            if w is not self.home_page:
                refresh_icons(w, self.dark_theme)

    @Slot(str, bool, str)
    def on_hosts_finished(self, action: str, ok: bool, error: str):
        if ok:
            if action == "install":
                msg = tr("install_success")
            elif action == "update":
                msg = tr("update_success")
            else:
                msg = tr("uninstall_success")
            self.show_message(msg, success=True, word_wrap=True)
        else:
            import sys
            hint = tr("admin_hint_windows") if sys.platform == "win32" else tr("admin_hint_unix")
            if action == "install":
                msg = tr("install_error", hint=hint)
            elif action == "update":
                msg = tr("update_error", hint=hint)
            else:
                msg = tr("uninstall_error", hint=hint)
            self.show_message(msg, success=False, word_wrap=True)

        if self._processing_widget is not None:
            proc = self._processing_widget
            self._processing_widget = None
            QTimer.singleShot(400, lambda: self.remove_widget(proc))
        
        self.update_installation_status_label()
        self.check_version_status()

    def start_installation(self, action: str):
        self._processing_widget = self.show_processing(action)
        worker = HostsWorker(action, self.hosts_manager)
        worker.signals.finished.connect(self.on_hosts_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def update_installation_status_label(self):
        installed = self.hosts_manager.is_installed()
        color = "#43b581" if installed else "#e06c75"
        key = "status_installed" if installed else "status_not_installed"
        self.textinformer.setText(tr("unlock_status", status=tr(key), color=color))

    @Slot(object)
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

    def check_version_status(self):
        worker = VersionWorker(self.hosts_manager)
        worker.signals.status_ready.connect(self.apply_hosts_version_status, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def switch_theme(self):
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
                    self.dark_theme = not self.dark_theme
                    self.styles = get_stylesheet(self.dark_theme, self.language)
                    self.setStyleSheet(self.styles["main"])
                    self.apply_main_texts()
                    self.apply_theme_styles()
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

    def switch_language(self):
        next_lang = "en" if self.language == "ru" else "ru"
        self.language = set_current_language(next_lang)
        clear_stylesheet_cache()
        self.apply_theme_styles()
        self.apply_main_texts()

    def apply_theme_styles(self):
        self.styles = get_stylesheet(self.dark_theme, self.language)
        self.setStyleSheet(self.styles["main"])
        self.textinformer.setStyleSheet(self.styles["label"])
        self.app_title_label.setStyleSheet(self.styles["about_title_style"])
        self.version_label.setStyleSheet(self.styles["label"])
        text_color = "#ffffff" if self.dark_theme else "#1a1a1a"
        self.update_date_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; border-radius: 8px; padding: 4px 8px; margin: 2px;"
        )
        self.install_button.setStyleSheet(self.styles["button1"])
        self.uninstall_button.setStyleSheet(self.styles["button2"])
        self.theme_button.setStyleSheet(self.styles["theme"])
        self.language_button.setStyleSheet(
            self.styles["theme"] +
            "\nQPushButton { padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }"
        )
        self.donate_button.setStyleSheet(self.styles["theme"])
        self.open_hosts_button.setStyleSheet(self.styles["theme"])
        self.backup_hosts_button.setStyleSheet(self.styles["theme"])
        self.update_button.setStyleSheet(self.styles["theme"])
        self.about_button.setStyleSheet(self.styles["theme"])
        self.refresh_status_container_style()
        self.update_subwindow_styles()
        refresh_icons(self, self.dark_theme)

    def refresh_status_container_style(self):
        light = "background:#f3f4f7; border:1.5px solid #cfd4db; border-radius:12px;"
        dark = "background:#2d333b; border:1.5px solid #3c434d; border-radius:12px;"
        self.status_container.setStyleSheet(dark if self.dark_theme else light)

    def apply_main_texts(self):
        self.title_label.setText("Goida AI Unlocker")
        self.app_title_label.setText(self.styles["about_title_html"])
        self.update_installation_status_label()

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
        self.theme_button.setText(tr("theme_button"))
        self.language_button.setText("")
        self.language_button.setToolTip(tr("language_button"))
        self.language_button.setStatusTip(tr("language_button"))
        self.language_button.setAccessibleName(tr("language_button"))
        self.donate_button.setText(tr("donate_button"))
        self.about_button.setText(tr("about_button"))
        self.update_button.setText(tr("update_button"))
        self.open_hosts_button.setText(tr("open_hosts_button"))
        self.backup_hosts_button.setText(tr("backup_hosts_button"))

    def show_donate(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(24)
        vbox.setContentsMargins(20, 20, 20, 20)
        self.fix_widget_size(widget)

        card = QWidget()
        card.setObjectName("donate_card")
        card.setMaximumWidth(380)
        card.setMinimumWidth(240)
        cl = QVBoxLayout(card)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(16)
        cl.setContentsMargins(32, 24, 32, 24)

        light = "background:#f3f4f7; border:2.5px solid #cfd4db; border-radius:12px;"
        dark = "background:#2d333b; border:2.5px solid #3c434d; border-radius:12px;"
        card.setStyleSheet(dark if self.dark_theme else light)

        title = QLabel(tr("donate_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:600;")
        cl.addWidget(title)

        card_num = "2202 2050 1464 4675"
        card_lbl = QLabel(f"ㅤSBER: <b>{card_num}</b>ㅤ")
        card_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lbl.setStyleSheet("font-size:16px;")
        cl.addWidget(card_lbl)

        copy_btn = QPushButton(tr("copy_card"))
        copy_btn.setProperty("style_role", "button1")
        cl.addWidget(copy_btn)

        vbox.addWidget(card)

        back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setProperty("style_role", "theme")
        back_btn.setStyleSheet(self.styles["theme"])
        vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        def copy_card():
            QApplication.clipboard().setText(card_num)
            if getattr(copy_btn, "_animating", False):
                return
            setattr(copy_btn, "_animating", True)
            orig = tr("copy_card")
            succ = tr("copied")

            def anim():
                eff = QGraphicsOpacityEffect(copy_btn)
                copy_btn.setGraphicsEffect(eff)
                fo = QPropertyAnimation(eff, b"opacity", copy_btn)
                fo.setDuration(150)
                fo.setStartValue(1.0)
                fo.setEndValue(0.0)

                def change():
                    copy_btn.setText(succ)
                    fi = QPropertyAnimation(eff, b"opacity", copy_btn)
                    fi.setDuration(150)
                    fi.setStartValue(0.0)
                    fi.setEndValue(1.0)

                    def hold():
                        def revert():
                            fo2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                            fo2.setDuration(150)
                            fo2.setStartValue(1.0)
                            fo2.setEndValue(0.0)

                            def reset():
                                copy_btn.setText(orig)
                                fi2 = QPropertyAnimation(eff, b"opacity", copy_btn)
                                fi2.setDuration(150)
                                fi2.setStartValue(0.0)
                                fi2.setEndValue(1.0)

                                def clear():
                                    copy_btn.setGraphicsEffect(None)
                                    setattr(copy_btn, "_animating", False)
                                fi2.finished.connect(clear)
                                fi2.start()
                            fo2.finished.connect(reset)
                            fo2.start()
                        QTimer.singleShot(1200, revert)
                    fi.finished.connect(hold)
                    fi.start()
                fo.finished.connect(change)
                fo.start()
            anim()

        copy_btn.clicked.connect(copy_card)
        back_btn.clicked.connect(lambda: self.return_to_main(widget))

        if self.stacked_widget:
            self.stacked_widget.addWidget(widget)
        self.update_subwindow_styles()
        self.animate_switch(widget)

    def show_about(self):
        about = QWidget()
        vbox = QVBoxLayout(about)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(8)
        vbox.setContentsMargins(12, 12, 12, 12)

        icon_label = create_icon_label("bulb.svg", size=32, dark_theme=self.dark_theme)
        vbox.addWidget(icon_label)

        label_ver = QLabel()
        label_ver.setObjectName("about_title")
        label_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(label_ver)

        info = QLabel()
        info.setObjectName("about_info")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(info)

        github_btn = QToolButton()
        github_btn.setText("GitHub")
        github_btn.setIcon(get_icon("github.svg", 24, dark_theme=self.dark_theme, force_dark=True))
        github_btn.setIconSize(QSize(24, 24))
        github_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setProperty("style_role", "about_tool")
        github_btn.setProperty("icon_name", "github.svg")
        github_btn.setProperty("icon_force_dark", True)
        github_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores"))

        repo_btn = QToolButton()
        repo_btn.setText(tr("repository"))
        repo_btn.setIcon(get_icon("github.svg", 24, dark_theme=self.dark_theme, force_dark=True))
        repo_btn.setIconSize(QSize(24, 24))
        repo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        repo_btn.setProperty("style_role", "about_tool")
        repo_btn.setProperty("icon_name", "github.svg")
        repo_btn.setProperty("icon_force_dark", True)
        repo_btn.clicked.connect(lambda: open_target("https://github.com/AvenCores/Goida-AI-Unlocker"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(github_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)

        social = [
            ("Telegram", "https://t.me/avencoresyt", "send.svg"),
            ("YouTube", "https://youtube.com/@avencores", "play.svg"),
            ("RuTube", "https://rutube.ru/channel/34072414", "video.svg"),
            ("Dzen", "https://dzen.ru/avencores", "book-open.svg"),
            ("VK", "https://vk.com/avencoresvk", "users.svg"),
        ]
        buttons = [github_btn, repo_btn]
        col_count = 3
        row, col = 0, 1
        for label, url, icon in social:
            btn = QToolButton()
            btn.setText(label)
            btn.setIcon(get_icon(icon, 24, dark_theme=self.dark_theme, force_dark=True))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setProperty("style_role", "about_tool")
            btn.setProperty("icon_name", icon)
            btn.setProperty("icon_force_dark", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, u=url: open_target(u))
            grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            buttons.append(btn)
            col += 1
            if col >= col_count:
                row += 1
                col = 0

        vbox.addLayout(grid)
        vbox.addSpacing(8)
        vbox.addWidget(repo_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addSpacing(8)

        def equalize():
            if not buttons:
                return
            try:
                ref = max(b.sizeHint().width() for b in buttons if b.sizeHint().width() > 0)
                for b in buttons:
                    b.setFixedWidth(ref)
            except Exception:
                pass

        back_btn = QPushButton(f"  {tr('back_to_menu')}  ")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setProperty("style_role", "theme")
        back_btn.setStyleSheet(self.styles["theme"])
        back_btn.clicked.connect(lambda: self.return_to_main(about))
        vbox.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        if self.stacked_widget:
            self.stacked_widget.addWidget(about)
        self.update_subwindow_styles()
        QTimer.singleShot(150, equalize)
        self.animate_switch(about)

    def check_for_updates(self):
        if self._check_updates_running:
            return
        self._check_updates_running = True

        worker = AppUpdateWorker(self.resource_path)
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
