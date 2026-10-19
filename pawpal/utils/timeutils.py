"""Clock arithmetic for the scheduler.

Everything internally is 'minutes since midnight' (an int); we only convert to
datetime.time at the edges, which keeps the placement loop trivial to test.
"""

from datetime import time

from pawpal.models.enums import TimeOfDay

MINUTES_PER_DAY = 24 * 60
LAST_MINUTE = MINUTES_PER_DAY - 1

# Default clock windows for each TimeOfDay, as (start_minute, end_minute).
TIME_OF_DAY_WINDOWS: dict[TimeOfDay, tuple[int, int]] = {
    TimeOfDay.MORNING: (5 * 60, 12 * 60),
    TimeOfDay.AFTERNOON: (12 * 60, 17 * 60),
    TimeOfDay.EVENING: (17 * 60, 23 * 60),
    TimeOfDay.ANY: (0, MINUTES_PER_DAY),
}


def to_minutes(value: time) -> int:
    """Convert a time to minutes since midnight (08:30 -> 510)."""
    return value.hour * 60 + value.minute


def to_time(minutes: int) -> time:
    """Convert minutes since midnight back to a time (510 -> 08:30)."""
    clamped = max(0, min(int(minutes), LAST_MINUTE))
    return time(clamped // 60, clamped % 60)


def add_minutes(start: int, delta: int) -> int:
    """Advance a minute-offset, clamped at 23:59 so a plan never wraps past midnight."""
    return max(0, min(start + delta, LAST_MINUTE))


def format_minutes(minutes: int) -> str:
    """Render a minute-offset as a 24h 'HH:MM' label for the plan table."""
    clamped = max(0, min(int(minutes), MINUTES_PER_DAY))
    return f"{clamped // 60:02d}:{clamped % 60:02d}"


def format_range(start: int, end: int) -> str:
    """Render a slot as 'HH:MM-HH:MM' for display and for DailyPlan.to_text()."""
    return f"{format_minutes(start)}-{format_minutes(end)}"


def format_duration(minutes: int) -> str:
    """Render a duration in human form ('1h 15m', '45 min')."""
    minutes = int(minutes)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h" if rest == 0 else f"{hours}h {rest}m"


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """True if two half-open minute ranges collide; the core conflict primitive."""
    return a_start < b_end and b_start < a_end


def window_for(slot: TimeOfDay) -> tuple[int, int]:
    """Return the (start, end) minute window a TimeOfDay preference maps to."""
    return TIME_OF_DAY_WINDOWS.get(slot, TIME_OF_DAY_WINDOWS[TimeOfDay.ANY])
