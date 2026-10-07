#!/usr/bin/env python3

import sys
from dataclasses import replace
from enum import Enum, auto
from http.client import HTTPException
import os
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from download_job import DownloadJob, YouTubeMode, BulkMode, VideoQuality, build_download_job
from gui_input import validate_gui_input
from gui_execution import create_download_process, ExecutionOutcome, UnsupportedExecution
from gui_metadata import MetadataProcess
from gui_quality import QualityProcess
from gui_progress import format_statistics
from inspection import classify_input, InputKind, MetadataStatus
from metadata import prepare_metadata
from status_event import StatusEvent, StatusKind, StatusReason
from progress_event import ProgressEvent


def render_status(event: StatusEvent) -> str:
    """Translate backend activity into GUI language, without changing state."""
    engine = event.engine or "download engine"
    if event.kind == StatusKind.STARTING_ENGINE:
        return f"Starting {engine}… ⚙️"
    if event.kind == StatusKind.FAILED and event.reason == StatusReason.START_FAILED:
        return f"Could not start {engine}. ⚠️"
    return {
        StatusKind.DOWNLOADING: "Downloading… ⬇️",
        StatusKind.DOWNLOADING_VIDEO: "Downloading video… 🎬",
        StatusKind.DOWNLOADING_AUDIO: "Downloading audio… 🎵",
        StatusKind.MERGING: "Merging audio and video… 🧩",
        StatusKind.CONVERTING_AUDIO: "Converting audio… 🎛️",
        StatusKind.REMUXING: "Remuxing video… 🧩",
        StatusKind.FINALIZING: "Finalizing… ⚙️",
        StatusKind.COMPLETE: "Download complete 🎉💫",
        StatusKind.FAILED: "Download failed 🚫🤕",
        StatusKind.ABORTING: "Aborting… 🛑",
        StatusKind.ABORTED: "Download aborted 🙄",
    }[event.kind]


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
    ABORTED = auto()


