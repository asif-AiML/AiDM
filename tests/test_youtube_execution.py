"""Offline command, captured telemetry, GUI and real local process-tree checks."""

from dataclasses import replace
import builtins
import json
import os
from pathlib import Path
import sys
import runpy
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import youtube
from download_job import DownloadJob, YouTubeMode, VideoQuality
from inspection import InputKind
from progress_event import ProgressEvent
from status_event import StatusEvent, StatusKind
from ytdlp_progress import YtDlpProgressParser, parse_ytdlp_record, DOWNLOAD_TEMPLATE, POSTPROCESS_TEMPLATE


class YouTubeCommandTests(unittest.TestCase):
    def test_defaults_preserve_cli_commands(self):
        baseline = ["yt-dlp", "--downloader", "aria2c", "--downloader", "dash,m3u8:native",
                    "--downloader-args", "aria2c:-x 8 -s 8 -k 1M"]
        self.assertEqual(youtube.build_youtube_command(), baseline)
        self.assertEqual(youtube.build_youtube_audio_command(), baseline + ["-f", "bestaudio/best"])
        self.assertEqual(youtube.build_youtube_audio_command(wav=True),
                         baseline + ["-f", "bestaudio/best", "--extract-audio", "--audio-format", "wav"])
        for builder in (youtube.build_youtube_video_command, youtube.build_youtube_audio_command):
            command = builder()
            self.assertNotIn("-P", command)
            self.assertNotIn("--progress-template", command)
            self.assertNotIn("--newline", command)
            self.assertNotIn("--recode-video", command)

    def test_destination_and_gui_only_templates(self):
        for builder in (youtube.build_youtube_video_command, youtube.build_youtube_audio_command):
            command = builder(destination="/tmp/chosen folder", telemetry=True)
            self.assertEqual(command[command.index("-P") + 1], "/tmp/chosen folder")
            self.assertIn(DOWNLOAD_TEMPLATE, command)
            self.assertIn(POSTPROCESS_TEMPLATE, command)
            self.assertIn("--newline", command)
            self.assertIn("--human-readable=false", command[command.index("--downloader-args") + 1])


class YouTubeTelemetryTests(unittest.TestCase):
    def test_parser_and_shared_builders_are_qt_independent(self):
        original = builtins.__import__

        def no_qt(name, *args, **kwargs):
            if name.startswith(("PySide", "PyQt")):
                raise AssertionError("Backend telemetry must not import Qt")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_qt):
            runpy.run_path("ytdlp_progress.py")
            runpy.run_path("youtube.py")

    def test_three_shared_command_captures_and_current_stream_progress(self):
        root = Path(__file__).parent / "fixtures" / "ytdlp"
        for name in ("video", "original", "wav"):
            events = YtDlpProgressParser().feed((root / (name + ".txt")).read_bytes(), final=True)
            kinds = [e.kind for e in events if isinstance(e, StatusEvent)]
            self.assertNotIn(StatusKind.COMPLETE, kinds)
            self.assertIn(StatusKind.FINALIZING, kinds)
            self.assertEqual(StatusKind.CONVERTING_AUDIO in kinds, name == "wav")
            self.assertEqual(StatusKind.MERGING in kinds, name == "video")
            if name == "video":
                percents = [e.percent for e in events if isinstance(e, ProgressEvent) and e.percent is not None]
                self.assertTrue(any(b < a for a, b in zip(percents, percents[1:])))

    def test_real_captures_chunking_and_external_aria2(self):
        root = Path(__file__).parent / "fixtures" / "ytdlp"
        for name in ("native", "aria2c"):
            raw = (root / (name + ".txt")).read_bytes()
            expected = YtDlpProgressParser().feed(raw, final=True)
            self.assertTrue(any(isinstance(e, ProgressEvent) and e.percent is not None
                                and 0 < e.percent < 100 for e in expected))
            self.assertIn(StatusEvent(StatusKind.CONVERTING_AUDIO, "yt-dlp"), expected)
            self.assertNotIn(StatusEvent(StatusKind.COMPLETE, "yt-dlp"), expected)
            for size in (1, 7, 103):
                parser = YtDlpProgressParser()
                events = []
                for pos in range(0, len(raw), size):
                    events.extend(parser.feed(raw[pos:pos + size]))
                events.extend(parser.feed(b"", final=True))
                self.assertEqual(events, expected)

    def test_partial_exact_only_and_invalid_records(self):
        prefix = "AIDM_PROGRESS:"
        event = parse_ytdlp_record(prefix + json.dumps({"progress": {
            "status": "downloading", "downloaded_bytes": 50,
            "total_bytes_estimate": 100, "speed": 24.8}, "info": {}}))[-1]
        self.assertEqual(event, ProgressEvent(downloaded_bytes=50, speed_bytes_per_second=24))
        for bad in ("[download] 50% of 10MiB", prefix + "bad", prefix + "[]",
                    prefix + '{"progress":[]}', 'AIDM_POSTPROCESS:{"status":"started","postprocessor":[]}'):
            self.assertEqual(parse_ytdlp_record(bad), [])
        event = parse_ytdlp_record(prefix + '{"progress":{"status":"downloading",'
                                  '"downloaded_bytes":-1,"speed":NaN},"info":{}}')[-1]
        self.assertEqual(event, ProgressEvent())

    def test_phase_status_and_postprocessing_clear_old_metrics(self):
        for info, kind in (({"vcodec": "avc1", "acodec": "none"}, StatusKind.DOWNLOADING_VIDEO),
                           ({"vcodec": "none", "acodec": "opus"}, StatusKind.DOWNLOADING_AUDIO)):
            events = parse_ytdlp_record("AIDM_PROGRESS:" + json.dumps({
                "progress": {"status": "downloading", "downloaded_bytes": 437, "total_bytes": 1000},
                "info": info}))
            self.assertEqual(events, [StatusEvent(kind, "yt-dlp"), ProgressEvent(43.7, 437, 1000)])
        for name, kind in (("Merger", StatusKind.MERGING), ("ExtractAudio", StatusKind.CONVERTING_AUDIO),
                           ("VideoRemuxer", StatusKind.REMUXING), ("MoveFiles", StatusKind.FINALIZING)):
            record = 'AIDM_POSTPROCESS:' + json.dumps({"status": "started", "postprocessor": name})
            self.assertEqual(parse_ytdlp_record(record), [ProgressEvent(), StatusEvent(kind, "yt-dlp")])

    def test_framing_is_bounded_and_recovers(self):
        parser = YtDlpProgressParser()
        self.assertEqual(parser.feed(b"x" * 100000), [])
        self.assertEqual(len(parser._buffer), 0)
        line = b'AIDM_PROGRESS:{"progress":{"status":"downloading","downloaded_bytes":5}}'
        events = parser.feed(b"\r\n" + line + b"\r" + line, final=True)
        self.assertEqual(len(events), 4)


