#!/usr/bin/env python3

import argparse
import sys
from urllib.parse import urlparse

from detector import is_youtube_url, looks_like_direct_file
from downloader import download_direct, download_with_ytdlp
from youtube import download_youtube


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