"""Cancellable Qt-native metadata subprocess, independent of download execution."""

from dataclasses import replace
import os
import signal

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from inspection import MetadataStatus
from metadata import build_metadata_command, read_metadata


class MetadataProcess(QObject):
    finished = Signal(int, object)
    TIMEOUT_MS = 20000
    MAX_OUTPUT_BYTES = 262144

    def __init__(self, revision, result, parent=None):
        super().__init__(parent)
        self.revision = revision
        self.result = result
        self.output = bytearray()
        self.cancelled = False
        self.failed = False
        self.done = False
        self.process = QProcess(self)
        # AiDM targets Linux. Isolate the process group so cancellation also
        # stops any extractor children, rather than leaving orphan processes.
        parameters = QProcess.UnixProcessParameters()
        parameters.flags = QProcess.UnixProcessFlag.CreateNewSession
        self.process.setUnixProcessParameters(parameters)
        self.process.setStandardInputFile(QProcess.nullDevice())
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.on_timeout)

    def start(self):
        command = build_metadata_command(self.result)
        if command is None:
            return
        self.timeout.start(self.TIMEOUT_MS)
        self.process.start(command[0], command[1:])

    def read_output(self):
        chunk = bytes(self.process.readAllStandardOutput())
        if len(self.output) + len(chunk) > self.MAX_OUTPUT_BYTES:
            self.failed = True
            self.stop_process()
        elif not self.failed:
            self.output.extend(chunk)

    def stop_process(self):
        pid = self.process.processId()
        if pid:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.kill()

    def cancel(self, wait=False):
        self.cancelled = True
        self.timeout.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_process()
            if wait:
                self.process.waitForFinished(1000)

    def on_timeout(self):
        self.failed = True
        self.stop_process()

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.complete(False)

    def on_finished(self, code, status):
        self.read_output()
        self.complete(code == 0 and status == QProcess.ExitStatus.NormalExit and not self.failed)

    def complete(self, success):
        if self.done:
            return
        self.done = True
        self.timeout.stop()
        if not self.cancelled:
            result = (
                read_metadata(self.result, bytes(self.output)) if success
                else replace(self.result, metadata_status=MetadataStatus.UNAVAILABLE)
            )
            self.finished.emit(self.revision, result)
        self.deleteLater()
