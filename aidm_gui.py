#!/usr/bin/env python3

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)


def main() -> int:
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("AiDM v0.1.0")
    window.resize(480, 200)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(16)
    layout.addStretch()

    heading = QLabel("AiDM")
    heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
    heading_font = heading.font()
    heading_font.setPointSize(22)
    heading_font.setBold(True)
    heading.setFont(heading_font)
    layout.addWidget(heading)

    input_field = QLineEdit()
    input_field.setPlaceholderText("Paste URL or AiDM data")
    input_field.setAccessibleName("URL or AiDM data")
    input_field.setStyleSheet("""
        QLineEdit {
            border: 1px solid palette(mid);
            border-radius: 8px;
            padding: 10px 12px;
        }
        QLineEdit:focus {
            border-color: palette(highlight);
        }
    """)
    layout.addWidget(input_field)
    layout.addStretch()

    window.setCentralWidget(content)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
