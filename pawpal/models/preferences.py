"""The owner's rules for a day: when they are available and how to rank tasks.

Split in two on purpose: OwnerPreferences is saved to JSON and persists,
DayConstraints is the per-run snapshot the Scheduler actually reads.
"""

from dataclasses import dataclass, field
from datetime import time

from pawpal.models.enums import StrategyName
from pawpal.utils.serialization import enum_value, iso_time, parse_enum, parse_time
from pawpal.utils.timeutils import to_minutes
from pawpal.utils.validation import ValidationError, require_positive_int


@dataclass
class OwnerPreferences:
    """Durable settings the owner sets once and reuses every day."""

    wake_time: time = time(7, 0)
    sleep_time: time = time(22, 0)
    available_minutes: int = 180
    break_minutes: int = 5
    strategy: StrategyName = StrategyName.WEIGHTED_SCORE
    currency: str = "USD"
    priority_weights: dict[str, float] = field(default_factory=dict)
    blocked_windows: list[tuple[time, time]] = field(default_factory=list)

    def validate(self) -> None:
        """Raise ValidationError if sleep <= wake or the budget exceeds the day."""
        if to_minutes(self.sleep_time) <= to_minutes(self.wake_time):
            raise ValidationError("Sleep time must be after wake time.")
        self.available_minutes = require_positive_int(
            self.available_minutes, "Available minutes", maximum=self.waking_minutes()
        )
        if self.break_minutes < 0:
            raise ValidationError("Break minutes cannot be negative.")
        for start, end in self.blocked_windows:
            if to_minutes(end) <= to_minutes(start):
                raise ValidationError("A blocked window must end after it starts.")

    def waking_minutes(self) -> int:
        """Total minutes between wake and sleep, the hard ceiling on any plan."""
        return to_minutes(self.sleep_time) - to_minutes(self.wake_time)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict (times become 'HH:MM' strings)."""
        return {
            "wake_time": iso_time(self.wake_time),
            "sleep_time": iso_time(self.sleep_time),
            "available_minutes": self.available_minutes,
            "break_minutes": self.break_minutes,
            "strategy": enum_value(self.strategy),
            "currency": self.currency,
            "priority_weights": dict(self.priority_weights),
            "blocked_windows": [[iso_time(s), iso_time(e)] for s, e in self.blocked_windows],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OwnerPreferences":
        """Rebuild preferences from JSON, parsing the time strings back."""
        data = data or {}
        windows = []
        for pair in data.get("blocked_windows", []):
            start, end = parse_time(pair[0]), parse_time(pair[1])
            if start and end:
                windows.append((start, end))
        return cls(
            wake_time=parse_time(data.get("wake_time")) or time(7, 0),
            sleep_time=parse_time(data.get("sleep_time")) or time(22, 0),
            available_minutes=int(data.get("available_minutes", 180)),
            break_minutes=int(data.get("break_minutes", 5)),
            strategy=parse_enum(
                StrategyName, data.get("strategy"), StrategyName.WEIGHTED_SCORE
            ),
            currency=data.get("currency", "USD"),
            priority_weights=dict(data.get("priority_weights", {})),
            blocked_windows=windows,
        )


@dataclass
class DayConstraints:
    """One day's resolved limits: the exact numbers the placement loop works with."""

    day_start: int = 420
    day_end: int = 1320
    available_minutes: int = 180
    break_minutes: int = 5
    blocked: list[tuple[int, int]] = field(default_factory=list)

    @classmethod
    def from_preferences(cls, prefs: OwnerPreferences) -> "DayConstraints":
        """Convert the owner's clock times into minute-offsets for the scheduler."""
        return cls(
            day_start=to_minutes(prefs.wake_time),
            day_end=to_minutes(prefs.sleep_time),
            available_minutes=prefs.available_minutes,
            break_minutes=prefs.break_minutes,
            blocked=[(to_minutes(s), to_minutes(e)) for s, e in prefs.blocked_windows],
        )

    def is_blocked(self, start: int, end: int) -> bool:
        """True if a candidate slot overlaps any blocked window (work, sleep)."""
        return any(start < b_end and b_start < end for b_start, b_end in self.blocked)

    def next_free_minute(self, after: int) -> int:
        """First minute at or after `after` that is not inside a blocked window."""
        cursor = max(after, self.day_start)
        moved = True
        while moved:
            moved = False
            for b_start, b_end in self.blocked:
                if b_start <= cursor < b_end:
                    cursor, moved = b_end, True
        return cursor
