import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DIRECT_EXTENSIONS = {
    ".zip",
    ".deb",
    ".iso",
    ".pdf",
    ".tar",
    ".gz",
    ".xz",
    ".7z",
    ".rar",
    ".exe",
    ".msi",
    ".apk",
    ".mp3",
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
    ".jpg",
    ".jpeg",
    ".png",
}


DIRECT_CONTENT_TYPES = {
    "application/octet-stream",
    "application/zip",
    "application/pdf",
    "application/x-debian-package",
    "application/vnd.debian.binary-package",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/ogg",
}


def is_youtube_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()

    return (
        hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
        or hostname == "youtu.be"
        or hostname.endswith(".youtu.be")
    )

def normalize_youtube_video_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if (
        hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
    ):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]

            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

    if (
        hostname == "youtu.be"
        or hostname.endswith(".youtu.be")
    ):
        video_id = parsed.path.strip("/")

        if video_id:
            return f"https://youtu.be/{video_id}"

    return url


def looks_like_direct_file(url: str) -> bool:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()

    if suffix in DIRECT_EXTENSIONS:
        return True

    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            content_disposition = response.headers.get(
                "Content-Disposition",
                "",
            ).lower()

            content_type = (
                response.headers.get("Content-Type", "")
                .split(";")[0]
                .strip()
                .lower()
            )

            if "attachment" in content_disposition:
                return True

            if content_type in DIRECT_CONTENT_TYPES:
                return True

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ):
        pass

    return False