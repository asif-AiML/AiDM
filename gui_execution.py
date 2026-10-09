"""Shared QProcess attempt lifecycle; DIRECT_SINGLE is the first engine adapter."""

from enum import Enum
import os
from pathlib import Path
import signal
import sys
import time
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from download_job import BulkMode, DownloadJob, VideoQuality, YouTubeMode
from aria2_progress import Aria2ProgressParser
from aria2_parallel_progress import Aria2ParallelProgressParser, Aria2Snapshot
from downloader import (
    build_direct_command, build_direct_bulk_parallel_command, build_stream_command,
    build_ytdlp_media_command, build_subtitle_command, select_subtitle_sidecar,
)
from inspection import InputKind
from stream_parser import StreamInput
from workflow_warning import WorkflowWarning
from status_event import StatusEvent, StatusKind, StatusReason
from progress_event import ProgressEvent
from youtube import build_youtube_video_command, build_youtube_audio_command, build_youtube_playlist_command
from ytdlp_progress import YtDlpProgressParser
from batch_event import ItemStarted, SequentialBatchProgress, ParallelBatchProgress


class ExecutionOutcome(Enum):
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTED = "aborted"


class UnsupportedExecution(ValueError):
    pass


class DownloadProcess(QObject):
    """One owned process per attempt. Engine adapters supply command and output."""

    status_event = Signal(object)
    warning_event = Signal(object)
    progress_event = Signal(object)
    batch_event = Signal(object)
    filename_resolved = Signal(str)
    finished = Signal(object)  # ExecutionOutcome, independent of presentation.
    can_abort = True
    can_retry = True
    engine = None
    downloading_status = StatusKind.DOWNLOADING
    owns_process_group = False
    ABORT_GRACE_MS = 2500
    MAX_STDERR_BYTES = 65536

    def __init__(self, job: DownloadJob, parent=None):
        super().__init__(parent)
        self.job = job
        self.active = False
        self.done = False
        self.closing = False
        self.abort_requested = False
        self.stderr_tail = b""
        self._process_group = None
        self._pending_outcome = None
        self.create_process()
        self._abort_timer = QTimer(self)
        self._abort_timer.setSingleShot(True)
        self._abort_timer.setInterval(self.ABORT_GRACE_MS)
        self._abort_timer.timeout.connect(self.escalate_abort)
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(50)
        self._cleanup_timer.timeout.connect(self.finish_group_cleanup)

    def create_process(self):
        """Create one owned stage; late notifications from replaced stages are ignored."""
        self.process = QProcess(self)
        self._process_events_enabled = True
        if self.owns_process_group:
            # Qt creates the session before exec, without Python fork callbacks.
            # Linux /proc lets cleanup distinguish running children from zombies
            # awaiting the OS reaper after their parent has exited.
            if (not sys.platform.startswith("linux")
                    or not hasattr(QProcess, "UnixProcessFlag")
                    or not hasattr(QProcess.UnixProcessFlag, "CreateNewSession")):
                raise UnsupportedExecution("Process-tree ownership currently requires Linux/Qt 6.7+")
            self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        self.process.setStandardInputFile(QProcess.nullDevice())
        process = self.process
        for notification, callback in (
            (process.started, self.on_started),
            (process.readyReadStandardOutput, self.drain_output),
            (process.readyReadStandardError, self.drain_output),
            (process.errorOccurred, self.on_error),
            (process.finished, self.on_finished),
        ):
            notification.connect(
                lambda *args, process=process, callback=callback:
                    callback(*args) if self.process is process and not self.done
                    and self._process_events_enabled else None
            )

    def build_command(self):
        raise NotImplementedError

    def start(self):
        if self.active or self.done or self.closing:
            return
        command = self.build_command()
        self.active = True
        self.status_event.emit(StatusEvent(StatusKind.STARTING_ENGINE, engine=self.engine))
        self.process.start(command[0], command[1:])

    def on_started(self):
        if self.owns_process_group:
            self._process_group = int(self.process.processId()) or None
        if self.done or self.closing:
            return
        if self.abort_requested:
            # terminate() may have arrived while QProcess was still starting.
            self._abort_timer.start()
            self.signal_process(signal.SIGTERM)
        else:
            self.status_event.emit(StatusEvent(self.downloading_status, engine=self.engine))

    def abort(self):
        if not self.can_abort or not self.active or self.abort_requested or self.closing:
            return
        self.abort_requested = True
        self.status_event.emit(StatusEvent(StatusKind.ABORTING, engine=self.engine))
        # Arm before terminate: even a synchronous finish cancels escalation.
        self._abort_timer.start()
        self.signal_process(signal.SIGTERM)

    def escalate_abort(self):
        if (self.active and (self.abort_requested or self._pending_outcome is not None)
                and not self.closing):
            self.signal_process(signal.SIGKILL)
        # finished is authoritative; never declare ABORTED before reaping.

    def signal_process(self, sig):
        """Signal only this attempt's dedicated session, or its single QProcess."""
        if self._process_group is not None:
            try:
                os.killpg(self._process_group, sig)
            except ProcessLookupError:
                pass
        elif self.process.state() != QProcess.ProcessState.NotRunning:
            if sig == signal.SIGTERM:
                self.process.terminate()
            else:
                self.process.kill()

    def group_running(self):
        if self._process_group is None:
            return False
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
                if int(fields[2]) == self._process_group and fields[0] not in {"Z", "X"}:
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue  # Process exited between enumeration and read.
            except PermissionError:
                # Same-user owned children are readable on Linux. Do not declare
                # successful cleanup if this assumption is no longer true.
                return True
        return False

    def finish_group_cleanup(self):
        if self._pending_outcome is not None and not self.group_running():
            self.complete(ExecutionOutcome.ABORTED if self.abort_requested else self._pending_outcome)

    def drain_output(self):
        chunk = bytes(self.process.readAllStandardOutput())
        if not self.done and not self.closing and not self.abort_requested:
            self.consume_stdout(chunk)
        chunk = bytes(self.process.readAllStandardError())
        self.stderr_tail = (self.stderr_tail + chunk)[-self.MAX_STDERR_BYTES:]

    def consume_stdout(self, chunk, *, final=False):
        """Engine hook. Output is drained even when the adapter needs no parser."""

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            # Startup failure remains failure even if Abort raced startup.
            self.complete(ExecutionOutcome.FAILED, StatusReason.START_FAILED)

    def on_finished(self, code, status):
        self.drain_output()
        if not self.done and not self.closing and not self.abort_requested:
            self.consume_stdout(b"", final=True)
        outcome = (ExecutionOutcome.ABORTED if self.abort_requested else
                   ExecutionOutcome.COMPLETE if code == 0 and status == QProcess.ExitStatus.NormalExit
                   else ExecutionOutcome.FAILED)
        if self.group_running():
            # Parent exit must not abandon a still-running aria2c/FFmpeg child.
            # Keep the attempt active until group cleanup finishes, including
            # when the parent exits before the interactive Abort grace timer.
            self._pending_outcome = outcome
            if not self._abort_timer.isActive():
                self._abort_timer.start()
                self.signal_process(signal.SIGTERM)
            self._cleanup_timer.start()
        else:
            self.complete(outcome)

    def clear_process_tracking(self):
        """Forget only a reaped process and its fully stopped process group."""
        self._abort_timer.stop()
        self._cleanup_timer.stop()
        self._process_group = None
        self._pending_outcome = None

    def complete(self, outcome, reason: StatusReason | None = None):
        if self.done:
            return
        self.clear_process_tracking()
        self.done = True
        self.active = False
        if not self.closing:
            kind = {ExecutionOutcome.COMPLETE: StatusKind.COMPLETE,
                    ExecutionOutcome.FAILED: StatusKind.FAILED,
                    ExecutionOutcome.ABORTED: StatusKind.ABORTED}[outcome]
            self.status_event.emit(StatusEvent(kind, engine=self.engine, reason=reason))
            self.finished.emit(outcome)

    def shutdown(self) -> bool:
        """Close-time hygiene only; interactive Abort never waits synchronously."""
        self.closing = True
        self._abort_timer.stop()
        self._cleanup_timer.stop()
        if self.process.state() == QProcess.ProcessState.Starting:
            self.process.waitForStarted(1000)
        self.signal_process(signal.SIGTERM)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if not self.process.waitForFinished(1000):
                self.signal_process(signal.SIGKILL)
                self.process.waitForFinished(1000)
        # Only close-time cleanup may wait. Interactive Abort uses Qt timers.
        if self.group_running():
            self.signal_process(signal.SIGKILL)
            deadline = time.monotonic() + 1
            while self.group_running() and time.monotonic() < deadline:
                time.sleep(.01)
        stopped = self.process.state() == QProcess.ProcessState.NotRunning and not self.group_running()
        if stopped:
            self._abort_timer.stop()
            self._cleanup_timer.stop()
            self._process_group = None
            self.active = False
        else:
            self.closing = False
            if self.abort_requested:
                self._abort_timer.start()
            if self._pending_outcome is not None:
                self._cleanup_timer.start()
        return stopped


