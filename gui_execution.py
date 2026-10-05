"""Qt process adapter for single direct jobs only; no telemetry or Abort UI."""

from PySide6.QtCore import QObject, QProcess, Signal

from download_job import DownloadJob
from downloader import build_direct_command
from inspection import InputKind


class DirectDownloadProcess(QObject):
    started = Signal()
    finished = Signal(bool, str)
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
        self.process = QProcess(self)
        self.process.setStandardInputFile(QProcess.nullDevice())
        self.process.started.connect(self.started.emit)
        self.process.readyReadStandardOutput.connect(self.drain_output)
        self.process.readyReadStandardError.connect(self.drain_output)
        self.process.errorOccurred.connect(self.on_error)
        self.process.finished.connect(self.on_finished)

    def start(self):
        if self.active or self.done:
            return
        command = build_direct_command(self.job.urls[0], self.job.destination)
        self.active = True
        self.process.start(command[0], command[1:])

    def drain_output(self):
        self.process.readAllStandardOutput()
        chunk = bytes(self.process.readAllStandardError())
        self.stderr_tail = (self.stderr_tail + chunk)[-self.MAX_STDERR_BYTES:]

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.complete(False, "Could not start aria2c.")

    def on_finished(self, code, status):
        self.drain_output()
        success = code == 0 and status == QProcess.ExitStatus.NormalExit
        self.complete(success, "Download complete" if success else "Download failed")

    def complete(self, success, message):
        if self.done:
            return
        self.done = True
        self.active = False
        if not self.closing:
            self.finished.emit(success, message)

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
