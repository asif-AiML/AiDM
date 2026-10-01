"""Validated download requests, independent of frontend and execution."""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from inspection import InputKind, InspectionResult


class YouTubeMode(Enum):
    VIDEO = "video"
    ORIGINAL_AUDIO = "original_audio"
    WAV = "wav"


class BulkMode(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class VideoQuality(Enum):
    """Explicit best-available fallback; None means no choice yet."""
    BEST = "best"


@dataclass(frozen=True)
class DownloadJob:
    kind: InputKind
    urls: tuple[str, ...]
    mode: YouTubeMode | None = None
    video_quality: int | VideoQuality | None = None
    bulk_mode: BulkMode | None = None
    title: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    subtitles: tuple[str, ...] = ()
    # Inspector context does not override the mature underlying CLI route.
    route_kind: InputKind | None = None

    def __post_init__(self) -> None:
        supported = {
            InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK,
            InputKind.YOUTUBE_PLAYLIST, InputKind.DIRECT_SINGLE,
            InputKind.DIRECT_BULK, InputKind.HLS, InputKind.DASH,
            InputKind.GENERIC_YTDLP, InputKind.STREAM_INSPECTOR, InputKind.TORRENT,
        }
        if self.kind not in supported:
            raise ValueError("Input kind cannot form a download job")
        for name, values in (("urls", self.urls), ("subtitles", self.subtitles)):
            if not isinstance(values, (list, tuple)) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(values))
        if not isinstance(self.headers, Mapping) or any(
            name not in {"User-Agent", "Referer"} or not isinstance(value, str)
            for name, value in self.headers.items()
        ):
            raise ValueError("Only explicit User-Agent and Referer headers are supported")
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        if self.title is not None and not isinstance(self.title, str):
            raise ValueError("title must be a string or None")

        if self.kind == InputKind.STREAM_INSPECTOR:
            if self.route_kind not in {
                InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_PLAYLIST,
                InputKind.DIRECT_SINGLE, InputKind.HLS, InputKind.DASH,
                InputKind.GENERIC_YTDLP,
            }:
                raise ValueError("Inspector job requires a supported single-media route")
        elif self.route_kind is not None or self.headers or self.subtitles:
            raise ValueError("Browser context and route_kind require an Inspector job")

        bulk = self.kind in {InputKind.YOUTUBE_BULK, InputKind.DIRECT_BULK}
        if (bulk and len(self.urls) < 2) or (not bulk and len(self.urls) != 1):
            raise ValueError("Bulk jobs require multiple URLs; other jobs require exactly one input")
        route = self.route_kind or self.kind
        if route in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK}:
            if not isinstance(self.mode, YouTubeMode):
                raise ValueError("YouTube single/bulk requires an explicit YouTubeMode")
        elif self.mode is not None:
            raise ValueError("mode is only valid for YouTube single/bulk")
        needs_video_quality = route == InputKind.YOUTUBE_PLAYLIST or (
            route in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK}
            and self.mode == YouTubeMode.VIDEO
        )
        if needs_video_quality:
            if not (type(self.video_quality) is int and self.video_quality > 0
                    or self.video_quality is VideoQuality.BEST):
                raise ValueError("YouTube video requires a positive maximum height or explicit VideoQuality.BEST")
        elif self.video_quality is not None:
            raise ValueError("video_quality is only valid for YouTube VIDEO mode or playlists")
        if route == InputKind.DIRECT_BULK:
            if not isinstance(self.bulk_mode, BulkMode):
                raise ValueError("Direct bulk requires an explicit BulkMode")
        elif self.bulk_mode is not None:
            raise ValueError("bulk_mode is only valid for direct bulk")
        if self.kind == InputKind.DIRECT_SINGLE and self.title is not None:
            raise ValueError("Direct single has no pre-download title")


def build_download_job(
    result: InspectionResult,
    *,
    mode: YouTubeMode | None = None,
    video_quality: int | VideoQuality | None = None,
    bulk_mode: BulkMode | None = None,
) -> DownloadJob:
    """Snapshot classification and explicit choices; never inspect or execute."""
    if result.error is not None:
        raise ValueError(f"Cannot build job: {result.error}")
    urls = result.urls
    title = None if result.kind == InputKind.DIRECT_SINGLE else result.title
    headers = {}
    subtitles = ()
    if result.kind == InputKind.STREAM_INSPECTOR:
        if len(urls) != 1 or result.stream is None:
            raise ValueError("Inspector job requires one selected media URL and its context")
        # Use the exact selected URL even if routing normalized a YouTube URL.
        urls = [result.stream.url]
        title = result.stream.title
        headers = result.stream.headers
        subtitles = result.stream.subtitles
    elif result.stream and (result.stream.headers or result.stream.subtitles):
        raise ValueError("Browser context requires an Inspector classification")
    return DownloadJob(
        kind=result.kind, urls=urls, mode=mode, video_quality=video_quality,
        bulk_mode=bulk_mode, title=title, headers=headers, subtitles=subtitles,
        route_kind=result.route_kind,
    )
