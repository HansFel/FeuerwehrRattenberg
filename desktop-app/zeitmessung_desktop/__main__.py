"""Einstiegspunkt: python -m zeitmessung_desktop"""
import sys

from PySide6.QtWidgets import QApplication

from .hauptfenster import Hauptfenster


def main() -> None:
    app = QApplication(sys.argv)
    fenster = Hauptfenster()
    fenster.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
