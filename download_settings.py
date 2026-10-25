"""Validated download preferences and their optional Qt persistence wrapper.

Auto stays unresolved here: connections mean 1 for direct transfers and 8 for
normal YouTube transfers delegated to aria2c. Retry Auto preserves the actual
transfer engine's defaults. Command builders resolve these per transfer path.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings


class ConnectionsPerFile(Enum):
    AUTO = "auto"
    ONE = 1
    FOUR = 4
    EIGHT = 8


class ParallelFiles(Enum):
    TWO = 2
    FOUR = 4


class FragmentConcurrency(Enum):
    ONE = 1
    FOUR = 4
    EIGHT = 8


class SpeedLimit(Enum):
    UNLIMITED = "unlimited"
    ONE_MBPS = "1 MB/s"
    TWO_MBPS = "2 MB/s"
    FIVE_MBPS = "5 MB/s"
    TEN_MBPS = "10 MB/s"


class RetryAttempts(Enum):
    AUTO = "auto"
    THREE = 3
    FIVE = 5
    TEN = 10


class FragmentRetries(Enum):
    AUTO = "auto"
    FIVE = 5
    TEN = 10
    TWENTY = 20


class PerformanceProfile(Enum):
    AIDM_DEFAULT = "AiDM Default"
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    FAST = "Fast"
    CUSTOM = "Custom"


_SETTING_TYPES = {
    "connections_per_file": ConnectionsPerFile,
    "parallel_files": ParallelFiles,
    "fragment_concurrency": FragmentConcurrency,
    "speed_limit": SpeedLimit,
    "retry_attempts": RetryAttempts,
    "fragment_retries": FragmentRetries,
}


def validate_setting(name: str, value) -> Enum:
    """Normalize enum choices and QSettings integer/text representations.

    Reject booleans, floats, containers and unknown choices rather than coercing
    them into valid numbers. Invalid stored values fall back at the load boundary.
    """
    if name not in _SETTING_TYPES:
        raise ValueError(f"Unknown download setting: {name}")
    choice_type = _SETTING_TYPES[name]
    if isinstance(value, choice_type):
        return value
    if type(value) in (int, str):
        text = str(value).strip().lower()
        for choice in choice_type:
            if text == str(choice.value).lower():
                return choice
    raise ValueError(f"Invalid value for {name}: {value!r}")


@dataclass(frozen=True)
class SettingsValues:
    """Validated snapshot; callers change persistent state through DownloadSettings."""

    connections_per_file: ConnectionsPerFile = ConnectionsPerFile.AUTO
    parallel_files: ParallelFiles = ParallelFiles.FOUR
    fragment_concurrency: FragmentConcurrency = FragmentConcurrency.FOUR
    speed_limit: SpeedLimit = SpeedLimit.UNLIMITED
    retry_attempts: RetryAttempts = RetryAttempts.AUTO
    fragment_retries: FragmentRetries = FragmentRetries.AUTO

    def __post_init__(self):
        for field in fields(self):
            object.__setattr__(self, field.name,
                               validate_setting(field.name, getattr(self, field.name)))

    @property
    def profile(self) -> PerformanceProfile:
        performance = (self.connections_per_file, self.parallel_files, self.fragment_concurrency)
        for profile, values in _PROFILE_VALUES.items():
            if performance == values:
                return profile
        return PerformanceProfile.CUSTOM


DEFAULT_VALUES = SettingsValues()

_PROFILE_VALUES = {
    PerformanceProfile.AIDM_DEFAULT: (
        ConnectionsPerFile.AUTO, ParallelFiles.FOUR, FragmentConcurrency.FOUR,
    ),
    PerformanceProfile.CONSERVATIVE: (
        ConnectionsPerFile.ONE, ParallelFiles.TWO, FragmentConcurrency.ONE,
    ),
    PerformanceProfile.BALANCED: (
        ConnectionsPerFile.FOUR, ParallelFiles.FOUR, FragmentConcurrency.FOUR,
    ),
    PerformanceProfile.FAST: (
        ConnectionsPerFile.EIGHT, ParallelFiles.FOUR, FragmentConcurrency.EIGHT,
    ),
}


class DownloadSettings:
    """Own the six preferences, with immediate persistence on each update.

    Defaults to the existing AiDM application store. Tests can inject a private
    QSettings instance. Only download_settings/* keys are written; destination
    preferences and other application state are untouched. Loading normalizes
    in memory without rewriting the store. No profile string is stored or trusted.
    """

    GROUP = "download_settings"

    def __init__(self, settings: QSettings | None = None):
        from PySide6.QtCore import QSettings

        self._settings = settings if settings is not None else QSettings("AiDM", "AiDM")
        values = {}
        for field in fields(DEFAULT_VALUES):
            default = getattr(DEFAULT_VALUES, field.name)
            raw = self._settings.value(f"{self.GROUP}/{field.name}", default.value)
            try:
                values[field.name] = validate_setting(field.name, raw)
            except ValueError:
                values[field.name] = default
        self._values = SettingsValues(**values)

    @property
    def values(self) -> SettingsValues:
        return self._values

    @property
    def profile(self) -> PerformanceProfile:
        return self._values.profile

    def update(self, **changes) -> None:
        """Validate all changes before writing; invalid caller input raises ValueError."""
        normalized = {name: validate_setting(name, value) for name, value in changes.items()}
        values = replace(self._values, **normalized)
        for name, value in normalized.items():
            self._settings.setValue(f"{self.GROUP}/{name}", value.value)
        self._settings.sync()
        if self._settings.status() != self._settings.Status.NoError:
            raise OSError("Could not save AiDM download settings")
        self._values = values

    def apply_profile(self, profile: PerformanceProfile) -> None:
        """Apply only performance controls. Custom is derived, never a preset."""
        if not isinstance(profile, PerformanceProfile) or profile == PerformanceProfile.CUSTOM:
            raise ValueError("Select a named performance profile; Custom is derived")
        connections, parallel, fragments = _PROFILE_VALUES[profile]
        self.update(connections_per_file=connections, parallel_files=parallel,
                    fragment_concurrency=fragments)

    def reset_to_defaults(self) -> None:
        self.update(**{field.name: getattr(DEFAULT_VALUES, field.name)
                       for field in fields(DEFAULT_VALUES)})
