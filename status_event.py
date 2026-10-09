"""Frontend-independent execution activity; progress metrics belong elsewhere."""

from dataclasses import dataclass
from enum import Enum


class StatusKind(Enum):
    STARTING_ENGINE = "starting_engine"
    DOWNLOADING = "downloading"
    DOWNLOADING_VIDEO = "downloading_video"
    DOWNLOADING_AUDIO = "downloading_audio"
    DOWNLOADING_SUBTITLE = "downloading_subtitle"
    MERGING = "merging"
    CONVERTING_AUDIO = "converting_audio"
    REMUXING = "remuxing"
    FINALIZING = "finalizing"
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
