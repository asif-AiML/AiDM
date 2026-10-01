#!/usr/bin/env python3

import sys
from dataclasses import replace
from enum import Enum, auto
from http.client import HTTPException
from threading import Thread

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from download_job import DownloadJob, YouTubeMode, BulkMode, VideoQuality, build_download_job
from gui_input import validate_gui_input
from gui_metadata import MetadataProcess
from gui_quality import QualityProcess
from inspection import classify_input, InputKind, MetadataStatus
from metadata import prepare_metadata


CLASSIFICATION_LABELS = {
    InputKind.TORRENT: "Torrent file — GUI support deferred",
    InputKind.YOUTUBE_SINGLE: "YouTube video",
    InputKind.YOUTUBE_BULK: "YouTube batch",
    InputKind.YOUTUBE_PLAYLIST: "YouTube playlist",
    InputKind.DIRECT_SINGLE: "Direct download",
    InputKind.DIRECT_BULK: "Direct batch",
    InputKind.HLS: "HLS stream",
    InputKind.DASH: "DASH stream",
    InputKind.VTT: "WebVTT subtitle — not the main media",
    InputKind.GENERIC_YTDLP: "Generic media URL — yt-dlp fallback (unverified)",
    InputKind.STREAM_INSPECTOR: "Browser-assisted stream",
    InputKind.MIXED_BULK: "Unsupported mixed batch",
    InputKind.UNSUPPORTED: "Unsupported input",
}


