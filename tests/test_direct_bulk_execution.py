"""Captured parallel aria2 truth, shared command policy and direct bulk lifecycle."""
import builtins
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from aria2_parallel_progress import Aria2ParallelProgressParser, Aria2Snapshot, Aria2Completed
from batch_event import ParallelBatchEvent, ParallelBatchProgress
from download_job import BulkMode, DownloadJob
from downloader import build_direct_bulk_parallel_command
import downloader
from inspection import InputKind
from progress_event import ProgressEvent

FIXTURES = Path(__file__).parent / 'fixtures/aria2'


def summary(*records):
    return (' *** Download Progress Summary as of Fri Oct  9 13:51:48 2026 *** \n'
            '===============================================================================\n'
            + ''.join(f'[#{gid} {done}B/{total}B({percent}%) CN:1 DL:{speed}B ETA:2s]\n'
                      f'FILE: /tmp/{gid}.bin\n' + '-' * 79 + '\n'
                      for gid, done, total, percent, speed in records) + '\n').encode()


def notice(gid):
    return f'10/09 13:51:50 [NOTICE] Download complete: /tmp/{gid}.bin\n'.encode()


class ParallelTelemetryTests(unittest.TestCase):
    def test_qt_independent_models_and_parser(self):
        original = builtins.__import__
        def no_qt(name, *args, **kwargs):
            if name.startswith(('PySide', 'PyQt')):
                raise AssertionError('Qt-independent telemetry')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=no_qt):
            for path in ('batch_event.py', 'aria2_parallel_progress.py'):
                runpy.run_path(path)
        for args in ((0,), (2, 3), (2, 1, 2), (2, True), (2, 0, -1), (2, 0, 0, float('nan'))):
            with self.assertRaises(ValueError):
                ParallelBatchEvent(*args)

    def test_real_captures_multiple_gids_completion_and_exact_bytes(self):
        for filename in ('parallel.txt', 'parallel-unknown.txt'):
            raw = (FIXTURES / filename).read_bytes()
            events = Aria2ParallelProgressParser(3).feed(raw, final=True)
            snapshots = [e for e in events if isinstance(e, Aria2Snapshot)]
            self.assertEqual([len(e.items) for e in snapshots], [3,3,3,2,2,2,1,1,1])
            tracker = ParallelBatchProgress(3)
            values = []
            completions = []
            for e in events:
                batch, stats = (tracker.snapshot(e.items) if isinstance(e, Aria2Snapshot)
                                else tracker.finish_item(e.gid))
                values.append(batch.aggregate_percent)
                completions.append(batch.completed_items)
                self.assertIsNone(stats.eta_seconds)
            self.assertEqual(values, sorted(values))
            self.assertTrue({0,1,2,3}.issubset(completions))
            self.assertEqual(batch.active_items, 0)
            first = ParallelBatchProgress(3)
            first_batch, first_stats = first.snapshot(snapshots[0].items)
            self.assertEqual(first_batch.active_items, 3)
            self.assertEqual(first_stats.downloaded_bytes, 3 * 163840)
            self.assertEqual(first_stats.speed_bytes_per_second,
                             sum(p.speed_bytes_per_second for p in snapshots[0].items.values()))
            if filename == 'parallel.txt':
                self.assertEqual(first_stats.total_bytes, 3145728)
                self.assertAlmostEqual(first_batch.aggregate_percent, 15.625)
                self.assertEqual(stats.downloaded_bytes, 3145728)
            else:
                self.assertIsNone(first_stats.total_bytes)
                self.assertIsNone(stats.total_bytes)
                self.assertAlmostEqual(first_batch.aggregate_percent, (31 + 15) / 3)

    def test_capture_chunking_crlf_final_tail_and_bounded_noise(self):
        raw = (FIXTURES / 'parallel.txt').read_bytes()
        expected = Aria2ParallelProgressParser(3).feed(raw, final=True)
        for payload in (raw, raw.replace(b'\r', b'').replace(b'\n', b'\r\n')):
            for size in (1, 7, 4096):
                parser = Aria2ParallelProgressParser(3)
                events = []
                for i in range(0, len(payload), size):
                    events.extend(parser.feed(payload[i:i+size]))
                events.extend(parser.feed(b'', final=True))
                self.assertEqual(events, expected)
        parser = Aria2ParallelProgressParser(3)
        parser.feed(b'x' * 100000)
        self.assertLessEqual(len(parser._buffer), parser.MAX_RECORD_BYTES)
        self.assertEqual(parser.feed(b'\n' + raw, final=True), expected)

    def test_disappearance_and_100_percent_do_not_prove_completion(self):
        tracker = ParallelBatchProgress(3)
        batch, _ = tracker.snapshot({'a': ProgressEvent(100, 100, 100, 10),
                                     'b': ProgressEvent(20, 20, 100, 5)})
        self.assertEqual(batch.completed_items, 0)
        self.assertEqual(batch.active_items, 2)
        batch, stats = tracker.snapshot({'b': ProgressEvent(10, 10, 100, 3)})
        self.assertEqual(batch.completed_items, 0)
        self.assertEqual(batch.active_items, 1)
        self.assertEqual(stats.speed_bytes_per_second, 3)
        self.assertEqual(batch.aggregate_percent, 40)
        self.assertIsNone(stats.total_bytes)
        batch, _ = tracker.finish_item('a')
        self.assertEqual(batch.completed_items, 1)
        self.assertEqual(tracker.finish_item('a')[0], batch)

    def test_weight_switch_unknown_items_and_reordered_updates(self):
        tracker = ParallelBatchProgress(3)
        batch, stats = tracker.snapshot({'a': ProgressEvent(90, 90, 100, 20),
                                         'b': ProgressEvent(downloaded_bytes=7)})
        self.assertEqual(batch.aggregate_percent, 30)
        self.assertEqual(stats.downloaded_bytes, 97)
        self.assertIsNone(stats.total_bytes)
        self.assertIsNone(stats.speed_bytes_per_second)
        batch, stats = tracker.snapshot({'a': ProgressEvent(80, 80, 100, 10),
                                         'b': ProgressEvent(1, 10, 1000, 20),
                                         'c': ProgressEvent(0, 0, 1000, 0)})
        self.assertEqual(stats.total_bytes, 2100)
        self.assertEqual(stats.speed_bytes_per_second, 30)
        self.assertEqual(batch.aggregate_percent, 30)  # No drop on weighting change.
        tracker.finish_item('a')
        batch, _ = tracker.snapshot({'a': ProgressEvent(0), 'b': ProgressEvent(5)})
        self.assertEqual(batch.completed_items, 1)
        self.assertEqual(batch.active_items, 1)  # Stale completed GID never revives.
        self.assertEqual(tracker.complete(), ParallelBatchEvent(3, 0, 3, 100))

    def test_only_verified_complete_notice_or_ok_table_row_counts(self):
        parser = Aria2ParallelProgressParser(2)
        parser.feed(summary(('abcdef', 100, 100, 100, 0)))
        self.assertEqual(parser.feed(b'warning Download complete: /tmp/abcdef.bin\n'), [])
        self.assertEqual(parser.feed(notice('abcdef')), [Aria2Completed('abcdef')])
        self.assertEqual(parser.feed(notice('fedcba')), [])  # No guessed GID.
        self.assertEqual(parser.feed(b'Download Results:\nfedcba|ERR | 1B/s|/tmp/b\n'), [])
        self.assertEqual(parser.feed(b'fedcba|OK  | 1B/s|/tmp/b', final=True), [Aria2Completed('fedcba')])