try:
    from PySide6.QtCore import QProcess
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from aidm_gui import GuiState
    from gui_execution import (create_download_process, DirectDownloadProcess, YouTubeDownloadProcess,
                               UnsupportedExecution, ExecutionOutcome)
    import test_gui_execution as gui_tests
except ImportError:
    gui_tests = None


@unittest.skipIf(gui_tests is None, "Requires PySide6")
class YouTubeExecutionTests(unittest.TestCase):
    if gui_tests is not None:
        setUp = gui_tests.GuiExecutionTests.setUp
        tearDown = gui_tests.GuiExecutionTests.tearDown
        inspect = gui_tests.GuiExecutionTests.inspect
        wait_for = gui_tests.GuiExecutionTests.wait_for

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def start_youtube(self, mode=YouTubeMode.VIDEO, quality=1080):
        self.window.input_field.clear()
        self.inspect(InputKind.YOUTUBE_SINGLE)
        self.window.inspection_result = replace(self.window.inspection_result, title="Actual YouTube Title")
        self.window.on_download_intent()
        with patch("gui_quality.QualityProcess.start"):
            self.window.mode_buttons[mode].click()
        if mode == YouTubeMode.VIDEO:
            self.window.finish_quality(self.window._quality_generation, [quality] if type(quality) is int else [])
            if type(quality) is int:
                self.window.quality_choice.setCurrentIndex(1)
        self.window.on_download_intent()
        return self.window._download_process

    def test_factory_and_all_modes_share_backend_builders(self):
        for mode in YouTubeMode:
            for quality in ([720, VideoQuality.BEST] if mode == YouTubeMode.VIDEO else [None]):
                worker = self.start_youtube(mode, quality)
                self.assertIsInstance(worker, YouTubeDownloadProcess)
                command = worker.process.calls[0]
                self.assertEqual(command[0], "yt-dlp")
                args = command[1]
                self.assertEqual(args[args.index("-P") + 1], worker.job.destination)
                self.assertEqual(args[-1], worker.job.urls[0])
                self.assertIn("--no-playlist", args)
                self.assertEqual(worker.job.title, "Actual YouTube Title")
                self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
                if mode == YouTubeMode.VIDEO:
                    self.assertEqual(args[args.index("-f") + 1], youtube.build_youtube_format(
                        quality if type(quality) is int else None))
                    self.assertEqual(args[args.index("--merge-output-format") + 1], "mp4")
                    self.assertEqual(args[args.index("--remux-video") + 1], "mp4")
                else:
                    self.assertEqual(args[args.index("-f") + 1], "bestaudio/best")
                    self.assertEqual("--extract-audio" in args, mode == YouTubeMode.WAV)
                    self.assertNotIn("--remux-video", args)
                worker.process.finish()
        direct = DownloadJob(InputKind.DIRECT_SINGLE, ("https://example.test/file.zip",), str(self.directory))
        self.assertIsInstance(create_download_process(direct), DirectDownloadProcess)
        for kind in (InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST, InputKind.HLS,
                     InputKind.DASH, InputKind.GENERIC_YTDLP, InputKind.TORRENT):
            if kind == InputKind.YOUTUBE_BULK:
                job = DownloadJob(kind, ("a", "b"), str(self.directory), mode=YouTubeMode.WAV)
            elif kind == InputKind.YOUTUBE_PLAYLIST:
                job = DownloadJob(kind, ("a",), str(self.directory), video_quality=720)
            else:
                job = DownloadJob(kind, ("a",), str(self.directory))
            with self.assertRaises(UnsupportedExecution):
                create_download_process(job)

    def test_gui_telemetry_status_title_abort_retry_and_stale_signals(self):
        worker = self.start_youtube()
        job = worker.job
        self.assertEqual(self.window.active_status.text(), "Starting yt-dlp… ⚙️")
        worker.process.begin()
        worker.process.stdout = (Path(__file__).parent / "fixtures/ytdlp/aria2c.txt").read_bytes()
        worker.process.readyReadStandardOutput.emit()
        self.assertEqual(self.window.active_status.text(), "Finalizing… ⚙️")
        self.assertTrue(self.window.progress.isHidden())
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        self.window.abort_button.click()
        self.assertEqual(self.window.current_state, GuiState.ABORTED)
        self.assertEqual(self.window.media_title.text(), job.title)
        self.assertFalse(self.window.retry_button.isHidden())
        self.window.retry_button.click()
        current = self.window._download_process
        self.assertIsNot(current, worker)
        self.assertIs(current.job, job)
        self.assertIsNone(self.window._progress_event)
        worker.progress_event.emit(ProgressEvent(95))
        worker.status_event.emit(StatusEvent(StatusKind.FAILED, "yt-dlp"))
        worker.filename_resolved.emit("wrong")
        worker.finished.emit(ExecutionOutcome.FAILED)
        self.assertEqual(self.window.current_state, GuiState.DOWNLOADING)
        self.assertIsNone(self.window._progress_event)
        current.process.stdout = b'[#abcdef 60B/100B(60%) CN:1 DL:5B ETA:8s]\n'
        current.process.readyReadStandardOutput.emit()
        self.assertEqual(self.window.progress.value(), 60)
        current.process.finish()
        self.assertEqual(self.window.current_state, GuiState.COMPLETE)
        self.assertEqual(self.window.media_title.text(), job.title)
        self.assertTrue(self.window.retry_button.isHidden())

    def test_start_failure_and_nonzero_exit_retain_title_and_retry(self):
        for start_failure in (False, True):
            worker = self.start_youtube(YouTubeMode.ORIGINAL_AUDIO)
            if start_failure:
                worker.process.current_state = QProcess.ProcessState.NotRunning
                worker.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
                self.assertEqual(self.window.result_message.text(), "Could not start yt-dlp. ⚠️")
            else:
                worker.process.begin()
                worker.process.finish(7)
            self.assertEqual(self.window.current_state, GuiState.FAILED)
            self.assertEqual(self.window.media_title.text(), "Actual YouTube Title")
            self.assertFalse(self.window.retry_button.isHidden())

    def test_owned_group_abort_and_close_stop_stubborn_child_after_parent_exit(self):
        self.process_patch.stop()
        # Local Python fixture: parent exits on TERM, child ignores TERM. This
        # reproduces the dangerous early-parent-exit race without a downloader.
        child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('child-ready',flush=True); time.sleep(30)"
        script = ("import subprocess,sys,time; "
                  f"p=subprocess.Popen([sys.executable,'-u','-c',{child!r}]); "
                  "print('child-pid:'+str(p.pid),file=sys.stderr,flush=True); time.sleep(30)")
        for close in (False, True, "after_abort"):
            with patch.object(YouTubeDownloadProcess, "build_command", return_value=[sys.executable, "-u", "-c", script]):
                worker = self.start_youtube()
            ready = []
            original_consume = worker.consume_stdout
            worker.consume_stdout = lambda chunk, **kw: (ready.append(chunk), original_consume(chunk, **kw))
            self.wait_for(lambda: b"child-ready" in b"".join(ready))
            group = worker._process_group
            self.assertIsNotNone(group)
            self.assertNotEqual(group, os.getpgrp())
            child_pid = int(worker.stderr_tail.decode().strip().split(":")[-1])
            worker._abort_timer.setInterval(150)
            if close:
                if close == "after_abort":
                    self.window.abort_button.click()
                self.assertTrue(worker.shutdown())
            else:
                self.window.abort_button.click()
                self.assertEqual(self.window.active_status.text(), "Aborting… 🛑")
                self.wait_for(lambda: self.window.current_state == GuiState.ABORTED)
            self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)
            path = Path(f"/proc/{child_pid}/stat")
            if path.exists():
                self.assertIn(path.read_text().rsplit(") ", 1)[1].split()[0], {"Z", "X"})

    def test_abort_during_parent_exit_cleanup_overrides_pending_success(self):
        worker = self.start_youtube()
        worker.process.begin()
        with patch.object(worker, "group_running", return_value=True):
            worker.process.finish()
        self.assertTrue(worker.active)
        self.assertEqual(worker._pending_outcome, ExecutionOutcome.COMPLETE)
        self.window.abort_button.click()
        with patch.object(worker, "group_running", return_value=False):
            worker.finish_group_cleanup()
        self.assertEqual(self.window.current_state, GuiState.ABORTED)


if __name__ == "__main__":
    unittest.main()
