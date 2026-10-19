"""CareTask behaviour: validation, scoring, recurrence, and subclass overrides."""

from datetime import date, time

import pytest

from pawpal.models.enums import Priority, Recurrence, TaskCategory
from pawpal.models.task import (
    CareTask,
    FeedingTask,
    MedicationTask,
    WalkTask,
    make_task,
    task_from_dict,
)
from pawpal.utils.validation import ValidationError

MONDAY = date(2026, 6, 15)
SATURDAY = date(2026, 6, 20)


def test_validate_rejects_blank_title():
    """A task with no title raises ValidationError."""
    with pytest.raises(ValidationError):
        CareTask(title="   ", duration_minutes=10).validate()


def test_validate_rejects_zero_duration():
    """duration_minutes must be >= 1."""
    with pytest.raises(ValidationError):
        CareTask(title="Walk", duration_minutes=0).validate()


def test_validate_rejects_absurd_duration():
    """A task longer than 8 hours is rejected as a typo."""
    with pytest.raises(ValidationError):
        CareTask(title="Walk", duration_minutes=600).validate()


def test_score_rises_with_priority():
    """Same duration, higher priority -> strictly higher score."""
    low = CareTask(title="A", duration_minutes=20, priority=Priority.LOW)
    high = CareTask(title="B", duration_minutes=20, priority=Priority.HIGH)
    assert high.score() > low.score()


def test_score_falls_with_duration():
    """Same priority, longer duration -> lower score under value density."""
    short = CareTask(title="A", duration_minutes=10, priority=Priority.HIGH)
    long = CareTask(title="B", duration_minutes=60, priority=Priority.HIGH)
    assert short.score() > long.score()


def test_medication_outranks_everything():
    """MedicationTask.score() beats a high-priority normal task."""
    med = MedicationTask(title="Tablet", duration_minutes=60, priority=Priority.LOW)
    urgent = CareTask(title="Walk", duration_minutes=5, priority=Priority.HIGH)
    assert med.score() > urgent.score()


def test_feeding_outranks_same_priority_task():
    """A meal beats an identical generic task of the same priority and length."""
    meal = FeedingTask(title="Breakfast", duration_minutes=10, priority=Priority.HIGH)
    other = CareTask(title="Other", duration_minutes=10, priority=Priority.HIGH)
    assert meal.score() > other.score()


def test_walk_outranks_same_priority_task():
    """Exercise gets a deliberate lift over an otherwise identical task."""
    walk = WalkTask(title="Walk", duration_minutes=30, priority=Priority.HIGH)
    other = CareTask(title="Other", duration_minutes=30, priority=Priority.HIGH)
    assert walk.score() > other.score()


def test_category_weight_changes_score():
    """A per-category weight scales the base score."""
    task = CareTask(title="Brush", category=TaskCategory.GROOMING, duration_minutes=10)
    assert task.score({"grooming": 2.0}) == pytest.approx(task.score() * 2)


def test_is_due_daily_is_always_true():
    """A DAILY task is due on any date."""
    task = CareTask(title="Walk", recurrence=Recurrence.DAILY)
    assert task.is_due(MONDAY) and task.is_due(SATURDAY)


def test_is_due_weekly_matches_weekday_only():
    """A WEEKLY task is due only on its configured weekday."""
    task = CareTask(title="Brush", recurrence=Recurrence.WEEKLY, weekdays={5})
    assert task.is_due(SATURDAY)
    assert not task.is_due(MONDAY)


def test_is_due_weekdays_skips_weekend():
    """A WEEKDAYS task is not due on Saturday."""
    task = CareTask(title="Training", recurrence=Recurrence.WEEKDAYS)
    assert task.is_due(MONDAY)
    assert not task.is_due(SATURDAY)


def test_is_due_once_only_on_its_date():
    """A ONCE task is due on exactly one day."""
    task = CareTask(title="Vet", recurrence=Recurrence.ONCE, due_date=MONDAY)
    assert task.is_due(MONDAY)
    assert not task.is_due(SATURDAY)


def test_completed_once_task_is_not_due():
    """Finishing a one-off removes it from later days."""
    task = CareTask(title="Vet", recurrence=Recurrence.ONCE, due_date=MONDAY)
    task.mark_complete()
    assert not task.is_due(MONDAY)


def test_is_anchored_true_when_fixed_time_set():
    """fixed_time present -> is_anchored() is True."""
    assert CareTask(title="Meal", fixed_time=time(8, 0)).is_anchored()
    assert not CareTask(title="Walk").is_anchored()


def test_mark_complete_and_reset_round_trip():
    """mark_complete() sets the flag; reset() clears it."""
    task = CareTask(title="Walk")
    task.mark_complete()
    assert task.is_completed
    task.reset()
    assert not task.is_completed


def test_task_round_trips_through_dict():
    """to_dict() then task_from_dict() returns an equal task of the same subclass."""
    task = WalkTask(
        title="Morning walk",
        category=TaskCategory.WALK,
        duration_minutes=30,
        priority=Priority.HIGH,
        distance_km=2.5,
        fixed_time=time(7, 30),
    )
    restored = task_from_dict(task.to_dict())
    assert isinstance(restored, WalkTask)
    assert restored == task


def test_medication_round_trip_keeps_subclass_fields():
    """dosage and min_hours_between_doses survive the JSON round trip."""
    med = MedicationTask(title="Insulin", dosage="2 units", min_hours_between_doses=12)
    restored = task_from_dict(med.to_dict())
    assert restored.dosage == "2 units"
    assert restored.min_hours_between_doses == 12
    assert restored.skippable is False


def test_make_task_picks_the_right_subclass():
    """The factory maps a category to its specialised class."""
    assert isinstance(make_task(TaskCategory.WALK, title="W"), WalkTask)
    assert isinstance(make_task(TaskCategory.MEDICATION, title="M"), MedicationTask)
    assert isinstance(make_task(TaskCategory.OTHER, title="O"), CareTask)


def test_medication_conflicts_within_gap():
    """Two doses of the same med inside the minimum gap conflict."""
    a = MedicationTask(title="Insulin", min_hours_between_doses=8)
    b = MedicationTask(title="Insulin", min_hours_between_doses=8)
    assert a.conflicts_with(b, gap_minutes=60)
    assert not a.conflicts_with(b, gap_minutes=9 * 60)


def test_different_medications_never_conflict():
    """Spacing applies per medication, not across different drugs."""
    a = MedicationTask(title="Insulin", min_hours_between_doses=8)
    b = MedicationTask(title="Meloxicam", min_hours_between_doses=8)
    assert not a.conflicts_with(b, gap_minutes=5)


def test_str_is_readable():
    """__str__ carries title, duration and priority."""
    task = CareTask(title="Morning walk", duration_minutes=30, priority=Priority.HIGH)
    assert str(task) == "Morning walk (30 min) [high]"
