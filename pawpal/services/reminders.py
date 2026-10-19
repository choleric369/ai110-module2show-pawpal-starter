"""Turns past records into future tasks — the bridge records <-> scheduler.

Without this, medical history is a read-only log. With it, a booster due next
week or a follow-up appointment shows up in today's plan automatically.
Generated tasks are marked so the UI can label them 'auto' and not save them.
"""

from datetime import date

from pawpal.models.enums import Priority, Recurrence, TaskCategory, TimeOfDay
from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.task import CareTask, GroomingTask, VetAppointment
from pawpal.utils.timeutils import to_time

# Marker written into a generated task's notes so it can be told apart.
AUTO_TAG = "[auto]"
DEFAULT_APPOINTMENT_MINUTES = 45
DEFAULT_VACCINATION_MINUTES = 30
DEFAULT_GROOMING_MINUTES = 60
# Follow-ups land mid-morning when the record does not name a time.
DEFAULT_APPOINTMENT_START = to_time(10 * 60)


def follow_up_tasks(pet: Pet, day: date) -> list[CareTask]:
    """VetAppointment tasks for any visit whose follow_up_on is today."""
    tasks = []
    for visit in pet.medical.visits:
        if visit.follow_up_on != day:
            continue
        tasks.append(
            VetAppointment(
                title=f"Vet follow-up: {visit.diagnosis or visit.reason or 'check-up'}",
                category=TaskCategory.VET,
                duration_minutes=DEFAULT_APPOINTMENT_MINUTES,
                priority=Priority.HIGH,
                recurrence=Recurrence.ONCE,
                due_date=day,
                fixed_time=DEFAULT_APPOINTMENT_START,
                skippable=False,
                clinic=visit.clinic,
                notes=f"{AUTO_TAG} from visit on {visit.visit_date}",
            )
        )
    return tasks


def vaccination_tasks(pet: Pet, day: date, lookahead_days: int = 30) -> list[CareTask]:
    """Reminder tasks for boosters due inside the window or already overdue."""
    tasks = []
    for vaccine in pet.medical.due_vaccinations(day, lookahead_days):
        overdue = vaccine.is_overdue(day)
        tasks.append(
            CareTask(
                title=f"Book {vaccine.name} booster",
                category=TaskCategory.VET,
                duration_minutes=DEFAULT_VACCINATION_MINUTES,
                priority=Priority.HIGH if overdue else Priority.MEDIUM,
                recurrence=Recurrence.ONCE,
                due_date=day,
                preferred_time=TimeOfDay.MORNING,
                notes=f"{AUTO_TAG} booster due {vaccine.next_due_on}",
            )
        )
    return tasks


def grooming_tasks(pet: Pet, day: date, lookahead_days: int = 14) -> list[CareTask]:
    """A GroomingTask when the last session's next_due_on has come around."""
    if not pet.grooming_due(day, lookahead_days):
        return []
    last = pet.last_grooming()
    services = ", ".join(last.service_labels()) if last else "grooming"
    return [
        GroomingTask(
            title=f"Grooming: {services}",
            category=TaskCategory.GROOMING,
            duration_minutes=last.duration_minutes if last else DEFAULT_GROOMING_MINUTES,
            priority=Priority.LOW,
            recurrence=Recurrence.ONCE,
            due_date=day,
            notes=f"{AUTO_TAG} last groomed {last.days_since(day)} days ago" if last else AUTO_TAG,
        )
    ]


def medication_tasks(pet: Pet, day: date) -> list[CareTask]:
    """Doses implied by active conditions whose treatment is an ongoing med.

    Deliberately conservative: if the pet has ANY hand-entered medication task,
    nothing is generated. Double-scheduling a dose is a safety problem, and
    matching free-text treatments to task titles is not reliable enough to risk.
    """
    from pawpal.models.task import MedicationTask

    if any(isinstance(task, MedicationTask) for task in pet.tasks):
        return []
    tasks = []
    for condition in pet.medical.active_conditions():
        if not condition.treatment.strip():
            continue
        title = f"{condition.treatment} for {condition.name}"
        tasks.append(
            MedicationTask(
                title=title,
                category=TaskCategory.MEDICATION,
                duration_minutes=5,
                priority=Priority.HIGH,
                recurrence=Recurrence.DAILY,
                dosage=condition.treatment,
                notes=f"{AUTO_TAG} from condition '{condition.name}'",
            )
        )
    return tasks


def bill_reminders(pet: Pet, day: date) -> list[str]:
    """Text nudges for overdue bills; shown as warnings, not scheduled tasks."""
    return [
        f"{pet.name}: '{bill.description}' is overdue ({bill.outstanding():.2f} outstanding)"
        for bill in pet.bills
        if bill.is_overdue(day)
    ]


def all_reminders(pet: Pet, day: date) -> list[CareTask]:
    """Every auto-generated task for one pet on one day, de-duplicated."""
    generated = [
        *follow_up_tasks(pet, day),
        *vaccination_tasks(pet, day),
        *grooming_tasks(pet, day),
        *medication_tasks(pet, day),
    ]
    seen: set[str] = {t.title.strip().lower() for t in pet.tasks}
    unique = []
    for task in generated:
        key = task.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    return unique


def household_reminders(owner: Owner, day: date) -> list[tuple[CareTask, Pet]]:
    """all_reminders across every pet, paired with the pet it belongs to."""
    return [(task, pet) for pet in owner.pets for task in all_reminders(pet, day)]


def is_auto(task: CareTask) -> bool:
    """True if a task was generated from a record rather than entered by hand."""
    return AUTO_TAG in (task.notes or "")
