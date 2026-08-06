from dataclasses import dataclass, field
import urllib.error
import urllib.request
from urllib.parse import parse_qsl


HLS_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}

DASH_CONTENT_TYPES = {
    "application/dash+xml",
}

VTT_CONTENT_TYPES = {
    "text/vtt",
}


@dataclass
class StreamInput:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    stream_type: str | None = None


def parse_stream_input(raw_input: str) -> StreamInput:
    """
    Supports:

    1. Plain URL:
       https://example.com/path/master.m3u8?token=...

    2. Stream Detector format:
       URL|User-Agent=...&Referer=...
    """

    raw_input = raw_input.strip()

    if "|" not in raw_input:
        return StreamInput(url=raw_input)

    url, encoded_headers = raw_input.split("|", 1)

    headers = {
        name.strip(): value.strip()
        for name, value in parse_qsl(
            encoded_headers,
            keep_blank_values=True,
        )
        if name.strip()
    }

    return StreamInput(
        url=url.strip(),
        headers=headers,
    )


def detect_stream_type(stream: StreamInput) -> str | None:
    """
    Detects stream type from response MIME type and initial content.

    Returns:
        "hls"
        "dash"
        "vtt"
        None
    """

    request_headers = {
        "User-Agent": "Mozilla/5.0",
        "Range": "bytes=0-4095",
        **stream.headers,
    }

    request = urllib.request.Request(
        stream.url,
        headers=request_headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content_type = (
                response.headers.get("Content-Type", "")
                .split(";")[0]
                .strip()
                .lower()
            )

            content = response.read(4096).decode(
                "utf-8",
                errors="ignore",
            )

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ) as error:
        print(f"Stream probe failed: {error}")
        return None

    if content_type in HLS_CONTENT_TYPES:
        return "hls"

    if content_type in DASH_CONTENT_TYPES:
        return "dash"

    if content_type in VTT_CONTENT_TYPES:
        return "vtt"

    stripped_content = content.lstrip()

    if stripped_content.startswith("#EXTM3U"):
        return "hls"

    if "<MPD" in content or "<mpd" in content:
        return "dash"

    if stripped_content.startswith("WEBVTT"):
        return "vtt"

    return None