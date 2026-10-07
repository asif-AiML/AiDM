"""Bounded yt-dlp JSON telemetry, plus its external aria2 transfer readouts.

Templates verified with yt-dlp 2026.08.19. Exact totals only; estimated totals
are deliberately omitted. Percent describes the current stream, not the job.
"""

import json
import math
import re

from aria2_progress import parse_aria2_progress
from progress_event import ProgressEvent
from status_event import StatusEvent, StatusKind


DOWNLOAD_PREFIX = "AIDM_PROGRESS:"
POSTPROCESS_PREFIX = "AIDM_POSTPROCESS:"
DOWNLOAD_TEMPLATE = (
    'download:' + DOWNLOAD_PREFIX + '{"progress":'
    '%(progress.{status,downloaded_bytes,total_bytes,total_bytes_estimate,speed,eta})j,'
    '"info":%(info.{vcodec,acodec})j}'
)
POSTPROCESS_TEMPLATE = (
    "postprocess:" + POSTPROCESS_PREFIX + "%(progress.{status,postprocessor})j"
)


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def parse_ytdlp_record(line: str) -> list[StatusEvent | ProgressEvent]:
    """Only recognize our sentinels or the existing strict aria2 record format."""
    if len(line) > YtDlpProgressParser.MAX_RECORD_BYTES:
        return []
    try:
        if line.startswith(POSTPROCESS_PREFIX):
            data = json.loads(line[len(POSTPROCESS_PREFIX):])
            if not isinstance(data, dict) or data.get("status") != "started":
                return []
            kind = {
                "Merger": StatusKind.MERGING,
                "ExtractAudio": StatusKind.CONVERTING_AUDIO,
                "VideoRemuxer": StatusKind.REMUXING,
                "MoveFiles": StatusKind.FINALIZING,
            }.get(data.get("postprocessor"))
            # No download metrics are known for post-processing. Clear the old
            # stream snapshot, without manufacturing post-processing percentage.
            return [ProgressEvent(), StatusEvent(kind, "yt-dlp")] if kind else []
        if line.startswith(DOWNLOAD_PREFIX):
            data = json.loads(line[len(DOWNLOAD_PREFIX):])
            if not isinstance(data, dict):
                return []
            progress, info = data.get("progress"), data.get("info", {})
            if not isinstance(progress, dict) or not isinstance(info, dict):
                return []
            if progress.get("status") not in {"downloading", "finished"}:
                return []
            downloaded = _number(progress.get("downloaded_bytes"))
            total = _number(progress.get("total_bytes")) or None
            speed = _number(progress.get("speed"))
            eta = _number(progress.get("eta"))
            percent = (100 * downloaded / total
                       if downloaded is not None and total and downloaded <= total else None)
            event = ProgressEvent(
                percent=percent,
                downloaded_bytes=int(downloaded) if downloaded is not None else None,
                total_bytes=int(total) if total is not None else None,
                speed_bytes_per_second=int(speed) if speed is not None else None,
                eta_seconds=int(eta) if eta is not None else None,
            )
            kind = StatusKind.DOWNLOADING
            if progress["status"] == "downloading":
                if info.get("vcodec") == "none" and info.get("acodec") not in (None, "none"):
                    kind = StatusKind.DOWNLOADING_AUDIO
                elif info.get("acodec") == "none" and info.get("vcodec") not in (None, "none"):
                    kind = StatusKind.DOWNLOADING_VIDEO
            return [StatusEvent(kind, "yt-dlp"), event]
    except (ValueError, TypeError, OverflowError, RecursionError):
        return []
    event = parse_aria2_progress(line)
    return [StatusEvent(StatusKind.DOWNLOADING, "yt-dlp"), event] if event else []


class YtDlpProgressParser:
    """Frame arbitrary UTF-8 stdout chunks; discard oversized/unrelated output."""

    MAX_RECORD_BYTES = 8192

    def __init__(self):
        self._buffer = b""
        self._discarding = False

    def feed(self, chunk: bytes, *, final=False):
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
                    events.extend(parse_ytdlp_record(self._buffer.decode("utf-8", errors="replace")))
                self._buffer = b""
                self._discarding = False
        return events
