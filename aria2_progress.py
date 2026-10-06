"""Parse aria2c single-transfer console readouts; ignore other console output.

Verified against aria2c 1.37.0 captures and ConsoleStatCalc/util.cc at that tag.
GUI telemetry uses exact byte readouts; human-readable captures are also accepted.
The /0B unknown-total sentinel becomes None. Percent is never manufactured.
"""

from decimal import Decimal
from collections.abc import Callable
import os.path
import re
import sys

from progress_event import ProgressEvent


_SIZE = r"[0-9]+(?:\.[0-9]+)?(?:KiB|MiB|GiB|B)"
_RECORD = re.compile(
    rf"\[#[0-9a-fA-F]{{6,16}} (?P<downloaded>{_SIZE})/(?P<total>{_SIZE})"
    r"(?:\((?P<percent>[0-9]+(?:\.[0-9]+)?)%\))? CN:[0-9]+"
    rf"(?: DL:(?P<speed>{_SIZE}))?(?: ETA:(?P<eta>[0-9hms]+))?\]"
)
_ETA = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}


def _bytes(value: str) -> int:
    number, unit = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([A-Za-z]+)", value).groups()
    return int(Decimal(number) * _UNITS[unit])


def parse_aria2_progress(line: str) -> ProgressEvent | None:
    if len(line) > Aria2ProgressParser.MAX_RECORD_BYTES:
        return None
    record = _RECORD.fullmatch(line.strip())
    if record is None:
        return None
    eta = None
    if record["eta"] is not None:
        parts = _ETA.fullmatch(record["eta"])
        if parts is None or not any(parts.groups()):
            return None
        eta = sum(int(value or 0) * scale for value, scale in zip(parts.groups(), (3600, 60, 1)))
    try:
        return ProgressEvent(
            percent=float(record["percent"]) if record["percent"] is not None else None,
            downloaded_bytes=_bytes(record["downloaded"]),
            total_bytes=_bytes(record["total"]) or None,
            speed_bytes_per_second=_bytes(record["speed"]) if record["speed"] else None,
            eta_seconds=eta,
        )
    except ValueError:
        # A malformed readout must not interrupt the download.
        return None


def parse_aria2_filename(line: str) -> str | None:
    """Accept explicit runtime FILE records, never URLs or completion tables."""
    if not line.startswith("FILE: ") or len(line) > Aria2ProgressParser.MAX_RECORD_BYTES:
        return None
    path = line[len("FILE: "):]
    if not os.path.isabs(path) or any(ord(char) < 32 or ord(char) == 127 for char in path):
        return None
    name = os.path.basename(path)
    return name if name and name not in {".", ".."} else None


class Aria2ProgressParser:
    """Bounded CR/LF framing across arbitrary stdout reads, including final tails."""

    MAX_RECORD_BYTES = 4096

    def __init__(self, on_filename: Callable[[str], None] | None = None):
        self._buffer = b""
        self._discarding = False
        self._on_filename = on_filename

    def feed(self, chunk: bytes, *, final: bool = False) -> list[ProgressEvent]:
        events = []
        parts = re.split(br"[\r\n]", chunk)
        for index, part in enumerate(parts):
            if not self._discarding:
                if len(self._buffer) + len(part) > self.MAX_RECORD_BYTES:
                    self._buffer = b""
                    self._discarding = True
                else:
                    self._buffer += part
            if index < len(parts) - 1 or final:
                if not self._discarding:
                    # Decode only complete records, including split multibyte names.
                    line = self._buffer.decode(sys.getfilesystemencoding(), errors="replace")
                    if self._on_filename is not None:
                        filename = parse_aria2_filename(line)
                        if filename is not None:
                            self._on_filename(filename)
                    event = parse_aria2_progress(line)
                    if event is not None:
                        events.append(event)
                self._buffer = b""
                self._discarding = False
        return events
