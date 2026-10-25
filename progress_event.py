"""Normalized optional telemetry, independent of Qt and activity/status wording."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    percent: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bytes_per_second: int | None = None
    eta_seconds: int | None = None

    def __post_init__(self):
        if self.percent is not None:
            if (type(self.percent) not in (int, float)
                    or not 0 <= self.percent <= 100):
                raise ValueError("percent must be a finite number between 0 and 100")
            object.__setattr__(self, "percent", float(self.percent))
        for name in ("downloaded_bytes", "total_bytes", "speed_bytes_per_second", "eta_seconds"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
