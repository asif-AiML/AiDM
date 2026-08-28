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
        nargs="+",
        help="Direct link, website URL, or captured stream input",
    )

    args = parser.parse_args()

    if len(args.url) > 1:
        direct_urls = [looks_like_direct_file(url) for url in args.url]

        if all(direct_urls):
            print(f"{len(args.url)} Direct URLs Detected✅")
            return 0

        print("Error: bulk mode currently supports direct URLs only.")
        return 2

    stream = parse_stream_input(args.url[0])
    parsed_url = urlparse(stream.url)

    if parsed_url.scheme not in {"http", "https"}:
        print("Error: only HTTP and HTTPS URLs are supported.")
        return 2

    if is_youtube_url(stream.url):
        return download_youtube(stream.url)

    stream.stream_type = detect_stream_type(stream)

    if stream.stream_type in {"hls", "dash"}:
        return download_stream(stream)

    if stream.stream_type == "vtt":
        print("Detected a WebVTT subtitle stream, not the main video.")
        return 3

    if looks_like_direct_file(stream.url):
        return download_direct(stream.url)

    return download_with_ytdlp(stream.url)


if __name__ == "__main__":
    sys.exit(main())