class BulkCommandTests(unittest.TestCase):
    FLAGS = ['aria2c', '--continue=true', '--max-connection-per-server=1', '--split=1',
             '--min-split-size=1M', '--console-log-level=warn', '--summary-interval=1']

    def test_cli_parallel_flags_output_file_lifetime_and_cleanup_unchanged(self):
        paths = []
        urls = ['https://example.test/a?x=1&y=2', 'https://example.test/b']
        def run(command):
            path = Path(command[-1].split('=', 1)[1])
            paths.append(path)
            self.assertEqual(path.read_text(), '\n'.join(urls) + '\n')
            self.assertEqual(command, self.FLAGS + ['--max-concurrent-downloads=2', f'--input-file={path}'])
            return 0
        output = StringIO()
        with patch.object(downloader, 'run_command', side_effect=run), redirect_stdout(output):
            self.assertEqual(downloader.download_direct_bulk(urls), 0)
        self.assertFalse(paths[0].exists())
        self.assertEqual(output.getvalue(), 'Input type: direct HTTP files\nDownload engine: aria2c\n2 Files Downloaded Successfully 💫🎉\n')
        command = build_direct_bulk_parallel_command('/tmp/urls.txt', 2, '/tmp/a b', telemetry=True)
        self.assertIn('--console-log-level=notice', command)
        self.assertIn('--human-readable=false', command)
        self.assertIn('--dir=/tmp/a b', command)

    def test_cli_sequential_stops_on_failure_and_success_wording_preserved(self):
        for results in ([0, 7], [0, 0, 0]):
            out = StringIO()
            with patch.object(downloader, 'download_direct', side_effect=results) as run, redirect_stdout(out):
                code = downloader.download_direct_bulk_sequential(['a', 'b', 'c'])
            self.assertEqual(code, results[-1])
            self.assertEqual([call.args[0] for call in run.call_args_list], ['a','b','c'][:len(results)])
            self.assertEqual('3 Files Downloaded Successfully 💫🎉' in out.getvalue(), code == 0)


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication
    from gui_execution import DirectBulkDownloadProcess, ExecutionOutcome
    from aidm_gui import GuiState
    import test_gui_execution as gui_tests
