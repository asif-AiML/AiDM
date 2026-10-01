import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("GUI job checks require PySide6")

from aidm_gui import AiDMWindow, GuiState
from download_job import YouTubeMode, VideoQuality
from inspection import InputKind, InspectionResult, MetadataStatus


class GuiDownloadJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_helper_builds_without_execution_or_ui_transition(self):
        window = AiDMWindow()
        self.addCleanup(window.close)
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected subprocess")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected probe")), \
                patch("gui_metadata.MetadataProcess.start", side_effect=AssertionError("Unexpected metadata")):
            with self.assertRaises(ValueError):
                window.build_job_for_testing()
            window.inspection_result = InspectionResult(InputKind.YOUTUBE_SINGLE, ["https://youtu.be/a"], metadata_status=MetadataStatus.PENDING)
            window.set_state(GuiState.NEEDS_OPTIONS)
            job = window.build_job_for_testing(mode=YouTubeMode.ORIGINAL_AUDIO)
            self.assertEqual(job.mode, YouTubeMode.ORIGINAL_AUDIO)
            for quality in (1080, VideoQuality.BEST):
                job = window.build_job_for_testing(mode=YouTubeMode.VIDEO, video_quality=quality)
                self.assertEqual(job.video_quality, quality)
            with self.assertRaises(ValueError):
                window.build_job_for_testing(mode=YouTubeMode.VIDEO)
            with self.assertRaises(ValueError):
                window.build_job_for_testing(mode=YouTubeMode.WAV, video_quality=720)
            self.assertEqual(window.current_state, GuiState.NEEDS_OPTIONS)
            self.assertTrue(window.download_button.isHidden())
            window.on_input_changed("--title 'unfinished")
            with self.assertRaises(ValueError):
                window.build_job_for_testing(mode=YouTubeMode.VIDEO)
            window.on_input_changed("")
            with self.assertRaises(ValueError):
                window.build_job_for_testing()
            self.assertEqual(window.current_state, GuiState.EMPTY)
            window.inspection_result = InspectionResult(InputKind.TORRENT, ["file.torrent"])
            with self.assertRaisesRegex(ValueError, "deferred"):
                window.build_job_for_testing()


if __name__ == "__main__":
    unittest.main()
