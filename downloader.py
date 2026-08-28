from pathlib import Path
from tempfile import TemporaryDirectory

from stream_parser import StreamInput
from utils import run_command

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


def download_direct_bulk(urls: list[str]) -> int:
    total = len(urls)

    print("Input type: direct HTTP files")
    print("Download engine: aria2c")

    with TemporaryDirectory(prefix="aidm-bulk-") as temp_dir:
        input_path = Path(temp_dir) / "urls.txt"
        input_path.write_text("\n".join(urls) + "\n")

        command = [
            "aria2c",
            "--continue=true",
            "--max-connection-per-server=1",
            "--split=1",
            "--min-split-size=1M",
            "--console-log-level=warn",
            "--summary-interval=1",
            f"--max-concurrent-downloads={total}",
            f"--input-file={input_path}",
        ]

        result = run_command(command)

    if result == 0:
        print(f"{total} Files Downloaded Successfully 💫🎉")

    return result


def download_direct_bulk_sequential(urls: list[str]) -> int:
    total = len(urls)

    for index, url in enumerate(urls, start=1):
        print(f"[{index}/{total}] Downloading...")

        result = download_direct(url)

        if result != 0:
            return result

    print(f"{total} Files Downloaded Successfully 💫🎉")
    return 0


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
        ARIA2_DOWNLOADER_ARGUMENTS,
        url,
    ]

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
