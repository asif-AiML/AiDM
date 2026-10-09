"""Parallel aria2 telemetry verified against local 1.37.0 captures.

Use full periodic summaries, not compact [DL:...] readouts (whose speed can
include recently completed transfers). Match completion notices to GIDs through
runtime FILE paths. Final OK result rows also prove completion, including items
which never appeared in a summary. Disappearance alone never proves success.
"""

from dataclasses import dataclass
import re

from aria2_progress import Aria2ProgressParser, _RECORD, parse_aria2_progress, parse_aria2_filename
from progress_event import ProgressEvent


@dataclass(frozen=True)
class Aria2Snapshot:
    items: dict[str, ProgressEvent]


@dataclass(frozen=True)
class Aria2Completed:
    gid: str


_NOTICE = re.compile(r"^\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[NOTICE\] Download complete: (.+)$")
_RESULT = re.compile(r"^([0-9a-fA-F]{6,16})\|OK\s*\|[^|]*\|(.+)$")


class Aria2ParallelProgressParser(Aria2ProgressParser):
    def __init__(self, total_items):
        super().__init__()
        self.total_items = total_items
        self._snapshot = None
        self._last_gid = None
        self._paths = {}
        self._results = False

    def parse_line(self, line):
        stripped = line.strip()
        if stripped.startswith("*** Download Progress Summary as of ") and stripped.endswith(" ***"):
            # A missing footer discards the partial snapshot, rather than
            # mistaking it for the complete active set.
            self._snapshot = {}
            self._last_gid = None
            return []
        if not stripped and self._snapshot is not None:
            snapshot, self._snapshot = self._snapshot, None
            self._last_gid = None
            return [Aria2Snapshot(snapshot)]
        if self._snapshot is not None:
            record = _RECORD.fullmatch(stripped)
            progress = parse_aria2_progress(stripped) if record else None
            if progress is not None and len(self._snapshot) < self.total_items:
                self._last_gid = record['gid'].lower()
                self._snapshot[self._last_gid] = progress
            elif line.startswith('FILE: ') and self._last_gid is not None:
                if parse_aria2_filename(line) is not None:
                    if self._last_gid in self._paths or len(self._paths) < self.total_items:
                        self._paths[self._last_gid] = line[len('FILE: '):]
                self._last_gid = None
        notice = _NOTICE.fullmatch(line)
        if notice:
            matches = [gid for gid, path in self._paths.items() if path == notice[1]]
            # Ambiguous/unseen paths wait for a GID result or successful exit.
            return [Aria2Completed(matches[0])] if len(matches) == 1 else []
        if stripped == 'Download Results:':
            self._results = True
        elif self._results:
            result = _RESULT.fullmatch(line)
            if result:
                return [Aria2Completed(result[1].lower())]
            if stripped == 'Status Legend:':
                self._results = False
        return []
