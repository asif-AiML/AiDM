#!/usr/bin/env python3

import sys
from enum import Enum, auto

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class GuiState(Enum):
    EMPTY = auto()
    INSPECTING = auto()
    NEEDS_OPTIONS = auto()
    READY = auto()
    DOWNLOADING = auto()
    COMPLETE = auto()
    FAILED = auto()


class AiDMWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AiDM v0.1.0")
        self.resize(480, 200)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addStretch()

        self.heading = QLabel("AiDM")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading_font = self.heading.font()
        heading_font.setPointSize(22)
        heading_font.setBold(True)
        self.heading.setFont(heading_font)
        layout.addWidget(self.heading)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Paste URL or AiDM data")
        self.input_field.setAccessibleName("URL or AiDM data")
        self.input_field.setStyleSheet("""
            QLineEdit {
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 10px 12px;
            }
            QLineEdit:focus {
                border-color: palette(highlight);
            }
        """)
        layout.addWidget(self.input_field)

        self.classification = QLabel("Classification placeholder")
        self.media_title = QLabel("Media title placeholder")
        self.download_button = QPushButton("Download")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.active_status = QLabel()
        self.abort_button = QPushButton("Abort")
        self.result_message = QLabel()

        for widget in (
            self.classification,
            self.media_title,
            self.download_button,
            self.progress,
            self.active_status,
            self.abort_button,
            self.result_message,
        ):
            layout.addWidget(widget)
        layout.addStretch()

        self.setCentralWidget(content)
        self.input_field.textChanged.connect(self.on_input_changed)
        self.set_state(GuiState.EMPTY)

    def on_input_changed(self, text: str) -> None:
        # Reserve the inspection state without classifying or inspecting input.
        self.set_state(GuiState.INSPECTING if text.strip() else GuiState.EMPTY)

    def set_state(self, state: GuiState) -> None:
        """Apply all state-dependent presentation in one place."""
        self.current_state = state
        has_details = state in {
            GuiState.NEEDS_OPTIONS,
            GuiState.READY,
            GuiState.DOWNLOADING,
            GuiState.COMPLETE,
            GuiState.FAILED,
        }
        downloading = state == GuiState.DOWNLOADING

        self.heading.setVisible(True)
        self.input_field.setVisible(True)
        self.input_field.setEnabled(True)
        self.classification.setVisible(has_details)
        self.media_title.setVisible(has_details)
        self.download_button.setVisible(state == GuiState.READY)
        self.download_button.setEnabled(False)
        self.progress.setVisible(downloading)
        self.progress.setEnabled(False)
        self.active_status.setVisible(state == GuiState.INSPECTING or downloading)
        self.active_status.setText(
            "Download status placeholder (no download running)"
            if downloading else "Inspection pending — not implemented yet"
        )
        self.abort_button.setVisible(downloading)
        self.abort_button.setEnabled(False)
        self.result_message.setText({
            GuiState.COMPLETE: "Download complete (state preview)",
            GuiState.FAILED: "Download failed (state preview)",
        }.get(state, ""))
        self.result_message.setVisible(state in {GuiState.COMPLETE, GuiState.FAILED})


def enable_state_test_shortcuts(window: AiDMWindow) -> None:
    """Temporary opt-in development preview: F1 through F7 follow enum order."""
    for number, state in enumerate(GuiState, start=1):
        shortcut = QShortcut(QKeySequence(f"F{number}"), window)
        shortcut.activated.connect(lambda state=state: window.set_state(state))


def main(state_test: bool = False) -> int:
    app = QApplication(sys.argv)

    window = AiDMWindow()
    if state_test:
        enable_state_test_shortcuts(window)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
