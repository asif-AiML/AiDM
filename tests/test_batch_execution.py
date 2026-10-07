"""Shared queue contract, captured item records and offline GUI bulk execution."""

import builtins
from dataclasses import fields, FrozenInstanceError, replace
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from batch_event import BatchEvent, ItemStarted, SequentialBatchProgress
from download_job import DownloadJob, YouTubeMode, VideoQuality, BulkMode
from inspection import InputKind
from progress_event import ProgressEvent
from status_event import StatusEvent, StatusKind
from ytdlp_progress import YtDlpProgressParser, parse_ytdlp_record, ITEM_TEMPLATE
import youtube


def item(index, title=None):
    return ('AIDM_ITEM:' + json.dumps({'video_autonumber': index, 'title': title}) + '\n').encode()


class BatchModelTests(unittest.TestCase):
    def test_qt_independent_immutable_optional_title_and_no_metrics(self):
        original = builtins.__import__

        def no_qt(name, *args, **kwargs):
            if name.startswith(('PySide', 'PyQt')):
                raise AssertionError('BatchEvent must not import Qt')
            return original(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=no_qt):
            runpy.run_path('batch_event.py')
        event = BatchEvent(1, 10)
        self.assertIsNone(event.title)
        self.assertIsNone(event.aggregate_percent)
        self.assertEqual([f.name for f in fields(event)],
                         ['current_index', 'total_items', 'title', 'aggregate_percent'])
        with self.assertRaises(FrozenInstanceError):
            event.current_index = 2

    def test_validation(self):
        for index, total in ((0, 2), (3, 2), (1, 0), (True, 3), (1, False), (1.5, 3)):
            with self.subTest(index=index, total=total), self.assertRaises(ValueError):
                BatchEvent(index, total)
        for percent in (-1, 101, float('nan'), float('inf'), True, '50'):
            with self.subTest(percent=percent), self.assertRaises(ValueError):
                BatchEvent(1, 2, aggregate_percent=percent)
        with self.assertRaises(ValueError):
            BatchEvent(1, 2, title=['not text'])

    def test_locked_equal_item_math(self):
        for index, percent, expected in ((1, 0, 0), (1, 50, 5), (2, 0, 10),
                                         (3, 50, 25), (10, 100, 100), (3, None, 20)):
            with self.subTest(index=index, percent=percent):
                batch = SequentialBatchProgress(10)
                batch.start_item(ItemStarted(index, 'Title'))
                batch.progress(percent)
                self.assertEqual(batch.event.aggregate_percent, expected)

    def test_phases_duplicates_advancement_and_terminal_authority(self):
        batch = SequentialBatchProgress(10)
        batch.start_item(ItemStarted(2, 'Second'))
        batch.progress(80)
        self.assertEqual(batch.event.aggregate_percent, 18)
        self.assertIsNone(batch.progress(10))
        self.assertIsNone(batch.progress(None))
        self.assertIsNone(batch.start_item(ItemStarted(2, 'Second')))
        self.assertIsNone(batch.start_item(ItemStarted(1, 'stale')))
        self.assertIsNone(batch.start_item(ItemStarted(11, 'invalid')))
        batch.progress(100)
        self.assertEqual(batch.event.current_index, 2)  # Stream finish is not advancement.
        batch.start_item(ItemStarted(3, 'Third'))
        self.assertEqual(batch.event.aggregate_percent, 20)
        batch.progress(50)
        self.assertEqual(batch.event.aggregate_percent, 25)
        self.assertEqual(batch.complete().aggregate_percent, 100)


