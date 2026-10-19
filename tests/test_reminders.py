"""Records -> tasks. The bridge that puts medical history into today's plan."""

from datetime import timedelta

from pawpal.models.enums import GroomingService, Priority, StrategyName
from pawpal.models.records import Bill, GroomingSession, Vaccination, VetVisit
from pawpal.models.task import MedicationTask, VetAppointment
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy
from pawpal.services import reminders, storage


def _titles(tasks):
    """Titles of a generated task list."""
    return [t.title for t in tasks]


def test_follow_up_becomes_a_vet_appointment(pet_with_records, today):
    """A visit with follow_up_on == today generates a VetAppointment task."""
    due = today + timedelta(days=7)
    tasks = reminders.follow_up_tasks(pet_with_records, due)
    assert len(tasks) == 1
    assert isinstance(tasks[0], VetAppointment)


def test_follow_up_task_is_anchored(pet_with_records, today):
    """The generated appointment is anchored and cannot be shifted."""
    task = reminders.follow_up_tasks(pet_with_records, today + timedelta(days=7))[0]
    assert task.is_anchored()
    assert task.skippable is False


def test_follow_up_on_another_day_generates_nothing(pet_with_records, today):
    """The reminder only fires on the follow-up date itself."""
    assert reminders.follow_up_tasks(pet_with_records, today) == []


def test_due_booster_becomes_a_task(pet_with_records, today):
    """A vaccination due inside the lookahead produces a reminder task."""
    tasks = reminders.vaccination_tasks(pet_with_records, today)
    assert any("Rabies" in title for title in _titles(tasks))


def test_future_booster_generates_nothing(sample_pet, today):
    """A shot due in six months adds no task today."""
    sample_pet.medical.add_vaccination(
        Vaccination(name="DHPP", given_on=today, next_due_on=today + timedelta(days=180))
    )
    assert reminders.vaccination_tasks(sample_pet, today) == []


def test_overdue_booster_is_high_priority(sample_pet, today):
    """A missed shot outranks one that is merely approaching."""
    sample_pet.medical.add_vaccination(
        Vaccination(name="Rabies", next_due_on=today - timedelta(days=10))
    )
    assert reminders.vaccination_tasks(sample_pet, today)[0].priority is Priority.HIGH


def test_overdue_grooming_becomes_a_task(pet_with_records, today):
    """A past next_due_on produces a GroomingTask."""
    tasks = reminders.grooming_tasks(pet_with_records, today)
    assert len(tasks) == 1
    assert "Grooming" in tasks[0].title


def test_recently_groomed_pet_gets_no_task(sample_pet, today):
    """A pet groomed last week produces no grooming reminder."""
    sample_pet.add_grooming_session(
        GroomingSession(
            session_date=today - timedelta(days=7),
            services=[GroomingService.BATH],
            next_due_on=today + timedelta(days=35),
        )
    )
    assert reminders.grooming_tasks(sample_pet, today) == []


def test_condition_treatment_becomes_a_medication_task(pet_with_records, today):
    """An active condition with a treatment generates a daily dose."""
    tasks = reminders.medication_tasks(pet_with_records, today)
    assert any(isinstance(t, MedicationTask) for t in tasks)


def test_manual_medication_suppresses_generated_ones(pet_with_records, today):
    """A hand-entered dose wins; nothing is auto-generated alongside it."""
    pet_with_records.add_task(MedicationTask(title="Anti-inflammatory", duration_minutes=5))
    assert reminders.medication_tasks(pet_with_records, today) == []


def test_generated_tasks_are_tagged_auto(pet_with_records, today):
    """is_auto() is True for everything reminders produces."""
    generated = reminders.all_reminders(pet_with_records, today)
    assert generated
    assert all(reminders.is_auto(task) for task in generated)


def test_hand_entered_tasks_are_not_auto(pet_with_records):
    """A task the owner typed is never reported as generated."""
    assert not reminders.is_auto(pet_with_records.tasks[0])


def test_reminders_are_deduplicated(sample_pet, today):
    """A reminder matching an existing task title is not added twice."""
    sample_pet.medical.add_vaccination(
        Vaccination(name="Rabies", next_due_on=today + timedelta(days=5))
    )
    from pawpal.models.task import CareTask

    sample_pet.add_task(CareTask(title="Book Rabies booster", duration_minutes=30))
    assert reminders.all_reminders(sample_pet, today) == []


def test_reminders_reach_the_plan(owner_with_records, constraints, today):
    """build_plan(include_reminders=True) schedules a due booster."""
    scheduler = Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST))
    plan = scheduler.build_plan(owner_with_records, today, include_reminders=True)
    titles = [s.task.title for s in plan.scheduled] + [d.task.title for d in plan.skipped]
    assert any("Rabies" in title for title in titles)


def test_reminders_can_be_switched_off(owner_with_records, constraints, today):
    """include_reminders=False plans only hand-entered tasks."""
    scheduler = Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST))
    plan = scheduler.build_plan(owner_with_records, today, include_reminders=False)
    assert [s.task.title for s in plan.scheduled] == ["Evening play"]


def test_auto_tasks_are_not_persisted(owner_with_records, constraints, today, temp_save):
    """A save/load round trip does not store generated reminder tasks."""
    scheduler = Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST))
    scheduler.build_plan(owner_with_records, today, include_reminders=True)
    storage.save_state(owner_with_records, temp_save)
    restored = storage.load_state(temp_save)
    assert not any(reminders.is_auto(t) for t in restored.pets[0].tasks)


def test_bill_reminders_name_overdue_bills(pet_with_records, today):
    """An overdue bill produces a text nudge, not a scheduled task."""
    nudges = reminders.bill_reminders(pet_with_records, today)
    assert any("Full groom" in nudge for nudge in nudges)


def test_bill_reminders_ignore_paid_bills(sample_pet, today):
    """A settled bill never nags."""
    sample_pet.add_bill(
        Bill(
            description="Paid thing",
            amount=50.0,
            amount_paid=50.0,
            billed_on=today - timedelta(days=200),
        )
    )
    assert reminders.bill_reminders(sample_pet, today) == []


def test_household_reminders_pair_task_with_pet(owner_with_records, today):
    """Each generated task knows which pet it belongs to."""
    pairs = reminders.household_reminders(owner_with_records, today)
    assert pairs
    assert all(pet.name == "Biscuit" for _, pet in pairs)


def test_visit_without_follow_up_generates_nothing(sample_pet, today):
    """A closed visit adds no future work."""
    sample_pet.medical.add_visit(VetVisit(visit_date=today, clinic="Bayside"))
    assert reminders.follow_up_tasks(sample_pet, today) == []
