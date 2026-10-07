"""Shared QProcess attempt lifecycle; DIRECT_SINGLE is the first engine adapter."""

from enum import Enum
import os
from pathlib import Path
import signal
import sys
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from download_job import DownloadJob, VideoQuality, YouTubeMode
from aria2_progress import Aria2ProgressParser
from downloader import build_direct_command
from inspection import InputKind
from status_event import StatusEvent, StatusKind, StatusReason
from progress_event import ProgressEvent
from youtube import build_youtube_video_command, build_youtube_audio_command
from ytdlp_progress import YtDlpProgressParser
from batch_event import ItemStarted, SequentialBatchProgress


class ExecutionOutcome(Enum):
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTED = "aborted"


class UnsupportedExecution(ValueError):
    pass


class DownloadProcess(QObject):
    """One owned process per attempt. Engine adapters supply command and output."""

    status_event = Signal(object)
    progress_event = Signal(object)
    batch_event = Signal(object)
    filename_resolved = Signal(str)
    finished = Signal(object)  # ExecutionOutcome, independent of presentation.
    can_abort = True
    can_retry = True
    engine = None
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
        self.process = QProcess(self)
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
        self.process.started.connect(self.on_started)
        self.process.readyReadStandardOutput.connect(self.drain_output)
        self.process.readyReadStandardError.connect(self.drain_output)
        self.process.errorOccurred.connect(self.on_error)
        self.process.finished.connect(self.on_finished)
        self._abort_timer = QTimer(self)
        self._abort_timer.setSingleShot(True)
        self._abort_timer.setInterval(self.ABORT_GRACE_MS)
        self._abort_timer.timeout.connect(self.escalate_abort)
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(50)
        self._cleanup_timer.timeout.connect(self.finish_group_cleanup)

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
            self.status_event.emit(StatusEvent(StatusKind.DOWNLOADING, engine=self.engine))

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

    def complete(self, outcome, reason: StatusReason | None = None):
        if self.done:
            return
        self._abort_timer.stop()
        self._cleanup_timer.stop()
        self._process_group = None
        self._pending_outcome = None
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


class YouTubeDownloadProcess(DownloadProcess):
    """Single/bulk YouTube modes, with one shared process attempt."""

    engine = "yt-dlp"
    owns_process_group = True

    def __init__(self, job: DownloadJob, parent=None):
        if job.kind not in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK}:
            raise ValueError("YouTube GUI execution supports single/bulk only")
        super().__init__(job, parent)
        self._progress_parser = YtDlpProgressParser()
        self._last_status = None
        self._batch = SequentialBatchProgress(len(job.urls)) if job.kind == InputKind.YOUTUBE_BULK else None

    def build_command(self):
        options = dict(destination=self.job.destination, telemetry=True)
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
    if job.kind == InputKind.DIRECT_SINGLE:
        return DirectDownloadProcess(job, parent)
    if job.kind in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK}:
        return YouTubeDownloadProcess(job, parent)
    raise UnsupportedExecution("GUI execution is not implemented for this job")