class BatchTelemetryTests(unittest.TestCase):
    def test_structured_records_unicode_chunking_and_invalid_input(self):
        payload = item(1, 'Title A') + item(2, 'Title "B" <b>é</b>') + item(3)
        expected = [ItemStarted(1, 'Title A'), ItemStarted(2, 'Title "B" <b>é</b>'), ItemStarted(3)]
        for size in (1, 7, len(payload)):
            parser = YtDlpProgressParser()
            events = []
            for i in range(0, len(payload), size):
                events.extend(parser.feed(payload[i:i+size]))
            self.assertEqual(events, expected)
        for line in ('AIDM_ITEM:bad', 'AIDM_ITEM:[]', 'AIDM_ITEM:{}',
                     'AIDM_ITEM:{"video_autonumber":true}',
                     'AIDM_ITEM:{"video_autonumber":0}',
                     'AIDM_ITEM:{"video_autonumber":1,"title":[]}',
                     '[2/10] Starting download: Decorative CLI output'):
            self.assertEqual(parse_ytdlp_record(line), [])

    def test_cli_human_output_and_gui_item_template_are_separate(self):
        cli = youtube.build_youtube_command(3)
        self.assertIn('before_dl:[%(video_autonumber)d/3] Starting download: %(title)s', cli)
        self.assertFalse(any('AIDM_' in arg for arg in cli))
        gui = youtube.build_youtube_command(3, telemetry=True)
        self.assertIn(ITEM_TEMPLATE, gui)
        self.assertNotIn('Starting download:', ' '.join(gui))
        self.assertNotIn(ITEM_TEMPLATE, youtube.build_youtube_command(telemetry=True))

    def test_real_local_three_item_and_skip_captures(self):
        root = Path(__file__).parent / 'fixtures/ytdlp/bulk'
        for mode in ('video', 'original', 'wav', 'retry'):
            raw = (root / (mode + '.txt')).read_bytes()
            events = YtDlpProgressParser().feed(raw, final=True)
            starts = [event for event in events if isinstance(event, ItemStarted)]
            self.assertEqual([event.current_index for event in starts], [1, 2, 3])
            self.assertEqual([event.title for event in starts], ['First', 'Second', 'Third'])
            batch = SequentialBatchProgress(3)
            values = []
            for event in events:
                update = (batch.start_item(event) if isinstance(event, ItemStarted)
                          else batch.progress(event.percent) if isinstance(event, ProgressEvent) else None)
                if update:
                    values.append(update.aggregate_percent)
            self.assertEqual(values, sorted(values))


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtWidgets import QApplication
    from aidm_gui import GuiState, format_batch_summary
    from gui_execution import YouTubeDownloadProcess, create_download_process, UnsupportedExecution, ExecutionOutcome
    import test_gui_execution as gui_tests
except ImportError:
    gui_tests = None


