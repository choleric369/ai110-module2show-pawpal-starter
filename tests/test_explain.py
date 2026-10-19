"""The explanation layer — the README explicitly asks the app to justify itself."""

from datetime import date

from pawpal.models.enums import EnergyLevel, Priority, Species, TaskCategory
from pawpal.models.pet import Pet
from pawpal.models.task import CareTask, MedicationTask
from pawpal.scheduling.explain import explain_plan, explain_strategy, warnings_for

DAY = date(2026, 6, 15)


def _plan(owner, scheduler):
    """Build a plan with reminders off."""
    return scheduler.build_plan(owner, DAY, include_reminders=False)


def test_every_scheduled_task_has_a_reason(sample_owner, roomy_scheduler, sample_pet, task_pool):
    """No ScheduledTask ships with an empty reason string."""
    for task in task_pool:
        sample_pet.add_task(task)
    plan = _plan(sample_owner, roomy_scheduler)
    assert all(item.reason.strip() for item in plan.scheduled)


def test_anchored_task_reason_mentions_the_fixed_time(
    sample_owner, roomy_scheduler, sample_pet
):
    """A pinned task explains itself as an appointment."""
    from datetime import time

    from pawpal.models.task import FeedingTask

    sample_pet.add_task(FeedingTask(title="Meal", duration_minutes=10, fixed_time=time(8, 0)))
    plan = _plan(sample_owner, roomy_scheduler)
    assert "Fixed appointment" in plan.scheduled[0].reason


def test_skip_reason_names_the_actual_constraint(sample_owner, scheduler, sample_pet):
    """A budget skip mentions minutes."""
    for i in range(5):
        sample_pet.add_task(CareTask(title=f"Task {i}", duration_minutes=40))
    plan = _plan(sample_owner, scheduler)
    assert any("min" in drop.reason for drop in plan.skipped)


def test_explanation_names_the_strategy_used(sample_owner, roomy_scheduler, sample_pet):
    """The narrative states which strategy produced the ordering."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    plan = _plan(sample_owner, roomy_scheduler)
    assert "Strategy:" in explain_plan(plan)


def test_explain_strategy_describes_each_option():
    """Every strategy name resolves to a non-empty description."""
    from pawpal.models.enums import StrategyName

    for name in StrategyName:
        assert explain_strategy(name.value).strip()


def test_unmet_needs_warns_on_short_exercise(sample_owner, roomy_scheduler, sample_pet):
    """A dog scheduled below its exercise need produces a warning line."""
    sample_pet.species = Species.DOG
    sample_pet.energy_level = EnergyLevel.HIGH
    sample_pet.add_task(
        CareTask(title="Short walk", category=TaskCategory.WALK, duration_minutes=5)
    )
    plan = _plan(sample_owner, roomy_scheduler)
    assert any("active min" in w for w in plan.unmet_needs())


def test_no_warning_when_exercise_target_is_met(sample_owner, roomy_scheduler, sample_pet):
    """A pet that gets enough activity generates no unmet-needs line."""
    sample_pet.species = Species.CAT
    sample_pet.energy_level = EnergyLevel.LOW
    sample_pet.add_task(
        CareTask(title="Long play", category=TaskCategory.ENRICHMENT, duration_minutes=60)
    )
    plan = _plan(sample_owner, roomy_scheduler)
    assert plan.unmet_needs() == []


def test_warnings_for_flags_dropped_medication(sample_owner, sample_pet):
    """Losing a dose is surfaced loudly, not as a quiet caption."""
    from pawpal.models.preferences import DayConstraints
    from pawpal.models.enums import StrategyName
    from pawpal.scheduling.scheduler import Scheduler
    from pawpal.scheduling.strategies import get_strategy

    sample_pet.add_task(MedicationTask(title="Insulin", duration_minutes=200))
    constraints = DayConstraints(day_start=600, day_end=700, available_minutes=100)
    plan = _plan(sample_owner, Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST)))
    assert [w.task.title for w in warnings_for(plan)] == ["Insulin"]


def test_warnings_for_ignores_dropped_grooming(sample_owner, scheduler, sample_pet):
    """A skipped brush is not an emergency and stays quiet."""
    sample_pet.add_task(
        CareTask(title="Brush", category=TaskCategory.GROOMING, duration_minutes=300)
    )
    plan = _plan(sample_owner, scheduler)
    assert warnings_for(plan) == []


def test_plan_to_text_is_readable(sample_owner, roomy_scheduler, sample_pet):
    """to_text() contains times, titles and priorities in time order."""
    sample_pet.add_task(
        CareTask(title="Morning walk", duration_minutes=30, priority=Priority.HIGH)
    )
    text = _plan(sample_owner, roomy_scheduler).to_text()
    assert "Morning walk" in text
    assert "priority: high" in text
    assert "07:00" in text


def test_plan_to_markdown_has_a_table(sample_owner, roomy_scheduler, sample_pet):
    """to_markdown() emits a real markdown table."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    markdown = _plan(sample_owner, roomy_scheduler).to_markdown()
    assert "| Time | Pet | Task |" in markdown


def test_tradeoff_summary_names_a_dropped_task(sample_owner, scheduler, sample_pet):
    """When something is cut, the summary says what was deferred."""
    from pawpal.scheduling.explain import summarize_tradeoff

    sample_pet.add_task(CareTask(title="Keep", duration_minutes=30, priority=Priority.HIGH))
    sample_pet.add_task(CareTask(title="Cut", duration_minutes=55, priority=Priority.LOW))
    plan = _plan(sample_owner, scheduler)
    assert "Cut" in summarize_tradeoff(plan)


def test_plan_text_handles_an_empty_day(sample_owner, scheduler):
    """An empty plan still renders a readable block."""
    text = _plan(sample_owner, scheduler).to_text()
    assert "nothing scheduled" in text


def test_household_plan_labels_itself(sample_owner, roomy_scheduler, sample_pet):
    """With two pets the heading says 'the household'."""
    second = Pet(name="Mochi", species=Species.CAT, age_years=3.0)
    second.add_task(CareTask(title="Cat meal", duration_minutes=10))
    sample_owner.add_pet(second)
    sample_pet.add_task(CareTask(title="Dog walk", duration_minutes=20))
    assert "the household" in _plan(sample_owner, roomy_scheduler).to_text()
