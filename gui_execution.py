"""Shared QProcess attempt lifecycle; DIRECT_SINGLE is the first engine adapter."""

from enum import Enum

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from download_job import DownloadJob
from aria2_progress import Aria2ProgressParser
from downloader import build_direct_command
from inspection import InputKind
from status_event import StatusEvent, StatusKind, StatusReason


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
    filename_resolved = Signal(str)
    finished = Signal(object)  # ExecutionOutcome, independent of presentation.
    can_abort = True
    can_retry = True
    engine = None
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
        self.process = QProcess(self)
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
        if self.done or self.closing:
            return
        if self.abort_requested:
            # terminate() may have arrived while QProcess was still starting.
            self._abort_timer.start()
            self.process.terminate()
        else:
            self.status_event.emit(StatusEvent(StatusKind.DOWNLOADING, engine=self.engine))

    def abort(self):
        if not self.can_abort or not self.active or self.abort_requested or self.closing:
            return
        self.abort_requested = True
        self.status_event.emit(StatusEvent(StatusKind.ABORTING, engine=self.engine))
        # Arm before terminate: even a synchronous finish cancels escalation.
        self._abort_timer.start()
        self.process.terminate()

    def escalate_abort(self):
        if (self.active and self.abort_requested and not self.closing
                and self.process.state() != QProcess.ProcessState.NotRunning):
            self.process.kill()
        # finished is authoritative; never declare ABORTED before reaping.

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
        self.complete(outcome)

    def complete(self, outcome, reason: StatusReason | None = None):
        if self.done:
            return
        self._abort_timer.stop()
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
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)
        stopped = self.process.state() == QProcess.ProcessState.NotRunning
        if stopped:
            self.active = False
        else:
            self.closing = False
            if self.abort_requested:
                self._abort_timer.start()
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


def create_download_process(job: DownloadJob, parent=None) -> DownloadProcess:
    """Only implemented adapters belong here; unsupported routes stay deferred."""
    if job.kind == InputKind.DIRECT_SINGLE:
        return DirectDownloadProcess(job, parent)
    raise UnsupportedExecution("GUI execution is not implemented for this job")
