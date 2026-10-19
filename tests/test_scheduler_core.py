"""The main scheduling contract: ordering, time budget, and selection."""

from datetime import date

from pawpal.models.enums import Priority, StrategyName, TaskCategory
from pawpal.models.task import CareTask
from pawpal.scheduling.conflicts import find_overlaps
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy

DAY = date(2026, 6, 15)


def _plan(owner, scheduler, day=DAY):
    """Build a plan with reminders off, so tests see only the tasks they set up."""
    return scheduler.build_plan(owner, day, include_reminders=False)


def _titles(plan):
    """Scheduled task titles in clock order."""
    return [item.task.title for item in plan.scheduled]


def test_high_priority_scheduled_before_low(sample_owner, roomy_scheduler, sample_pet):
    """With PriorityFirst, the high-priority task gets the earlier slot."""
    sample_pet.add_task(CareTask(title="Low", duration_minutes=20, priority=Priority.LOW))
    sample_pet.add_task(CareTask(title="High", duration_minutes=20, priority=Priority.HIGH))
    plan = _plan(sample_owner, roomy_scheduler)
    assert _titles(plan).index("High") < _titles(plan).index("Low")


def test_total_minutes_never_exceeds_budget(sample_owner, scheduler, sample_pet):
    """Sum of scheduled durations <= available_minutes, always."""
    for i in range(10):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=25))
    plan = _plan(sample_owner, scheduler)
    assert plan.total_minutes() <= scheduler.constraints.available_minutes


def test_tasks_do_not_overlap(sample_owner, roomy_scheduler, sample_pet, task_pool):
    """No two scheduled slots share a minute."""
    for task in task_pool:
        sample_pet.add_task(task)
    plan = _plan(sample_owner, roomy_scheduler)
    assert find_overlaps(plan.scheduled) == []


def test_slots_are_contiguous_with_breaks(sample_owner, roomy_scheduler, sample_pet):
    """Each task starts after the previous end plus the configured break."""
    for i in range(3):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    gap = roomy_scheduler.constraints.break_minutes
    for earlier, later in zip(plan.scheduled, plan.scheduled[1:]):
        assert later.start_minute >= earlier.end_minute + gap


def test_plan_starts_at_wake_time(sample_owner, roomy_scheduler, sample_pet):
    """The first slot never begins before day_start."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.scheduled[0].start_minute >= roomy_scheduler.constraints.day_start


def test_plan_never_runs_past_sleep_time(sample_owner, roomy_scheduler, sample_pet):
    """The last slot ends at or before day_end."""
    for i in range(8):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert all(s.end_minute <= roomy_scheduler.constraints.day_end for s in plan.scheduled)


def test_skipped_tasks_have_reasons(sample_owner, scheduler, sample_pet):
    """Every SkippedTask carries a non-empty reason string."""
    for i in range(6):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=30))
    plan = _plan(sample_owner, scheduler)
    assert plan.skipped
    assert all(drop.reason.strip() for drop in plan.skipped)


def test_every_task_is_either_scheduled_or_skipped(sample_owner, scheduler, sample_pet):
    """No due task silently disappears — the two lists account for all of them."""
    for i in range(6):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=30))
    plan = _plan(sample_owner, scheduler)
    seen = {s.task.id for s in plan.scheduled} | {d.task.id for d in plan.skipped}
    assert seen == {t.id for t in sample_pet.tasks}


def test_strategy_change_changes_order(sample_owner, constraints, sample_pet):
    """ShortestFirst produces a different order than PriorityFirst on the same pool."""
    sample_pet.add_task(CareTask(title="Long high", duration_minutes=60, priority=Priority.HIGH))
    sample_pet.add_task(CareTask(title="Short low", duration_minutes=5, priority=Priority.LOW))
    by_priority = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    by_length = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.SHORTEST_FIRST)))
    assert _titles(by_priority)[0] == "Long high"
    assert _titles(by_length)[0] == "Short low"


def test_shortest_first_fits_more_tasks(sample_owner, tight_constraints, sample_pet):
    """On a tight budget, ShortestFirst schedules a larger count."""
    sample_pet.add_task(CareTask(title="Long", duration_minutes=55, priority=Priority.HIGH))
    for i in range(4):
        sample_pet.add_task(CareTask(title=f"Short {i}", duration_minutes=10, priority=Priority.LOW))
    priority_plan = _plan(
        sample_owner, Scheduler(tight_constraints, get_strategy(StrategyName.PRIORITY_FIRST))
    )
    shortest_plan = _plan(
        sample_owner, Scheduler(tight_constraints, get_strategy(StrategyName.SHORTEST_FIRST))
    )
    assert len(shortest_plan.scheduled) > len(priority_plan.scheduled)


def test_balanced_strategy_spreads_categories(sample_owner, constraints, sample_pet):
    """BalancedStrategy does not place three walks before the first meal."""
    for i in range(3):
        sample_pet.add_task(
            CareTask(title=f"Walk {i}", category=TaskCategory.WALK, duration_minutes=10)
        )
        sample_pet.add_task(
            CareTask(title=f"Meal {i}", category=TaskCategory.FEEDING, duration_minutes=10)
        )
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.BALANCED)))
    first_three = [s.task.category for s in plan.scheduled[:3]]
    assert len(set(first_three)) > 1


def test_non_skippable_task_bypasses_budget(sample_owner, scheduler, sample_pet):
    """Medication is scheduled even when the time budget is already spent."""
    from pawpal.models.task import MedicationTask

    sample_pet.add_task(CareTask(title="Filler", duration_minutes=55, priority=Priority.HIGH))
    sample_pet.add_task(MedicationTask(title="Insulin", duration_minutes=10))
    plan = _plan(sample_owner, scheduler)
    assert "Insulin" in _titles(plan)


def test_preferred_time_is_respected(sample_owner, roomy_scheduler, sample_pet):
    """An evening-preferred task lands in the evening window."""
    from pawpal.models.enums import TimeOfDay

    sample_pet.add_task(
        CareTask(title="Evening play", duration_minutes=15, preferred_time=TimeOfDay.EVENING)
    )
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.scheduled[0].start_minute >= 17 * 60


def test_plan_records_the_strategy_used(sample_owner, roomy_scheduler, sample_pet):
    """The plan remembers which strategy built it."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.strategy_used == StrategyName.PRIORITY_FIRST.value


def test_household_plan_covers_every_pet(sample_owner, roomy_scheduler, sample_pet):
    """With no pet argument, all pets' tasks are considered."""
    from pawpal.models.pet import Pet

    second = Pet(name="Mochi", age_years=3.0)
    second.add_task(CareTask(title="Cat meal", duration_minutes=10))
    sample_owner.add_pet(second)
    sample_pet.add_task(CareTask(title="Dog walk", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert {"Dog walk", "Cat meal"} <= set(_titles(plan))


def test_single_pet_plan_excludes_others(sample_owner, roomy_scheduler, sample_pet):
    """Passing a pet limits the plan to that pet's tasks."""
    from pawpal.models.pet import Pet

    second = Pet(name="Mochi", age_years=3.0)
    second.add_task(CareTask(title="Cat meal", duration_minutes=10))
    sample_owner.add_pet(second)
    sample_pet.add_task(CareTask(title="Dog walk", duration_minutes=20))
    plan = roomy_scheduler.build_plan(sample_owner, DAY, sample_pet, include_reminders=False)
    assert _titles(plan) == ["Dog walk"]