class DirectDownloadProcess(DownloadProcess):
    engine = "aria2c"

    def __init__(self, job: DownloadJob, parent=None):
        if job.kind != InputKind.DIRECT_SINGLE:
            raise ValueError("GUI execution supports DIRECT_SINGLE only")
        super().__init__(job, parent)
        self._runtime_filename = None
        self._progress_parser = Aria2ProgressParser(self.on_filename)

    def build_command(self):
        return build_direct_command(self.job.urls[0], self.job.destination, telemetry=True)

    def consume_stdout(self, chunk, *, final=False):
        for event in self._progress_parser.feed(chunk, final=final):
            self.progress_event.emit(event)

    def on_filename(self, filename):
        if filename != self._runtime_filename:
            self._runtime_filename = filename
            self.filename_resolved.emit(filename)


class DirectBulkDownloadProcess(DownloadProcess):
    """One owned aria2 process at a time, using the shared attempt lifecycle."""

    engine = "aria2c"

    def __init__(self, job: DownloadJob, parent=None):
        if job.kind != InputKind.DIRECT_BULK:
            raise ValueError("Direct bulk execution requires DIRECT_BULK")
        super().__init__(job, parent)
        self._parallel = job.bulk_mode == BulkMode.PARALLEL
        self._index = 1
        self._between_items = False
        self._input_directory = None
        self._batch = (ParallelBatchProgress(len(job.urls)) if self._parallel
                       else SequentialBatchProgress(len(job.urls)))
        self._progress_parser = (Aria2ParallelProgressParser(len(job.urls)) if self._parallel
                                 else Aria2ProgressParser(self.on_filename))
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self.advance)

    def build_command(self):
        if not self._parallel:
            return build_direct_command(self.job.urls[self._index - 1], self.job.destination, telemetry=True)
        if self._input_directory is None:
            self._input_directory = TemporaryDirectory(prefix="aidm-gui-bulk-")
            input_path = Path(self._input_directory.name) / "urls.txt"
            input_path.write_text("\n".join(self.job.urls) + "\n")
        return build_direct_bulk_parallel_command(
            str(Path(self._input_directory.name) / "urls.txt"), len(self.job.urls),
            self.job.destination, telemetry=True,
        )

    def start(self):
        if self.active or self.done or self.closing:
            return
        self.batch_event.emit(self._batch.event if self._parallel else
                              self._batch.start_item(ItemStarted(self._index)))
        try:
            super().start()
        except OSError as error:
            self.stderr_tail = str(error).encode()[-self.MAX_STDERR_BYTES:]
            self.complete(ExecutionOutcome.FAILED, StatusReason.START_FAILED)

    def on_filename(self, filename):
        batch = self._batch.start_item(ItemStarted(self._index, filename))
        if batch is not None:
            self.batch_event.emit(batch)

    def consume_stdout(self, chunk, *, final=False):
        for event in self._progress_parser.feed(chunk, final=final):
            if self._parallel:
                batch, progress = (self._batch.snapshot(event.items) if isinstance(event, Aria2Snapshot)
                                   else self._batch.finish_item(event.gid))
                self.batch_event.emit(batch)
                self.progress_event.emit(progress)
            else:
                batch = self._batch.progress(event.percent)
                if batch is not None:
                    self.batch_event.emit(batch)
                self.progress_event.emit(event)

    def advance(self):
        # Yield between items so an Abort queued at the finish boundary wins.
        if self.done or self.closing or not self._between_items:
            return
        if self.abort_requested:
            self.complete(ExecutionOutcome.ABORTED)
            return
        self._between_items = False
        self._index += 1
        self._progress_parser = Aria2ProgressParser(self.on_filename)
        self.progress_event.emit(ProgressEvent())
        self.batch_event.emit(self._batch.start_item(ItemStarted(self._index)))
        self.status_event.emit(StatusEvent(StatusKind.STARTING_ENGINE, self.engine))
        # Signals can synchronously request Abort/close, too.
        if self.abort_requested or self.closing or self.done:
            if self.abort_requested and not self.closing:
                self.complete(ExecutionOutcome.ABORTED)
            return
        command = self.build_command()
        self.process.start(command[0], command[1:])

    def abort(self):
        super().abort()
        if self._between_items and self.abort_requested and not self.closing:
            self.complete(ExecutionOutcome.ABORTED)

    def complete(self, outcome, reason=None):
        if self.done:
            return
        if not self.closing and outcome == ExecutionOutcome.COMPLETE:
            if not self._parallel and self._index < len(self.job.urls):
                self._between_items = True
                batch = self._batch.progress(100)
                if batch is not None:
                    self.batch_event.emit(batch)
                if not self.done and not self.closing and not self.abort_requested:
                    self._next_timer.start(0)
                return
            batch = self._batch.complete()
            if batch is not None:
                self.batch_event.emit(batch)
            if self.abort_requested:
                outcome = ExecutionOutcome.ABORTED
        self._next_timer.stop()
        self.cleanup_input()
        super().complete(outcome, reason)

    def cleanup_input(self):
        if self._input_directory is not None:
            self._input_directory.cleanup()
            self._input_directory = None

    def shutdown(self):
        stopped = super().shutdown()
        if stopped:
            self._next_timer.stop()
            self.cleanup_input()
        return stopped


