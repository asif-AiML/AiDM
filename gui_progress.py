"""GUI presentation of normalized telemetry; decimal SI units (1000 bytes/KB)."""

from progress_event import ProgressEvent


def format_bytes(value: int) -> str:
    amount = value
    for unit in ("B", "KB", "MB", "GB", "TB", "PB", "EB"):
        if amount < 1000 or unit == "EB":
            number = str(amount) if unit == "B" else f"{amount:.1f}".removesuffix(".0")
            return f"{number} {unit}"
        amount /= 1000


def format_eta(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def format_statistics(event: ProgressEvent) -> str:
    parts = []
    if event.speed_bytes_per_second is not None:
        parts.append(f"{format_bytes(event.speed_bytes_per_second)}/s")
    if event.downloaded_bytes is not None:
        downloaded = format_bytes(event.downloaded_bytes)
        parts.append(f"{downloaded} / {format_bytes(event.total_bytes)}"
                     if event.total_bytes is not None else f"{downloaded} downloaded")
    elif event.total_bytes is not None:
        parts.append(f"{format_bytes(event.total_bytes)} total")
    if event.eta_seconds is not None:
        parts.append(f"ETA {format_eta(event.eta_seconds)}")
    return " • ".join(parts)
