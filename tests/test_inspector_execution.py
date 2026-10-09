"""Offline Inspector command contracts, workflow stages and shared Qt lifecycle."""
import builtins
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError, replace
from io import StringIO
import os
from pathlib import Path
import runpy
import shlex
import sys
import unittest
from unittest.mock import patch

import aidm
import downloader
from download_job import DownloadJob, build_download_job, YouTubeMode
from inspection import InputKind, classify_input
from metadata import prepare_metadata, build_metadata_command
from progress_event import ProgressEvent
from status_event import StatusEvent, StatusKind
from stream_parser import StreamInput
from utils import sanitize_filename
from workflow_warning import WorkflowWarning
from ytdlp_progress import DOWNLOAD_TEMPLATE, POSTPROCESS_TEMPLATE, YtDlpProgressParser

URL = 'https://example.test/media?token=a%2Fb&signature=x=y'
SUBTITLE = 'https://example.test/subtitle.VTT?token=c%2Fd&language=en'
HEADERS = {'User-Agent': 'Browser UA / 123', 'Referer': 'https://example.test/player?a=1&b=2'}
TITLE = 'Browser / Movie: café'
DESTINATION = '/tmp/inspector destination'


class InspectorCommandTests(unittest.TestCase):
    def test_builders_keep_exact_cli_commands_and_opt_in_destination_telemetry(self):
        title_options = ['-o', sanitize_filename(TITLE) + '.%(ext)s']
        header_options = [arg for k, v in HEADERS.items() for arg in ('--add-header', f'{k}:{v}')]
        generic = ['yt-dlp'] + title_options + header_options + [
            '--downloader', 'aria2c', '--downloader', 'dash,m3u8:native',
            '--downloader-args', 'aria2c:-x 8 -s 8 -k 1M', URL,
        ]
        self.assertEqual(downloader.build_ytdlp_media_command(URL, TITLE, HEADERS), generic)
        for stream_type in ('hls', 'dash'):
            stream = StreamInput(URL, HEADERS, stream_type, TITLE)
            expected = ['yt-dlp', '--downloader', 'dash,m3u8:native'] + title_options + header_options + [URL]
            self.assertEqual(downloader.build_stream_command(stream), expected)
            gui = downloader.build_stream_command(stream, destination=DESTINATION, telemetry=True)
            self.assertNotIn('aria2c', gui)
            self.assertEqual(gui[-1], URL)
            self.assertEqual(gui[gui.index('-P')+1], DESTINATION)
            self.assertIn(DOWNLOAD_TEMPLATE, gui)
            self.assertIn(POSTPROCESS_TEMPLATE, gui)
            self.assertTrue(all(option in gui for option in header_options))
        gui = downloader.build_ytdlp_media_command(URL, TITLE, HEADERS, destination=DESTINATION, telemetry=True)
        self.assertEqual(gui[-1], URL)
        self.assertEqual(gui[gui.index('-P')+1], DESTINATION)
        self.assertIn('--human-readable=false', gui[gui.index('--downloader-args')+1])
        self.assertIn(DOWNLOAD_TEMPLATE, gui)
        self.assertNotIn('-P', generic)
        self.assertFalse(any('AIDM_' in value for value in generic))

    def test_subtitle_suffix_title_headers_destination_and_cli_defaults(self):
        for suffix in ('.vtt', '.srt', '.ass', '.ssa', '.ttml', '.dfxp', '.unknown', ''):
            url = 'https://example.test/sub' + suffix.upper() + '?token=a%2Fb'
            expected_suffix = suffix if suffix in ('.vtt', '.srt', '.ass', '.ssa', '.ttml', '.dfxp') else '.vtt'
            expected = ['aria2c', '--continue=true', '--console-log-level=warn', '--summary-interval=1',
                        '--out=' + sanitize_filename(TITLE) + expected_suffix,
                        *[f'--header={k}:{v}' for k,v in HEADERS.items()], url]
            self.assertEqual(downloader.build_subtitle_command(url, TITLE, HEADERS), expected)
            self.assertEqual(downloader.build_subtitle_command(url, TITLE, HEADERS, destination=DESTINATION),
                             expected[:-1] + ['--dir=' + DESTINATION, url])

    def test_cli_wrappers_share_builders_and_preserve_prints_and_return_codes(self):
        stream = StreamInput(URL, HEADERS, 'hls', TITLE)
        cases = (
            ('build_stream_command', lambda: downloader.download_stream(stream),
             'Input type: HLS stream\nExtractor/downloader: yt-dlp native\nPost-processing: FFmpeg when required\n'),
            ('build_ytdlp_media_command', lambda: downloader.download_with_ytdlp(URL, TITLE, HEADERS),
             'Input type: supported website/media URL\nExtractor: yt-dlp\nDownload engine: aria2c where supported\n'),
            ('build_subtitle_command', lambda: downloader.download_subtitle(SUBTITLE, TITLE, HEADERS), ''),
        )
        for name, invoke, expected in cases:
            output = StringIO()
            with patch.object(downloader, name, return_value=['fixture']) as build, \
                 patch.object(downloader, 'run_command', return_value=7) as run, redirect_stdout(output):
                self.assertEqual(invoke(), 7)
            self.assertEqual(output.getvalue(), expected)
            build.assert_called_once()
            self.assertNotIn('destination', build.call_args.kwargs)
            run.assert_called_once_with(['fixture'])

    def test_cli_media_first_routing_and_nonfatal_sidecar_semantics(self):
        for stream_type in ('hls', 'dash', None):
            for media_code, subs, title, sidecar_code, warning in (
                (7, [SUBTITLE], TITLE, 0, ''), (0, [], TITLE, 0, ''),
                (0, [SUBTITLE], TITLE, 0, ''),
                (0, [SUBTITLE], TITLE, 7, 'Warning: subtitle download failed; main media downloaded successfully.\n'),
                (0, [SUBTITLE, SUBTITLE], TITLE, 0, 'Warning: multiple subtitle sidecars are not yet supported; subtitles skipped.\n'),
                (0, [SUBTITLE], None, 0, 'Warning: subtitle skipped because no title was supplied for deterministic sidecar naming.\n'),
            ):
                calls = []
                stream = StreamInput(URL, HEADERS, stream_type, title, subs)
                out = StringIO()
                def media(*args, **kw):
                    calls.append('media')
                    return media_code
                def subtitle(*args, **kw):
                    self.assertEqual(calls, ['media'])
                    self.assertEqual(args, (SUBTITLE, title))
                    self.assertEqual(kw, {'headers': HEADERS})
                    calls.append('subtitle')
                    return sidecar_code
                with patch('aidm.download_stream', side_effect=media) as native, \
                     patch('aidm.download_with_ytdlp', side_effect=media) as generic, \
                     patch('aidm.download_subtitle', side_effect=subtitle), redirect_stdout(out):
                    self.assertEqual(aidm.download_media_with_sidecar(stream), media_code)
                self.assertEqual(native.call_count, int(stream_type is not None))
                self.assertEqual(generic.call_count, int(stream_type is None))
                self.assertEqual(out.getvalue(), warning)
                self.assertEqual(len(calls), 2 if media_code == 0 and len(subs) == 1 and title else 1)

    def test_shared_warning_contract_has_no_qt_and_is_semantic(self):
        original = builtins.__import__
        def no_qt(name, *args, **kwargs):
            if name.startswith(('PySide', 'PyQt')):
                raise AssertionError('Warning must not import Qt')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=no_qt):
            runpy.run_path('workflow_warning.py')
        self.assertEqual(downloader.select_subtitle_sidecar([], TITLE), (None, None))
        self.assertEqual(downloader.select_subtitle_sidecar([SUBTITLE], TITLE), (SUBTITLE, None))

    def test_immutable_job_has_exact_context_and_no_rediscovery_or_options(self):
        args = aidm.parse_args([URL, '--title', TITLE, '--user-agent', HEADERS['User-Agent'],
                                '--referer', HEADERS['Referer'], '--subtitle', SUBTITLE])
        with patch('inspection.detect_stream_type', return_value='hls'):
            result = prepare_metadata(classify_input(args))
        self.assertIsNone(build_metadata_command(result))
        job = build_download_job(result, destination=DESTINATION)
        result.stream.headers['User-Agent'] = 'changed'
        result.stream.subtitles.clear()
        result.stream.title = 'changed'
        self.assertEqual(job.urls, (URL,))
        self.assertEqual(dict(job.headers), HEADERS)
        self.assertEqual(job.subtitles, (SUBTITLE,))
        self.assertEqual(job.title, TITLE)
        self.assertEqual(job.destination, DESTINATION)
        self.assertEqual(job.route_kind, InputKind.HLS)
        with self.assertRaises(TypeError):
            job.headers['Referer'] = 'changed'
        with self.assertRaises(FrozenInstanceError):
            job.title = 'changed'


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication
    from aidm_gui import GuiState
    from gui_execution import StreamInspectorDownloadProcess, create_download_process, UnsupportedExecution, ExecutionOutcome
    import test_gui_execution as gui_tests
