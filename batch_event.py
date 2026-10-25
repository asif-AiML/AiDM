"""Qt-independent batch identity and sequential/parallel aggregate progress."""

from dataclasses import dataclass, replace
from progress_event import ProgressEvent


@dataclass(frozen=True)
class ItemStarted:
    """Normalized backend item identity, before the job supplies its total."""

    current_index: int
    title: str | None = None
    # Runtime collection size, used only if inspection did not know the total.
    total_items: int | None = None

    def __post_init__(self):
        if type(self.current_index) is not int or self.current_index < 1:
            raise ValueError("current_index must be a positive integer")
        if self.title is not None and not isinstance(self.title, str):
            raise ValueError("title must be text or None")
        if self.total_items is not None and (
                type(self.total_items) is not int or self.total_items < self.current_index):
            raise ValueError("total_items must be an integer >= current_index")


@dataclass(frozen=True)
class BatchEvent:
    current_index: int
    total_items: int
    title: str | None = None
    aggregate_percent: float | None = None

    def __post_init__(self):
        ItemStarted(self.current_index, self.title)
        if type(self.total_items) is not int or self.total_items < self.current_index:
            raise ValueError("total_items must be an integer >= current_index")
        if self.aggregate_percent is not None:
            if (type(self.aggregate_percent) not in (int, float)
                    or not 0 <= self.aggregate_percent <= 100):
                raise ValueError("aggregate_percent must be finite and between 0 and 100")


class SequentialBatchProgress:
    """High-water contribution across transfer phases, never byte-weighted.

    A stream's 100% is contribution only, not item-completion authority. Item
    advancement and successful process exit remain separate workflow facts.
    """

    def __init__(self, total_items: int):
        BatchEvent(1, total_items)
        self.total_items = total_items
        self.event: BatchEvent | None = None

    def start_item(self, item: ItemStarted) -> BatchEvent | None:
        if item.current_index > self.total_items:
            return None
        previous = self.event
        if previous and item.current_index < previous.current_index:
            return None
        baseline = 100 * (item.current_index - 1) / self.total_items
        event = BatchEvent(item.current_index, self.total_items, item.title,
                           max(baseline, previous.aggregate_percent if previous else 0))
        return self._store(event)

    def progress(self, percent: float | None) -> BatchEvent | None:
        if self.event is None or percent is None:
            return None
        if type(percent) not in (int, float) or not 0 <= percent <= 100:
            raise ValueError("item percent must be finite and between 0 and 100")
        aggregate = 100 * (self.event.current_index - 1 + percent / 100) / self.total_items
        return self._store(replace(self.event, aggregate_percent=max(self.event.aggregate_percent, aggregate)))

    def complete(self) -> BatchEvent | None:
        # Only the successful execution lifecycle may call this. Do not invent
        # item identity if no item-start record was received.
        return self._store(replace(self.event, aggregate_percent=100)) if self.event else None

    def _store(self, event):
        if event == self.event:
            return None
        self.event = event
        return event


@dataclass(frozen=True)
class ParallelBatchEvent:
    """Batch identity without a fictitious current item or title."""

    total_items: int
    active_items: int = 0
    completed_items: int = 0
    aggregate_percent: float = 0

    def __post_init__(self):
        BatchEvent(1, self.total_items, aggregate_percent=self.aggregate_percent)
        for value in (self.active_items, self.completed_items):
            if type(value) is not int or not 0 <= value <= self.total_items:
                raise ValueError("item counts must be integers within the batch")
        if self.active_items + self.completed_items > self.total_items:
            raise ValueError("active and completed counts exceed the batch")


class ParallelBatchProgress:
    """Reusable item tracker; the backend supplies stable IDs and completion facts.

    Byte weighting requires totals for every item. Otherwise each completed
    item contributes 1/N and each active known fraction contributes fraction/N.
    A high-water aggregate survives incomplete/reordered telemetry and a change
    of weighting. Bytes retain the last observed lower bound for unknown sizes.
    Neither 100% nor disappearance is completion evidence.
    """

    def __init__(self, total_items: int):
        self.event = ParallelBatchEvent(total_items)
        self.total_items = total_items
        self.items = {}
        self.active = set()
        self.completed = set()

    def snapshot(self, items):
        """Replace the active set from one whole backend summary, not one line."""
        self.active = set()
        for key, progress in items.items():
            if key in self.completed:
                continue
            if key not in self.items and len(self.items) >= self.total_items:
                continue
            self.items[key] = progress
            self.active.add(key)
        return self.render()

    def finish_item(self, key):
        if key not in self.items and len(self.items) >= self.total_items:
            return self.render()
        progress = self.items.get(key, ProgressEvent())
        self.items[key] = replace(
            progress, downloaded_bytes=progress.total_bytes or progress.downloaded_bytes,
            speed_bytes_per_second=None, eta_seconds=None,
        )
        self.completed.add(key)
        self.active.discard(key)
        return self.render()

    def render(self):
        whole_total = (sum(p.total_bytes for p in self.items.values())
                       if len(self.items) == self.total_items
                       and all(p.total_bytes is not None for p in self.items.values()) else None)
        observed_bytes = [p.downloaded_bytes for p in self.items.values() if p.downloaded_bytes is not None]
        downloaded = sum(observed_bytes) if observed_bytes else None
        if whole_total and downloaded is not None:
            percent = min(100, 100 * downloaded / whole_total)
        else:
            percent = 100 * (len(self.completed) + sum(
                (self.items[key].percent or 0) / 100 for key in self.active
            )) / self.total_items
        percent = max(self.event.aggregate_percent, percent)
        speeds = [self.items[key].speed_bytes_per_second for key in self.active]
        speed = sum(speeds) if speeds and all(value is not None for value in speeds) else None
        self.event = ParallelBatchEvent(self.total_items, len(self.active), len(self.completed), percent)
        return self.event, ProgressEvent(percent, downloaded, whole_total, speed)

    def complete(self):
        # Successful overall process exit is authoritative even for items too
        # fast to appear in a periodic summary. Do not invent their byte sizes.
        self.event = ParallelBatchEvent(self.total_items, 0, self.total_items, 100)
        return self.event
