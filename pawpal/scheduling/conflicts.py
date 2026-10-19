"""Conflict detection and resolution.

Rule: anchored tasks (fixed_time, vet appointments) are immovable; flexible
tasks bend around them. Medication spacing is a second, separate constraint.
"""

from pawpal.models.plan import ScheduledTask
from pawpal.models.preferences import DayConstraints
from pawpal.models.task import CareTask, MedicationTask
from pawpal.utils.timeutils import format_minutes, overlaps, to_minutes


def find_overlaps(items: list[ScheduledTask]) -> list[tuple[ScheduledTask, ScheduledTask]]:
    """Return every pair of placed tasks whose time ranges collide."""
    ordered = sorted(items, key=lambda s: s.start_minute)
    clashes = []
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            if second.start_minute >= first.end_minute:
                break
            if overlaps(
                first.start_minute, first.end_minute, second.start_minute, second.end_minute
            ):
                clashes.append((first, second))
    return clashes


def split_anchored(tasks: list[CareTask]) -> tuple[list[CareTask], list[CareTask]]:
    """Split a task pool into (anchored, flexible) so anchors can be placed first."""
    anchored = [t for t in tasks if t.is_anchored()]
    flexible = [t for t in tasks if not t.is_anchored()]
    return anchored, flexible


def place_anchors(
    anchored: list[CareTask], constraints: DayConstraints
) -> tuple[list[ScheduledTask], list[tuple[CareTask, str]]]:
    """Pin fixed-time tasks to their slot; return placements plus any that clash."""
    placed: list[ScheduledTask] = []
    rejected: list[tuple[CareTask, str]] = []
    ordered = sorted(anchored, key=lambda t: to_minutes(t.fixed_time) if t.fixed_time else 0)
    for task in ordered:
        if task.fixed_time is None:
            rejected.append((task, "marked as fixed-time but no time was set"))
            continue
        start = to_minutes(task.fixed_time)
        end = start + task.duration_minutes
        if start < constraints.day_start or end > constraints.day_end:
            rejected.append(
                (task, f"fixed at {format_minutes(start)}, outside your waking hours")
            )
            continue
        if constraints.is_blocked(start, end):
            rejected.append(
                (task, f"fixed at {format_minutes(start)}, which is a blocked window")
            )
            continue
        clash = next(
            (p for p in placed if overlaps(start, end, p.start_minute, p.end_minute)), None
        )
        if clash:
            rejected.append(
                (task, f"clashes with {clash.task.title} at {clash.time_label()}")
            )
            continue
        placed.append(ScheduledTask(task=task, start_minute=start, end_minute=end))
    return placed, rejected


def first_free_slot(
    duration: int,
    taken: list[ScheduledTask],
    constraints: DayConstraints,
    after: int,
    padding: int = 0,
) -> int | None:
    """Earliest start minute where a task of this length fits; None if nowhere.

    `padding` is the owner's break: a placed task reserves that many extra
    minutes either side, so back-to-back tasks never touch.
    """
    start = max(after, constraints.day_start)
    while start + duration <= constraints.day_end:
        blocker_end = None
        for b_start, b_end in constraints.blocked:
            if overlaps(start, start + duration, b_start, b_end):
                blocker_end = max(blocker_end or 0, b_end)
        for item in taken:
            if overlaps(
                start,
                start + duration,
                item.start_minute - padding,
                item.end_minute + padding,
            ):
                blocker_end = max(blocker_end or 0, item.end_minute + padding)
        if blocker_end is None:
            return start
        start = blocker_end
    return None


def respects_medication_gap(
    task: CareTask, start: int, placed: list[ScheduledTask]
) -> bool:
    """False if this dose would land too close to an earlier dose of the same med."""
    if not isinstance(task, MedicationTask):
        return True
    for item in placed:
        other = item.task
        if not isinstance(other, MedicationTask):
            continue
        gap = abs(start - item.start_minute)
        if task.conflicts_with(other, gap):
            return False
    return True


def shift_conflicting(
    item: ScheduledTask, taken: list[ScheduledTask], constraints: DayConstraints
) -> ScheduledTask | None:
    """Push a flexible task later until it stops colliding; None if it never fits."""
    if item.task is None:
        return None
    others = [t for t in taken if t is not item]
    start = first_free_slot(item.duration(), others, constraints, item.start_minute)
    if start is None:
        return None
    return ScheduledTask(
        task=item.task,
        pet=item.pet,
        start_minute=start,
        end_minute=start + item.duration(),
        reason=item.reason,
    )
