"""Offline playlist execution through the shared YouTube lifecycle."""

from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from batch_event import BatchEvent, ItemStarted
from download_job import DownloadJob, VideoQuality, YouTubeMode, build_download_job
from inspection import InputKind, InspectionResult
from progress_event import ProgressEvent
from status_event import StatusEvent, StatusKind
from ytdlp_progress import YtDlpProgressParser, PLAYLIST_ITEM_TEMPLATE
import youtube


def item(index, title, total=14):
    return ('AIDM_ITEM:' + json.dumps(dict(playlist_autonumber=index, n_entries=total, title=title)) + '\n').encode()


class PlaylistContractTests(unittest.TestCase):
    def test_count_snapshot_validation_and_no_bulk_duplication(self):
        result = InspectionResult(InputKind.YOUTUBE_PLAYLIST, ['playlist'], title='Collection', item_count=14)
        job = build_download_job(result, destination='/tmp/example', video_quality=720)
        self.assertEqual(len(job.urls), 1)
        self.assertEqual(job.item_count, 14)
        self.assertEqual(job.title, 'Collection')
        for count in (0, -1, True, '14', 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                replace(job, item_count=count)
        self.assertIsNone(replace(job, item_count=None).item_count)
        for mode in YouTubeMode:
            with self.assertRaises(ValueError):
                replace(job, mode=mode)
        bulk = InspectionResult(InputKind.YOUTUBE_BULK, ['a', 'b'], item_count=2)
        self.assertIsNone(build_download_job(bulk, destination='/tmp/example', mode=YouTubeMode.WAV).item_count)

    def test_shared_command_and_cli_defaults(self):
        for height in (None, 720, 1080):
            self.assertEqual(youtube.build_youtube_playlist_command('playlist', height),
                             youtube.build_youtube_video_command(height) + ['--yes-playlist', 'playlist'])
            command = youtube.build_youtube_playlist_command('playlist', height, destination='/tmp/a b', telemetry=True)
            self.assertEqual(command[-2:], ['--yes-playlist', 'playlist'])
            self.assertNotIn('--no-playlist', command)
            self.assertEqual(command[command.index('-f')+1], youtube.build_youtube_format(height))
            self.assertEqual(command[command.index('-P')+1], '/tmp/a b')
            self.assertIn(PLAYLIST_ITEM_TEMPLATE, command)
            for option in ('--merge-output-format', '--remux-video'):
                self.assertEqual(command[command.index(option)+1], 'mp4')
            self.assertNotIn('--recode-video', command)
        self.assertFalse(any('AIDM_' in arg for arg in youtube.build_youtube_playlist_command('playlist')))

    def test_installed_ytdlp_capture_and_chunked_playlist_records(self):
        raw = (Path(__file__).parent / 'fixtures/ytdlp/playlist/items.txt').read_bytes()
        expected = [ItemStarted(1, 'First', 3), ItemStarted(2, 'Second é', 3), ItemStarted(3, 'Third', 3)]
        for size in (1, 11, len(raw)):
            parser = YtDlpProgressParser()
            events = []
            for start in range(0, len(raw), size):
                events.extend(parser.feed(raw[start:start+size]))
            self.assertEqual(events, expected)
        parser = YtDlpProgressParser()
        for bad in (item(0, 'bad'), item(True, 'bad'), item(3, 'bad', 2), b'AIDM_ITEM:garbage\n'):
            self.assertEqual(parser.feed(bad), [])


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import Qt, QProcess
    from PySide6.QtWidgets import QApplication
    from aidm_gui import GuiState, format_batch_summary
    from gui_execution import YouTubeDownloadProcess, create_download_process, ExecutionOutcome
    import test_gui_execution as gui_tests
except ImportError:
    gui_tests = None


@unittest.skipIf(gui_tests is None, 'Requires PySide6')
class PlaylistGuiTests(unittest.TestCase):
    if gui_tests is not None:
        setUp = gui_tests.GuiExecutionTests.setUp
        tearDown = gui_tests.GuiExecutionTests.tearDown
        inspect = gui_tests.GuiExecutionTests.inspect

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def start_playlist(self, count=14, quality=720, title='My Favorite Songs'):
        self.window.input_field.clear()
        self.inspect(InputKind.YOUTUBE_PLAYLIST)
        self.window.inspection_result = replace(self.window.inspection_result, title=title, item_count=count)
        self.window.set_state(GuiState.READY)
        self.assertEqual(self.window.job_title.full_title, title)
        with patch('gui_quality.QualityProcess.start'):
            self.window.on_download_intent()
        self.assertTrue(self.window.mode_options.isHidden())
        self.window.finish_quality(self.window._quality_generation, [] if quality == VideoQuality.BEST else [quality])
        if quality != VideoQuality.BEST:
            self.window.quality_choice.setCurrentIndex(1)
        with patch('youtube.get_available_youtube_qualities', side_effect=AssertionError('Execution must not discover qualities')):
            self.window.on_download_intent()
        return self.window._download_process

    def feed(self, worker, data):
        worker.process.stdout = data
        worker.process.readyReadStandardOutput.emit()

    def test_factory_quality_count_and_one_playlist_url(self):
        for quality in (1080, VideoQuality.BEST):
            worker = self.start_playlist(14, quality)
            self.assertIsInstance(worker, YouTubeDownloadProcess)
            self.assertEqual(worker._batch.total_items, 14)
            self.assertEqual(len(worker.job.urls), 1)
            expected = youtube.build_youtube_playlist_command(worker.job.urls[0], None if quality == VideoQuality.BEST else quality,
                                                              destination=worker.job.destination, telemetry=True)
            self.assertEqual(worker.process.calls[0], (expected[0], expected[1:]))
            self.assertIsNone(worker.job.mode)
            worker.process.finish()

    def test_primary_identity_current_title_and_aggregate(self):
        worker = self.start_playlist(count=10)
        window = self.window
        self.assertEqual(window.current_state, GuiState.DOWNLOADING)
        self.assertFalse(window.job_title.isHidden())
        self.assertTrue(window.media_title.isHidden())
        self.assertTrue(window.queue_position.isHidden())
        self.assertFalse(window.abort_button.isHidden())
        worker.process.begin()
        # Runtime total must not overwrite the known immutable inspection total.
        self.feed(worker, item(2, 'Second video', 50))
        self.feed(worker, b'[#abcdef 50B/100B(50%) CN:1 DL:5B ETA:10s]\n')
        self.assertEqual(window.queue_position.text(), '2 / 10')
        self.assertEqual(window.media_title.full_title, 'Second video')
        self.assertEqual(window.progress.value(), 15)
        self.assertIn('50 B / 100 B', window.statistics.text())
        self.feed(worker, b'[#abcdef 5B/100B(5%) CN:1 DL:5B ETA:19s]\n')
        self.assertEqual(window.progress.value(), 15)
        self.feed(worker, item(3, 'Third video'))
        self.assertEqual(window.media_title.full_title, 'Third video')
        self.assertEqual(window.job_title.full_title, 'My Favorite Songs')
        self.assertEqual(window.inspection_result.title, 'My Favorite Songs')
        self.assertEqual(window.progress.value(), 20)
        self.assertTrue(window.statistics.isHidden())
        self.assertTrue(window.job_title.font().bold())
        self.assertGreater(window.job_title.font().pointSize(), window.media_title.font().pointSize())
        self.assertGreater(window.job_title.font().pointSize(), window.queue_position.font().pointSize())
        self.assertLess(window.job_title.font().pointSize(), window.result_message.font().pointSize())
        self.assertTrue(window.queue_position.font().bold())
        self.assertEqual(window.job_title.textFormat(), Qt.TextFormat.PlainText)
        self.app.processEvents()
        self.assertLess(window.job_title.y(), window.queue_position.y())
        self.assertLess(window.queue_position.y(), window.media_title.y())
        worker.process.finish()
        self.assertFalse(window.job_title.isHidden())
        self.assertTrue(window.media_title.isHidden())
        self.assertEqual(window.batch_summary.text(), 'YouTube playlist downloaded • 10 videos')
        self.assertEqual(window.result_message.text(), 'Download complete 🎉💫')
        self.assertTrue(window.retry_button.isHidden())

    def test_terminal_count_snapshot_long_title_and_singular(self):
        title = 'Very.Long.Playlist.Title.' * 30
        worker = self.start_playlist(count=1, title=title)
        self.feed(worker, item(1, 'Very.Long.Video.Title.' * 30, 1))
        self.app.processEvents()
        self.assertLessEqual(self.window.width(), 520)
        self.assertEqual(self.window.job_title.full_title, title)
        self.assertEqual(self.window.job_title.toolTip(), title)
        self.window.inspection_result = replace(self.window.inspection_result, title='mutated', item_count=999)
        worker.process.finish()
        self.assertEqual(self.window.job_title.full_title, title)
        self.assertEqual(self.window.batch_summary.text(), 'YouTube playlist downloaded • 1 video')
        self.assertEqual(format_batch_summary(InputKind.YOUTUBE_BULK, 4), '4 videos downloaded')
        self.assertEqual(format_batch_summary(InputKind.DIRECT_BULK, 4), '4 files downloaded')

    def test_failed_aborted_retry_same_snapshot_and_stale_signals(self):
        for aborted in (False, True):
            worker = self.start_playlist()
            worker.process.begin()
            self.feed(worker, item(2, 'Current video'))
            job = worker.job
            if aborted:
                self.window.abort_button.click()
            else:
                worker.process.finish(7)
            self.assertEqual(self.window.current_state, GuiState.ABORTED if aborted else GuiState.FAILED)
            self.assertFalse(self.window.job_title.isHidden())
            self.assertTrue(self.window.media_title.isHidden())
            self.assertTrue(self.window.batch_summary.isHidden())
            self.assertFalse(self.window.retry_button.isHidden())
            self.window.retry_button.click()
            current = self.window._download_process
            self.assertIsNot(current, worker)
            self.assertIs(current.job, job)
            self.assertIsNone(self.window._batch_event)
            self.assertTrue(self.window.media_title.isHidden())
            self.assertEqual(current.build_command(), worker.build_command())
            worker.batch_event.emit(BatchEvent(9, 14, 'stale', 80))
            worker.finished.emit(ExecutionOutcome.FAILED)
            self.assertIsNone(self.window._batch_event)
            self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
            self.feed(current, item(1, 'Retry first'))
            self.assertEqual(self.window.queue_position.text(), '1 / 14')
            current.process.finish()

    def test_unknown_inspection_count_uses_runtime_total_not_url_count(self):
        worker = self.start_playlist(count=None)
        self.assertIsNone(worker._batch)
        self.assertTrue(self.window.queue_position.isHidden())
        self.feed(worker, b'[#abcdef 50B/100B(50%) CN:1 DL:5B ETA:10s]\n')
        self.assertTrue(self.window.progress.isHidden())
        self.assertFalse(self.window.statistics.isHidden())
        self.feed(worker, item(2, 'Second', 14))
        self.assertEqual(worker._batch.total_items, 14)
        self.assertIsNone(worker.job.item_count)  # Snapshot is never mutated.
        self.assertEqual(self.window.queue_position.text(), '2 / 14')
        worker.process.finish()
        self.assertEqual(self.window.batch_summary.text(), 'YouTube playlist downloaded • 14 videos')

    def test_start_failure_and_reset_keep_shared_lifecycle(self):
        worker = self.start_playlist()
        worker.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertIn('Could not start yt-dlp', self.window.result_message.text())
        self.assertFalse(self.window.retry_button.isHidden())
        self.assertFalse(self.window.job_title.isHidden())
        self.window.input_field.clear()
        self.assertTrue(self.window.job_title.isHidden())
        self.assertTrue(self.window.media_title.isHidden())


if __name__ == '__main__':
    unittest.main()
