import json
import subprocess

from downloader import ARIA2_DOWNLOADER_ARGUMENTS, ARIA2_GUI_TELEMETRY_ARGUMENTS
from utils import run_command
from ytdlp_progress import ITEM_TEMPLATE, PLAYLIST_ITEM_TEMPLATE, ytdlp_telemetry_options


YOUTUBE_VIDEO_FORMAT = (
    "bv*+ba[ext=m4a]/bv*+ba/b"
)


def get_available_youtube_qualities(url: str, *, inspection_only: bool = False) -> list[int]:
    command = [
        "yt-dlp",
        "--dump-single-json",
        "--skip-download",
        "--playlist-items",
        "1",
        url,
    ]
    if inspection_only:
        # GUI inspection must not inherit file-writing or execution config.
        # Default CLI discovery remains unchanged.
        command[1:1] = [
            "--ignore-config", "--no-plugin-dirs", "--no-cache-dir",
            "--simulate", "--no-check-formats", "--socket-timeout", "10",
            "--retries", "0", "--extractor-retries", "0",
        ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        print(f"Warning: could not discover YouTube qualities: {error}")
        return []

    if result.returncode != 0:
        print("Warning: yt-dlp could not discover YouTube qualities.")
        return []

    try:
        metadata = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        print("Warning: yt-dlp returned invalid quality metadata.")
        return []

    if not isinstance(metadata, dict):
        print("Warning: yt-dlp returned invalid quality metadata.")
        return []

    entries = metadata.get("entries") or [metadata]
    heights = {
        format_info.get("height")
        for entry in entries
        if isinstance(entry, dict)
        for format_info in entry.get("formats") or []
        if isinstance(format_info, dict)
        and format_info.get("vcodec") not in {None, "none"}
        and isinstance(format_info.get("height"), int)
        and not isinstance(format_info.get("height"), bool)
        and format_info["height"] > 0
    }

    if not heights:
        print("Warning: no YouTube video qualities were found.")

    return sorted(heights, reverse=True)


def choose_youtube_quality(qualities: list[int]) -> int | None:
    if not qualities:
        return None

    print("\nAvailable video qualities:\n")

    for index, height in enumerate(qualities, start=1):
        print(f"{index} - {height}p")

    while True:
        choice = input(
            f"\nSelect quality [1-{len(qualities)}]: "
        ).strip()

        if choice.isdigit():
            selected_index = int(choice) - 1

            if 0 <= selected_index < len(qualities):
                return qualities[selected_index]

        print(f"Invalid option. Enter a number from 1 to {len(qualities)}.")


def build_youtube_format(max_height: int | None = None) -> str:
    # MP4 video preference lives in the shared command's resolution-first sort.
    # An ext=mp4 video filter here could discard higher-resolution alternatives.
    if max_height is None:
        return YOUTUBE_VIDEO_FORMAT

    return (
        f"bv*[height<={max_height}]+ba[ext=m4a]/"
        f"bv*[height<={max_height}]+ba/"
        f"b[height<={max_height}]"
    )


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


def build_youtube_command(
    total_videos: int | None = None, *, destination: str | None = None,
    telemetry: bool = False,
) -> list[str]:
    command = [
        "yt-dlp",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        ARIA2_DOWNLOADER_ARGUMENTS + (
            ARIA2_GUI_TELEMETRY_ARGUMENTS
            if telemetry else ""
        ),
    ]

    if total_videos is not None:
        command.extend([
            "--print",
            ITEM_TEMPLATE if telemetry else
            f"before_dl:[%(video_autonumber)d/{total_videos}] Starting download: %(title)s",
            "--no-quiet",
            "--progress",
        ])

    if destination is not None:
        command.extend(["-P", destination])
    if telemetry:
        command.extend(ytdlp_telemetry_options())
    return command


def build_youtube_video_command(
    max_height: int | None = None,
    total_videos: int | None = None,
    *, destination: str | None = None, telemetry: bool = False,
) -> list[str]:
    """Resolution first, native MP4/M4A preferred, stream-copy final MP4."""
    command = build_youtube_command(total_videos, destination=destination, telemetry=telemetry)
    command.extend([
        "-f", build_youtube_format(max_height),
        "--format-sort", "res,ext:mp4:m4a",
        "--format-sort-force",
        "--merge-output-format", "mp4",
        "--remux-video", "mp4",
    ])
    return command


def build_youtube_audio_command(
    total_videos: int | None = None, *, wav: bool = False,
    destination: str | None = None, telemetry: bool = False,
) -> list[str]:
    """Share the mature original-audio and WAV paths with frontends."""
    command = build_youtube_command(total_videos, destination=destination, telemetry=telemetry)
    command.extend(["-f", "bestaudio/best"])
    if wav:
        command.extend(["--extract-audio", "--audio-format", "wav"])
    return command


def download_youtube_video(urls: list[str], max_height: int | None = None) -> int:
    print("Mode: YouTube video")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = build_youtube_video_command(max_height, len(urls))

    command.extend(urls)

    return run_command(command)


def build_youtube_playlist_command(
    url: str, max_height: int | None = None, *,
    destination: str | None = None, telemetry: bool = False,
) -> list[str]:
    """The same video policy, with playlist traversal and optional item records."""
    command = build_youtube_video_command(max_height, destination=destination, telemetry=telemetry)
    if telemetry:
        command.extend(["--print", PLAYLIST_ITEM_TEMPLATE, "--no-quiet", "--progress"])
    return command + ["--yes-playlist", url]


def download_youtube_playlist(url: str) -> int:
    print("Mode: YouTube playlist")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    qualities = get_available_youtube_qualities(url)

    if qualities:
        selected_height = choose_youtube_quality(qualities)
    else:
        print(
            "Could not determine playlist qualities; "
            "using best available quality."
        )
        selected_height = None

    if selected_height is not None:
        print(f"Selected quality: {selected_height}p")

    command = build_youtube_playlist_command(url, selected_height)

    result = run_command(command)

    if result == 0:
        print("YouTube playlist download completed successfully 🎉💫")
    else:
        print("Playlist download finished with errors ⚠️")
        print("Some items may have completed successfully.")

    return result


def download_youtube_audio(urls: list[str]) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Output: original best available audio")

    command = build_youtube_audio_command(len(urls))

    command.extend(urls)

    return run_command(command)


def download_youtube_audio_wav(urls: list[str]) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Conversion: FFmpeg → WAV")

    command = build_youtube_audio_command(len(urls), wav=True)

    command.extend(urls)

    return run_command(command)


def download_youtube(urls: list[str]) -> int:
    mode = choose_youtube_mode()

    if mode == "video":
        # One representative lookup for both single and bulk video requests.
        qualities = get_available_youtube_qualities(urls[0])
        if qualities:
            selected_height = choose_youtube_quality(qualities)
        else:
            print(
                "Could not determine YouTube video qualities; "
                "using best available quality."
            )
            selected_height = None

        if selected_height is not None:
            print(f"Selected quality: {selected_height}p")

        result = download_youtube_video(urls, max_height=selected_height)

    elif mode == "audio":
        result = download_youtube_audio(urls)

    else:
        result = download_youtube_audio_wav(urls)

    if result == 0:
        total = len(urls)
        download_word = "download" if total == 1 else "downloads"

        print(
            f"\n{total} YouTube {download_word} completed successfully 🎉💫"
        )
    else:
        print(
            f"\nBulk download finished with errors ⚠️"
            "\nSome items may have completed successfully."
        )
    return result
