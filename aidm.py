#!/usr/bin/env python3

import argparse
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


DIRECT_EXTENSIONS = {
    ".zip", ".deb", ".iso", ".pdf", ".tar", ".gz", ".xz", ".7z", ".rar",
    ".exe", ".msi", ".apk", ".mp3", ".mp4", ".mkv", ".webm", ".avi",
    ".jpg", ".jpeg", ".png"
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


def run_command(command: list[str]) -> int:
    print("\nRunning:")
    print(" ".join(command))
    print()

    try:
        return subprocess.run(command).returncode
    except FileNotFoundError:
        print(f"Error: '{command[0]}' is not installed or not in PATH.")
        return 127
    except KeyboardInterrupt:
        print("\nDownload cancelled.")
        return 130


def is_youtube_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()

    return (
        hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
        or hostname == "youtu.be"
        or hostname.endswith(".youtu.be")
    )


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
                "Content-Disposition", ""
            ).lower()

            content_type = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip().lower()

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


def download_direct(url: str) -> int:
    print("Input type: direct HTTP file")
    print("Download engine: aria2c")

    command = [
        "aria2c",
        "--continue=true",
        "--max-connection-per-server=8",
        "--split=8",
        "--min-split-size=1M",
        url,
    ]

    return run_command(command)


def choose_youtube_mode() -> str:
    while True:
        print("\nYouTube download options:")
        print("1 - Download Video")
        print("2 - Download Audio (Original Best Quality)")
        print("3 - Download Audio (Convert to WAV)")

        choice = input("Select option [1/2/3]: ").strip()

        if choice == "1":
            return "video"

        if choice == "2":
            return "audio"

        if choice == "3":
            return "wav"

        print("Invalid option. Enter 1, 2 or 3.")


def download_youtube_video(url: str) -> int:
    print("Mode: YouTube video")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = [
        "yt-dlp",
        "-f",
        "bv*[vcodec^=vp09]+ba[acodec=opus]/bv*+ba/b",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        "aria2c:-x 8 -s 8 -k 1M",
        url,
    ]

    return run_command(command)


def download_youtube_audio(url: str) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Output: original best available audio")

    command = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        "aria2c:-x 8 -s 8 -k 1M",
        url,
    ]

    return run_command(command)


def download_youtube_audio_wav(url: str) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Conversion: FFmpeg → WAV")

    command = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        "aria2c:-x 8 -s 8 -k 1M",
        "--extract-audio",
        "--audio-format",
        "wav",
        url,
    ]

    return run_command(command)


def download_youtube(url: str) -> int:
    mode = choose_youtube_mode()

    if mode == "video":
        return download_youtube_video(url)

    if mode == "audio":
        return download_youtube_audio(url)

    return download_youtube_audio_wav(url)


def download_with_ytdlp(url: str) -> int:
    print("Input type: supported website/media URL")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = [
        "yt-dlp",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        "aria2c:-x 8 -s 8 -k 1M",
        url,
    ]

    return run_command(command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIDM terminal download router"
    )

    parser.add_argument(
        "url",
        help="Direct download link or supported website URL",
    )

    args = parser.parse_args()
    url = args.url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        print("Error: only HTTP and HTTPS URLs are supported.")
        return 2

    if is_youtube_url(url):
        return download_youtube(url)

    if looks_like_direct_file(url):
        return download_direct(url)

    return download_with_ytdlp(url)


if __name__ == "__main__":
    sys.exit(main())