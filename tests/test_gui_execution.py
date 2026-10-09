"""Offline process-boundary tests, with local child fixtures for Qt lifecycle."""
import os
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QObject, QProcess, QSettings, QTimer, Qt, Signal
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("GUI execution checks require PySide6")

from aidm_gui import AiDMWindow, GuiState, render_status
from download_job import BulkMode, DownloadJob, YouTubeMode
from downloader import build_direct_command
from gui_execution import DirectDownloadProcess, DownloadProcess, ExecutionOutcome
from inspection import InputKind, InspectionResult
from stream_parser import StreamInput
from status_event import StatusEvent, StatusKind, StatusReason
from progress_event import ProgressEvent


class FakeProcess(QObject):
    started = Signal()
    finished = Signal(int, QProcess.ExitStatus)
    errorOccurred = Signal(QProcess.ProcessError)
    readyReadStandardOutput = Signal()
    readyReadStandardError = Signal()
    ProcessState = QProcess.ProcessState
    ProcessError = QProcess.ProcessError
    ExitStatus = QProcess.ExitStatus
    nullDevice = staticmethod(QProcess.nullDevice)
    UnixProcessFlag = QProcess.UnixProcessFlag

    def __init__(self, parent=None):
        super().__init__(parent)
        self.calls = []
        self.current_state = self.ProcessState.NotRunning
        self.stdout = self.stderr = b""
        self.stop_on_terminate = True

    def setStandardInputFile(self, path):
        pass

    def setUnixProcessParameters(self, flags):
        self.unix_flags = flags

    def processId(self):
        return 0  # Fake adapters must never signal a real OS process group.

    def waitForStarted(self, timeout):
        self.begin()
        return True

    def start(self, program, arguments):
        self.calls.append((program, arguments))
        self.current_state = self.ProcessState.Starting

    def state(self):
        return self.current_state

    def begin(self):
        self.current_state = self.ProcessState.Running
        self.started.emit()

    def finish(self, code=0, status=QProcess.ExitStatus.NormalExit):
        self.current_state = self.ProcessState.NotRunning
        self.finished.emit(code, status)

    def readAllStandardOutput(self):
        value, self.stdout = self.stdout, b""
        return value

    def readAllStandardError(self):
        value, self.stderr = self.stderr, b""
        return value

    def terminate(self):
        self.calls.append("terminate")
        if self.stop_on_terminate:
            self.finish(15)

    def kill(self):
        self.calls.append("kill")
        self.finish(9, self.ExitStatus.CrashExit)

    def waitForFinished(self, timeout):
        self.calls.append(("wait", timeout))
        return self.current_state == self.ProcessState.NotRunning


class GuiExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = TemporaryDirectory(prefix="aidm-execution-test-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        settings = QSettings(str(self.directory / "settings.ini"), QSettings.Format.IniFormat)
        settings.setValue("downloads/destination", str(self.directory))
        self.window = AiDMWindow(settings=settings)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.process_patch = patch("gui_execution.QProcess", FakeProcess)
        self.process_patch.start()
        self.addCleanup(self.process_patch.stop)
        for target in ("urllib.request.urlopen", "subprocess.run", "subprocess.Popen",
                       "gui_quality.QualityProcess.start", "gui_metadata.MetadataProcess.start"):
            guard = patch(target, side_effect=AssertionError(f"Unexpected {target}"))
            guard.start()
            self.addCleanup(guard.stop)

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def inspect(self, kind=InputKind.DIRECT_SINGLE, route=None):
        window = self.window
        window.input_field.setText("https://example.test/file.zip?token=a%2Fb&x=1")
        window._inspection_timer.stop()
        window._pending = None
        urls = list(window.input_result.args.urls)
        if kind in {InputKind.DIRECT_BULK, InputKind.YOUTUBE_BULK}:
            urls.append("https://example.test/second")
        stream = StreamInput(urls[0], title="Inspector title") if route else None
        window.finish_inspection(window._revision,
                                 InspectionResult(kind, urls, stream=stream, route_kind=route), "")
        window._metadata_timer.stop()

    def start(self):
        self.inspect()
        self.window.download_button.click()
        return self.window._download_process.process

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def start_with_events(self):
        self.inspect()
        events = []
        sequence = []

        def create(job, parent):
            worker = DirectDownloadProcess(job, parent)
            worker.status_event.connect(events.append)
            worker.status_event.connect(lambda event: sequence.append(event.kind))
            worker.finished.connect(lambda success: sequence.append(("finished", success)))
            return worker

        with patch("aidm_gui.create_download_process", side_effect=create):
            self.window.on_download_intent()
        return self.window._download_process.process, events, sequence

    def test_successful_semantic_event_order_and_single_completion_presentation(self):
        process, events, sequence = self.start_with_events()
        self.assertEqual(events, [StatusEvent(StatusKind.STARTING_ENGINE, "aria2c")])
        self.assertEqual(self.window.active_status.text(), "Starting aria2c… ⚙️")
        self.window.on_download_intent()  # No duplicate launch/status.
        process.begin()
        self.assertEqual(self.window.active_status.text(), "Downloading… ⬇️")
        self.assertTrue(self.window.result_message.isHidden())
        process.finish()
        self.assertEqual(sequence, [StatusKind.STARTING_ENGINE, StatusKind.DOWNLOADING,
                                    StatusKind.COMPLETE, ("finished", ExecutionOutcome.COMPLETE)])
        self.assertTrue(all(isinstance(event, StatusEvent) and event.engine == "aria2c" for event in events))
        self.assertEqual(self.window._download_event, events[-1])
        self.assertEqual(self.window.result_message.text(), "Download complete 🎉💫")
        self.assertFalse(self.window.result_message.isHidden())
        self.assertTrue(self.window.active_status.isHidden())
        process.finish()  # A repeated Qt terminal notification is ignored.
        self.assertEqual(len(events), 3)

    def test_failure_events_and_start_failure_reason(self):
        for failed_start in (False, True):
            self.window.input_field.clear()
            process, events, sequence = self.start_with_events()
            if failed_start:
                process.current_state = QProcess.ProcessState.NotRunning
                process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
                expected = [StatusKind.STARTING_ENGINE, StatusKind.FAILED, ("finished", ExecutionOutcome.FAILED)]
                reason = StatusReason.START_FAILED
                message = "Could not start aria2c. ⚠️"
            else:
                process.begin()
                process.stderr = b"raw diagnostic not part of the event"
                process.finish(7)
                expected = [StatusKind.STARTING_ENGINE, StatusKind.DOWNLOADING,
                            StatusKind.FAILED, ("finished", ExecutionOutcome.FAILED)]
                reason = None
                message = "Download failed 🚫🤕"
                self.assertIn(b"raw diagnostic", self.window._download_process.stderr_tail)
            self.assertEqual(sequence, expected)
            self.assertEqual(events[-1], StatusEvent(StatusKind.FAILED, "aria2c", reason))
            self.assertEqual(self.window.current_state, GuiState.FAILED)
            self.assertEqual(self.window.result_message.text(), message)
            self.assertTrue(self.window.active_status.isHidden())

    def test_status_presentation_does_not_drive_gui_state(self):
        with patch("aidm_gui.render_status", return_value="Different frontend wording"):
            process = self.start()
            self.assertEqual(self.window.active_status.text(), "Different frontend wording")
            process.begin()
            self.assertEqual(self.window.active_status.text(), "Different frontend wording")
            worker = self.window._download_process
            # Even terminal activity alone cannot change structural GuiState.
            worker.status_event.emit(StatusEvent(StatusKind.COMPLETE, "aria2c"))
            self.assertEqual(self.window.active_status.text(), "Different frontend wording")
            self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
            process.finish()
            self.assertEqual(self.window.current_state, GuiState.COMPLETE)
            self.assertEqual(self.window.result_message.text(), "Different frontend wording")
        self.window.input_field.clear()
        self.assertIsNone(self.window._download_event)
        self.assertEqual(self.window.current_state, GuiState.EMPTY)

    def test_renderer_owns_execution_language(self):
        self.assertEqual(render_status(StatusEvent(StatusKind.STARTING_ENGINE, "aria2c")), "Starting aria2c… ⚙️")
        self.assertEqual(render_status(StatusEvent(StatusKind.DOWNLOADING)), "Downloading… ⬇️")
        self.assertEqual(render_status(StatusEvent(StatusKind.COMPLETE)), "Download complete 🎉💫")
        self.assertEqual(render_status(StatusEvent(StatusKind.FAILED)), "Download failed 🚫🤕")
        self.assertEqual(render_status(StatusEvent(StatusKind.FAILED, "aria2c", StatusReason.START_FAILED)),
                         "Could not start aria2c. ⚠️")

    def test_friendly_inspection_and_prominent_terminal_outcomes(self):
        window = self.window
        window.input_field.setText("https://example.test/file.zip")
        window._inspection_timer.stop()
        self.assertEqual(window.active_status.text(), "Inspecting… 👀")
        for outcome, message in (("complete", "Download complete 🎉💫"),
                                 ("failed", "Download failed 🚫🤕"),
                                 ("aborted", "Download aborted 🙄")):
            window.input_field.clear()
            process = self.start()
            if outcome == "aborted":
                process.stop_on_terminate = False
                window.abort_button.click()
                self.assertEqual(window.active_status.text(), "Aborting… 🛑")
                process.finish(15)
            else:
                process.finish(0 if outcome == "complete" else 7)
            self.app.processEvents()
            self.assertEqual(window.result_message.text(), message)
            self.assertEqual(window.result_message.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(window.result_message.alignment(), Qt.AlignmentFlag.AlignCenter)
            self.assertTrue(window.result_message.font().bold())
            self.assertGreater(window.result_message.font().pointSize(), window.active_status.font().pointSize())
            self.assertGreaterEqual(window.result_message.contentsMargins().top(), 16)
            self.assertEqual(window.retry_button.isHidden(), outcome == "complete")
            if outcome != "complete":
                self.assertGreater(window.retry_button.y(), window.result_message.y())
                self.assertLessEqual(abs(window.retry_button.geometry().center().x()
                                         - window.result_message.geometry().center().x()), 1)
            self.assertTrue(window.abort_button.isHidden())
            self.assertEqual(window.classification.text(), "● Direct download")
            self.assertEqual(window.retry_button.text(), "Retry")

    def test_close_does_not_publish_a_spurious_completion(self):
        process, events, sequence = self.start_with_events()
        process.begin()
        self.window.close()
        self.assertEqual(sequence, [StatusKind.STARTING_ENGINE, StatusKind.DOWNLOADING])
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)

    def test_chunked_progress_signal_and_gui_rendering(self):
        process = self.start()
        worker = self.window._download_process
        events = []
        worker.progress_event.connect(events.append)
        self.assertIsNone(self.window._progress_event)
        self.assertTrue(self.window.progress.isHidden())
        self.assertTrue(self.window.statistics.isHidden())
        process.begin()
        process.stdout = b"warning 90%\n[#abcdef 812000000B/2100000000B(38.6%) CN:1 DL:480"
        process.readyReadStandardOutput.emit()
        self.assertEqual(events, [])
        process.stdout = b"0000B ETA:4m37s]\r\n"
        process.readyReadStandardOutput.emit()
        self.assertEqual(events, [ProgressEvent(38.6, 812000000, 2100000000, 4800000, 277)])
        self.assertFalse(self.window.progress.isHidden())
        self.assertEqual(self.window.progress.value(), 38)  # Deliberate truncation.
        self.assertEqual(self.window._progress_event.percent, 38.6)
        self.assertEqual(self.window.statistics.text(), "4.8 MB/s • 812 MB / 2.1 GB • ETA 04:37")
        self.assertEqual(self.window.active_status.text(), "Downloading… ⬇️")
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        process.stdout = b"[#abcdef 900000000B/2100000000B(42%) CN:1 DL:5000000B]\n"
        process.readyReadStandardOutput.emit()
        self.assertEqual([event.percent for event in events], [38.6, 42])
        self.assertNotIn("ETA", self.window.statistics.text())

    def test_unknown_percent_partial_fields_and_no_state_changes(self):
        self.start()
        worker = self.window._download_process
        worker.progress_event.emit(ProgressEvent(10, 100, 1000, 20, 45))
        worker.progress_event.emit(ProgressEvent(downloaded_bytes=150, speed_bytes_per_second=20))
        self.assertTrue(self.window.progress.isHidden())
        self.assertEqual(self.window.statistics.text(), "20 B/s • 150 B downloaded")
        worker.progress_event.emit(ProgressEvent(eta_seconds=37))
        self.assertEqual(self.window.statistics.text(), "ETA 00:37")
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)

    def test_final_tail_and_terminal_states_never_manufacture_100(self):
        for code in (0, 7):
            self.window.input_field.clear()
            process = self.start()
            process.stdout = b"[#abcdef 933888B/1048576B(89%) CN:1 DL:325283B]"
            process.finish(code)
            self.assertEqual(self.window.current_state, GuiState.COMPLETE if code == 0 else GuiState.FAILED)
            self.assertEqual(self.window._progress_event.percent, 89)
            self.assertEqual(self.window.progress.value(), 89)
            self.assertTrue(self.window.progress.isHidden())
            self.assertTrue(self.window.statistics.isHidden())
            self.assertFalse(self.window.result_message.isHidden())
            self.assertTrue(self.window.active_status.isHidden())
            self.assertFalse(self.window.input_field.isHidden())
        self.window.input_field.clear()
        process = self.start()
        process.finish()
        self.assertIsNone(self.window._progress_event)
        self.assertTrue(self.window.progress.isHidden())
        self.assertTrue(self.window.statistics.isHidden())

    def test_reset_and_late_telemetry_from_previous_job(self):
        process = self.start()
        old = self.window._download_process
        old.progress_event.emit(ProgressEvent(50, 500, 1000))
        process.finish()
        self.window.input_field.clear()
        self.assertIsNone(self.window._progress_event)
        self.assertEqual(self.window.statistics.text(), "")
        self.assertTrue(self.window.progress.isHidden())
        self.start()
        old.progress_event.emit(ProgressEvent(99, 990, 1000))
        self.assertIsNone(self.window._progress_event)
        self.assertTrue(self.window.progress.isHidden())

    def test_passive_job_and_exact_shared_command_started_once(self):
        self.inspect()
        job = self.window.download_job
        self.assertEqual(job.kind, InputKind.DIRECT_SINGLE)
        self.assertIsNone(job.title)
        self.assertEqual(job.destination, str(self.directory))
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertIsNone(self.window._download_process)
        with patch("gui_execution.build_direct_command", wraps=build_direct_command) as build:
            self.window.on_download_intent()
            worker = self.window._download_process
            self.window.on_download_intent()
            self.window.download_button.click()
            worker.start()
            build.assert_called_once_with(job.urls[0], job.destination, telemetry=True)
        self.assertEqual(worker.job, job)
        command = build_direct_command(job.urls[0], job.destination, telemetry=True)
        self.assertEqual(worker.process.calls, [(command[0], command[1:])])

    def test_start_status_edit_lock_and_preview_cannot_interrupt(self):
        process = self.start()
        window = self.window
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        self.assertEqual(window.active_status.text(), "Starting aria2c… ⚙️")
        self.assertFalse(window.input_field.isEnabled())
        self.assertFalse(window.browse_button.isEnabled())
        for control in (window.download_button, window.progress, window.retry_button):
            self.assertTrue(control.isHidden())
        window.preview_state(GuiState.EMPTY)
        window.update_configuration()
        with patch("aidm_gui.QFileDialog.getExistingDirectory") as picker:
            window.browse_destination()
            picker.assert_not_called()
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        process.begin()
        self.assertEqual(window.active_status.text(), "Downloading… ⬇️")

    def test_active_layout_hides_configuration_and_preserves_identity_and_input(self):
        self.inspect()
        window = self.window
        text = window.input_field.text()
        job = window.download_job
        ready_height = window.height()
        window.on_download_intent()
        self.app.processEvents()
        for control in (window.input_field, window.destination_section,
                        window.download_button, window.mode_options, window.bulk_options,
                        window.quality_options, window.retry_button,
                        window.progress, window.statistics, window.media_title):
            self.assertTrue(control.isHidden())
        self.assertTrue(window.abort_button.isEnabled())
        self.assertFalse(window.abort_button.isHidden())
        self.assertFalse(window.browse_button.isVisible())
        self.assertFalse(window.classification.isHidden())
        self.assertEqual(window.classification.text(), "● Direct download")
        self.assertFalse(window.active_status.isHidden())
        self.assertEqual(window.input_field.text(), text)
        self.assertEqual(window._download_process.job, job)
        self.assertLess(window.height(), ready_height)
        self.assertEqual(window.width(), 480)
        window._download_process.process.finish()
        self.assertFalse(window.input_field.isHidden())
        self.assertEqual(window.input_field.text(), text)

    def test_active_layout_known_title_and_statistics_only(self):
        process = self.start()
        window = self.window
        # Presentation fixture only: no new route execution or title discovery.
        window.inspection_result = replace(window.inspection_result, title="Known media title")
        process.begin()
        window._download_process.progress_event.emit(
            ProgressEvent(downloaded_bytes=124900000, speed_bytes_per_second=181200)
        )
        self.app.processEvents()
        self.assertFalse(window.media_title.isHidden())
        self.assertEqual(window.media_title.text(), "Known media title")
        self.assertTrue(window.progress.isHidden())
        self.assertFalse(window.statistics.isHidden())
        self.assertEqual(window.statistics.text(), "181.2 KB/s • 124.9 MB downloaded")
        self.assertFalse(window.active_status.isHidden())
        self.assertEqual(window.active_status.text(), "Downloading… ⬇️")
        self.assertLess(window.classification.y(), window.media_title.y())
        self.assertLess(window.media_title.y(), window.statistics.y())
        self.assertLess(window.statistics.y(), window.active_status.y())

    def test_runtime_filename_before_and_after_progress_with_deduplication(self):
        for progress_first in (False, True):
            self.window.input_field.clear()
            process = self.start()
            window = self.window
            worker = window._download_process
            names = []
            worker.filename_resolved.connect(names.append)
            self.assertIsNone(window._runtime_filename)
            self.assertIsNone(window.inspection_result.title)
            self.assertTrue(window.media_title.isHidden())
            process.begin()
            if progress_first:
                worker.progress_event.emit(ProgressEvent(30))
            process.stdout = b"FI"
            process.readyReadStandardOutput.emit()
            self.assertEqual(names, [])
            process.stdout = "LE: /tmp/My 日本語 File (2026).zip\r\n".encode()
            process.readyReadStandardOutput.emit()
            self.assertEqual(names, ["My 日本語 File (2026).zip"])
            self.assertEqual(window.media_title.text(), names[0])
            self.assertFalse(window.media_title.isHidden())
            self.assertEqual(window.media_title.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(window.active_status.text(), "Downloading… ⬇️")
            self.assertIsNone(window.inspection_result.title)
            self.assertIsNone(worker.job.title)
            process.stdout = "FILE: /tmp/My 日本語 File (2026).zip\nFILE: /tmp/<b>changed.zip\n".encode()
            process.readyReadStandardOutput.emit()
            self.assertEqual(names, ["My 日本語 File (2026).zip", "<b>changed.zip"])
            worker.progress_event.emit(ProgressEvent(40))
            self.assertEqual(window.media_title.text(), "<b>changed.zip")
            # Genuine backend/inspection title has precedence over filename.
            window.inspection_result = replace(window.inspection_result, title="Known title")
            window.set_state(GuiState.DOWNLOADING)
            self.assertEqual(window.media_title.text(), "Known title")
            process.finish()

    def test_runtime_filename_reset_and_stale_signal_guard(self):
        process = self.start()
        window = self.window
        old = window._download_process
        process.stdout = b"FILE: /tmp/first.zip\n"
        process.readyReadStandardOutput.emit()
        process.finish()
        self.assertEqual(window._runtime_filename, "first.zip")
        self.assertFalse(window.media_title.isHidden())
        self.assertEqual(window.media_title.text(), "first.zip")
        window.preview_state(GuiState.EMPTY)
        self.assertIsNone(window._runtime_filename)
        self.start()
        old.filename_resolved.emit("stale.zip")
        self.assertIsNone(window._runtime_filename)
        self.assertTrue(window.media_title.isHidden())
        current = window._download_process
        current.filename_resolved.emit("current.zip")
        current.process.finish()
        # New execution resets identity even with the same input.
        window.set_state(GuiState.READY)
        window.on_download_intent()
        self.assertIsNone(window._runtime_filename)
        self.assertTrue(window.media_title.isHidden())
        window._download_process.filename_resolved.emit("next.zip")
        window._download_process.process.finish()
        window.input_field.clear()
        self.assertIsNone(window._runtime_filename)
        self.assertEqual(window.current_state, GuiState.EMPTY)

    def test_terminal_identity_retention_style_and_retry_reset(self):
        for outcome in ("complete", "failed", "aborted"):
            self.window.input_field.clear()
            process = self.start()
            window = self.window
            active_font = window.media_title.font()
            active_alignment = window.media_title.alignment()
            worker = window._download_process
            worker.filename_resolved.emit("actual-file-name.ext")
            self.assertFalse(window.media_title.isHidden())
            if outcome == "aborted":
                window.abort_button.click()
            else:
                process.finish(0 if outcome == "complete" else 7)
            self.app.processEvents()
            self.assertFalse(window.media_title.isHidden())
            self.assertEqual(window.media_title.text(), "actual-file-name.ext")
            self.assertTrue(window.media_title.font().bold())
            self.assertEqual(window.media_title.alignment(), Qt.AlignmentFlag.AlignCenter)
            self.assertEqual(window.media_title.textFormat(), Qt.TextFormat.PlainText)
            self.assertTrue(window.media_title.wordWrap())
            self.assertGreater(window.result_message.font().pointSize(), window.media_title.font().pointSize())
            self.assertLess(window.classification.y(), window.media_title.y())
            self.assertLess(window.media_title.y(), window.result_message.y())
            self.assertEqual(window.retry_button.isHidden(), outcome == "complete")
            if outcome != "complete":
                window.retry_button.click()
                self.assertTrue(window.media_title.isHidden())
                self.assertEqual(window.media_title.font(), active_font)
                self.assertEqual(window.media_title.alignment(), active_alignment)
                window._download_process.process.finish()

    def test_terminal_identity_is_route_neutral_and_wraps_long_names(self):
        self.inspect(InputKind.YOUTUBE_SINGLE)
        window = self.window
        # Presentation fixture only: no YouTube execution/metadata work.
        window._runtime_filename = "runtime-name.ext"
        title = "Very.Long.Movie.Release.Name.2018.480p.WEBRip.x264.AAC.mkv" * 3
        window.inspection_result = replace(window.inspection_result, title=title)
        for state in (GuiState.COMPLETE, GuiState.FAILED, GuiState.ABORTED):
            window.resize(480, window.height())
            window.set_state(state)
            self.app.processEvents()
            self.assertEqual(window.media_title.full_title, title)
            self.assertEqual(window.media_title.toolTip(), title)
            self.assertIn("…", window.media_title.text())
            self.assertLessEqual(window.media_title.fontMetrics().horizontalAdvance(window.media_title.text()),
                                 window.media_title.width())
            self.assertLessEqual(window.width(), 480)
            self.assertLessEqual(window.media_title.width(), window.width() - 56)
        window.inspection_result = replace(window.inspection_result, title=None)
        window.set_state(GuiState.COMPLETE)
        self.assertEqual(window.media_title.text(), "runtime-name.ext")
        window._runtime_filename = None
        for state in (GuiState.COMPLETE, GuiState.FAILED, GuiState.ABORTED):
            window.set_state(state)
            self.assertTrue(window.media_title.isHidden())
            self.assertEqual(window.media_title.text(), "")

    def test_exit_status_success_failure_and_crash(self):
        for code, status, expected, message in (
            (0, QProcess.ExitStatus.NormalExit, GuiState.COMPLETE, "Download complete 🎉💫"),
            (7, QProcess.ExitStatus.NormalExit, GuiState.FAILED, "Download failed 🚫🤕"),
            (0, QProcess.ExitStatus.CrashExit, GuiState.FAILED, "Download failed 🚫🤕"),
        ):
            process = self.start()
            process.begin()
            process.finish(code, status)
            self.assertEqual(self.window.current_state, expected)
            self.assertEqual(self.window.result_message.text(), message)
            self.assertTrue(self.window.input_field.isEnabled())
            self.window.input_field.clear()
            self.assertEqual(self.window.current_state, GuiState.EMPTY)
            self.assertTrue(self.window.result_message.isHidden())

    def test_failed_to_start(self):
        process = self.start()
        process.current_state = QProcess.ProcessState.NotRunning
        process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertEqual(self.window.result_message.text(), "Could not start aria2c. ⚠️")
        # A duplicate terminal signal cannot replace the startup diagnosis.
        process.finish(1)
        self.assertEqual(self.window.result_message.text(), "Could not start aria2c. ⚠️")

    def test_disappeared_destination_never_launches_or_redirects(self):
        folder = self.directory / "removed"
        folder.mkdir()
        self.window.destination = str(folder)
        self.inspect()
        folder.rmdir()
        self.window.on_download_intent()
        self.assertIsNone(self.window._download_process)
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertEqual(self.window.destination, str(folder))
        self.assertEqual(self.window.active_status.text(),
                         "Download folder is unavailable — choose another folder. 📁⚠️")
        self.assertFalse(self.window.destination_section.isHidden())

    def test_unimplemented_routes_remain_deferred(self):
        for kind in (InputKind.HLS, InputKind.DASH, InputKind.GENERIC_YTDLP,
                     InputKind.TORRENT):
            self.window.input_field.clear()
            self.inspect(kind, InputKind.DIRECT_SINGLE if kind == InputKind.STREAM_INSPECTOR else None)
            if kind in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK}:
                self.window.on_download_intent()
                self.window.mode_buttons[YouTubeMode.WAV].click()
            elif kind == InputKind.DIRECT_BULK:
                self.window.on_download_intent()
                self.window.bulk_buttons[BulkMode.SEQUENTIAL].click()
            elif kind == InputKind.YOUTUBE_PLAYLIST:
                with patch("gui_quality.QualityProcess.start"):
                    self.window.on_download_intent()
                self.window.finish_quality(self.window._quality_generation, [1080])
                self.window.quality_choice.setCurrentIndex(1)
            self.window.on_download_intent()
            self.assertIsNone(self.window._download_process, kind)
            if kind != InputKind.TORRENT:
                self.assertIn("execution is not implemented", self.window.active_status.text())

    def test_adapter_rejects_other_kinds_even_with_direct_underlying_route(self):
        for kind, route in ((InputKind.HLS, None), (InputKind.STREAM_INSPECTOR, InputKind.DIRECT_SINGLE)):
            job = DownloadJob(kind, ("https://example.test/a",), str(self.directory), route_kind=route)
            with self.assertRaisesRegex(ValueError, "DIRECT_SINGLE only"):
                DirectDownloadProcess(job)

    def test_enter_starts_same_direct_job(self):
        self.inspect()
        self.window.input_field.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        self.assertEqual(len(self.window._download_process.process.calls), 1)

    def test_output_drained_with_bounded_diagnostics(self):
        process = self.start()
        process.stdout = b"unparsed output" * 10000
        process.stderr = b"e" * 100000 + b"tail"
        process.readyReadStandardOutput.emit()
        self.assertEqual(process.stdout, b"")
        self.assertEqual(process.stderr, b"")
        worker = self.window._download_process
        self.assertEqual(len(worker.stderr_tail), worker.MAX_STDERR_BYTES)
        self.assertTrue(worker.stderr_tail.endswith(b"tail"))
        self.assertNotIn("tail", self.window.active_status.text())

    def test_close_terminates_then_kills_only_if_needed(self):
        process = self.start()
        process.stop_on_terminate = False
        self.window.close()
        self.assertEqual(process.calls[-4:], ["terminate", ("wait", 1000), "kill", ("wait", 1000)])
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)
        self.assertFalse(self.window.download_active())

    def test_real_start_failure_and_immediate_close(self):
        self.process_patch.stop()
        with patch("gui_execution.build_direct_command", return_value=[str(self.directory / "missing-aria2c")]):
            self.start()
            self.wait_for(lambda: self.window.current_state == GuiState.FAILED)
            self.assertEqual(self.window.result_message.text(), "Could not start aria2c. ⚠️")
        with patch("gui_execution.build_direct_command", return_value=[
            sys.executable, "-B", "-c", "import time; time.sleep(30)",
        ]):
            process = self.start()
            # Close before the started signal is delivered, too.
            self.window.close()
            self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)

    def test_abort_async_once_then_retry_same_snapshot_and_stale_signals(self):
        process = self.start()
        window = self.window
        old = window._download_process
        job = old.job
        process.begin()
        old.progress_event.emit(ProgressEvent(63, 630, 1000))
        old.filename_resolved.emit("partial.zip")
        process.stop_on_terminate = False
        self.assertTrue(window.abort_button.isVisible())
        self.assertTrue(window.retry_button.isHidden())
        window.abort_button.click()
        window.abort_button.click()
        window.abort_download()
        self.assertEqual(process.calls.count("terminate"), 1)
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "wait" for call in process.calls))
        self.assertEqual(window.active_status.text(), "Aborting… 🛑")
        self.assertFalse(window.abort_button.isEnabled())
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        old.progress_event.emit(ProgressEvent(70))
        old.filename_resolved.emit("late.zip")
        self.assertEqual(window._progress_event.percent, 63)
        self.assertEqual(window._runtime_filename, "partial.zip")
        process.stdout = b"[#abcdef 700B/1000B(70%) CN:1]\nFILE: /tmp/late.zip\n"
        process.readyReadStandardOutput.emit()
        self.assertEqual(window._progress_event.percent, 63)
        process.finish(9, QProcess.ExitStatus.CrashExit)
        self.assertEqual(window.current_state, GuiState.ABORTED)
        self.assertEqual(window.result_message.text(), "Download aborted 🙄")
        self.assertTrue(window.abort_button.isHidden())
        self.assertTrue(window.progress.isHidden())
        self.assertTrue(window.retry_button.isVisible())
        self.assertFalse(old._abort_timer.isActive())
        old.escalate_abort()
        self.assertNotIn("kill", process.calls)
        # Retry cannot rebuild from mutable configuration or reclassify input.
        window.destination = "/not-the-job-folder"
        window.download_job = None
        with patch("aidm_gui.build_download_job", side_effect=AssertionError("Retry rebuilt job")), \
             patch("aidm_gui.classify_input", side_effect=AssertionError("Retry classified")):
            window.retry_button.click()
        new = window._download_process
        self.assertIsNot(new, old)
        self.assertIs(new.job, job)
        self.assertEqual(new.job.destination, str(self.directory))
        self.assertIn("--continue=true", new.process.calls[0][1])
        self.assertIn("--dir=" + job.destination, new.process.calls[0][1])
        self.assertIsNone(window._progress_event)
        self.assertIsNone(window._runtime_filename)
        self.assertEqual(window._download_event.kind, StatusKind.STARTING_ENGINE)
        self.assertTrue(window.result_message.isHidden())
        old.status_event.emit(StatusEvent(StatusKind.FAILED))
        old.progress_event.emit(ProgressEvent(99))
        old.filename_resolved.emit("stale.zip")
        old.finished.emit(ExecutionOutcome.FAILED)
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        self.assertEqual(window._download_event.kind, StatusKind.STARTING_ENGINE)
        self.assertIsNone(window._progress_event)
        self.assertIsNone(window._runtime_filename)
        new.progress_event.emit(ProgressEvent(64))
        self.assertEqual(window.progress.value(), 64)

    def test_abort_grace_timer_and_finish_races(self):
        process = self.start()
        process.begin()
        worker = self.window._download_process
        process.stop_on_terminate = False
        worker._abort_timer.setInterval(20)
        self.window.abort_button.click()
        self.wait_for(lambda: self.window.current_state == GuiState.ABORTED)
        self.assertEqual(process.calls[-2:], ["terminate", "kill"])
        self.assertFalse(worker._abort_timer.isActive())
        # User abort wins even if a normal zero exit races the request.
        self.window.retry_button.click()
        worker = self.window._download_process
        worker.process.stop_on_terminate = False
        worker.abort()
        worker.process.finish(0)
        self.assertEqual(self.window.current_state, GuiState.ABORTED)
        worker.escalate_abort()
        self.assertNotIn("kill", worker.process.calls)

    def test_abort_while_starting_and_failed_to_start_stays_failed(self):
        process = self.start()
        process.stop_on_terminate = False
        worker = self.window._download_process
        worker.abort()
        process.begin()
        self.assertEqual(self.window.active_status.text(), "Aborting… 🛑")
        self.assertEqual(process.calls.count("terminate"), 2)
        process.current_state = QProcess.ProcessState.NotRunning
        process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertEqual(self.window.result_message.text(), "Could not start aria2c. ⚠️")
        self.assertFalse(worker._abort_timer.isActive())
        self.assertTrue(self.window.retry_button.isVisible())

    def test_failure_retry_success_and_partial_files_untouched(self):
        partial = self.directory / "partial.zip"
        control = self.directory / "partial.zip.aria2"
        partial.write_bytes(b"partial fixture")
        control.write_bytes(b"resume fixture")
        process = self.start()
        process.finish(7)
        self.assertTrue(self.window.retry_button.isVisible())
        self.window.retry_button.click()
        self.window.abort_button.click()
        self.assertEqual(self.window.current_state, GuiState.ABORTED)
        self.window.retry_button.click()
        self.window._download_process.process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.assertTrue(self.window.retry_button.isHidden())
        self.assertTrue(self.window.abort_button.isHidden())
        self.assertEqual(partial.read_bytes(), b"partial fixture")
        self.assertEqual(control.read_bytes(), b"resume fixture")

    def test_retry_destination_missing_and_input_edit_discards_retry(self):
        folder = self.directory / "destination"
        folder.mkdir()
        self.window.destination = str(folder)
        process = self.start()
        process.finish(7)
        old = self.window._download_process
        folder.rmdir()
        with patch("aidm_gui.create_download_process") as factory:
            self.window.retry_button.click()
            factory.assert_not_called()
        self.assertIs(self.window._download_process, old)
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertEqual(self.window.result_message.text(),
                         "Download folder is unavailable — choose another folder. 📁⚠️")
        self.window.input_field.clear()
        self.assertIsNone(self.window._retry_job)
        self.assertTrue(self.window.retry_button.isHidden())

    def test_close_during_abort_cancels_escalation_and_reaps(self):
        process = self.start()
        process.stop_on_terminate = False
        worker = self.window._download_process
        outcomes = []
        worker.finished.connect(outcomes.append)
        worker.abort()
        self.window.close()
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)
        self.assertFalse(worker._abort_timer.isActive())
        self.assertEqual(outcomes, [])
        calls = list(process.calls)
        worker.escalate_abort()
        self.assertEqual(process.calls, calls)

    def test_route_neutral_adapter_contract_and_capabilities(self):
        class FixtureProcess(DownloadProcess):
            engine = "fixture"

            def build_command(self):
                return ["fixture-engine"]

        attempts = []

        def factory(job, parent):
            adapter = FixtureProcess(job, parent)
            attempts.append(adapter)
            return adapter

        self.inspect(InputKind.HLS)
        with patch("aidm_gui.create_download_process", side_effect=factory):
            self.window.on_download_intent()
            worker = attempts[0]
            worker.process.begin()
            self.assertEqual(self.window.active_status.text(), "Downloading… ⬇️")
            worker.progress_event.emit(ProgressEvent(23))
            self.assertEqual(self.window.progress.value(), 23)
            self.window.abort_button.click()
            self.assertEqual(self.window.current_state, GuiState.ABORTED)
            self.window.retry_button.click()
            self.assertEqual(len(attempts), 2)
            self.assertIs(attempts[0].job, attempts[1].job)
            self.assertIsNot(attempts[0], attempts[1])
            self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
            attempts[1].can_abort = False
            attempts[1].can_retry = False
            self.window._retry_job = None
            self.window.set_state(GuiState.DOWNLOADING)
            self.assertTrue(self.window.abort_button.isHidden())
            attempts[1].process.finish(7)
            self.assertTrue(self.window.retry_button.isHidden())

    def test_enter_never_aborts_or_retries(self):
        process = self.start()
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertNotIn("terminate", process.calls)
        process.finish(7)
        old = self.window._download_process
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertIs(self.window._download_process, old)

    def test_real_abort_is_responsive_and_kill_is_reaped(self):
        self.process_patch.stop()
        script = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',file=__import__('sys').stderr,flush=True); time.sleep(30)"
        ticks = []
        timer = QTimer(self.window)
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        with patch("gui_execution.build_direct_command", return_value=[sys.executable, "-B", "-c", script]):
            self.start()
            worker = self.window._download_process
            self.wait_for(lambda: b"ready" in worker.stderr_tail)
            worker._abort_timer.setInterval(150)
            timer.start()
            self.window.abort_button.click()
            self.wait_for(lambda: self.window.current_state == GuiState.ABORTED)
            self.assertGreater(len(ticks), 2)
            self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)

    def test_real_local_process_event_loop_and_close_cleanup(self):
        # Local Python fixtures only; no aria2c, network or media output.
        self.process_patch.stop()
        ticks = []
        timer = QTimer(self.window)
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start()
        with patch("gui_execution.build_direct_command", return_value=[
            sys.executable, "-B", "-c", "import time; time.sleep(.2)",
        ]):
            self.start()
            self.wait_for(lambda: self.window.current_state == GuiState.COMPLETE)
        self.assertGreater(len(ticks), 2)
        # Wait for SIGTERM handler installation before testing kill fallback.
        script = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',file=__import__('sys').stderr,flush=True); time.sleep(30)"
        with patch("gui_execution.build_direct_command", return_value=[sys.executable, "-B", "-c", script]):
            self.start()
            worker = self.window._download_process
            self.wait_for(lambda: b"ready" in worker.stderr_tail)
            self.window.close()
            self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)


if __name__ == "__main__":
    unittest.main()
