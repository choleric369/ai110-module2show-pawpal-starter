"""Which tasks appear on which day."""

from datetime import date, timedelta

from pawpal.models.enums import Recurrence
from pawpal.models.task import CareTask

MONDAY = date(2026, 6, 15)
SATURDAY = date(2026, 6, 20)
SUNDAY = date(2026, 6, 21)


def _week_from(start: date) -> list[date]:
    """Seven consecutive days starting at `start`."""
    return [start + timedelta(days=i) for i in range(7)]


def test_daily_task_appears_every_day():
    """A DAILY task shows up in Monday's and Sunday's plan alike."""
    task = CareTask(title="Walk", recurrence=Recurrence.DAILY)
    assert all(task.is_due(day) for day in _week_from(MONDAY))


def test_weekly_task_appears_once_per_week():
    """A WEEKLY task is absent on six of seven days."""
    task = CareTask(title="Brush", recurrence=Recurrence.WEEKLY, weekdays={2})
    assert sum(task.is_due(day) for day in _week_from(MONDAY)) == 1


def test_weekly_task_defaults_to_monday():
    """With no weekday chosen, a WEEKLY task falls on Monday."""
    task = CareTask(title="Brush", recurrence=Recurrence.WEEKLY)
    assert task.is_due(MONDAY)
    assert not task.is_due(SATURDAY)


def test_weekdays_task_skips_the_weekend():
    """A WEEKDAYS task is not due on Saturday or Sunday."""
    task = CareTask(title="Training", recurrence=Recurrence.WEEKDAYS)
    assert sum(task.is_due(day) for day in _week_from(MONDAY)) == 5
    assert not task.is_due(SATURDAY)
    assert not task.is_due(SUNDAY)


def test_completed_once_task_does_not_return():
    """A completed ONCE task is filtered out of later days."""
    task = CareTask(title="Vet", recurrence=Recurrence.ONCE, due_date=MONDAY)
    assert task.is_due(MONDAY)
    task.mark_complete()
    assert not task.is_due(MONDAY)


def test_undated_once_task_stays_due_until_done():
    """A one-off with no date stays on the list until it is completed."""
    task = CareTask(title="Order food", recurrence=Recurrence.ONCE)
    assert task.is_due(MONDAY) and task.is_due(SATURDAY)
    task.mark_complete()
    assert not task.is_due(SATURDAY)


def test_scheduler_reports_not_due_tasks_as_skipped(sample_owner, roomy_scheduler, sample_pet):
    """A task that isn't due today is explained, not silently dropped."""
    sample_pet.add_task(CareTask(title="Saturday brush", recurrence=Recurrence.WEEKLY, weekdays={5}))
    plan = roomy_scheduler.build_plan(sample_owner, MONDAY, include_reminders=False)
    assert plan.is_empty()
    assert "not scheduled for this day" in plan.skipped[0].reason