@unittest.skipIf(gui_tests is None, 'Requires PySide6')
class BatchGuiTests(unittest.TestCase):
    if gui_tests is not None:
        setUp = gui_tests.GuiExecutionTests.setUp
        tearDown = gui_tests.GuiExecutionTests.tearDown
        inspect = gui_tests.GuiExecutionTests.inspect

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def start_bulk(self, mode=YouTubeMode.VIDEO, quality=720, count=2):
        self.window.input_field.clear()
        self.inspect(InputKind.YOUTUBE_BULK)
        if count != 2:
            self.window.inspection_result = replace(
                self.window.inspection_result,
                urls=[f'https://youtu.be/fixture{i:04d}' for i in range(count)], item_count=count,
            )
        self.window.on_download_intent()
        with patch('gui_quality.QualityProcess.start'):
            self.window.mode_buttons[mode].click()
        if mode == YouTubeMode.VIDEO:
            self.window.finish_quality(self.window._quality_generation, [quality] if type(quality) is int else [])
            if type(quality) is int:
                self.window.quality_choice.setCurrentIndex(1)
        self.window.on_download_intent()
        return self.window._download_process

    def feed(self, worker, data):
        worker.process.stdout = data
        worker.process.readyReadStandardOutput.emit()

    def test_all_modes_one_command_url_order_quality_destination(self):
        for mode in YouTubeMode:
            for quality in ((1080, VideoQuality.BEST) if mode == YouTubeMode.VIDEO else (None,)):
                worker = self.start_bulk(mode, quality)
                self.assertIsInstance(worker, YouTubeDownloadProcess)
                program, args = worker.process.calls[0]
                self.assertEqual(program, 'yt-dlp')
                self.assertEqual(args[args.index('--')+1:], list(worker.job.urls))
                self.assertEqual(args[args.index('-P')+1], worker.job.destination)
                self.assertIn(ITEM_TEMPLATE, args)
                self.assertEqual(len(worker.process.calls), 1)
                if mode == YouTubeMode.VIDEO:
                    self.assertEqual(args[args.index('-f')+1], youtube.build_youtube_format(
                        quality if type(quality) is int else None))
                    for option in ('--merge-output-format', '--remux-video'):
                        self.assertEqual(args[args.index(option)+1], 'mp4')
                else:
                    self.assertEqual(args[args.index('-f')+1], 'bestaudio/best')
                    self.assertEqual('--extract-audio' in args, mode == YouTubeMode.WAV)
                worker.process.finish()

    def test_queue_title_aggregate_and_current_item_stats(self):
        worker = self.start_bulk()
        self.assertTrue(self.window.queue_position.isHidden())
        self.assertTrue(self.window.progress.isHidden())
        worker.process.begin()
        self.feed(worker, item(1, 'Title A'))
        self.assertEqual(self.window.queue_position.text(), '1 / 2')
        self.assertEqual(self.window.media_title.text(), 'Title A')
        self.assertEqual(self.window.active_status.text(), 'Downloading item 1 of 2… ⬇️')
        self.feed(worker, b'[#abcdef 80B/100B(80%) CN:1 DL:5B ETA:4s]\n')
        self.assertEqual(self.window.progress.value(), 40)
        self.assertIn('80 B / 100 B', self.window.statistics.text())
        self.feed(worker, b'[#abcdef 10B/100B(10%) CN:1 DL:5B ETA:18s]\n')
        self.assertEqual(self.window.progress.value(), 40)
        self.assertIn('10 B / 100 B', self.window.statistics.text())
        self.feed(worker, item(1, 'Title A'))
        self.assertEqual(self.window.progress.value(), 40)
        self.feed(worker, item(2, '<b>Title B</b>'))
        self.assertEqual(self.window.queue_position.text(), '2 / 2')
        self.assertEqual(self.window.media_title.text(), '<b>Title B</b>')
        self.assertEqual(self.window.media_title.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(self.window.progress.value(), 50)
        self.assertTrue(self.window.statistics.isHidden())
        self.feed(worker, b'AIDM_POSTPROCESS:{"status":"started","postprocessor":"Merger"}\n')
        self.assertEqual(self.window.progress.value(), 50)
        self.assertIn('Merging', self.window.active_status.text())
        last_progress = self.window._progress_event
        worker.process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.assertEqual(self.window._batch_event.aggregate_percent, 100)
        self.assertIs(self.window._progress_event, last_progress)
        self.assertIn('YouTube batch', self.window.classification.text())
        self.assertTrue(self.window.media_title.isHidden())
        self.assertEqual(self.window.batch_summary.text(), '2 videos downloaded')
        self.assertFalse(self.window.batch_summary.isHidden())
        self.assertTrue(self.window.progress.isHidden())
        self.assertTrue(self.window.retry_button.isHidden())

    def test_failure_abort_retry_same_job_resets_and_stale_batch_is_ignored(self):
        for abort in (False, True):
            worker = self.start_bulk()
            worker.process.begin()
            self.feed(worker, item(2, 'Last known title'))
            job = worker.job
            if abort:
                self.window.abort_button.click()
            else:
                worker.process.finish(7)
            self.assertEqual(self.window.current_state, GuiState.ABORTED if abort else GuiState.FAILED)
            self.assertEqual(self.window._batch_event.aggregate_percent, 50)
            self.assertTrue(self.window.media_title.isHidden())
            self.assertTrue(self.window.batch_summary.isHidden())
            self.assertTrue(self.window.item_count.isHidden())
            self.assertFalse(self.window.retry_button.isHidden())
            self.assertTrue(self.window.result_message.font().bold())
            self.window.retry_button.click()
            current = self.window._download_process
            self.assertIsNot(current, worker)
            self.assertIs(current.job, job)
            self.assertIsNone(self.window._batch_event)

            self.assertTrue(self.window.queue_position.isHidden())
            self.assertTrue(self.window.media_title.isHidden())
            worker.batch_event.emit(BatchEvent(2, 2, 'stale', 99))
            worker.finished.emit(ExecutionOutcome.FAILED)
            self.assertIsNone(self.window._batch_event)
            self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
            self.feed(current, item(1, 'Retry first'))
            self.assertEqual(self.window.queue_position.text(), '1 / 2')
            self.assertEqual(self.window.progress.value(), 0)
            current.process.finish()
            self.window.input_field.clear()
            self.assertIsNone(self.window._batch_event)

    def test_queue_emphasis_and_terminal_summary_use_job_count(self):
        worker = self.start_bulk(count=4)
        worker.process.begin()
        self.feed(worker, item(3, 'Third title'))
        window = self.window
        self.assertFalse(window.queue_position.isHidden())
        self.assertTrue(window.queue_position.font().bold())
        self.assertGreater(window.queue_position.font().pointSize(), window.item_count.font().pointSize())
        self.assertLess(window.queue_position.font().pointSize(), window.result_message.font().pointSize())
        self.assertEqual(window.media_title.text(), 'Third title')
        self.feed(worker, item(4, 'Fourth title'))
        self.assertEqual(window.media_title.text(), 'Fourth title')
        # Neither mutable inspection metadata nor the last queue record supplies
        # the authoritative completed URL count.
        window.inspection_result = replace(window.inspection_result, item_count=999)
        worker.batch_event.emit(BatchEvent(1, 9, 'Wrong summary source', 0))
        worker.process.finish()
        self.assertTrue(window.media_title.isHidden())
        self.assertTrue(window.item_count.isHidden())
        self.assertEqual(window.batch_summary.text(), '4 videos downloaded')
        self.assertTrue(window.batch_summary.font().bold())
        self.assertLess(window.batch_summary.font().pointSize(), window.result_message.font().pointSize())
        self.assertEqual(window.batch_summary.alignment(), Qt.AlignmentFlag.AlignCenter)
        self.assertEqual(window.batch_summary.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(window.result_message.text(), 'Download complete 🎉💫')
        self.assertTrue(window.retry_button.isHidden())
        window.input_field.clear()
        self.assertTrue(window.batch_summary.isHidden())

    def test_shared_summary_nouns_and_future_multi_item_terminal_presentation(self):
        for kind, noun in ((InputKind.YOUTUBE_BULK, 'video'),
                           (InputKind.DIRECT_BULK, 'file')):
            self.assertEqual(format_batch_summary(kind, 1), f'1 {noun} downloaded')
            self.assertEqual(format_batch_summary(kind, 4), f'4 {noun}s downloaded')
        self.assertEqual(format_batch_summary(InputKind.GENERIC_YTDLP, 4), '4 items downloaded')
        self.assertEqual(format_batch_summary(InputKind.YOUTUBE_PLAYLIST, None), '')
        for kind, count, expected in ((InputKind.DIRECT_BULK, 2, '2 files downloaded'),
                                      (InputKind.YOUTUBE_PLAYLIST, 4, 'YouTube playlist downloaded • 4 videos')):
            self.inspect(kind)
            self.window.inspection_result = replace(self.window.inspection_result, title='Last item', item_count=count)
            self.window.set_state(GuiState.COMPLETE)
            self.assertTrue(self.window.media_title.isHidden())
            self.assertEqual(self.window.batch_summary.text(), expected)

    def test_batch_channel_is_route_neutral_and_state_independent(self):
        # Reuse an existing executable single fixture to prove the GUI consumes
        # batch events without a YOUTUBE_BULK-specific rendering branch.
        self.inspect(InputKind.DIRECT_SINGLE)
        self.window.on_download_intent()
        worker = self.window._download_process
        worker.batch_event.emit(BatchEvent(3, 10, 'Shared identity', 25))
        worker.progress_event.emit(ProgressEvent(70, 70, 100))
        self.assertEqual(self.window.progress.value(), 25)
        self.assertEqual(self.window.queue_position.text(), '3 / 10')
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        worker.process.finish(7)
        self.window.preview_state(GuiState.EMPTY)
        self.assertIsNone(self.window._batch_event)
        self.assertTrue(self.window.queue_position.isHidden())

    def test_other_routes_stay_deferred(self):
        for kind in (InputKind.DIRECT_BULK, InputKind.HLS,
                     InputKind.DASH, InputKind.GENERIC_YTDLP, InputKind.STREAM_INSPECTOR, InputKind.TORRENT):
            extra = {}
            urls = ('first',)
            if kind == InputKind.YOUTUBE_PLAYLIST:
                extra['video_quality'] = 720
            elif kind == InputKind.DIRECT_BULK:
                urls = ('first', 'second')
                extra['bulk_mode'] = BulkMode.PARALLEL
            elif kind == InputKind.STREAM_INSPECTOR:
                extra.update(route_kind=InputKind.YOUTUBE_SINGLE, mode=YouTubeMode.WAV)
            with self.assertRaises(UnsupportedExecution):
                create_download_process(DownloadJob(kind, urls, str(self.directory), **extra))


if __name__ == '__main__':
    unittest.main()