class InspectionWorker(QObject):
    finished = Signal(int, object, str)

    def __init__(self, revision, args):
        super().__init__()
        self.revision = revision
        self.args = args

    def run(self):
        try:
            result = classify_input(self.args)
        except (ValueError, OSError, HTTPException) as error:
            self.finished.emit(self.revision, None, str(error))
        else:
            self.finished.emit(self.revision, result, "")


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
        self.classification.setWordWrap(True)
        self.media_title = QLabel("Media title placeholder")
        self.media_title.setTextFormat(Qt.TextFormat.PlainText)
        self.media_title.setWordWrap(True)
        self.item_count = QLabel()
        self.mode_options, self.mode_group, self.mode_buttons = self.make_options(
            "Download as", {
                YouTubeMode.VIDEO: "Video", YouTubeMode.ORIGINAL_AUDIO: "Original Audio",
                YouTubeMode.WAV: "WAV",
            }, self.on_mode_changed,
        )
        self.bulk_options, self.bulk_group, self.bulk_buttons = self.make_options(
            "Download mode", {BulkMode.SEQUENTIAL: "Sequential", BulkMode.PARALLEL: "Parallel"},
            self.on_bulk_changed,
        )
        self.quality_options = QWidget()
        quality_layout = QVBoxLayout(self.quality_options)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.addWidget(QLabel("Quality"))
        self.quality_choice = QComboBox()
        self.quality_choice.setAccessibleName("Maximum video quality")
        quality_layout.addWidget(self.quality_choice)
        self.quality_choice.currentIndexChanged.connect(self.on_quality_changed)
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.on_download_intent)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.active_status = QLabel()
        self.active_status.setTextFormat(Qt.TextFormat.PlainText)
        self.active_status.setWordWrap(True)
        self.abort_button = QPushButton("Abort")
        self.result_message = QLabel()

        for widget in (
            self.classification,
            self.media_title,
            self.item_count,
            self.mode_options,
            self.bulk_options,
            self.quality_options,
            self.active_status,
            self.download_button,
            self.progress,
            self.abort_button,
            self.result_message,
        ):
            layout.addWidget(widget)
        layout.addStretch()

        self.setCentralWidget(content)
        self.input_result = validate_gui_input("")
        self.inspection_result = None
        self.inspection_error = ""
        self._revision = 0
        self._worker = None
        self._pending = None
        self._closing = False
        self.download_job = None
        self._configuration_started = False
        self._configuration_error = ""
        self._execution_deferred = False
        self._quality_generation = 0
        self._quality_worker = None
        self._quality_pending = False
        self._metadata = None
        self._metadata_timer = QTimer(self)
        self._metadata_timer.setSingleShot(True)
        self._metadata_timer.setInterval(250)
        self._metadata_timer.timeout.connect(self.start_metadata)
        self._inspection_timer = QTimer(self)
        self._inspection_timer.setSingleShot(True)
        self._inspection_timer.setInterval(350)
        self._inspection_timer.timeout.connect(self.start_inspection)
        self.input_field.textChanged.connect(self.on_input_changed)
        self._enter_shortcuts = []
        for key in ("Return", "Enter"):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(self.on_download_intent)
            self._enter_shortcuts.append(shortcut)
        self.set_state(GuiState.EMPTY)

    def make_options(self, label, choices, callback):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        row = QHBoxLayout()
        group = QButtonGroup(container)
        buttons = {}
        for value, text in choices.items():
            button = QRadioButton(text)
            group.addButton(button)
            row.addWidget(button)
            buttons[value] = button
            button.toggled.connect(lambda checked, callback=callback: callback() if checked else None)
        layout.addLayout(row)
        return container, group, buttons

    def usable_input(self):
        result = self.inspection_result
        return bool(not self._closing and result and not self.inspection_error
                    and self.input_result.error is None and result.error is None
                    and result.route in {
                        InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST,
                        InputKind.DIRECT_SINGLE, InputKind.DIRECT_BULK, InputKind.HLS,
                        InputKind.DASH, InputKind.GENERIC_YTDLP,
                    })

    def requires_options(self):
        return self.inspection_result.route in {
            InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK,
            InputKind.YOUTUBE_PLAYLIST, InputKind.DIRECT_BULK,
        }

    def cancel_quality(self):
        self._quality_generation += 1
        self._quality_pending = False
        if self._quality_worker is not None:
            self._quality_worker.cancel()
            self._quality_worker = None

    def clear_quality(self):
        self.quality_choice.blockSignals(True)
        self.quality_choice.clear()
        self.quality_choice.blockSignals(False)

    def reset_configuration(self):
        self.cancel_quality()
        self.clear_quality()
        for group in (self.mode_group, self.bulk_group):
            group.setExclusive(False)
            for button in group.buttons():
                button.setChecked(False)
            group.setExclusive(True)
        self.download_job = None
        self._configuration_started = False
        self._configuration_error = ""
        self._execution_deferred = False

    def on_download_intent(self):
        if self.current_state != GuiState.READY or not self.usable_input():
            return
        if not self._configuration_started and self.requires_options():
            self._configuration_started = True
            self.set_state(GuiState.NEEDS_OPTIONS)
            if self.inspection_result.route == InputKind.YOUTUBE_PLAYLIST:
                self.start_quality()
            return
        self.update_configuration()
        if self.download_job is not None:
            # Execution boundary only: no downloader is connected in Milestone 8.
            self._execution_deferred = True
            self.set_state(GuiState.READY)

    def on_mode_changed(self):
        if not self._configuration_started or not self.usable_input():
            return
        self.cancel_quality()
        self.clear_quality()
        self._execution_deferred = False
        if self.mode_buttons[YouTubeMode.VIDEO].isChecked():
            self.start_quality()
        else:
            self.update_configuration()

    def on_bulk_changed(self):
        self._execution_deferred = False
        self.update_configuration()

    def on_quality_changed(self):
        self._execution_deferred = False
        self.update_configuration()

    def start_quality(self):
        self.cancel_quality()
        self.download_job = None
        self._quality_pending = True
        self.set_state(GuiState.NEEDS_OPTIONS)
        self._quality_worker = QualityProcess(
            self._quality_generation, self.inspection_result.urls[0], self,
        )
        self._quality_worker.finished.connect(self.finish_quality)
        self._quality_worker.start()

    @Slot(int, object)
    def finish_quality(self, generation, qualities):
        if self._closing or generation != self._quality_generation or not self._configuration_started:
            return
        self._quality_worker = None
        self._quality_pending = False
        self.quality_choice.blockSignals(True)
        self.quality_choice.clear()
        if qualities:
            self.quality_choice.addItem("Choose quality", None)
            for height in qualities:
                self.quality_choice.addItem(f"{height}p", height)
        else:
            self.quality_choice.addItem("Best available", VideoQuality.BEST)
        self.quality_choice.blockSignals(False)
        self.update_configuration()

    def update_configuration(self):
        self.download_job = None
        self._configuration_error = ""
        if not self.usable_input():
            self.set_state(GuiState.NEEDS_OPTIONS)
            return
        if self.requires_options() and not self._configuration_started:
            self.set_state(GuiState.READY)
            return
        mode = next((value for value, button in self.mode_buttons.items() if button.isChecked()), None)
        bulk = next((value for value, button in self.bulk_buttons.items() if button.isChecked()), None)
        quality = self.quality_choice.currentData()
        route = self.inspection_result.route
        missing = (
            self._quality_pending
            or (route in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK} and mode is None)
            or ((route == InputKind.YOUTUBE_PLAYLIST or mode == YouTubeMode.VIDEO) and quality is None)
            or (route == InputKind.DIRECT_BULK and bulk is None)
        )
        if not missing:
            try:
                self.download_job = build_download_job(
                    self.inspection_result, mode=mode, video_quality=quality, bulk_mode=bulk,
                )
            except ValueError as error:
                self._configuration_error = str(error)
        self.set_state(GuiState.READY if self.download_job is not None else GuiState.NEEDS_OPTIONS)

    def on_input_changed(self, text: str) -> None:
        self._revision += 1
        self.reset_configuration()
        self.cancel_metadata()
        self._inspection_timer.stop()
        self._pending = None
        self.inspection_result = None
        self.inspection_error = ""
        self.input_result = validate_gui_input(text)
        # Parser validity alone never makes an input ready to download.
        empty = not self.input_result.argv and self.input_result.error is None
        self.set_state(GuiState.EMPTY if empty else GuiState.INSPECTING)
        if self.input_result.args is not None:
            self._pending = (self._revision, self.input_result.args)
            self._inspection_timer.start()

    def start_inspection(self) -> None:
        # At most one probe runs; retain only the latest pending input.
        if self._worker is not None or self._pending is None or self._closing:
            return
        revision, args = self._pending
        self._pending = None
        self._worker = InspectionWorker(revision, args)
        self._worker.finished.connect(self.finish_inspection)
        # Existing urllib probes are bounded by their existing timeouts. A
        # daemon worker lets closing the GUI exit without waiting for the probe.
        Thread(target=self._worker.run, daemon=True).start()

    @Slot(int, object, str)
    def finish_inspection(self, revision, result, error) -> None:
        self._worker = None
        if self._closing:
            return
        if revision == self._revision:
            self.inspection_result = prepare_metadata(result) if result else None
            self.inspection_error = error
            self.update_configuration()
            if self.inspection_result and self.inspection_result.metadata_status == MetadataStatus.PENDING:
                self._metadata_timer.start()
        if self._pending is not None and not self._inspection_timer.isActive():
            self.start_inspection()

    def build_job_for_testing(
        self, *, mode: YouTubeMode | None = None,
        video_quality: int | VideoQuality | None = None,
        bulk_mode: BulkMode | None = None,
    ) -> DownloadJob:
        """Temporary development helper: return a job without state changes/execution."""
        if (self._closing or self.inspection_result is None
                or self.input_result.error is not None or self.inspection_error):
            raise ValueError("Current input has no successful classification")
        if self.inspection_result.kind == InputKind.TORRENT:
            raise ValueError("Torrent GUI support is deferred")
        return build_download_job(
            self.inspection_result, mode=mode,
            video_quality=video_quality, bulk_mode=bulk_mode,
        )

    def start_metadata(self) -> None:
        result = self.inspection_result
        if self._closing or result is None or result.metadata_status != MetadataStatus.PENDING:
            return
        self._metadata = MetadataProcess(self._revision, result, self)
        self._metadata.finished.connect(self.finish_metadata)
        self._metadata.start()

    @Slot(int, object)
    def finish_metadata(self, revision, result) -> None:
        if self._closing or revision != self._revision:
            return
        self._metadata = None
        self.inspection_result = result
        self.update_configuration()

    def cancel_metadata(self) -> None:
        self._metadata_timer.stop()
        if self._metadata is not None:
            self._metadata.cancel()
            self._metadata = None
        if self.inspection_result and self.inspection_result.metadata_status == MetadataStatus.PENDING:
            self.inspection_result = replace(self.inspection_result, metadata_status=MetadataStatus.NOT_REQUESTED)

    def preview_state(self, state: GuiState) -> None:
        self._revision += 1
        self.reset_configuration()
        self.cancel_metadata()
        self._inspection_timer.stop()
        self._pending = None
        self.set_state(state)

    def closeEvent(self, event) -> None:
        self._closing = True
        self._revision += 1
        self.reset_configuration()
        self.cancel_metadata()
        # Reap even processes cancelled by a preceding edit before closing.
        for worker in self.findChildren(MetadataProcess):
            worker.cancel(wait=True)
        self._inspection_timer.stop()
        self._pending = None
        super().closeEvent(event)

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
        result = self.inspection_result
        self.classification.setText(
            "● " + CLASSIFICATION_LABELS[result.kind] if result else ""
        )
        title = result.title if result else None
        self.media_title.setText(title or "")
        self.classification.setVisible(has_details and result is not None)
        self.media_title.setVisible(has_details and bool(title))
        count = result.item_count if result else None
        count_unit = (
            "videos" if result and result.route == InputKind.YOUTUBE_BULK
            else "files" if result and result.route == InputKind.DIRECT_BULK else "items"
        )
        self.item_count.setText(f"{count} {count_unit}" if count is not None else "")
        self.item_count.setVisible(has_details and count is not None)
        configuring = self._configuration_started and state in {GuiState.READY, GuiState.NEEDS_OPTIONS}
        route = result.route if result else None
        self.mode_options.setVisible(configuring and route in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK})
        self.bulk_options.setVisible(configuring and route == InputKind.DIRECT_BULK)
        self.quality_options.setVisible(configuring and not self._quality_pending
                                        and self.quality_choice.count() > 1)
        self.download_button.setVisible(state == GuiState.READY)
        self.download_button.setEnabled(state == GuiState.READY and self.usable_input())
        for shortcut in self._enter_shortcuts:
            shortcut.setEnabled(state == GuiState.READY and self.usable_input())
        self.progress.setVisible(downloading)
        self.progress.setEnabled(False)
        if downloading:
            status = "Download status placeholder (no download running)"
        elif self.input_result.error is not None:
            status = "Input incomplete or invalid — continue editing"
        elif self.inspection_error:
            status = "Could not inspect input — check the URL and edit to retry"
        elif self._quality_pending:
            status = "Fetching available video qualities…"
        elif self._configuration_error:
            status = self._configuration_error
        elif self._execution_deferred:
            status = "Download configured — execution is not implemented yet."
        elif self.quality_choice.currentData() == VideoQuality.BEST:
            status = "Available qualities could not be determined — best available will be used."
        elif result is not None:
            if result.error:
                status = result.error
            elif result.metadata_status == MetadataStatus.PENDING:
                status = "Inspecting playlist…" if result.route == InputKind.YOUTUBE_PLAYLIST else "Fetching media information…"
            elif result.metadata_status == MetadataStatus.UNAVAILABLE:
                status = "Media information unavailable"
            else:
                status = ""
        else:
            status = "Inspecting…"
        self.active_status.setText(status)
        self.active_status.setVisible(
            state == GuiState.INSPECTING or downloading
            or (state in {GuiState.NEEDS_OPTIONS, GuiState.READY} and bool(status))
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
        shortcut.activated.connect(lambda state=state: window.preview_state(state))


def main(state_test: bool = False) -> int:
    app = QApplication(sys.argv)

    window = AiDMWindow()
    if state_test:
        enable_state_test_shortcuts(window)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
