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