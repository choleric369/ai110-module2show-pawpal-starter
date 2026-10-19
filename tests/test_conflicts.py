"""Fixed-time anchors, overlap resolution, and medication spacing."""

from datetime import date, time

from pawpal.models.enums import StrategyName
from pawpal.models.plan import ScheduledTask
from pawpal.models.preferences import DayConstraints
from pawpal.models.task import CareTask, FeedingTask, MedicationTask
from pawpal.scheduling.conflicts import (
    find_overlaps,
    first_free_slot,
    place_anchors,
    respects_medication_gap,
    split_anchored,
)
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy
from pawpal.utils.timeutils import overlaps

DAY = date(2026, 6, 15)


def _plan(owner, scheduler):
    """Build a plan with reminders off."""
    return scheduler.build_plan(owner, DAY, include_reminders=False)


def test_anchored_task_keeps_its_exact_time(sample_owner, roomy_scheduler, sample_pet):
    """A task with fixed_time=15:00 is scheduled at 15:00."""
    sample_pet.add_task(
        FeedingTask(title="Lunch", duration_minutes=10, fixed_time=time(15, 0))
    )
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.scheduled[0].start_minute == 15 * 60


def test_flexible_task_shifts_around_an_anchor(sample_owner, roomy_scheduler, sample_pet):
    """A flexible task overlapping an anchor is moved, not dropped."""
    sample_pet.add_task(FeedingTask(title="Meal", duration_minutes=30, fixed_time=time(7, 0)))
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=30))
    plan = _plan(sample_owner, roomy_scheduler)
    assert len(plan.scheduled) == 2
    assert find_overlaps(plan.scheduled) == []


def test_two_anchors_at_same_time_flags_a_clash():
    """Two immovable tasks at one time: one is placed, one reported as a conflict."""
    constraints = DayConstraints(day_start=420, day_end=1320, available_minutes=300)
    a = FeedingTask(title="Meal A", duration_minutes=30, fixed_time=time(8, 0))
    b = FeedingTask(title="Meal B", duration_minutes=30, fixed_time=time(8, 15))
    placed, rejected = place_anchors([a, b], constraints)
    assert len(placed) == 1
    assert len(rejected) == 1
    assert "clashes with" in rejected[0][1]


def test_anchor_outside_waking_hours_is_rejected():
    """A 05:00 anchor cannot be placed in a 07:00-22:00 day."""
    constraints = DayConstraints(day_start=420, day_end=1320, available_minutes=300)
    task = FeedingTask(title="Early meal", duration_minutes=10, fixed_time=time(5, 0))
    placed, rejected = place_anchors([task], constraints)
    assert placed == []
    assert "outside your waking hours" in rejected[0][1]


def test_anchor_inside_blocked_window_is_rejected():
    """An anchor landing in a blocked window is reported, not forced."""
    constraints = DayConstraints(
        day_start=420, day_end=1320, available_minutes=300, blocked=[(540, 1020)]
    )
    task = FeedingTask(title="Midday meal", duration_minutes=10, fixed_time=time(12, 0))
    placed, rejected = place_anchors([task], constraints)
    assert placed == []
    assert "blocked window" in rejected[0][1]


def test_overlaps_detects_partial_collision():
    """Ranges 09:00-09:30 and 09:15-09:45 are reported as overlapping."""
    assert overlaps(540, 570, 555, 585)


def test_overlaps_allows_touching_slots():
    """09:00-09:30 and 09:30-10:00 do not count as an overlap."""
    assert not overlaps(540, 570, 570, 600)


def test_split_anchored_separates_the_pool():
    """split_anchored() puts fixed-time tasks in the first bucket."""
    anchored = FeedingTask(title="Meal", fixed_time=time(8, 0))
    flexible = CareTask(title="Walk")
    fixed, free = split_anchored([anchored, flexible])
    assert fixed == [anchored]
    assert free == [flexible]


def test_first_free_slot_respects_padding():
    """A break of 10 minutes pushes the next slot 10 minutes past the last end."""
    constraints = DayConstraints(day_start=420, day_end=1320, available_minutes=300)
    taken = [ScheduledTask(task=CareTask(title="A"), start_minute=420, end_minute=450)]
    assert first_free_slot(30, taken, constraints, 420, padding=10) == 460


def test_first_free_slot_returns_none_when_full():
    """A day with no room returns None rather than an invalid slot."""
    constraints = DayConstraints(day_start=600, day_end=630, available_minutes=300)
    assert first_free_slot(60, [], constraints, 600) is None


def test_blocked_window_is_never_used(sample_owner, sample_pet):
    """No slot is placed inside a blocked window (e.g. work hours)."""
    for i in range(4):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=30))
    constraints = DayConstraints(
        day_start=420, day_end=1320, available_minutes=300, blocked=[(540, 1020)]
    )
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert all(not constraints.is_blocked(s.start_minute, s.end_minute) for s in plan.scheduled)


def test_medication_gap_is_enforced():
    """Two doses closer than min_hours_between_doses are separated or flagged."""
    first = MedicationTask(title="Insulin", duration_minutes=5, min_hours_between_doses=8)
    second = MedicationTask(title="Insulin", duration_minutes=5, min_hours_between_doses=8)
    placed = [ScheduledTask(task=first, start_minute=420, end_minute=425)]
    assert not respects_medication_gap(second, 480, placed)
    assert respects_medication_gap(second, 420 + 9 * 60, placed)


def test_non_medication_ignores_the_gap_rule():
    """A normal task is never blocked by medication spacing."""
    med = MedicationTask(title="Insulin", duration_minutes=5)
    placed = [ScheduledTask(task=med, start_minute=420, end_minute=425)]
    assert respects_medication_gap(CareTask(title="Walk"), 430, placed)


def test_find_overlaps_reports_nothing_on_a_clean_plan():
    """A well-formed plan has no colliding pairs."""
    items = [
        ScheduledTask(task=CareTask(title="A"), start_minute=420, end_minute=450),
        ScheduledTask(task=CareTask(title="B"), start_minute=460, end_minute=480),
    ]
    assert find_overlaps(items) == []
