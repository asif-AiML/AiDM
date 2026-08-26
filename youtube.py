import json
import subprocess

from downloader import ARIA2_DOWNLOADER_ARGUMENTS
from utils import run_command


YOUTUBE_VIDEO_FORMAT = (
    "bv*[vcodec^=vp09]+ba[acodec=opus]/bv*+ba/b"
)


def get_available_youtube_qualities(url: str) -> list[int]:
    command = [
        "yt-dlp",
        "--dump-single-json",
        "--skip-download",
        "--playlist-items",
        "1",
        url,
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
    if max_height is None:
        return YOUTUBE_VIDEO_FORMAT

    preferred_video = f"bv*[height<={max_height}][vcodec^=vp09]"
    capped_video = f"bv*[height<={max_height}]"

    return (
        f"{preferred_video}+ba[acodec=opus]/"
        f"{preferred_video}+ba/"
        f"{capped_video}+ba/"
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


def build_youtube_command(total_videos: int | None = None) -> list[str]:
    command = [
        "yt-dlp",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        ARIA2_DOWNLOADER_ARGUMENTS,
    ]

    if total_videos is not None:
        command.extend([
            "--print",
            f"before_dl:[%(video_autonumber)d/{total_videos}] Starting download: %(title)s",
            "--no-quiet",
            "--progress",
        ])

    return command


def download_youtube_video(urls: list[str]) -> int:
    print("Mode: YouTube video")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = build_youtube_command(len(urls))

    command.extend([
        "-f",
        YOUTUBE_VIDEO_FORMAT,
    ])

    command.extend(urls)

    return run_command(command)


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

    command = build_youtube_command()

    command.extend([
        "--yes-playlist",
        "-f",
        build_youtube_format(selected_height),
        url,
    ])

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

    command = build_youtube_command(len(urls))

    command.extend([
        "-f",
        "bestaudio/best",
    ])

    command.extend(urls)

    return run_command(command)


def download_youtube_audio_wav(urls: list[str]) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Conversion: FFmpeg → WAV")

    command = build_youtube_command(len(urls))

    command.extend([
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "wav",
    ])

    command.extend(urls)

    return run_command(command)


def download_youtube(urls: list[str]) -> int:
    mode = choose_youtube_mode()

    if mode == "video":
        result = download_youtube_video(urls)

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
