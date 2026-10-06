"""Frontend-independent execution activity; progress metrics belong elsewhere."""

from dataclasses import dataclass
from enum import Enum


class StatusKind(Enum):
    STARTING_ENGINE = "starting_engine"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTING = "aborting"
    ABORTED = "aborted"


class StatusReason(Enum):
    START_FAILED = "start_failed"


@dataclass(frozen=True)
class StatusEvent:
    kind: StatusKind
    engine: str | None = None
    reason: StatusReason | None = None