except ImportError:
    gui_tests = None


@unittest.skipIf(gui_tests is None, 'Requires PySide6')
class DirectBulkGuiTests(unittest.TestCase):
    if gui_tests is not None:
        setUp = gui_tests.GuiExecutionTests.setUp
        tearDown = gui_tests.GuiExecutionTests.tearDown
        inspect = gui_tests.GuiExecutionTests.inspect

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def start_bulk(self, mode):
        self.window.input_field.clear()
        self.inspect(InputKind.DIRECT_BULK)
        self.window.on_download_intent()
        self.window.bulk_buttons[mode].click()
        self.window.on_download_intent()
        worker = self.window._download_process
        self.assertIsInstance(worker, DirectBulkDownloadProcess)
        return worker

    def feed(self, worker, data):
        worker.process.stdout = data
        worker.process.readyReadStandardOutput.emit()

    def input_path(self, worker):
        return Path(next(arg.split('=', 1)[1] for arg in worker.process.calls[0][1]
                         if arg.startswith('--input-file=')))

    def test_sequential_order_position_runtime_name_aggregate_and_success(self):
        worker = self.start_bulk(BulkMode.SEQUENTIAL)
        process = worker.process
        self.assertEqual(len(process.calls), 1)
        self.assertEqual(process.calls[0][1][-1], worker.job.urls[0])
        self.assertEqual(self.window.queue_position.text(), '1 / 2')
        self.assertTrue(self.window.media_title.isHidden())
        process.begin()
        self.feed(worker, b'FILE: /tmp/runtime-name.iso\n[#abcdef 80B/100B(80%) CN:1 DL:5B ETA:4s]\n')
        self.assertEqual(self.window.media_title.text(), 'runtime-name.iso')
        self.assertEqual(self.window.progress.value(), 40)
        self.assertEqual(self.window.statistics.text(), '5 B/s • 80 B / 100 B • ETA 00:04')
        self.assertEqual(self.window.active_status.text(), 'Downloading item 1 of 2… ⬇️')
        process.finish()
        self.assertEqual(len(process.calls), 1)  # No inline launch in finished callback.
        self.app.processEvents()
        self.assertIs(worker.process, process)
        self.assertEqual(len(process.calls), 2)
        self.assertEqual(process.calls[1][1][-1], worker.job.urls[1])
        self.assertIn('--dir=' + worker.job.destination, process.calls[1][1])
        self.assertEqual(self.window.queue_position.text(), '2 / 2')
        self.assertTrue(self.window.media_title.isHidden())
        self.assertTrue(self.window.statistics.isHidden())
        self.assertEqual(self.window.progress.value(), 50)
        process.begin()
        self.feed(worker, b'[#abcdef 0B/100B(0%) CN:1]\nFILE: /tmp/next.bin\n')
        self.assertEqual(self.window.progress.value(), 50)
        self.assertEqual(self.window.media_title.text(), 'next.bin')
        self.assertEqual(self.window.active_status.text(), 'Downloading item 2 of 2… ⬇️')
        process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.assertEqual(self.window.batch_summary.text(), '2 files downloaded')
        self.assertEqual(self.window.result_message.text(), 'Download complete 🎉💫')
        self.assertTrue(self.window.media_title.isHidden())

    def test_sequential_abort_at_finish_and_signal_boundary_never_starts_next(self):
        for when in ('running', 'gap', 'baseline_signal', 'next_signal'):
            worker = self.start_bulk(BulkMode.SEQUENTIAL)
            worker.process.begin()
            if when == 'running':
                self.window.abort_button.click()
            elif when == 'gap':
                worker.process.finish()
                self.window.abort_button.click()
            else:
                worker.batch_event.connect(lambda event, w=worker, phase=when:
                    w.abort() if (event.aggregate_percent == 50 if phase == 'baseline_signal'
                                  else event.current_index == 2) else None)
                worker.process.finish()
            self.app.processEvents()
            self.assertEqual(self.window.current_state, GuiState.ABORTED, when)
            self.assertEqual(len([c for c in worker.process.calls if isinstance(c, tuple)]), 1)
            self.assertTrue(self.window.batch_summary.isHidden())

    def test_sequential_failure_stops_first_and_retry_restarts_same_job(self):
        worker = self.start_bulk(BulkMode.SEQUENTIAL)
        job = worker.job
        worker.process.finish(7)
        self.app.processEvents()
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertEqual(len(worker.process.calls), 1)
        self.window.retry_button.click()
        retry = self.window._download_process
        self.assertIs(retry.job, job)
        self.assertEqual(retry.process.calls[0][1][-1], job.urls[0])
        self.assertEqual(self.window.queue_position.text(), '1 / 2')
        self.assertTrue(self.window.media_title.isHidden())
        retry.process.finish(7)

    def test_parallel_one_process_lifetime_counts_metrics_and_no_current_identity(self):
        worker = self.start_bulk(BulkMode.PARALLEL)
        path = self.input_path(worker)
        self.assertEqual(path.read_text(), '\n'.join(worker.job.urls) + '\n')
        self.assertIn('--dir=' + worker.job.destination, worker.process.calls[0][1])
        self.assertIn('--max-concurrent-downloads=2', worker.process.calls[0][1])
        worker.process.begin()
        self.feed(worker, summary(('abcdef', 50, 100, 50, 10), ('fedcba', 20, 200, 10, 20)))
        self.assertEqual(self.window.queue_position.text(), '2 files • 2 active • 0 complete')
        self.assertTrue(self.window.media_title.isHidden())
        self.assertEqual(self.window.statistics.text(), '30 B/s • 70 B / 300 B')
        self.assertEqual(self.window.progress.value(), 23)
        self.assertEqual(self.window.active_status.text(), 'Downloading in parallel… ⚡')
        self.feed(worker, notice('abcdef'))
        self.assertEqual(self.window.queue_position.text(), '2 files • 1 active • 1 complete')
        self.assertEqual(self.window.statistics.text(), '20 B/s • 120 B / 300 B')
        self.assertTrue(path.exists())
        self.assertEqual(len(worker.process.calls), 1)
        worker.process.finish()
        self.assertFalse(path.exists())
        self.assertFalse(path.parent.exists())
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.assertEqual(self.window.batch_summary.text(), '2 files downloaded')
        self.assertTrue(self.window.media_title.isHidden())
        self.assertTrue(self.window.queue_position.isHidden())

    def test_parallel_failure_abort_start_failure_retry_and_close_cleanup(self):
        for terminal in ('failure', 'abort', 'start_failure', 'close'):
            worker = self.start_bulk(BulkMode.PARALLEL)
            path = self.input_path(worker)
            job = worker.job
            if terminal == 'start_failure':
                worker.process.current_state = QProcess.ProcessState.NotRunning
                worker.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            else:
                worker.process.begin()
                if terminal == 'failure':
                    self.feed(worker, summary(('abcdef', 50, 100, 50, 10)))
                    self.feed(worker, notice('abcdef'))
                    worker.process.finish(7)
                elif terminal == 'abort':
                    worker.process.stop_on_terminate = False
                    worker.abort()
                    self.assertTrue(path.exists())
                    worker.process.finish(0)  # Abort wins racing success.
                else:
                    self.assertTrue(worker.shutdown())
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())
            if terminal == 'close':
                self.window.set_state(GuiState.ABORTED)
                continue
            self.assertEqual(self.window.current_state, GuiState.ABORTED if terminal == 'abort' else GuiState.FAILED)
            self.assertTrue(self.window.batch_summary.isHidden())
            self.assertTrue(self.window.media_title.isHidden())
            self.window.retry_button.click()
            retry = self.window._download_process
            self.assertIs(retry.job, job)
            new_path = self.input_path(retry)
            self.assertNotEqual(new_path, path)
            self.assertEqual(new_path.read_text(), '\n'.join(job.urls) + '\n')
            self.assertEqual(self.window.queue_position.text(), '2 files • 0 active • 0 complete')
            worker.batch_event.emit(ParallelBatchEvent(2, 0, 2, 100))
            self.assertEqual(self.window._batch_event.completed_items, 0)
            retry.process.finish(7)

    def test_parallel_unknown_total_uses_downloaded_only_and_item_weighting(self):
        worker = self.start_bulk(BulkMode.PARALLEL)
        worker.process.begin()
        payload = summary(('abcdef', 50, 100, 50, 10), ('fedcba', 20, 200, 10, 20))
        self.feed(worker, payload.replace(b'20B/200B(10%)', b'20B/0B'))
        self.assertEqual(self.window.progress.value(), 25)
        self.assertEqual(self.window.statistics.text(), '30 B/s • 70 B downloaded')
        self.assertTrue(self.window.media_title.isHidden())
        self.feed(worker, notice('fedcba'))
        self.assertEqual(self.window.progress.value(), 75)
        self.assertEqual(self.window.queue_position.text(), '2 files • 1 active • 1 complete')
        worker.process.finish()

    def test_parallel_presentation_is_driven_by_event_not_job_route(self):
        self.inspect(InputKind.DIRECT_SINGLE)
        self.window.on_download_intent()
        worker = self.window._download_process
        worker.process.begin()
        worker.filename_resolved.emit('single-file-name.bin')
        worker.batch_event.emit(ParallelBatchEvent(10, 4, 3, 40))
        self.assertEqual(self.window.queue_position.text(), '10 files • 4 active • 3 complete')
        self.assertTrue(self.window.media_title.isHidden())
        self.assertEqual(self.window.active_status.text(), 'Downloading in parallel… ⚡')
        worker.process.finish(7)

    def test_parallel_temp_creation_failure_is_failed_and_cleans_partial_resource(self):
        with patch('gui_execution.Path.write_text', side_effect=OSError('fixture disk error')):
            worker = self.start_bulk(BulkMode.PARALLEL)
        self.assertEqual(self.window.current_state, GuiState.FAILED)
        self.assertIsNone(worker._input_directory)
        self.assertEqual(worker.process.calls, [])
        self.assertIn(b'fixture disk error', worker.stderr_tail)

    def test_sequential_close_in_gap_stops_advance(self):
        worker = self.start_bulk(BulkMode.SEQUENTIAL)
        worker.process.finish()
        self.assertTrue(worker.shutdown())
        self.app.processEvents()
        self.assertEqual(len(worker.process.calls), 1)


if __name__ == '__main__':
    unittest.main()
