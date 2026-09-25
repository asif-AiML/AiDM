#!/usr/bin/env python3

import argparse
import sys
from urllib.parse import urlparse

from detector import (
    is_torrent_file_path,
    is_youtube_playlist_url,
    is_youtube_url,
    looks_like_direct_file,
    normalize_youtube_video_url,
)
from downloader import (
    download_direct,
    download_direct_bulk,
    download_direct_bulk_sequential,
    download_stream,
    download_torrent,
    download_with_ytdlp,
)
from stream_parser import StreamInput, detect_stream_type, parse_stream_input
from youtube import download_youtube, download_youtube_playlist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AIDM terminal download router"
    )

    parser.add_argument(
        "urls",
        nargs="+",
        help="One or more direct links, website URLs, or stream inputs",
    )

    parser.add_argument(
        "--user-agent",
        help="Stream Inspector User-Agent (not yet applied)",
    )
    parser.add_argument(
        "--referer",
        help="Stream Inspector Referer (not yet applied)",
    )
    parser.add_argument(
        "--subtitle",
        action="append",
        default=[],
        help="Stream Inspector subtitle URL (repeatable; not yet downloaded)",
    )
    parser.add_argument(
        "--title",
        help="Stream Inspector title (not yet applied)",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


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


def run_from_args(args: argparse.Namespace) -> int:
    if len(args.urls) > 1:
        if all(is_youtube_url(url) for url in args.urls):
            youtube_urls = [
                normalize_youtube_video_url(url)
                for url in args.urls
            ]

            print(f"{len(youtube_urls)} YouTube URLs detected.✅")
            return download_youtube(youtube_urls)

        direct_urls = [
            urlparse(url).scheme in {"http", "https"}
            and not is_youtube_url(url)
            and looks_like_direct_file(url)
            for url in args.urls
        ]

        if all(direct_urls):
            print(f"{len(args.urls)} Direct URLs Detected✅")

            while True:
                print("Choose Mode: [1/2]")
                print()
                print("1 - Sequential")
                print("2 - Parallel")

                mode = input().strip()

                if mode == "1":
                    return download_direct_bulk_sequential(args.urls)

                if mode == "2":
                    return download_direct_bulk(args.urls)

        print(
            "Error: bulk mode supports only all-YouTube or all-direct URLs; "
            "mixed batches are unsupported."
        )
        return 2

    raw_input = args.urls[0]

    if is_torrent_file_path(raw_input):
        return download_torrent(raw_input)

    stream = parse_stream_input(raw_input)
    parsed_url = urlparse(stream.url)

    if parsed_url.scheme not in {"http", "https"}:
        print("Error: only HTTP and HTTPS URLs are supported.")
        return 2

    if is_youtube_playlist_url(stream.url):
        print("YouTube playlist detected. ✅")
        return download_youtube_playlist(stream.url)

    if is_youtube_url(stream.url):
        youtube_url = normalize_youtube_video_url(stream.url)
        return download_youtube([youtube_url])

    stream.stream_type = detect_stream_type(stream)

    if stream.stream_type in {"hls", "dash"}:
        return download_stream(stream)

    if stream.stream_type == "vtt":
        print("Detected a WebVTT subtitle stream, not the main video.")
        return 3

    if looks_like_direct_file(stream.url):
        return download_direct(stream.url)

    return download_with_ytdlp(
        stream.url,
        headers=stream.headers,
    )


def main() -> int:
    return run_from_args(parse_args())


if __name__ == "__main__":
    sys.exit(main())
