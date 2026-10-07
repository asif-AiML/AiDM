from dataclasses import replace
import json
import os
import sys
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("GUI metadata checks require PySide6")

from aidm_gui import AiDMWindow, GuiState, enable_state_test_shortcuts
from gui_metadata import MetadataProcess
from inspection import InputKind, InspectionResult, MetadataStatus
from stream_parser import StreamInput


class GuiMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.kind = InputKind.YOUTUBE_SINGLE
        self.command_count = 0
        self.delay = 0.08
        self.exit_code = 0
        self.body = None
        directory = TemporaryDirectory(prefix="aidm-test-settings-")
        self.addCleanup(directory.cleanup)
        settings = QSettings(f"{directory.name}/settings.ini", QSettings.Format.IniFormat)
        self.window = AiDMWindow(settings=settings)
        self.window._inspection_timer.setInterval(1)
        self.window._metadata_timer.setInterval(30)
        self.window.show()
        self.app.processEvents()
        for target in ["urllib.request.urlopen", "socket.socket.connect", "subprocess.run", "subprocess.Popen"]:
            guard = patch(target, side_effect=AssertionError(f"Unexpected {target}"))
            guard.start()
            self.addCleanup(guard.stop)
        # Real QProcess lifecycle, but only local Python fixtures are launched.
        command = patch("gui_metadata.build_metadata_command", side_effect=self.command)
        command.start()
        self.addCleanup(command.stop)
        classifier = patch("aidm_gui.classify_input", side_effect=self.classify)
        classifier.start()
        self.addCleanup(classifier.stop)

    def classify(self, args):
        return InspectionResult(self.kind, list(args.urls),
                                stream=StreamInput(args.urls[0], title=args.title))

    def command(self, result):
        self.command_count += 1
        data = self.body if self.body is not None else json.dumps({"title": result.urls[0], "item_count": 167})
        script = f"import time,sys; time.sleep({self.delay!r}); print({data!r}); sys.exit({self.exit_code!r})"
        return [sys.executable, "-B", "-c", script]

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def paste(self, text):
        self.window.input_field.setText(text)
        self.wait_for(lambda: self.window.inspection_result is not None)

    def resolved(self):
        self.wait_for(lambda: self.window.inspection_result.metadata_status != MetadataStatus.PENDING)

    def test_single_classification_precedes_title(self):
        self.paste("https://youtu.be/abcdefghijk")
        self.assertIn("YouTube video", self.window.classification.text())
        self.assertFalse(self.window.classification.isHidden())
        self.assertTrue(self.window.media_title.isHidden())
        self.assertEqual(self.command_count, 0)
        self.assertIn("Fetching", self.window.active_status.text())
        self.resolved()
        self.assertEqual(self.window.media_title.text(), "https://youtu.be/abcdefghijk")
        self.assertTrue(self.window.active_status.isHidden())
        self.assertFalse(self.window.download_button.isHidden())

    def test_playlist_title_and_count(self):
        self.kind = InputKind.YOUTUBE_PLAYLIST
        self.body = '{"title":"My Playlist","item_count":167}'
        self.paste("https://youtube.com/playlist?list=test")
        self.assertEqual(self.window.active_status.text(), "Inspecting playlist… 👀")
        self.resolved()
        self.assertEqual(self.window.job_title.full_title, "My Playlist")
        self.assertFalse(self.window.job_title.isHidden())
        self.assertEqual(self.window.item_count.text(), "167 videos")

    def test_local_metadata_and_hls_never_start_process(self):
        cases = [
            (InputKind.YOUTUBE_BULK, "https://youtu.be/a https://youtu.be/b", "", "2 videos"),
            (InputKind.DIRECT_BULK, "https://example.test/a.zip https://example.test/b.zip", "", "2 files"),
            (InputKind.DIRECT_SINGLE, "https://example.test/linuxmint.iso?token=secret", "", ""),
            (InputKind.STREAM_INSPECTOR, "--title 'Browser title' https://example.test/master.m3u8", "Browser title", ""),
            (InputKind.HLS, "https://example.test/master.m3u8", "", ""),
        ]
        for kind, text, title, count in cases:
            self.kind = kind
            self.paste(text)
            QTest.qWait(50)
            self.assertEqual(self.window.media_title.text(), title)
            self.assertEqual(self.window.item_count.text(), count)
        self.assertEqual(self.command_count, 0)

    def test_direct_single_has_only_classification_then_clears(self):
        self.kind = InputKind.DIRECT_SINGLE
        for url in ["https://example.test/vlc-3.0.24-win32.exe",
                    "https://cdn.example.test/long/opaque/file.zip?token=a%2Fb&signature=c%3Dd&expires=999999"]:
            with self.subTest(url=url):
                self.paste(url)
                QTest.qWait(50)
                self.assertEqual(self.window.classification.text(), "● Direct download")
                self.assertFalse(self.window.classification.isHidden())
                self.assertTrue(self.window.media_title.isHidden())
                self.assertEqual(self.window.media_title.text(), "")
                self.assertTrue(self.window.active_status.isHidden())
                self.assertEqual(self.window.active_status.text(), "")
                self.assertFalse(self.window.download_button.isHidden())
                self.assertEqual(self.command_count, 0)
                self.window.input_field.clear()
                self.assertEqual(self.window.current_state, GuiState.EMPTY)
                self.assertTrue(self.window.classification.isHidden())

    def test_generic_success_and_failure_remain_classified(self):
        self.kind = InputKind.GENERIC_YTDLP
        self.paste("https://example.test/page")
        self.resolved()
        self.assertEqual(self.window.media_title.text(), "https://example.test/page")
        self.exit_code = 1
        self.paste("https://example.test/unreachable")
        self.resolved()
        self.assertFalse(self.window.classification.isHidden())
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertEqual(self.window.active_status.text(), "Media information unavailable ⚠️")
        self.assertFalse(self.window.download_button.isHidden())

    def test_replace_cancels_process_and_rejects_late_result(self):
        self.delay = 1
        self.paste("https://youtu.be/A")
        self.wait_for(lambda: self.window._metadata is not None and self.window._metadata.process.state() == QProcess.ProcessState.Running)
        old = self.window._metadata
        old_revision = self.window._revision
        late = replace(self.window.inspection_result, title="STALE A", metadata_status=MetadataStatus.AVAILABLE)
        self.window.input_field.setText("https://youtu.be/B")
        self.assertTrue(old.cancelled)
        self.wait_for(lambda: self.window.inspection_result is not None)
        self.window.finish_metadata(old_revision, late)
        self.assertNotEqual(self.window.media_title.text(), "STALE A")
        self.resolved()
        self.assertEqual(self.window.media_title.text(), "https://youtu.be/B")

    def test_clear_and_malformed_replacement_discard_metadata(self):
        for replacement in ["", "--title 'unfinished"]:
            self.delay = 1
            self.paste("https://youtu.be/A")
            self.wait_for(lambda: self.window._metadata is not None)
            revision = self.window._revision
            late = replace(self.window.inspection_result, title="STALE", metadata_status=MetadataStatus.AVAILABLE)
            self.window.input_field.setText(replacement)
            self.window.finish_metadata(revision, late)
            self.assertIsNone(self.window.inspection_result)
            self.assertTrue(self.window.media_title.isHidden())
            self.assertTrue(self.window.item_count.isHidden())
        self.window.input_field.clear()
        self.assertEqual(self.window.current_state, GuiState.EMPTY)

    def test_debounce_prevents_superseded_metadata_requests(self):
        self.window._metadata_timer.setInterval(100)
        self.paste("https://youtu.be/A")
        self.paste("https://youtu.be/B")
        self.assertEqual(self.command_count, 0)
        self.resolved()
        self.assertEqual(self.command_count, 1)
        self.assertEqual(self.window.media_title.text(), "https://youtu.be/B")

    def test_close_reaps_process_and_shortcuts_cancel_metadata(self):
        self.delay = 5
        self.paste("https://youtu.be/A")
        self.wait_for(lambda: self.window._metadata is not None and self.window._metadata.process.state() == QProcess.ProcessState.Running)
        worker = self.window._metadata
        process = worker.process
        enable_state_test_shortcuts(self.window)
        self.window.activateWindow()
        self.window.input_field.setFocus()
        self.app.processEvents()
        for number, state in enumerate(list(GuiState)[:7], 1):
            QTest.keyClick(self.window.input_field, getattr(Qt.Key, f"Key_F{number}"))
            self.assertEqual(self.window.current_state, state)
        self.assertTrue(worker.cancelled)
        self.window.close()
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)

    def test_timeout_missing_executable_and_invalid_json(self):
        with patch.object(MetadataProcess, "TIMEOUT_MS", 50):
            self.delay = 5
            self.paste("https://youtu.be/timeout")
            self.resolved()
            self.assertEqual(self.window.inspection_result.metadata_status, MetadataStatus.UNAVAILABLE)
        with patch("gui_metadata.build_metadata_command", return_value=["/nonexistent/aidm-metadata-tool"]):
            self.paste("https://youtu.be/missing")
            self.resolved()
            self.assertEqual(self.window.inspection_result.metadata_status, MetadataStatus.UNAVAILABLE)
        self.delay = 0
        self.body = "invalid json"
        self.paste("https://youtu.be/json")
        self.resolved()
        self.assertEqual(self.window.inspection_result.metadata_status, MetadataStatus.UNAVAILABLE)

    def test_close_during_active_fetch(self):
        self.delay = 5
        self.paste("https://youtu.be/closing")
        self.wait_for(lambda: self.window._metadata is not None and self.window._metadata.process.state() == QProcess.ProcessState.Running)
        process = self.window._metadata.process
        started = time.monotonic()
        self.window.close()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertFalse(self.window.isVisible())
        self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)


if __name__ == "__main__":
    unittest.main()
