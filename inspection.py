"""Shared classification in CLI route order; no prompts or downloader execution.

Single non-YouTube URLs retain the existing 4096-byte stream GET probe
(15-second timeout), followed by direct-file detection, which may use HEAD
(10-second timeout). Bulk direct detection retains its existing HEAD behavior.
No metadata subprocesses, subtitle requests, or filesystem writes occur here.
"""

import argparse
from dataclasses import dataclass
from enum import Enum, auto
from urllib.parse import urlparse

from detector import (
    is_torrent_file_path,
    is_youtube_playlist_url,
    is_youtube_url,
    looks_like_direct_file,
    normalize_youtube_video_url,
)
from stream_parser import StreamInput, detect_stream_type, parse_stream_input


class InputKind(Enum):
    TORRENT = auto()
    YOUTUBE_SINGLE = auto()
    YOUTUBE_BULK = auto()
    YOUTUBE_PLAYLIST = auto()
    DIRECT_SINGLE = auto()
    DIRECT_BULK = auto()
    HLS = auto()
    DASH = auto()
    VTT = auto()
    GENERIC_YTDLP = auto()
    STREAM_INSPECTOR = auto()
    MIXED_BULK = auto()
    UNSUPPORTED = auto()


class MetadataStatus(Enum):
    NOT_REQUESTED = auto()
    PENDING = auto()
    AVAILABLE = auto()
    UNAVAILABLE = auto()


@dataclass
class InspectionResult:
    kind: InputKind
    urls: list[str]
    stream: StreamInput | None = None
    route_kind: InputKind | None = None
    error: str | None = None
    title: str | None = None
    item_count: int | None = None
    metadata_status: MetadataStatus = MetadataStatus.NOT_REQUESTED

    @property
    def route(self) -> InputKind:
        return self.route_kind or self.kind


def build_stream_input_from_args(
    args: argparse.Namespace,
    media_url: str,
) -> StreamInput:
    """Copy parsed handoff values into a stream input without routing it."""
    headers = {}
    if args.user_agent is not None:
        headers["User-Agent"] = args.user_agent
    if args.referer is not None:
        headers["Referer"] = args.referer

    return StreamInput(
        url=media_url,
        headers=headers,
        title=args.title,
        subtitles=list(args.subtitle),
    )


def has_stream_inspector_args(args: argparse.Namespace) -> bool:
    return (
        args.user_agent is not None
        or args.referer is not None
        or bool(args.subtitle)
        or args.title is not None
    )


def classify_input(args: argparse.Namespace) -> InspectionResult:
    """Inspect parsed input using the mature CLI precedence without executing it."""
    urls = list(args.urls)
    assisted = has_stream_inspector_args(args)
    if assisted and len(urls) != 1:
        return InspectionResult(InputKind.UNSUPPORTED, urls, error=
            "Error: Stream Inspector handoff expects exactly one selected media URL.")

    if len(urls) > 1:
        if all(is_youtube_url(url) for url in urls):
            return InspectionResult(InputKind.YOUTUBE_BULK, [
                normalize_youtube_video_url(url) for url in urls
            ])
        direct_urls = [
            urlparse(url).scheme in {"http", "https"}
            and not is_youtube_url(url)
            and looks_like_direct_file(url)
            for url in urls
        ]
        if all(direct_urls):
            return InspectionResult(InputKind.DIRECT_BULK, urls)
        return InspectionResult(InputKind.MIXED_BULK, urls, error=
            "Error: bulk mode supports only all-YouTube or all-direct URLs; "
            "mixed batches are unsupported.")

    raw_input = urls[0]
    if is_torrent_file_path(raw_input):
        return InspectionResult(InputKind.TORRENT, urls)

    stream = (
        build_stream_input_from_args(args, raw_input)
        if assisted else parse_stream_input(raw_input)
    )
    if urlparse(stream.url).scheme not in {"http", "https"}:
        return InspectionResult(InputKind.UNSUPPORTED, urls, error=
            "Error: only HTTP and HTTPS URLs are supported.")

    if is_youtube_playlist_url(stream.url):
        kind = InputKind.YOUTUBE_PLAYLIST
        urls = [stream.url]
    elif is_youtube_url(stream.url):
        kind = InputKind.YOUTUBE_SINGLE
        urls = [normalize_youtube_video_url(stream.url)]
    else:
        stream.stream_type = detect_stream_type(stream)
        if stream.stream_type == "hls":
            kind = InputKind.HLS
        elif stream.stream_type == "dash":
            kind = InputKind.DASH
        elif stream.stream_type == "vtt":
            kind = InputKind.VTT
        elif looks_like_direct_file(stream.url):
            kind = InputKind.DIRECT_SINGLE
        else:
            kind = InputKind.GENERIC_YTDLP
        urls = [stream.url]

    return InspectionResult(
        InputKind.STREAM_INSPECTOR if assisted else kind,
        urls,
        stream=stream,
        route_kind=kind if assisted else None,
    )