class StreamInspectorDownloadProcess(DownloadProcess):
    """One browser-assisted attempt: main media, then an optional subtitle."""

    engine = "yt-dlp"
    owns_process_group = True

    def __init__(self, job: DownloadJob, parent=None):
        if job.kind != InputKind.STREAM_INSPECTOR:
            raise ValueError("Inspector workflow requires STREAM_INSPECTOR")
        super().__init__(job, parent)
        self._subtitle_stage = False
        self._between_stages = False
        self._subtitle_url = None
        self._progress_parser = YtDlpProgressParser()
        self._last_status = None
        self._stage_timer = QTimer(self)
        self._stage_timer.setSingleShot(True)
        self._stage_timer.timeout.connect(self.start_subtitle)

    def build_command(self):
        job = self.job
        if self._subtitle_stage:
            return build_subtitle_command(
                self._subtitle_url, job.title, job.headers, destination=job.destination,
            )
        options = dict(destination=job.destination, telemetry=True)
        stream_type = {InputKind.HLS: "hls", InputKind.DASH: "dash"}.get(job.route_kind)
        if stream_type is not None:
            return build_stream_command(StreamInput(
                job.urls[0], dict(job.headers), stream_type, job.title, list(job.subtitles),
            ), **options)
        return build_ytdlp_media_command(job.urls[0], job.title, job.headers, **options)

    def consume_stdout(self, chunk, *, final=False):
        if self._subtitle_stage:
            return  # Tiny sidecars need no new progress parser or artificial bar.
        for event in self._progress_parser.feed(chunk, final=final):
            if self.done or self.closing or self.abort_requested:
                break
            if isinstance(event, ProgressEvent):
                self.progress_event.emit(event)
            elif isinstance(event, StatusEvent) and event != self._last_status:
                self._last_status = event
                self.status_event.emit(event)
            # Item/title output cannot replace the browser-provided identity.

    def complete(self, outcome, reason=None):
        if self.done:
            return
        if not self.closing and self.abort_requested:
            outcome = ExecutionOutcome.ABORTED
        if not self.closing and outcome != ExecutionOutcome.ABORTED:
            if self._subtitle_stage and outcome == ExecutionOutcome.FAILED:
                self.warning_event.emit(WorkflowWarning.SUBTITLE_FAILED)
                outcome, reason = ExecutionOutcome.COMPLETE, None
            elif not self._subtitle_stage and outcome == ExecutionOutcome.COMPLETE:
                self._subtitle_url, warning = select_subtitle_sidecar(self.job.subtitles, self.job.title)
                if warning is not None:
                    self.warning_event.emit(warning)
                if self._subtitle_url is not None:
                    # Called only after the parent and owned children have stopped.
                    self.clear_process_tracking()
                    self._process_events_enabled = False
                    self._between_stages = True
                    self.progress_event.emit(ProgressEvent())
                    if not self.done and not self.closing and not self.abort_requested:
                        self._stage_timer.start(0)
                    return
        if self.abort_requested:
            outcome = ExecutionOutcome.ABORTED
        self._stage_timer.stop()
        super().complete(outcome, reason)

    def start_subtitle(self):
        if self.done or self.closing or not self._between_stages:
            return
        if self.abort_requested:
            self.complete(ExecutionOutcome.ABORTED)
            return
        self._between_stages = False
        self._subtitle_stage = True
        self.engine = "aria2c"
        self.downloading_status = StatusKind.DOWNLOADING_SUBTITLE
        previous = self.process
        self.create_process()
        previous.deleteLater()
        self.stderr_tail = b""
        command = self.build_command()
        self.status_event.emit(StatusEvent(StatusKind.STARTING_ENGINE, self.engine))
        # A status callback can synchronously request Abort or close.
        if self.done or self.closing or self.abort_requested:
            if self.abort_requested and not self.closing:
                self.complete(ExecutionOutcome.ABORTED)
            return
        self.process.start(command[0], command[1:])

    def abort(self):
        super().abort()
        if self._between_stages and self.abort_requested and not self.closing:
            self.complete(ExecutionOutcome.ABORTED)

    def shutdown(self):
        stopped = super().shutdown()
        if stopped:
            self._stage_timer.stop()
        return stopped


