"""Non-fatal workflow facts, independent of Qt and frontend wording."""

from enum import Enum


class WorkflowWarning(Enum):
    SUBTITLE_FAILED = "subtitle_failed"
    MULTIPLE_SUBTITLES_SKIPPED = "multiple_subtitles_skipped"
    SUBTITLE_WITHOUT_TITLE = "subtitle_without_title"
