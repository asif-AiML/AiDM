from stream_parser import StreamInput
from utils import run_command, sanitize_filename

ARIA2_DOWNLOADER_ARGUMENTS = "aria2c:-x 8 -s 8 -k 1M"


def download_direct(url: str) -> int:
    print("Input type: direct HTTP file")
    print("Download engine: aria2c")

    command = [
        "aria2c",
        "--continue=true",
        "--max-connection-per-server=1",
        "--split=1",
        "--min-split-size=1M",
        "--console-log-level=warn",
        "--summary-interval=1",
        url,
    ]

    return run_command(command)


def download_with_ytdlp(url: str, title: str | None = None) -> int:
    print("Input type: supported website/media URL")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = [
    "yt-dlp",
    ]

    if title:
        safe_title = sanitize_filename(title)
        command.extend([
            "-o",
            f"{safe_title}.%(ext)s",
        ])

    command.extend([
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        ARIA2_DOWNLOADER_ARGUMENTS,
        url,
    ])


    return run_command(command)


def download_stream(stream: StreamInput) -> int:
    print(f"Input type: {stream.stream_type.upper()} stream")
    print("Extractor/downloader: yt-dlp native")
    print("Post-processing: FFmpeg when required")

    command = [
        "yt-dlp",
        "--downloader",
        "dash,m3u8:native",
    ]

    for header_name, header_value in stream.headers.items():
        command.extend([
            "--add-header",
            f"{header_name}:{header_value}",
        ])

    command.append(stream.url)

    return run_command(command)