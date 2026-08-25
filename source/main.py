import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from app.core.constants import APP_VERSION, resource_path
from app.core.settings import get_setting
from app.gui.localization import detect_system_language, set_current_language
from app.gui.styles import get_stylesheet
from app.gui.main_window import MainWindow


def main():
    # Дробные коэффициенты масштабирования ОС (125%, 150%…) без округления:
    # картинка остаётся чёткой на HiDPI-экранах
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Goida AI Unlocker")
    app.setApplicationDisplayName("Goida AI Unlocker")
    app.setOrganizationName("AvenCores")
    app.setApplicationVersion(APP_VERSION)
    icon_file = "assets/icon.icns" if sys.platform == "darwin" else "assets/icon.ico"
    app.setWindowIcon(QIcon(resource_path(icon_file)))
    app.setStyleSheet(get_stylesheet(False)["outline_reset"])

    saved_lang = get_setting("language")
    set_current_language(saved_lang or detect_system_language())

    # Смена масштаба интерфейса пересобирает окно: все размеры виджетов
    # фиксируются при сборке, поэтому старое окно закрывается после
    # показа нового (ссылка держится, пока окно не закрыто)
    current_window = None

    def start_main_window():
        nonlocal current_window
        window = MainWindow()

        def on_restart_requested():
            old_window = window
            start_main_window()
            old_window.close()

        window.restart_requested.connect(on_restart_requested)
        window.show()
        current_window = window

    start_main_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
