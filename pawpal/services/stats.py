"""Derived numbers for the Insights tab. Read-only: never mutates a plan."""

from datetime import date, timedelta

from pawpal.models.plan import DailyPlan


def completion_rate(plan: DailyPlan) -> float:
    """Share of today's scheduled tasks marked complete, 0.0-1.0."""
    return plan.completion_rate()


def minutes_by_category(plan: DailyPlan) -> dict[str, int]:
    """Scheduled minutes grouped by TaskCategory, for the breakdown chart."""
    totals: dict[str, int] = {}
    for item in plan.scheduled:
        if item.task is None:
            continue
        key = item.task.category.value
        totals[key] = totals.get(key, 0) + item.duration()
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def minutes_by_pet(plan: DailyPlan) -> dict[str, int]:
    """Scheduled minutes per pet, to show whether attention is split fairly."""
    totals: dict[str, int] = {}
    for item in plan.scheduled:
        if item.pet is None:
            continue
        totals[item.pet.name] = totals.get(item.pet.name, 0) + item.duration()
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def streak_days(history: list[dict]) -> int:
    """Consecutive days ending at the latest entry where everything was completed."""
    dated = sorted(
        ((date.fromisoformat(e["day"]), e) for e in history if e.get("day")),
        reverse=True,
    )
    streak = 0
    expected = None
    for day, entry in dated:
        if expected is not None and day != expected:
            break
        if entry.get("completion_rate", 0) < 1.0:
            break
        streak += 1
        expected = day - timedelta(days=1)
    return streak


def most_skipped(history: list[dict], limit: int = 3) -> list[tuple[str, int]]:
    """Tasks that get dropped most often — the 'you keep skipping grooming' nudge."""
    counts: dict[str, int] = {}
    for entry in history:
        for drop in entry.get("skipped", []):
            title = drop.get("title", "")
            if title:
                counts[title] = counts.get(title, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


def history_trend(history: list[dict]) -> list[tuple[str, float]]:
    """(date, completion_rate) pairs for the trend line in the Insights tab."""
    points = [
        (entry["day"], float(entry.get("completion_rate", 0.0)))
        for entry in history
        if entry.get("day")
    ]
    return sorted(points)
