"""Inline intent/configuration and bounded worker regressions, all offline."""
import contextlib
import io
import os
import sys
import time
import unittest
from tempfile import TemporaryDirectory
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("GUI options require PySide6")

from aidm_gui import AiDMWindow, GuiState
from download_job import BulkMode, VideoQuality, YouTubeMode
from gui_quality import QualityProcess, quality_command
from inspection import InputKind, InspectionResult, MetadataStatus, classify_input
from stream_parser import StreamInput
import youtube


class GuiOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = TemporaryDirectory(prefix="aidm-test-settings-")
        self.addCleanup(directory.cleanup)
        settings = QSettings(f"{directory.name}/settings.ini", QSettings.Format.IniFormat)
        self.window = AiDMWindow(settings=settings)
        self.window._inspection_timer.setInterval(1)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.workers = []
        for target in ["urllib.request.urlopen", "subprocess.run", "subprocess.Popen"]:
            guard = patch(target, side_effect=AssertionError(f"Unexpected {target}"))
            guard.start()
            self.addCleanup(guard.stop)
        self.quality_patch = patch.object(QualityProcess, "start", lambda worker: self.workers.append(worker))
        self.quality_patch.start()
        self.addCleanup(self.quality_patch.stop)
        metadata = patch("gui_metadata.MetadataProcess.start")
        metadata.start()
        self.addCleanup(metadata.stop)

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def paste(self, kind=InputKind.YOUTUBE_SINGLE, text="https://youtu.be/abcdefghijk"):
        def classify(args):
            if kind in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST}:
                return classify_input(args)
            return InspectionResult(kind, list(args.urls),
                                    stream=StreamInput(args.urls[0], title=args.title),
                                    route_kind=InputKind.HLS if kind == InputKind.STREAM_INSPECTOR else None)
        with patch("aidm_gui.classify_input", side_effect=classify):
            self.window.input_field.setText(text)
            self.wait_for(lambda: self.window.inspection_result is not None)
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertFalse(self.window.download_button.isHidden())
        self.assertTrue(self.window.download_button.isEnabled())
        self.assertTrue(self.window.mode_options.isHidden())
        self.assertTrue(self.window.bulk_options.isHidden())
        self.assertTrue(self.window.quality_options.isHidden())

    def video(self):
        self.window.download_button.click()
        self.assertEqual(self.window.current_state, GuiState.NEEDS_OPTIONS)
        self.assertFalse(self.window.mode_options.isHidden())
        self.assertIsNone(self.window.mode_group.checkedButton())
        self.window.mode_buttons[YouTubeMode.VIDEO].click()
        self.assertEqual(self.window.active_status.text(), "Fetching available video qualities…")
        self.assertTrue(self.window.quality_options.isHidden())
        self.assertTrue(self.window.download_button.isHidden())
        return self.workers[-1]

    def test_single_video_intent_quality_and_no_execution(self):
        self.paste()
        self.assertEqual(self.workers, [])
        worker = self.video()
        # Late title completion must not reset the configuration phase.
        enriched = replace(self.window.inspection_result, title="Resolved title", metadata_status=MetadataStatus.AVAILABLE)
        self.window.finish_metadata(self.window._revision, enriched)
        self.assertEqual(self.window.current_state, GuiState.NEEDS_OPTIONS)
        self.assertIn("available video qualities", self.window.active_status.text())
        worker.finished.emit(worker.revision, [1080, 720])
        self.assertFalse(self.window.quality_options.isHidden())
        self.assertEqual(self.window.quality_choice.currentText(), "Choose quality")
        self.assertIsNone(self.window.download_job)
        self.window.quality_choice.setCurrentIndex(1)
        self.assertEqual(self.window.download_job.video_quality, 1080)
        self.assertEqual(self.window.download_job.title, "Resolved title")
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.window.download_button.click()
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertIn("execution is not implemented", self.window.active_status.text())

    def test_audio_and_wav_never_discover(self):
        self.paste()
        self.window.download_button.click()
        for mode in (YouTubeMode.ORIGINAL_AUDIO, YouTubeMode.WAV):
            self.window.mode_buttons[mode].click()
            self.assertEqual(self.window.download_job.mode, mode)
            self.assertIsNone(self.window.download_job.video_quality)
            self.assertEqual(self.window.current_state, GuiState.READY)
            self.assertTrue(self.window.quality_options.isHidden())
        self.assertEqual(self.workers, [])

    def test_bulk_uses_only_first_normalized_url(self):
        self.paste(InputKind.YOUTUBE_BULK, "https://youtube.com/watch?v=abcdefghijk&list=unused https://youtu.be/lmnopqrstuv")
        self.assertEqual(self.window.item_count.text(), "2 videos")
        self.assertEqual(self.workers, [])
        worker = self.video()
        self.assertEqual(worker.url, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(len(self.workers), 1)
        worker.finished.emit(worker.revision, [720])
        self.window.quality_choice.setCurrentIndex(1)
        self.assertEqual(self.window.download_job.video_quality, 720)
        self.assertEqual(len(self.window.download_job.urls), 2)

    def test_playlist_intent_only_and_best_fallback(self):
        url = "https://youtube.com/playlist?list=PLexample"
        self.paste(InputKind.YOUTUBE_PLAYLIST, url)
        self.assertEqual(self.workers, [])
        self.window.download_button.click()
        self.assertTrue(self.window.mode_options.isHidden())
        self.assertEqual(self.workers[-1].url, url)
        self.assertEqual(self.window.active_status.text(), "Fetching available video qualities…")
        worker = self.workers[-1]
        worker.finished.emit(worker.revision, [])
        self.assertEqual(self.window.download_job.video_quality, VideoQuality.BEST)
        self.assertIsNone(self.window.download_job.mode)
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertIn("best available will be used", self.window.active_status.text())

    def test_direct_bulk_both_modes(self):
        self.paste(InputKind.DIRECT_BULK, "https://example.test/a.zip https://example.test/b.zip")
        self.window.download_button.click()
        self.assertFalse(self.window.bulk_options.isHidden())
        self.assertIsNone(self.window.bulk_group.checkedButton())
        for mode in BulkMode:
            self.window.bulk_buttons[mode].click()
            self.assertEqual(self.window.download_job.bulk_mode, mode)
            self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertEqual(self.workers, [])

    def test_simple_routes_have_no_options_or_execution(self):
        for kind in (InputKind.HLS, InputKind.DASH,
                     InputKind.GENERIC_YTDLP, InputKind.STREAM_INSPECTOR):
            self.paste(kind, f"https://example.test/{kind.name}")
            self.window.download_button.click()
            self.assertFalse(self.window._configuration_started)
            self.assertIsNotNone(self.window.download_job)
            self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertEqual(self.workers, [])

    def test_enter_mirrors_download_and_does_not_bypass_choices(self):
        self.paste()
        self.window.input_field.setFocus()
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)
        self.assertEqual(self.window.current_state, GuiState.NEEDS_OPTIONS)
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)
        self.assertIsNone(self.window.download_job)
        self.window.mode_buttons[YouTubeMode.WAV].click()
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)
        self.assertIn("execution is not implemented", self.window.active_status.text())

    def test_video_to_audio_invalidates_late_result(self):
        self.paste()
        worker = self.video()
        for mode in (YouTubeMode.ORIGINAL_AUDIO, YouTubeMode.WAV):
            self.window.mode_buttons[mode].click()
            self.assertTrue(worker.cancelled)
            worker.finished.emit(worker.revision, [2160])
            self.assertEqual(self.window.download_job.mode, mode)
            self.assertIsNone(self.window.download_job.video_quality)
            self.assertTrue(self.window.quality_options.isHidden())
            self.assertNotIn("available video qualities", self.window.active_status.text())

    def test_input_change_clear_and_preview_reset_discard_results(self):
        self.paste()
        worker = self.video()
        self.paste(InputKind.DIRECT_SINGLE, "https://example.test/a.zip")
        worker.finished.emit(worker.revision, [2160])
        self.assertEqual(self.window.download_job.kind, InputKind.DIRECT_SINGLE)
        self.assertEqual(self.window.quality_choice.count(), 0)
        self.paste()
        worker = self.video()
        self.window.preview_state(GuiState.EMPTY)
        worker.finished.emit(worker.revision, [720])
        self.assertEqual(self.window.current_state, GuiState.EMPTY)
        self.assertIsNone(self.window.download_job)
        self.window.input_field.clear()
        self.assertTrue(self.window.mode_options.isHidden())
        self.assertTrue(self.window.quality_options.isHidden())

    def test_real_quality_process_success_failure_timeout_and_close(self):
        self.quality_patch.stop()
        for script, expected in [("print('[1080,720]')", 2), ("print('bad')", 0)]:
            with patch("gui_quality.quality_command", return_value=[sys.executable, "-B", "-c", script]):
                self.window.input_field.clear()
                self.paste(InputKind.YOUTUBE_PLAYLIST, "https://youtube.com/playlist?list=PLtest")
                self.window.download_button.click()
                self.wait_for(lambda: not self.window._quality_pending)
                if expected:
                    self.assertEqual(self.window.quality_choice.count(), expected + 1)
                else:
                    self.assertEqual(self.window.download_job.video_quality, VideoQuality.BEST)
        with patch("gui_quality.quality_command", return_value=[sys.executable, "-B", "-c", "import time; time.sleep(5)"]):
            for closing in (False, True):
                self.window.input_field.clear()
                self.paste(InputKind.YOUTUBE_PLAYLIST, "https://youtube.com/playlist?list=PLtest")
                with patch.object(QualityProcess, "TIMEOUT_MS", 5000 if closing else 50):
                    self.window.download_button.click()
                if closing:
                    worker = self.window._quality_worker
                    self.wait_for(lambda: worker.process.state() == QProcess.ProcessState.Running)
                    self.window.close()
                    self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)
                else:
                    self.wait_for(lambda: not self.window._quality_pending)
                    self.assertEqual(self.window.download_job.video_quality, VideoQuality.BEST)

    def test_adapter_calls_shared_helper_and_uses_safe_inspection(self):
        command = quality_command("https://youtu.be/exact?token=a%2Fb")
        output = io.StringIO()
        with patch.object(youtube, "get_available_youtube_qualities", return_value=[1080]) as discover, \
                patch.object(sys, "argv", ["-c", command[-1]]), contextlib.redirect_stdout(output):
            exec(command[3], {})
        discover.assert_called_once_with(command[-1], inspection_only=True)
        self.assertEqual(output.getvalue().strip(), "[1080]")
        with patch.object(youtube.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 1
            self.assertEqual(youtube.get_available_youtube_qualities("url", inspection_only=True), [])
            args = run.call_args.args[0]
            for flag in ("--ignore-config", "--simulate", "--skip-download", "--no-cache-dir"):
                self.assertIn(flag, args)


if __name__ == "__main__":
    unittest.main()
