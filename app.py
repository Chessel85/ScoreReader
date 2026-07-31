# app.py
import sys
from PySide6.QtWidgets import QApplication

# Import the MainWindow class from main_window.py
from main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()