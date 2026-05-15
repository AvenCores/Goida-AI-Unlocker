import sys
from PySide6.QtWidgets import QApplication
from app.gui.localization import detect_system_language, set_current_language
from app.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("QPushButton:focus { outline: none; }")

    # Detect language
    set_current_language(detect_system_language())

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
