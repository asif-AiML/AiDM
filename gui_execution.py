"""Qt process adapter and telemetry for single direct jobs only; no Abort UI."""

from PySide6.QtCore import QObject, QProcess, Signal

from download_job import DownloadJob
from aria2_progress import Aria2ProgressParser
from downloader import build_direct_command
from inspection import InputKind
from status_event import StatusEvent, StatusKind, StatusReason


class DirectDownloadProcess(QObject):
    status_event = Signal(object)  # Payload: shared, Qt-independent StatusEvent.
    progress_event = Signal(object)  # Payload: Qt-independent ProgressEvent.
    filename_resolved = Signal(str)  # Runtime identity, separate from telemetry/status.
    finished = Signal(bool)
    MAX_STDERR_BYTES = 65536

    def __init__(self, job: DownloadJob, parent=None):
        super().__init__(parent)
        # Check kind, not underlying route: Inspector execution is deferred.
        if job.kind != InputKind.DIRECT_SINGLE:
            raise ValueError("GUI execution supports DIRECT_SINGLE only")
        self.job = job
        self.active = False
        self.done = False
        self.closing = False
        self.stderr_tail = b""
        self._runtime_filename = None
        self._progress_parser = Aria2ProgressParser(self.on_filename)
        self.process = QProcess(self)
        self.process.setStandardInputFile(QProcess.nullDevice())
        self.process.started.connect(self.on_started)
        self.process.readyReadStandardOutput.connect(self.drain_output)
        self.process.readyReadStandardError.connect(self.drain_output)
        self.process.errorOccurred.connect(self.on_error)
        self.process.finished.connect(self.on_finished)

    def start(self):
        if self.active or self.done:
            return
        command = build_direct_command(self.job.urls[0], self.job.destination, telemetry=True)
        self.active = True
        self.status_event.emit(StatusEvent(StatusKind.STARTING_ENGINE, engine="aria2c"))
        self.process.start(command[0], command[1:])

    def on_started(self):
        if not self.done and not self.closing:
            self.status_event.emit(StatusEvent(StatusKind.DOWNLOADING, engine="aria2c"))

    def drain_output(self):
        self.emit_progress(bytes(self.process.readAllStandardOutput()))
        chunk = bytes(self.process.readAllStandardError())
        self.stderr_tail = (self.stderr_tail + chunk)[-self.MAX_STDERR_BYTES:]

    def emit_progress(self, chunk, *, final=False):
        if not self.done and not self.closing:
            for event in self._progress_parser.feed(chunk, final=final):
                self.progress_event.emit(event)

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.complete(False, StatusReason.START_FAILED)

    def on_filename(self, filename):
        if not self.done and not self.closing and filename != self._runtime_filename:
            self._runtime_filename = filename
            self.filename_resolved.emit(filename)

    def on_finished(self, code, status):
        self.drain_output()
        self.emit_progress(b"", final=True)
        success = code == 0 and status == QProcess.ExitStatus.NormalExit
        self.complete(success)

    def complete(self, success, reason: StatusReason | None = None):
        if self.done:
            return
        self.done = True
        self.active = False
        if not self.closing:
            self.status_event.emit(StatusEvent(
                StatusKind.COMPLETE if success else StatusKind.FAILED,
                engine="aria2c", reason=reason,
            ))
            self.finished.emit(success)

    def shutdown(self) -> bool:
        """Close-time hygiene only; bounded waits never run during a transfer."""
        self.closing = True
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)
        stopped = self.process.state() == QProcess.ProcessState.NotRunning
        if stopped:
            self.active = False
        else:
            # Keep the window/process owner alive if the OS has not reaped it.
            self.closing = False
        return stopped