except ImportError:
    gui_tests = None


@unittest.skipIf(gui_tests is None, 'Requires PySide6')
class InspectorGuiTests(unittest.TestCase):
    if gui_tests is not None:
        setUp = gui_tests.GuiExecutionTests.setUp
        tearDown = gui_tests.GuiExecutionTests.tearDown
        wait_for = gui_tests.GuiExecutionTests.wait_for

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def start_inspector(self, route=InputKind.HLS, title=TITLE, subtitles=(SUBTITLE,)):
        self.window.input_field.clear()
        url = {InputKind.YOUTUBE_SINGLE: 'https://youtube.com/watch?v=abcdefghijk&token=a%2Fb',
               InputKind.YOUTUBE_PLAYLIST: 'https://youtube.com/playlist?list=PLtest&token=a%2Fb'}.get(route, URL)
        args = [url, '--user-agent', HEADERS['User-Agent'], '--referer', HEADERS['Referer']]
        if title is not None:
            args += ['--title', title]
        for subtitle in subtitles:
            args += ['--subtitle', subtitle]
        self.window.input_field.setText(shlex.join(args))
        self.window._inspection_timer.stop()
        self.window._pending = None
        stream_type = {InputKind.HLS:'hls', InputKind.DASH:'dash'}.get(route)
        with patch('inspection.detect_stream_type', return_value=stream_type), \
             patch('inspection.looks_like_direct_file', return_value=route == InputKind.DIRECT_SINGLE):
            result = classify_input(self.window.input_result.args)
        self.window.finish_inspection(self.window._revision, result, '')
        self.assertEqual(self.window.current_state, GuiState.READY)
        self.assertFalse(self.window._metadata_timer.isActive())
        self.window.on_download_intent()
        worker = self.window._download_process
        self.assertIsInstance(worker, StreamInspectorDownloadProcess)
        self.assertFalse(self.window._configuration_started)
        return worker

    def feed(self, worker, payload):
        worker.process.stdout = payload
        worker.process.readyReadStandardOutput.emit()

    def enter_subtitle(self, worker):
        media = worker.process
        media.finish()
        self.assertTrue(worker.active)
        self.assertFalse(worker.done)
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        self.assertTrue(self.window.progress.isHidden())
        worker.start_subtitle()  # Also allow emitting old-stage signals before deferred deletion.
        self.assertIsNot(worker.process, media)
        self.assertEqual(worker.process.calls[0][0], 'aria2c')
        worker.process.begin()
        self.assertEqual(self.window.active_status.text(), 'Downloading subtitle… 📄')
        return media

    def test_factory_hls_dash_and_other_inspector_routes_need_no_secondary_options(self):
        for route in (InputKind.HLS, InputKind.DASH, InputKind.GENERIC_YTDLP,
                      InputKind.DIRECT_SINGLE, InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_PLAYLIST):
            worker = self.start_inspector(route, subtitles=())
            program, args = worker.process.calls[0]
            self.assertEqual(program, 'yt-dlp')
            self.assertEqual(args[-1], worker.job.urls[0])
            self.assertEqual(args[args.index('-P')+1], worker.job.destination)
            self.assertEqual(args[args.index('-o')+1], sanitize_filename(TITLE) + '.%(ext)s')
            self.assertEqual('aria2c' in args, route not in (InputKind.HLS, InputKind.DASH))
            self.assertIn('dash,m3u8:native', args)
            for key, value in HEADERS.items():
                self.assertIn(f'{key}:{value}', args)
            self.assertIsNone(worker.job.mode)
            self.assertIsNone(worker.job.video_quality)
            self.assertTrue(self.window.mode_options.isHidden())
            self.assertTrue(self.window.quality_options.isHidden())
            self.assertTrue(self.window.bulk_options.isHidden())
            worker.process.finish()
            self.assertEqual(self.window.current_state, GuiState.COMPLETE)
            self.assertIsNone(self.window._workflow_warning)
            self.assertEqual(len(worker.process.calls), 1)
        for kind in (InputKind.HLS, InputKind.DASH, InputKind.GENERIC_YTDLP, InputKind.TORRENT):
            with self.assertRaises(UnsupportedExecution):
                create_download_process(DownloadJob(kind, (URL,), str(self.directory)))

    def test_successful_media_then_subtitle_one_terminal_event_and_context(self):
        worker = self.start_inspector()
        outcomes = []
        worker.finished.connect(outcomes.append)
        self.assertEqual(self.window.active_status.text(), 'Starting yt-dlp… ⚙️')
        worker.process.begin()
        self.assertEqual(self.window.active_status.text(), 'Downloading… ⬇️')
        self.feed(worker, b'AIDM_PROGRESS:{"progress":{"status":"downloading","downloaded_bytes":50,"total_bytes":100},"info":{}}\n')
        self.assertEqual(self.window.progress.value(), 50)
        self.enter_subtitle(worker)
        self.assertEqual(outcomes, [])
        command = worker.process.calls[0][1]
        self.assertEqual(command[-1], SUBTITLE)
        self.assertIn('--out=' + sanitize_filename(TITLE) + '.vtt', command)
        self.assertIn('--dir=' + worker.job.destination, command)
        for k,v in HEADERS.items():
            self.assertIn(f'--header={k}:{v}', command)
        self.assertTrue(self.window.statistics.isHidden())
        self.feed(worker, b'FILE: /tmp/wrong-name.vtt\n[#abcdef 50B/100B(50%) CN:1]\n')
        self.assertTrue(self.window.progress.isHidden())
        self.assertEqual(self.window.media_title.full_title, TITLE)
        worker.process.finish()
        self.assertEqual(outcomes, [ExecutionOutcome.COMPLETE])
        self.assertEqual(self.window.result_message.text(), 'Download complete 🎉💫')
        self.assertEqual(self.window.media_title.full_title, TITLE)
        self.assertTrue(self.window.workflow_warning.isHidden())

    def test_media_parser_reused_captures_unknown_totals_and_title_authority(self):
        worker = self.start_inspector(subtitles=())
        worker.process.begin()
        self.assertIsInstance(worker._progress_parser, YtDlpProgressParser)
        self.feed(worker, (Path(__file__).parent / 'fixtures/ytdlp/native.txt').read_bytes())
        self.feed(worker, b'AIDM_ITEM:{"video_autonumber":1,"title":"Wrong title"}\n')
        self.assertIsNone(self.window._batch_event)
        self.window.inspection_result.title = 'Mutable inspection title'
        self.feed(worker, b'AIDM_PROGRESS:{"progress":{"status":"downloading","downloaded_bytes":120,"total_bytes_estimate":999},"info":{}}\n')
        self.assertTrue(self.window.progress.isHidden())
        self.assertEqual(self.window.statistics.text(), '120 B downloaded')
        self.assertEqual(self.window.media_title.full_title, TITLE)
        worker.process.finish()
        self.assertEqual(self.window.media_title.full_title, TITLE)

    def test_multiple_subtitles_or_missing_title_skip_with_visible_nonfatal_warning(self):
        for subtitles, title, warning in (
            ((SUBTITLE, SUBTITLE), TITLE, WorkflowWarning.MULTIPLE_SUBTITLES_SKIPPED),
            ((SUBTITLE,), None, WorkflowWarning.SUBTITLE_WITHOUT_TITLE),
        ):
            worker = self.start_inspector(title=title, subtitles=subtitles)
            media = worker.process
            media.finish()
            self.assertIs(worker.process, media)
            self.assertEqual(self.window.current_state, GuiState.COMPLETE)
            self.assertEqual(self.window._workflow_warning, warning)
            self.assertFalse(self.window.workflow_warning.isHidden())
            self.assertIn('skipped', self.window.workflow_warning.text())
            self.assertTrue(self.window.retry_button.isHidden())
        self.window.input_field.clear()
        self.assertIsNone(self.window._workflow_warning)
        self.assertTrue(self.window.workflow_warning.isHidden())

    def test_subtitle_nonzero_crash_and_start_failure_are_complete_with_warning(self):
        for failure in ('nonzero', 'crash', 'start'):
            worker = self.start_inspector()
            worker.process.finish()
            worker.start_subtitle()
            if failure == 'start':
                worker.process.current_state = QProcess.ProcessState.NotRunning
                worker.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            else:
                worker.process.begin()
                worker.process.finish(7, QProcess.ExitStatus.CrashExit if failure == 'crash' else QProcess.ExitStatus.NormalExit)
            self.assertEqual(self.window.current_state, GuiState.COMPLETE)
            self.assertEqual(self.window.result_message.text(), 'Download complete 🎉💫')
            self.assertEqual(self.window.workflow_warning.text(), 'Subtitle could not be downloaded ⚠️')
            self.assertFalse(self.window.workflow_warning.isHidden())
            self.assertEqual(self.window.media_title.full_title, TITLE)
            self.assertTrue(self.window.retry_button.isHidden())

    def test_media_nonzero_crash_and_start_failure_do_not_launch_subtitle(self):
        for failure in ('nonzero', 'crash', 'start'):
            worker = self.start_inspector()
            media = worker.process
            if failure == 'start':
                media.current_state = QProcess.ProcessState.NotRunning
                media.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            else:
                media.begin()
                media.finish(7, QProcess.ExitStatus.CrashExit if failure == 'crash' else QProcess.ExitStatus.NormalExit)
            worker.start_subtitle()
            self.assertEqual(self.window.current_state, GuiState.FAILED)
            self.assertIs(worker.process, media)
            self.assertFalse(self.window.retry_button.isHidden())
            self.assertTrue(self.window.workflow_warning.isHidden())
            self.assertEqual(self.window.media_title.full_title, TITLE)

    def test_abort_media_gap_and_subtitle_prevents_further_launches(self):
        for when in ('media', 'gap', 'subtitle', 'clearing_signal', 'starting_signal'):
            worker = self.start_inspector()
            media = worker.process
            media.begin()
            if when == 'subtitle':
                self.enter_subtitle(worker)
                worker.process.stop_on_terminate = False
            elif when == 'gap':
                media.finish()
            elif when == 'clearing_signal':
                worker.progress_event.connect(lambda event, w=worker: w.abort())
                media.finish()
            elif when == 'starting_signal':
                worker.status_event.connect(lambda event, w=worker:
                    w.abort() if event.kind == StatusKind.STARTING_ENGINE and event.engine == 'aria2c' else None)
                media.finish()
                worker.start_subtitle()
            if when not in ('clearing_signal', 'starting_signal'):
                worker.abort()
            if when == 'subtitle':
                worker.process.finish(0)  # User Abort wins a racing successful exit.
            self.app.processEvents()
            self.assertEqual(self.window.current_state, GuiState.ABORTED, when)
            self.assertFalse(worker._stage_timer.isActive())
            self.assertTrue(self.window.workflow_warning.isHidden())
            if when in ('media', 'gap', 'clearing_signal'):
                self.assertIs(worker.process, media)
            if when == 'starting_signal':
                self.assertEqual(worker.process.calls, [])

    def test_old_stage_signals_and_repeated_finished_are_ignored(self):
        worker = self.start_inspector()
        media = worker.process
        media.finish()
        # Already-reaped media cannot fail the workflow during the handoff gap.
        media.finish(7)
        media.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.assertFalse(worker.done)
        worker.start_subtitle()
        worker.process.begin()
        for emit in (
            lambda: media.started.emit(), lambda: media.finish(7),
            lambda: media.errorOccurred.emit(QProcess.ProcessError.FailedToStart),
            lambda: media.readyReadStandardOutput.emit(),
        ):
            media.stdout = b'AIDM_PROGRESS:{"progress":{"status":"downloading","downloaded_bytes":1,"total_bytes":1}}\n'
            emit()
            self.assertEqual(self.window.active_status.text(), 'Downloading subtitle… 📄')
            self.assertFalse(worker.done)
            self.assertEqual(self.window._progress_event, ProgressEvent())
        worker.process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)

    def test_retry_exact_snapshot_and_stale_attempt_warning_status_progress(self):
        worker = self.start_inspector()
        job = worker.job
        worker.process.begin()
        worker.abort()
        self.window.destination = '/not-the-job-folder'
        with patch('aidm_gui.build_download_job', side_effect=AssertionError('rebuilt job')), \
             patch('aidm_gui.classify_input', side_effect=AssertionError('reclassified')):
            self.window.retry_button.click()
        retry = self.window._download_process
        self.assertIs(retry.job, job)
        self.assertEqual(retry.process.calls[0], worker.process.calls[0])
        worker.warning_event.emit(WorkflowWarning.SUBTITLE_FAILED)
        worker.status_event.emit(StatusEvent(StatusKind.FAILED))
        worker.progress_event.emit(ProgressEvent(99))
        worker.finished.emit(ExecutionOutcome.FAILED)
        self.assertIsNone(self.window._workflow_warning)
        self.assertIsNone(self.window._progress_event)
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        retry.process.finish(7)
        self.window.retry_button.click()
        self.assertIs(self.window._download_process.job, job)

    def test_warning_cannot_change_terminal_state_and_resets_on_preview(self):
        worker = self.start_inspector(subtitles=())
        worker.warning_event.emit(WorkflowWarning.SUBTITLE_FAILED)
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        worker.process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.window.preview_state(GuiState.EMPTY)
        self.assertIsNone(self.window._workflow_warning)
        self.assertTrue(self.window.workflow_warning.isHidden())

    def test_close_in_media_gap_or_subtitle_stops_workflow_without_terminal_signals(self):
        for stage in ('media', 'gap', 'subtitle'):
            worker = self.start_inspector()
            outcomes = []
            worker.finished.connect(outcomes.append)
            worker.process.begin()
            if stage == 'gap':
                worker.process.finish()
            elif stage == 'subtitle':
                self.enter_subtitle(worker)
            worker.process.stop_on_terminate = False
            self.assertTrue(worker.shutdown())
            worker.start_subtitle()
            self.app.processEvents()
            self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)
            self.assertEqual(outcomes, [])
            self.assertFalse(worker._stage_timer.isActive())
            self.window.set_state(GuiState.ABORTED)

    def test_media_group_cleanup_finishes_before_subtitle_and_abort_wins(self):
        for abort in (False, True):
            worker = self.start_inspector()
            media = worker.process
            media.begin()
            with patch.object(worker, 'group_running', return_value=True):
                media.finish()
            self.assertEqual(worker._pending_outcome, ExecutionOutcome.COMPLETE)
            self.assertFalse(worker._between_stages)
            if abort:
                worker.abort()
            with patch.object(worker, 'group_running', return_value=False):
                worker.finish_group_cleanup()
            if abort:
                self.assertEqual(self.window.current_state, GuiState.ABORTED)
            else:
                self.assertIsNone(worker._pending_outcome)
                self.assertIsNone(worker._process_group)
                self.assertFalse(worker._cleanup_timer.isActive())
                worker.start_subtitle()
                worker.process.finish()
                self.assertEqual(self.window.current_state, GuiState.COMPLETE)

    def test_real_owned_groups_abort_and_close_for_both_stages(self):
        self.process_patch.stop()
        child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('child-ready',flush=True); time.sleep(30)"
        script = ("import subprocess,sys,time; "
                  f"p=subprocess.Popen([sys.executable,'-u','-c',{child!r}]); "
                  "print('child-pid:'+str(p.pid),file=sys.stderr,flush=True); time.sleep(30)")
        for stage in ('media', 'subtitle'):
            for close in (False, True):
                with patch.object(StreamInspectorDownloadProcess, 'build_command',
                                  return_value=[sys.executable, '-u', '-c', script]) as build:
                    if stage == 'subtitle':
                        build.side_effect = [[sys.executable, '-c', 'pass'], [sys.executable, '-u', '-c', script]]
                    worker = self.start_inspector()
                    self.wait_for(lambda: b'child-pid:' in worker.stderr_tail)
                    child_pid = int(worker.stderr_tail.decode().strip().split(':')[-1])
                    # The child readiness record is stdout; retain it outside telemetry.
                    self.wait_for(lambda: Path(f'/proc/{child_pid}/stat').exists())
                    worker._abort_timer.setInterval(100)
                    if close:
                        self.assertTrue(worker.shutdown())
                        self.window.set_state(GuiState.ABORTED)
                    else:
                        worker.abort()
                        self.wait_for(lambda: worker.done)
                        self.assertEqual(self.window.current_state, GuiState.ABORTED)
                    self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)
                    stat = Path(f'/proc/{child_pid}/stat')
                    if stat.exists():
                        self.assertIn(stat.read_text().rsplit(') ', 1)[1].split()[0], {'Z', 'X'})


if __name__ == '__main__':
    unittest.main()
