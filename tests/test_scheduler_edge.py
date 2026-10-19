"""Edge cases — the cheap tests that catch the expensive bugs."""

from datetime import date

from pawpal.models.enums import Priority
from pawpal.models.pet import Pet
from pawpal.models.preferences import DayConstraints
from pawpal.models.task import CareTask, MedicationTask
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy
from pawpal.models.enums import StrategyName

DAY = date(2026, 6, 15)


def _plan(owner, scheduler):
    """Build a plan with reminders off."""
    return scheduler.build_plan(owner, DAY, include_reminders=False)


def test_no_tasks_returns_empty_plan(sample_owner, scheduler):
    """An empty pool produces an empty plan, not a crash."""
    plan = _plan(sample_owner, scheduler)
    assert plan.is_empty()
    assert plan.total_minutes() == 0


def test_zero_budget_schedules_nothing(sample_owner, sample_pet):
    """available_minutes = 0 skips everything with a budget reason."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    constraints = DayConstraints(day_start=420, day_end=1320, available_minutes=0)
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert plan.is_empty()
    assert "budget" in plan.skipped[0].reason


def test_task_longer_than_budget_is_skipped(sample_owner, scheduler, sample_pet):
    """A 300-minute task never fits a 60-minute budget."""
    sample_pet.add_task(CareTask(title="Marathon", duration_minutes=300))
    plan = _plan(sample_owner, scheduler)
    assert plan.is_empty()
    assert plan.skipped[0].reason


def test_task_longer_than_whole_day_is_skipped(sample_owner, sample_pet):
    """Duration beyond wake->sleep is rejected with a window reason."""
    sample_pet.add_task(CareTask(title="Endless", duration_minutes=480))
    constraints = DayConstraints(day_start=600, day_end=840, available_minutes=1000)
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert plan.is_empty()
    assert "longer than your whole available day" in plan.skipped[0].reason


def test_identical_tasks_are_deterministic(sample_owner, roomy_scheduler, sample_pet):
    """Two identical tasks always come out in the same order (stable sort)."""
    for i in range(4):
        sample_pet.add_task(CareTask(title=f"Same {i}", duration_minutes=15))
    first = [s.task.title for s in _plan(sample_owner, roomy_scheduler).scheduled]
    for item in sample_pet.tasks:
        item.reset()
    second = [s.task.title for s in _plan(sample_owner, roomy_scheduler).scheduled]
    assert first == second


def test_all_same_priority_falls_back_to_tiebreak(sample_owner, roomy_scheduler, sample_pet):
    """A flat-priority pool still produces a deterministic order."""
    sample_pet.add_task(CareTask(title="B long", duration_minutes=40, priority=Priority.MEDIUM))
    sample_pet.add_task(CareTask(title="A short", duration_minutes=10, priority=Priority.MEDIUM))
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.scheduled[0].task.title == "A short"


def test_unschedulable_medication_is_flagged_loudly(sample_owner, sample_pet):
    """A non-skippable task that cannot fit appears in the warnings, not silently."""
    from pawpal.scheduling.explain import warnings_for

    sample_pet.add_task(MedicationTask(title="Insulin", duration_minutes=300))
    constraints = DayConstraints(day_start=600, day_end=700, available_minutes=100)
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert plan.is_empty()
    assert warnings_for(plan)


def test_pet_with_no_tasks_is_not_in_plan(sample_owner, roomy_scheduler, sample_pet):
    """Household planning tolerates a pet that has nothing to do."""
    sample_owner.add_pet(Pet(name="Ghost", age_years=2.0))
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert [p.name for p in plan.pets()] == ["Biscuit"]


def test_blocked_window_is_skipped_over(sample_owner, sample_pet):
    """A task cannot be placed inside a blocked window."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=30))
    constraints = DayConstraints(
        day_start=540, day_end=1080, available_minutes=180, blocked=[(540, 720)]
    )
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert plan.scheduled[0].start_minute >= 720


def test_empty_plan_utilization_is_zero(sample_owner, scheduler):
    """Utilization of an empty plan is 0, not a division error."""
    plan = _plan(sample_owner, scheduler)
    assert plan.utilization(180) == 0.0
    assert plan.utilization(0) == 0.0


def test_completion_rate_of_empty_plan_is_zero(sample_owner, scheduler):
    """No scheduled tasks means a 0% completion rate, not a crash."""
    assert _plan(sample_owner, scheduler).completion_rate() == 0.0
