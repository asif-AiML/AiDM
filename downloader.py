from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from stream_parser import StreamInput
from utils import run_command, sanitize_filename
from workflow_warning import WorkflowWarning
from ytdlp_progress import ytdlp_telemetry_options

ARIA2_DOWNLOADER_ARGUMENTS = "aria2c:-x 8 -s 8 -k 1M"
ARIA2_GUI_TELEMETRY_ARGUMENTS = (
    " --show-console-readout=true --enable-color=false"
    " --truncate-console-readout=false --human-readable=false --summary-interval=1"
)


def select_subtitle_sidecar(subtitles, title):
    """Shared CLI/GUI policy; the caller invokes this only after media success."""
    if not subtitles:
        return None, None
    if len(subtitles) > 1:
        return None, WorkflowWarning.MULTIPLE_SUBTITLES_SKIPPED
    if not title:
        return None, WorkflowWarning.SUBTITLE_WITHOUT_TITLE
    return subtitles[0], None


def download_subtitle(
    subtitle_url: str,
    title: str,
    headers: dict[str, str] | None = None,
) -> int:
    return run_command(build_subtitle_command(subtitle_url, title, headers))


def build_subtitle_command(
    subtitle_url: str, title: str, headers: dict[str, str] | None = None,
    *, destination: str | None = None,
) -> list[str]:
    suffix = Path(urlparse(subtitle_url).path).suffix.lower()
    if suffix not in {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".dfxp"}:
        suffix = ".vtt"

    safe_title = sanitize_filename(title)
    command = [
        "aria2c",
        "--continue=true",
        "--console-log-level=warn",
        "--summary-interval=1",
        f"--out={safe_title}{suffix}",
    ]

    for header_name, header_value in (headers or {}).items():
        command.append(f"--header={header_name}:{header_value}")

    if destination is not None:
        command.append(f"--dir={destination}")
    command.append(subtitle_url)
    return command


def download_torrent(torrent_path: str) -> int:
    path = Path(torrent_path).expanduser()

    if not path.is_file():
        print(f"Error: torrent file does not exist or is not a regular file: {path}")
        return 2

    print("Input type: BitTorrent file")
    print("Download engine: aria2c")

    command = [
        "aria2c",
        str(path),
    ]

    return run_command(command)


def build_direct_command(
    url: str, destination: str | None = None, *, telemetry: bool = False,
) -> list[str]:
    """Shared direct-download flags; omitted destination preserves CLI cwd."""
    return _direct_options(destination, telemetry=telemetry) + [url]


def _direct_options(destination=None, *, telemetry=False):
    command = [
        "aria2c",
        "--continue=true",
        "--max-connection-per-server=1",
        "--split=1",
        "--min-split-size=1M",
        "--console-log-level=warn",
        "--summary-interval=1",
    ]
    if telemetry:
        # Full, uncolored records with exact bytes for the GUI's isolated parser.
        command.extend([
            "--show-console-readout=true", "--enable-color=false",
            "--truncate-console-readout=false", "--human-readable=false",
        ])
    if destination is not None:
        command.append(f"--dir={destination}")
    return command


def build_direct_bulk_parallel_command(
    input_path: str, total: int, destination: str | None = None, *, telemetry: bool = False,
) -> list[str]:
    """One aria2 scheduler for all URLs; the caller owns the input file lifetime."""
    command = _direct_options(destination, telemetry=telemetry)
    if telemetry:
        # Live completion notices supplement per-GID progress summaries.
        command[command.index("--console-log-level=warn")] = "--console-log-level=notice"
    return command + [f"--max-concurrent-downloads={total}", f"--input-file={input_path}"]


def download_direct(url: str, destination: str | None = None) -> int:
    print("Input type: direct HTTP file")
    print("Download engine: aria2c")
    return run_command(build_direct_command(url, destination))


def download_direct_bulk(urls: list[str]) -> int:
    total = len(urls)

    print("Input type: direct HTTP files")
    print("Download engine: aria2c")

    with TemporaryDirectory(prefix="aidm-bulk-") as temp_dir:
        input_path = Path(temp_dir) / "urls.txt"
        input_path.write_text("\n".join(urls) + "\n")

        command = build_direct_bulk_parallel_command(str(input_path), total)

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


def download_with_ytdlp(
    url: str,
    title: str | None = None,
    headers: dict[str, str] | None = None,
) -> int:
    print("Input type: supported website/media URL")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    return run_command(build_ytdlp_media_command(url, title, headers))


def build_ytdlp_media_command(
    url: str, title: str | None = None, headers: dict[str, str] | None = None,
    *, destination: str | None = None, telemetry: bool = False,
) -> list[str]:

    command = [
        "yt-dlp",
    ]

    if title:
        safe_title = sanitize_filename(title)
        command.extend([
            "-o",
            f"{safe_title}.%(ext)s",
        ])


    if headers:
        for header_name, header_value in headers.items():
            command.extend([
                "--add-header",
                f"{header_name}:{header_value}",
            ])

    command.extend([
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        ARIA2_DOWNLOADER_ARGUMENTS + (ARIA2_GUI_TELEMETRY_ARGUMENTS if telemetry else ""),
    ])
    if destination is not None:
        command.extend(["-P", destination])
    if telemetry:
        command.extend(ytdlp_telemetry_options())
    return command + [url]


def download_stream(stream: StreamInput) -> int:
    print(f"Input type: {stream.stream_type.upper()} stream")
    print("Extractor/downloader: yt-dlp native")
    print("Post-processing: FFmpeg when required")

    return run_command(build_stream_command(stream))


def build_stream_command(
    stream: StreamInput, *, destination: str | None = None, telemetry: bool = False,
) -> list[str]:

    command = [
        "yt-dlp",
        "--downloader",
        "dash,m3u8:native",
    ]

    if stream.title:
        safe_title = sanitize_filename(stream.title)
        command.extend([
            "-o",
            f"{safe_title}.%(ext)s",
        ])

    for header_name, header_value in stream.headers.items():
        command.extend([
            "--add-header",
            f"{header_name}:{header_value}",
        ])

    if destination is not None:
        command.extend(["-P", destination])
    if telemetry:
        command.extend(ytdlp_telemetry_options())
    return command + [stream.url]
