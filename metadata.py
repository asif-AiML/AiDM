"""Optional pre-download metadata policy; no execution or Qt dependency."""

from dataclasses import replace
import json

from inspection import InputKind, InspectionResult, MetadataStatus


def prepare_metadata(result: InspectionResult) -> InspectionResult:
    """Use authoritative/local information before requesting remote metadata."""
    if result.error:
        return result
    if result.stream and result.stream.title and result.stream.title.strip():
        return replace(result, title=result.stream.title, metadata_status=MetadataStatus.AVAILABLE)
    if result.kind == InputKind.STREAM_INSPECTOR:
        # The browser handoff is authoritative, including an absent title.
        return replace(result, title=result.stream.title if result.stream else None,
                       metadata_status=MetadataStatus.NOT_REQUESTED)
    if result.route in {InputKind.YOUTUBE_BULK, InputKind.DIRECT_BULK}:
        return replace(result, item_count=len(result.urls), metadata_status=MetadataStatus.AVAILABLE)
    if result.route == InputKind.DIRECT_SINGLE:
        # Intentionally untitled before execution; aria2c will resolve the name.
        # Inspector-supplied titles remain authoritative via the rule above.
        return replace(result, title=None, metadata_status=MetadataStatus.NOT_REQUESTED)
    if result.route in {InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_PLAYLIST, InputKind.GENERIC_YTDLP}:
        return replace(result, metadata_status=MetadataStatus.PENDING)
    # Naked HLS/DASH and unsupported workflows need no invented title.
    return result


def build_metadata_command(result: InspectionResult) -> list[str] | None:
    if result.metadata_status != MetadataStatus.PENDING:
        return None
    playlist = result.route == InputKind.YOUTUBE_PLAYLIST
    template = '{"title": %(title)j, "item_count": %(playlist_count)j}'
    command = [
        "yt-dlp", "--ignore-config", "--no-plugin-dirs", "--no-cache-dir",
        "--no-js-runtimes", "--simulate", "--skip-download",
        "--no-check-formats", "--ignore-no-formats-error",
        "--socket-timeout", "10", "--retries", "0", "--extractor-retries", "0",
        "--flat-playlist", "--playlist-end", "1",
        "--yes-playlist" if playlist else "--no-playlist",
        "--output-na-placeholder", "null",
        "--print", ("playlist:" if playlist else "video:") + template,
    ]
    # No output files, format listing, quality discovery or per-video playlist
    # extraction. Ignore user config so it cannot add downloads or side effects.
    for name, value in (result.stream.headers if result.stream else {}).items():
        command.extend(["--add-header", f"{name}:{value}"])
    command.extend(["--", result.urls[0]])
    return command


def read_metadata(result: InspectionResult, output: bytes) -> InspectionResult:
    """Read only title and explicitly reported playlist total, never entry length."""
    try:
        data = json.loads(output)
    except (ValueError, UnicodeError):
        data = None
    if not isinstance(data, dict):
        return replace(result, metadata_status=MetadataStatus.UNAVAILABLE)
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        title = None
    count = data.get("item_count") if result.route == InputKind.YOUTUBE_PLAYLIST else None
    if type(count) is not int or count < 0:
        count = None
    return replace(
        result, title=title, item_count=count,
        metadata_status=MetadataStatus.AVAILABLE if title or count is not None else MetadataStatus.UNAVAILABLE,
    )
