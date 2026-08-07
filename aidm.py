#!/usr/bin/env python3

import argparse
import sys
from urllib.parse import urlparse

from detector import is_youtube_url, looks_like_direct_file
from downloader import (
    download_direct,
    download_stream,
    download_with_ytdlp,
)
from stream_parser import detect_stream_type, parse_stream_input
from youtube import download_youtube


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIDM terminal download router"
    )

    parser.add_argument(
        "url",
        help="Direct link, website URL, or captured stream input",
    )

    args = parser.parse_args()

    stream = parse_stream_input(args.url)
    parsed_url = urlparse(stream.url)

    if parsed_url.scheme not in {"http", "https"}:
        print("Error: only HTTP and HTTPS URLs are supported.")
        return 2

    if is_youtube_url(stream.url):
        return download_youtube(stream.url)

    stream.stream_type = detect_stream_type(stream)

    if stream.stream_type in {"hls", "dash"}:
        title = input("Enter movie/video name: ").strip()

        if not title:
            title = "AIDM_Stream"

        return download_stream(stream, title)


    if stream.stream_type == "vtt":
        print("Detected a WebVTT subtitle stream, not the main video.")
        return 3


    if stream.stream_type == "unknown":
        print("\nStream probe inconclusive.")
        print("Delegating detection to yt-dlp...\n")

        title = input("Enter movie/video name (optional): ").strip()
        if not title:
            title = "AIDM_Stream"

        return download_with_ytdlp(
            stream.url,
            title,
            stream.headers,
        )


    if looks_like_direct_file(stream.url):
        return download_direct(stream.url)


    return download_with_ytdlp(
        stream.url,
        headers=stream.headers,
    )


if __name__ == "__main__":
    sys.exit(main())