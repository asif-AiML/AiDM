"""Offline process-boundary tests, with local child fixtures for Qt lifecycle."""
import os
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

from aidm_gui import AiDMWindow, GuiState
from download_job import BulkMode, DownloadJob, YouTubeMode
from downloader import build_direct_command
from gui_execution import DirectDownloadProcess
from inspection import InputKind, InspectionResult
from stream_parser import StreamInput


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.calls = []
        self.current_state = self.ProcessState.NotRunning
        self.stdout = self.stderr = b""
        self.stop_on_terminate = True

    def setStandardInputFile(self, path):
        pass

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
            build.assert_called_once_with(job.urls[0], job.destination)
        self.assertEqual(worker.job, job)
        command = build_direct_command(job.urls[0], job.destination)
        self.assertEqual(worker.process.calls, [(command[0], command[1:])])

    def test_start_status_edit_lock_and_preview_cannot_interrupt(self):
        process = self.start()
        window = self.window
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        self.assertEqual(window.active_status.text(), "Starting aria2c…")
        self.assertFalse(window.input_field.isEnabled())
        self.assertFalse(window.browse_button.isEnabled())
        for control in (window.download_button, window.progress, window.abort_button):
            self.assertTrue(control.isHidden())
        window.preview_state(GuiState.EMPTY)
        window.update_configuration()
        with patch("aidm_gui.QFileDialog.getExistingDirectory") as picker:
            window.browse_destination()
            picker.assert_not_called()
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        process.begin()
        self.assertEqual(window.active_status.text(), "Downloading…")

    def test_exit_status_success_failure_and_crash(self):
        for code, status, expected, message in (
            (0, QProcess.ExitStatus.NormalExit, GuiState.COMPLETE, "Download complete"),
            (7, QProcess.ExitStatus.NormalExit, GuiState.FAILED, "Download failed"),
            (0, QProcess.ExitStatus.CrashExit, GuiState.FAILED, "Download failed"),
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
        self.assertEqual(self.window.result_message.text(), "Could not start aria2c.")
        # A duplicate terminal signal cannot replace the startup diagnosis.
        process.finish(1)
        self.assertEqual(self.window.result_message.text(), "Could not start aria2c.")

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
                         "Download folder is unavailable — choose another folder.")
        self.assertFalse(self.window.destination_section.isHidden())

    def test_all_other_routes_remain_deferred_including_inspector_direct(self):
        for kind in (InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK,
                     InputKind.YOUTUBE_PLAYLIST, InputKind.DIRECT_BULK,
                     InputKind.HLS, InputKind.DASH, InputKind.GENERIC_YTDLP,
                     InputKind.STREAM_INSPECTOR, InputKind.TORRENT):
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
            self.assertEqual(self.window.result_message.text(), "Could not start aria2c.")
        with patch("gui_execution.build_direct_command", return_value=[
            sys.executable, "-B", "-c", "import time; time.sleep(30)",
        ]):
            process = self.start()
            # Close before the started signal is delivered, too.
            self.window.close()
            self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)

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
