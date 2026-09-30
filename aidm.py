#!/usr/bin/env python3

import argparse
import sys

from downloader import (
    download_direct,
    download_direct_bulk,
    download_direct_bulk_sequential,
    download_stream,
    download_subtitle,
    download_torrent,
    download_with_ytdlp,
)
from inspection import (
    InputKind,
    build_stream_input_from_args,
    classify_input,
    has_stream_inspector_args,
)
from stream_parser import StreamInput
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
        help="Stream Inspector User-Agent for media requests",
    )
    parser.add_argument(
        "--referer",
        help="Stream Inspector Referer for media requests",
    )
    parser.add_argument(
        "--subtitle",
        action="append",
        default=[],
        help="Stream Inspector subtitle URL (one sidecar supported; requires --title)",
    )
    parser.add_argument(
        "--title",
        help="Stream Inspector title for media output naming",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def download_media_with_sidecar(stream: StreamInput) -> int:
    """Download main media before attempting an optional subtitle sidecar."""
    if stream.stream_type in {"hls", "dash"}:
        media_result = download_stream(stream)
    else:
        media_result = download_with_ytdlp(
            stream.url,
            title=stream.title,
            headers=stream.headers,
        )

    if media_result != 0 or not stream.subtitles:
        return media_result

    if len(stream.subtitles) > 1:
        print("Warning: multiple subtitle sidecars are not yet supported; subtitles skipped.")
        return 0

    if not stream.title:
        print("Warning: subtitle skipped because no title was supplied for deterministic sidecar naming.")
        return 0

    subtitle_result = download_subtitle(
        stream.subtitles[0],
        stream.title,
        headers=stream.headers,
    )
    if subtitle_result != 0:
        print("Warning: subtitle download failed; main media downloaded successfully.")

    return 0


def run_from_args(args: argparse.Namespace) -> int:
    result = classify_input(args)
    route = result.route

    if result.error is not None:
        print(result.error)
        return 2

    if route == InputKind.YOUTUBE_BULK:
        print(f"{len(result.urls)} YouTube URLs detected.✅")
        return download_youtube(result.urls)

    if route == InputKind.DIRECT_BULK:
        print(f"{len(result.urls)} Direct URLs Detected✅")
        while True:
            print("Choose Mode: [1/2]")
            print()
            print("1 - Sequential")
            print("2 - Parallel")
            mode = input().strip()
            if mode == "1":
                return download_direct_bulk_sequential(result.urls)
            if mode == "2":
                return download_direct_bulk(result.urls)

    if route == InputKind.TORRENT:
        return download_torrent(result.urls[0])

    if route == InputKind.YOUTUBE_PLAYLIST:
        print("YouTube playlist detected. ✅")
        return download_youtube_playlist(result.urls[0])

    if route == InputKind.YOUTUBE_SINGLE:
        return download_youtube(result.urls)

    if route == InputKind.VTT:
        print("Detected a WebVTT subtitle stream, not the main video.")
        return 3

    if route == InputKind.DIRECT_SINGLE:
        return download_direct(result.urls[0])

    return download_media_with_sidecar(result.stream)


def main() -> int:
    return run_from_args(parse_args())


if __name__ == "__main__":
    sys.exit(main())
