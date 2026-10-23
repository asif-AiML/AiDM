"""Translate validated snapshots for explicit transfer engines; no persistence."""

from download_settings import (
    ConnectionsPerFile, FragmentRetries, RetryAttempts, SettingsValues, SpeedLimit,
)


_SPEED_LIMITS = {
    SpeedLimit.UNLIMITED: None,
    SpeedLimit.ONE_MBPS: "1M",
    SpeedLimit.TWO_MBPS: "2M",
    SpeedLimit.FIVE_MBPS: "5M",
    SpeedLimit.TEN_MBPS: "10M",
}


def aria2_settings_options(
    settings: SettingsValues, *, auto_connections: int, short_connections: bool = False,
) -> list[str]:
    """Only aria2 transfer controls; parallel scheduling stays in the bulk builder."""
    connections = (auto_connections if settings.connections_per_file == ConnectionsPerFile.AUTO
                   else settings.connections_per_file.value)
    command = (["-x", str(connections), "-s", str(connections)] if short_connections else
               [f"--max-connection-per-server={connections}", f"--split={connections}"])
    limit = _SPEED_LIMITS[settings.speed_limit]
    if limit is not None:
        command.append(f"--max-overall-download-limit={limit}")
    if settings.retry_attempts != RetryAttempts.AUTO:
        command.append(f"--max-tries={settings.retry_attempts.value}")
    return command


def native_stream_settings_options(settings: SettingsValues) -> list[str]:
    """Only for commands known to use yt-dlp native HLS/DASH fragments."""
    command = ["-N", str(settings.fragment_concurrency.value)]
    limit = _SPEED_LIMITS[settings.speed_limit]
    if limit is not None:
        command.extend(["--limit-rate", limit])
    if settings.retry_attempts != RetryAttempts.AUTO:
        command.extend(["--retries", str(settings.retry_attempts.value)])
    if settings.fragment_retries != FragmentRetries.AUTO:
        command.extend(["--fragment-retries", str(settings.fragment_retries.value)])
    return command
