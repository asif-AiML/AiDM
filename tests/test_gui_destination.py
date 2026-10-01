"""Destination behavior using temporary homes and private INI settings only."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("Destination GUI checks require PySide6")

from aidm_gui import AiDMWindow, GuiState, existing_destination, initial_destination
from download_job import BulkMode, YouTubeMode
from inspection import InputKind, InspectionResult, MetadataStatus
from stream_parser import StreamInput


class DestinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = TemporaryDirectory(prefix="aidm-destination-")
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.downloads = self.home / "Downloads"
        self.downloads.mkdir()
        self.custom = self.home / "Custom folder"
        self.custom.mkdir()
        self.settings_file = str(self.home / "preferences.ini")
        self.settings = self.new_settings()
        self.windows = []
        for target, kwargs in [
            ("aidm_gui.Path.home", {"return_value": self.home}),
            ("aidm_gui.QSettings", {"side_effect": AssertionError("Real settings must not be opened")}),
            ("gui_metadata.MetadataProcess.start", {}),
            ("gui_quality.QualityProcess.start", {}),
            ("subprocess.run", {"side_effect": AssertionError("Unexpected execution")}),
            ("subprocess.Popen", {"side_effect": AssertionError("Unexpected execution")}),
            ("urllib.request.urlopen", {"side_effect": AssertionError("Unexpected network")}),
        ]:
            guard = patch(target, **kwargs)
            guard.start()
            self.addCleanup(guard.stop)

    def new_settings(self):
        return QSettings(self.settings_file, QSettings.Format.IniFormat)

    def window(self, settings=None):
        window = AiDMWindow(settings=self.settings if settings is None else settings)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def tearDown(self):
        for window in self.windows:
            window.close()
        self.app.processEvents()

    def inspect(self, window, kind=InputKind.DIRECT_SINGLE):
        urls = ["https://example.test/a"]
        if kind in {InputKind.YOUTUBE_BULK, InputKind.DIRECT_BULK}:
            urls.append("https://example.test/b")
        stream = StreamInput(urls[0], title="Browser title") if kind == InputKind.STREAM_INSPECTOR else None
        result = InspectionResult(kind, urls, stream=stream,
                                  route_kind=InputKind.HLS if stream else None)
        window.finish_inspection(window._revision, result, "")
        window._metadata_timer.stop()
        self.assertEqual(window.current_state, GuiState.READY)
        self.assertFalse(window.destination_section.isHidden())

    def browse(self, window, value):
        previous = window.destination
        with patch("aidm_gui.QFileDialog.getExistingDirectory", return_value=str(value)) as picker:
            window.browse_button.click()
            picker.assert_called_once_with(window, "Choose download folder", previous)

    def test_default_and_home_fallback_without_creating_downloads(self):
        self.assertEqual(initial_destination(self.settings), str(self.downloads))
        self.downloads.rmdir()
        self.assertEqual(initial_destination(self.settings), str(self.home))
        self.assertFalse(self.downloads.exists())

    def test_invalid_or_inaccessible_remembered_path_falls_back(self):
        file = self.home / "file"
        file.write_text("fixture")
        for value in (str(self.home / "missing"), str(file), "relative", "", "/bad\x00path"):
            with self.subTest(value=value):
                self.settings.setValue("downloads/destination", value)
                self.assertEqual(initial_destination(self.settings), str(self.downloads))
        self.settings.setValue("downloads/destination", str(self.custom))
        with patch("aidm_gui.os.access", side_effect=lambda path, mode: path != self.custom):
            self.assertEqual(initial_destination(self.settings), str(self.downloads))
        with patch("aidm_gui.Path.resolve", side_effect=PermissionError):
            self.assertIsNone(existing_destination(str(self.custom)))

    def test_browse_cancel_persistence_and_removed_directory(self):
        window = self.window()
        self.assertTrue(window.destination_section.isHidden())
        self.inspect(window)
        self.assertTrue(window.destination_field.isReadOnly())
        self.browse(window, self.custom)
        self.assertEqual(window.destination_field.text(), str(self.custom))
        self.assertEqual(window.download_job.destination, str(self.custom))
        self.browse(window, "")
        self.assertEqual(window.destination, str(self.custom))
        window.close()
        restored = self.window(self.new_settings())
        self.assertEqual(restored.destination, str(self.custom))
        restored.close()
        self.custom.rmdir()
        fallback = self.window(self.new_settings())
        self.assertEqual(fallback.destination, str(self.downloads))

    def test_invalid_browse_keeps_previous_destination(self):
        window = self.window()
        self.inspect(window)
        self.browse(window, self.home / "missing")
        self.assertEqual(window.destination, str(self.downloads))
        self.assertIn("unavailable", window.active_status.text())
        self.assertIsNone(self.settings.value("downloads/destination"))

    def test_youtube_destination_survives_configuration_and_change(self):
        for kind in (InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST):
            with self.subTest(kind=kind):
                window = self.window()
                self.inspect(window, kind)
                window.download_button.click()
                self.assertFalse(window.destination_section.isHidden())
                if kind != InputKind.YOUTUBE_PLAYLIST:
                    window.mode_buttons[YouTubeMode.VIDEO].click()
                self.assertTrue(window._quality_pending)
                generation = window._quality_generation
                self.browse(window, self.custom)
                self.assertEqual(window._quality_generation, generation)
                self.assertEqual(window.current_state, GuiState.NEEDS_OPTIONS)
                window.finish_quality(generation, [1080, 720])
                window.quality_choice.setCurrentIndex(1)
                self.assertEqual(window.download_job.video_quality, 1080)
                self.assertEqual(window.download_job.destination, str(self.custom))
                old_job = window.download_job
                self.browse(window, self.downloads)
                self.assertEqual(window.current_state, GuiState.READY)
                self.assertFalse(window.destination_section.isHidden())
                self.assertEqual(window.download_job.video_quality, 1080)
                self.assertEqual(window.download_job.mode, old_job.mode)
                self.assertEqual(window.download_job.destination, str(self.downloads))
                self.assertEqual(old_job.destination, str(self.custom))

    def test_audio_wav_direct_bulk_and_inspector_jobs(self):
        for mode in (YouTubeMode.ORIGINAL_AUDIO, YouTubeMode.WAV):
            window = self.window()
            self.inspect(window, InputKind.YOUTUBE_SINGLE)
            window.download_button.click()
            window.mode_buttons[mode].click()
            self.browse(window, self.custom)
            self.assertEqual(window.download_job.mode, mode)
            self.assertEqual(window.download_job.destination, str(self.custom))
            self.assertEqual(window.build_job_for_testing(mode=mode).destination, str(self.custom))
        for bulk_mode in BulkMode:
            window = self.window()
            self.inspect(window, InputKind.DIRECT_BULK)
            window.download_button.click()
            self.assertFalse(window.destination_section.isHidden())
            window.bulk_buttons[bulk_mode].click()
            self.browse(window, self.custom)
            self.assertEqual(window.download_job.bulk_mode, bulk_mode)
            self.assertEqual(window.download_job.destination, str(self.custom))
        window = self.window()
        self.inspect(window, InputKind.STREAM_INSPECTOR)
        self.browse(window, self.custom)
        self.assertEqual(window.download_job.title, "Browser title")
        self.assertEqual(window.download_job.destination, str(self.custom))

    def test_input_change_resets_options_but_preserves_folder(self):
        window = self.window()
        self.inspect(window, InputKind.YOUTUBE_SINGLE)
        window.download_button.click()
        window.mode_buttons[YouTubeMode.WAV].click()
        self.browse(window, self.custom)
        window.input_field.setText("--title 'unfinished")
        self.assertFalse(window._configuration_started)
        self.assertIsNone(window.download_job)
        self.assertTrue(window.destination_section.isHidden())
        self.assertEqual(window.destination, str(self.custom))
        window.input_field.clear()
        self.assertEqual(window.current_state, GuiState.EMPTY)
        self.inspect(window)
        self.assertEqual(window.download_job.destination, str(self.custom))

    def test_enter_with_destination_focus_does_not_open_picker(self):
        window = self.window()
        self.inspect(window)
        window.activateWindow()
        window.destination_field.setFocus()
        self.app.processEvents()
        with patch("aidm_gui.QFileDialog.getExistingDirectory", side_effect=AssertionError("Unexpected picker")):
            QTest.keyClick(window.destination_field, Qt.Key.Key_Return)
        self.assertEqual(window.current_state, GuiState.READY)
        self.assertIn("execution is not implemented", window.active_status.text())


if __name__ == "__main__":
    unittest.main()