def existing_destination(value) -> str | None:
    """Resolve an accessible directory; do not create it or test future writes."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    try:
        path = Path(value)
        if not path.is_absolute():
            return None
        path = path.resolve(strict=True)
        if path.is_dir() and os.access(path, os.R_OK | os.X_OK):
            return str(path)
    except (OSError, RuntimeError, ValueError):
        pass
    return None


def initial_destination(settings: QSettings) -> str:
    remembered = existing_destination(settings.value("downloads/destination"))
    if remembered is not None:
        return remembered
    home = Path.home()
    return existing_destination(str(home / "Downloads")) or str(home.resolve())


class JobTitleLabel(QLabel):
    """Elide terminal identity to the available width, retaining its full text."""

    def set_identity(self, text: str, terminal: bool):
        self.full_title = text
        self.terminal = terminal
        self.setToolTip(text if terminal else "")
        self.render_identity()

    def render_identity(self):
        text = self.full_title
        if self.terminal:
            text = self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle,
                                                max(0, self.contentsRect().width()))
        self.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "full_title"):
            self.render_identity()


class AiDMWindow(QMainWindow):
    def __init__(self, *, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings("AiDM", "AiDM")
        self.destination = initial_destination(self.settings)
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
        self.media_title = JobTitleLabel("Media title placeholder")
        self.media_title.setTextFormat(Qt.TextFormat.PlainText)
        self.media_title.setWordWrap(True)
        self._media_title_font = self.media_title.font()
        self._media_title_alignment = self.media_title.alignment()
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
        self.destination_section = QWidget()
        destination_layout = QVBoxLayout(self.destination_section)
        destination_layout.setContentsMargins(0, 0, 0, 0)
        destination_layout.addWidget(QLabel("Save to"))
        destination_row = QHBoxLayout()
        self.destination_field = QLineEdit(self.destination)
        self.destination_field.setReadOnly(True)
        self.destination_field.setAccessibleName("Download destination")
        self.destination_field.setMinimumWidth(0)
        self.destination_field.setToolTip(self.destination)
        self.destination_field.setCursorPosition(0)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_destination)
        destination_row.addWidget(self.destination_field, 1)
        destination_row.addWidget(self.browse_button)
        destination_layout.addLayout(destination_row)
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.on_download_intent)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.reset()
        self.progress.setTextVisible(True)
        self.progress.setMinimumHeight(24)
        self.progress.setAccessibleName("Download progress")
        self.statistics = QLabel()
        self.statistics.setTextFormat(Qt.TextFormat.PlainText)
        self.statistics.setWordWrap(True)
        self.statistics.setAccessibleName("Download statistics")
        self.active_status = QLabel()
        self.active_status.setTextFormat(Qt.TextFormat.PlainText)
        self.active_status.setWordWrap(True)
        self.active_status.setAccessibleName("Current activity")
        self.abort_button = QPushButton("Abort")
        self.abort_button.clicked.connect(self.abort_download)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self.retry_download)
        self.result_message = QLabel()
        self.result_message.setTextFormat(Qt.TextFormat.PlainText)
        self.result_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_message.setWordWrap(True)
        self.result_message.setContentsMargins(0, 16, 0, 16)
        self.result_message.setAccessibleName("Download result")
        result_font = self.result_message.font()
        result_font.setPointSize(20)
        result_font.setBold(True)
        self.result_message.setFont(result_font)

        for widget in (
            self.classification,
            self.media_title,
            self.item_count,
            self.mode_options,
            self.bulk_options,
            self.quality_options,
            self.destination_section,
            self.progress,
            self.statistics,
            self.active_status,
            self.download_button,
            self.result_message,
            self.abort_button,
            self.retry_button,
        ):
            if widget is self.retry_button:
                layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignHCenter)
            elif widget is self.abort_button:
                layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignRight)
            else:
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
        self._download_process = None
        self._retry_job = None
        self._retry_error = ""
        self._download_event: StatusEvent | None = None
        self._progress_event: ProgressEvent | None = None
        self._runtime_filename: str | None = None
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

    def browse_destination(self):
        if self.download_active():
            return
        selected = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.destination,
        )
        if not selected:
            return
        destination = existing_destination(selected)
        if destination is None:
            self._configuration_error = "Selected folder is unavailable — choose another folder."
            self.set_state(self.current_state)
            return
        self.destination = destination
        self.destination_field.setText(destination)
        self.destination_field.setToolTip(destination)
        self.destination_field.setCursorPosition(0)
        self.settings.setValue("downloads/destination", destination)
        self.settings.sync()
        self._execution_deferred = False
        # Preserve all mode/quality selections and any active quality request.
        self.update_configuration()

    def checked_destination(self):
        if existing_destination(self.destination) is None:
            raise ValueError("Download folder is unavailable — choose another folder.")
        return self.destination

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
            self.start_download(self.download_job)

    def download_active(self):
        return self._download_process is not None and self._download_process.active

    def start_download(self, job, *, retry=False):
        if self.download_active() or job is None:
            return
        if existing_destination(job.destination) is None:
            message = "Download folder is unavailable — choose another folder."
            if retry:
                self._retry_error = message
                self.set_state(self.current_state)
            else:
                self._configuration_error = message
                self.set_state(GuiState.READY)
            return
        try:
            process = create_download_process(job, self)
        except UnsupportedExecution:
            self._execution_deferred = True
            self.set_state(GuiState.READY)
            return
        if self._download_process is not None:
            self._download_process.deleteLater()
        self._download_process = process
        self._retry_job = job if process.can_retry else None
        self._retry_error = ""
        process.status_event.connect(self.on_download_status)
        process.progress_event.connect(self.on_download_progress)
        process.filename_resolved.connect(self.on_filename_resolved)
        process.finished.connect(self.on_download_finished)
        self._download_event = None
        self._progress_event = None
        self._runtime_filename = None
        self.set_state(GuiState.DOWNLOADING)
        process.start()

    def abort_download(self):
        process = self._download_process
        if (self.download_active() and process.can_abort
                and not process.abort_requested):
            process.abort()

    def retry_download(self):
        if (self.current_state in {GuiState.FAILED, GuiState.ABORTED}
                and self._retry_job is not None and not self.download_active()):
            self.start_download(self._retry_job, retry=True)

    @Slot(object)
    def on_download_status(self, event: StatusEvent):
        if (not self._closing and self.sender() is self._download_process
                and self.current_state == GuiState.DOWNLOADING):
            self._download_event = event
            self.set_state(self.current_state)

    @Slot(object)
    def on_download_finished(self, outcome):
        if (not self._closing and self.sender() is self._download_process
                and self.current_state == GuiState.DOWNLOADING):
            self.set_state({ExecutionOutcome.COMPLETE: GuiState.COMPLETE,
                            ExecutionOutcome.FAILED: GuiState.FAILED,
                            ExecutionOutcome.ABORTED: GuiState.ABORTED}[outcome])

    @Slot(object)
    def on_download_progress(self, event: ProgressEvent):
        if (not self._closing and self.current_state == GuiState.DOWNLOADING
                and self.sender() is self._download_process
                and not self._download_process.abort_requested):
            self._progress_event = event
            self.set_state(self.current_state)

    @Slot(str)
    def on_filename_resolved(self, filename: str):
        if (not self._closing and self.current_state == GuiState.DOWNLOADING
                and self.sender() is self._download_process
                and not self._download_process.abort_requested):
            self._runtime_filename = filename
            self.set_state(self.current_state)

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
        if self.download_active():
            return
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
                    self.inspection_result, destination=self.checked_destination(),
                    mode=mode, video_quality=quality, bulk_mode=bulk,
                )
            except ValueError as error:
                self._configuration_error = str(error)
        # A missing folder is recoverable with Browse, not a job-mode choice.
        ready = self.download_job is not None or (
            not missing and self.inspection_result.kind == InputKind.DIRECT_SINGLE
        )
        self.set_state(GuiState.READY if ready else GuiState.NEEDS_OPTIONS)

    def on_input_changed(self, text: str) -> None:
        if self.download_active():
            return
        self._retry_job = None
        self._retry_error = ""
        self._download_event = None
        self._progress_event = None
        self._runtime_filename = None
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
            self.inspection_result, destination=self.checked_destination(), mode=mode,
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
        if self.download_active():
            return
        self._retry_job = None
        self._retry_error = ""
        self._download_event = None
        self._progress_event = None
        self._runtime_filename = None
        self._revision += 1
        self.reset_configuration()
        self.cancel_metadata()
        self._inspection_timer.stop()
        self._pending = None
        self.set_state(state)

    def closeEvent(self, event) -> None:
        self._closing = True
        if self._download_process is not None and not self._download_process.shutdown():
            self._closing = False
            event.ignore()
            return
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
        previous_state = getattr(self, "current_state", None)
        self.current_state = state
        has_details = state in {
            GuiState.NEEDS_OPTIONS,
            GuiState.READY,
            GuiState.DOWNLOADING,
            GuiState.COMPLETE,
            GuiState.FAILED,
            GuiState.ABORTED,
        }
        downloading = state == GuiState.DOWNLOADING
        terminal = state in {GuiState.COMPLETE, GuiState.FAILED, GuiState.ABORTED}

        self.heading.setVisible(True)
        self.input_field.setVisible(not downloading)
        self.input_field.setEnabled(not downloading)
        self.browse_button.setEnabled(not downloading)
        result = self.inspection_result
        self.classification.setText(
            "● " + CLASSIFICATION_LABELS[result.kind] if result else ""
        )
        title = result.title if result else None
        if not title and (downloading or terminal):
            title = self._runtime_filename
        title_font = QFont(self._media_title_font)
        if terminal:
            title_font.setPointSize(13)
            title_font.setBold(True)
        self.media_title.setFont(title_font)
        self.media_title.setAlignment(Qt.AlignmentFlag.AlignCenter if terminal else self._media_title_alignment)
        title_policy = QSizePolicy(
            QSizePolicy.Policy.Ignored if terminal else QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        title_policy.setHeightForWidth(True)
        self.media_title.setSizePolicy(title_policy)
        self.media_title.set_identity(title or "", terminal)
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
        self.destination_section.setVisible(
            state in {GuiState.READY, GuiState.NEEDS_OPTIONS} and self.usable_input()
        )
        self.download_button.setVisible(state == GuiState.READY)
        self.download_button.setEnabled(state == GuiState.READY and self.usable_input())
        for shortcut in self._enter_shortcuts:
            shortcut.setEnabled(state == GuiState.READY and self.usable_input())
        # Terminal states retain the real snapshot internally, not on screen.
        telemetry_visible = downloading
        progress = self._progress_event
        percent = progress.percent if progress else None
        if percent is None:
            self.progress.reset()
        else:
            # Truncate only for display; preserve fractional precision in the event.
            self.progress.setValue(int(percent))
        self.progress.setVisible(telemetry_visible and percent is not None)
        statistics = format_statistics(progress) if progress else ""
        self.statistics.setText(statistics)
        self.statistics.setVisible(telemetry_visible and bool(statistics))
        download_status = render_status(self._download_event) if self._download_event else ""
        if downloading:
            status = download_status or "Download status placeholder (no download running)"
        elif self.input_result.error is not None:
            status = "Input incomplete or invalid — continue editing ✏️"
        elif self.inspection_error:
            status = "Could not inspect input — check the URL and edit to retry 🔎⚠️"
        elif self._quality_pending:
            status = "Fetching available video qualities… 🎞️"
        elif self._configuration_error:
            status = self._configuration_error + (" 📁⚠️" if "folder" in self._configuration_error else " ⚠️")
        elif self._execution_deferred:
            status = "Download configured — execution is not implemented yet. 🧩"
        elif self.quality_choice.currentData() == VideoQuality.BEST:
            status = "Available qualities could not be determined — best available will be used. ⚠️"
        elif result is not None:
            if result.error:
                status = result.error + " ⚠️"
            elif result.metadata_status == MetadataStatus.PENDING:
                status = "Inspecting playlist… 👀" if result.route == InputKind.YOUTUBE_PLAYLIST else "Fetching media information… 🔎"
            elif result.metadata_status == MetadataStatus.UNAVAILABLE:
                status = "Media information unavailable ⚠️"
            else:
                status = ""
        else:
            status = "Inspecting… 👀"
        self.active_status.setText(status)
        self.active_status.setVisible(
            state == GuiState.INSPECTING or downloading
            or (state in {GuiState.NEEDS_OPTIONS, GuiState.READY} and bool(status))
        )
        process = self._download_process
        abort_visible = downloading and self.download_active() and process.can_abort
        self.abort_button.setVisible(abort_visible)
        self.abort_button.setEnabled(abort_visible and not process.abort_requested)
        self.retry_button.setVisible(
            state in {GuiState.FAILED, GuiState.ABORTED} and self._retry_job is not None
        )
        self.result_message.setText((self._retry_error + " 📁⚠️" if self._retry_error else "") or download_status or {
            GuiState.COMPLETE: "Download complete 🎉💫 (state preview)",
            GuiState.FAILED: "Download failed 🚫🤕 (state preview)",
            GuiState.ABORTED: "Download aborted 🙄 (state preview)",
        }.get(state, ""))
        self.result_message.setVisible(state in {GuiState.COMPLETE, GuiState.FAILED, GuiState.ABORTED})
        if previous_state != state and state in {
            GuiState.DOWNLOADING, GuiState.COMPLETE, GuiState.FAILED, GuiState.ABORTED,
        }:
            # Collapse space left by configuration/telemetry without resizing on
            # every progress update or changing the user's chosen window width.
            self.centralWidget().layout().activate()
            self.resize(self.width(), self.sizeHint().height())


def enable_state_test_shortcuts(window: AiDMWindow) -> None:
    """Temporary opt-in development preview: F1 through F7 follow enum order."""
    for number, state in enumerate(list(GuiState)[:7], start=1):
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
