import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from app.core.constants import APP_VERSION, resource_path
from app.core.settings import get_setting
from app.gui.localization import detect_system_language, set_current_language
from app.gui.styles import get_stylesheet
from app.gui.main_window import MainWindow


def main():
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

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
