"""Qt-independent queue identity and equal-item-weight sequential progress."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ItemStarted:
    """Normalized backend item identity, before the job supplies its total."""

    current_index: int
    title: str | None = None

    def __post_init__(self):
        if type(self.current_index) is not int or self.current_index < 1:
            raise ValueError("current_index must be a positive integer")
        if self.title is not None and not isinstance(self.title, str):
            raise ValueError("title must be text or None")


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
