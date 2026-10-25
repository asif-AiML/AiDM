"""Cancellable adapter for the existing backend quality-discovery helper."""

import json
from pathlib import Path
import sys

from gui_metadata import MetadataProcess


def quality_command(url):
    # The backend owns extraction/parsing. This child only serializes its result.
    script = (
        "import contextlib,json,sys; from youtube import get_available_youtube_qualities; "
        "\nwith contextlib.redirect_stdout(sys.stderr):\n"
        " qualities = get_available_youtube_qualities(sys.argv[1], inspection_only=True)\n"
        "print(json.dumps(qualities))"
    )
    return [sys.executable, "-B", "-c", script, url]


class QualityProcess(MetadataProcess):
    """Reuse bounded output, timeout, process-group cancellation and cleanup."""

    def __init__(self, generation, url, parent=None):
        super().__init__(generation, None, parent)
        self.url = url
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parent))

    def start(self):
        command = quality_command(self.url)
        self.timeout.start(self.TIMEOUT_MS)
        self.process.start(command[0], command[1:])

    def complete(self, success):
        if self.done:
            return
        self.done = True
        self.timeout.stop()
        qualities = []
        if success:
            try:
                value = json.loads(bytes(self.output))
            except (ValueError, UnicodeError):
                value = None
            if isinstance(value, list) and all(type(h) is int and h > 0 for h in value):
                qualities = value
        if not self.cancelled:
            self.finished.emit(self.revision, qualities)
        self.deleteLater()
