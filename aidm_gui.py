#!/usr/bin/env python3

import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def main() -> int:
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("AiDM")
    window.resize(480, 240)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