class YouTubeDownloadProcess(DownloadProcess):
    """YouTube modes and video playlists, with one shared process attempt."""

    engine = "yt-dlp"
    owns_process_group = True

    def __init__(self, job: DownloadJob, parent=None):
        if job.kind not in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST}:
            raise ValueError("YouTube GUI execution requires a YouTube job")
        super().__init__(job, parent)
        self._progress_parser = YtDlpProgressParser()
        self._last_status = None
        total = (len(job.urls) if job.kind == InputKind.YOUTUBE_BULK else
                 job.item_count if job.kind == InputKind.YOUTUBE_PLAYLIST else None)
        self._batch = SequentialBatchProgress(total) if total is not None else None

    def build_command(self):
        options = dict(destination=self.job.destination, telemetry=True)
        if self.job.kind == InputKind.YOUTUBE_PLAYLIST:
            height = None if self.job.video_quality == VideoQuality.BEST else self.job.video_quality
            return build_youtube_playlist_command(self.job.urls[0], height, **options)
        if self._batch is not None:
            options["total_videos"] = len(self.job.urls)
        if self.job.mode == YouTubeMode.VIDEO:
            height = None if self.job.video_quality == VideoQuality.BEST else self.job.video_quality
            command = build_youtube_video_command(height, **options)
        else:
            command = build_youtube_audio_command(wav=self.job.mode == YouTubeMode.WAV, **options)
        # This adapter cannot execute a playlist, even if a URL contains list=.
        return command + ["--no-playlist", "--", *self.job.urls]

    def consume_stdout(self, chunk, *, final=False):
        for event in self._progress_parser.feed(chunk, final=final):
            if isinstance(event, ItemStarted):
                if (self._batch is None and self.job.kind == InputKind.YOUTUBE_PLAYLIST
                        and event.total_items is not None):
                    self._batch = SequentialBatchProgress(event.total_items)
                if self._batch is not None:
                    previous = self._batch.event
                    batch = self._batch.start_item(event)
                    if batch is not None:
                        if previous is None or batch.current_index != previous.current_index:
                            self.progress_event.emit(ProgressEvent())
                            self._last_status = None
                            self.status_event.emit(StatusEvent(StatusKind.DOWNLOADING, self.engine))
                        self.batch_event.emit(batch)
            elif isinstance(event, ProgressEvent):
                if self._batch is not None:
                    batch = self._batch.progress(event.percent)
                    if batch is not None:
                        self.batch_event.emit(batch)
                self.progress_event.emit(event)
            else:
                if (event.kind == StatusKind.DOWNLOADING
                        and self.job.mode in {YouTubeMode.ORIGINAL_AUDIO, YouTubeMode.WAV}):
                    event = StatusEvent(StatusKind.DOWNLOADING_AUDIO, self.engine)
                if event != self._last_status:
                    self._last_status = event
                    self.status_event.emit(event)

    def complete(self, outcome, reason=None):
        if (not self.done and not self.closing and outcome == ExecutionOutcome.COMPLETE
                and self._batch is not None):
            batch = self._batch.complete()
            if batch is not None:
                self.batch_event.emit(batch)
        super().complete(outcome, reason)


def create_download_process(job: DownloadJob, parent=None) -> DownloadProcess:
    """Only implemented adapters belong here; unsupported routes stay deferred."""
    if job.kind == InputKind.STREAM_INSPECTOR:
        return StreamInspectorDownloadProcess(job, parent)
    if job.kind == InputKind.DIRECT_SINGLE:
        return DirectDownloadProcess(job, parent)
    if job.kind == InputKind.DIRECT_BULK:
        return DirectBulkDownloadProcess(job, parent)
    if job.kind in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST}:
        return YouTubeDownloadProcess(job, parent)
    raise UnsupportedExecution("GUI execution is not implemented for this job")
