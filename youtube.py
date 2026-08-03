from downloader import ARIA2_DOWNLOADER_ARGUMENTS
from utils import run_command


YOUTUBE_VIDEO_FORMAT = (
    "bv*[vcodec^=vp09]+ba[acodec=opus]/bv*+ba/b"
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


def build_youtube_command() -> list[str]:
    return [
        "yt-dlp",
        "--downloader",
        "aria2c",
        "--downloader",
        "dash,m3u8:native",
        "--downloader-args",
        ARIA2_DOWNLOADER_ARGUMENTS,
    ]


def download_youtube_video(url: str) -> int:
    print("Mode: YouTube video")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")

    command = build_youtube_command()

    command.extend([
        "-f",
        YOUTUBE_VIDEO_FORMAT,
        url,
    ])

    return run_command(command)


def download_youtube_audio(url: str) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Output: original best available audio")

    command = build_youtube_command()

    command.extend([
        "-f",
        "bestaudio/best",
        url,
    ])

    return run_command(command)


def download_youtube_audio_wav(url: str) -> int:
    print("Mode: YouTube audio")
    print("Extractor: yt-dlp")
    print("Download engine: aria2c where supported")
    print("Conversion: FFmpeg → WAV")

    command = build_youtube_command()

    command.extend([
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "wav",
        url,
    ])

    return run_command(command)


def download_youtube(url: str) -> int:
    mode = choose_youtube_mode()

    if mode == "video":
        return download_youtube_video(url)

    if mode == "audio":
        return download_youtube_audio(url)

    return download_youtube_audio_wav(url)