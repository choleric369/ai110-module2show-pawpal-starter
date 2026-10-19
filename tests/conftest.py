"""Shared pytest fixtures.

Every test builds its world from these so a change to the model shape is a
one-file fix rather than a rewrite of the suite.
"""

from datetime import date, time, timedelta

import pytest

from pawpal.models.contact import Contact, VetClinic
from pawpal.models.enums import (
    BillCategory,
    ConditionStatus,
    EnergyLevel,
    GroomingService,
    PaymentStatus,
    Priority,
    Severity,
    Species,
    StrategyName,
    TaskCategory,
    TimeOfDay,
)
from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.preferences import DayConstraints, OwnerPreferences
from pawpal.models.records import (
    Allergy,
    Bill,
    Condition,
    GroomingSession,
    MedicalHistory,
    Vaccination,
    VetVisit,
)
from pawpal.models.task import CareTask, FeedingTask, MedicationTask, WalkTask
from pawpal.scheduling.scheduler import Scheduler
from pawpal.scheduling.strategies import get_strategy

FIXED_TODAY = date(2026, 6, 15)  # a Monday


@pytest.fixture
def today():
    """A fixed date so every record test is deterministic, never 'depends on now'."""
    return FIXED_TODAY


@pytest.fixture
def sample_pet():
    """A medium-energy adult dog with no tasks attached yet."""
    return Pet(
        name="Biscuit",
        species=Species.DOG,
        breed="Golden Retriever",
        age_years=4.0,
        weight_kg=30.0,
        energy_level=EnergyLevel.MEDIUM,
    )


@pytest.fixture
def sample_owner(sample_pet):
    """An owner with one pet and default preferences (180 min budget)."""
    owner = Owner(name="Jordan", phone="5551234567", email="jordan@example.com")
    owner.add_pet(sample_pet)
    return owner


@pytest.fixture
def task_pool():
    """Mixed tasks: high/medium/low, short/long, one anchored, one medication."""
    return [
        WalkTask(
            title="Morning walk",
            category=TaskCategory.WALK,
            duration_minutes=30,
            priority=Priority.HIGH,
        ),
        CareTask(
            title="Puzzle feeder",
            category=TaskCategory.ENRICHMENT,
            duration_minutes=10,
            priority=Priority.MEDIUM,
        ),
        CareTask(
            title="Brush coat",
            category=TaskCategory.GROOMING,
            duration_minutes=20,
            priority=Priority.LOW,
        ),
        FeedingTask(
            title="Breakfast",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            fixed_time=time(8, 0),
            skippable=False,
        ),
        MedicationTask(
            title="Joint tablet",
            category=TaskCategory.MEDICATION,
            duration_minutes=5,
            priority=Priority.HIGH,
        ),
    ]


@pytest.fixture
def preferences():
    """07:00-22:00 with a 180 minute budget and 5 minute breaks."""
    return OwnerPreferences(
        wake_time=time(7, 0),
        sleep_time=time(22, 0),
        available_minutes=180,
        break_minutes=5,
        strategy=StrategyName.PRIORITY_FIRST,
    )


@pytest.fixture
def constraints(preferences):
    """DayConstraints derived from the default preferences."""
    return DayConstraints.from_preferences(preferences)


@pytest.fixture
def tight_constraints():
    """A 60-minute day — small enough that the scheduler must drop something."""
    return DayConstraints(
        day_start=7 * 60, day_end=22 * 60, available_minutes=60, break_minutes=5
    )


@pytest.fixture
def scheduler(tight_constraints):
    """A Scheduler wired to PriorityFirstStrategy for predictable assertions."""
    return Scheduler(tight_constraints, get_strategy(StrategyName.PRIORITY_FIRST))


@pytest.fixture
def roomy_scheduler(constraints):
    """A Scheduler with the full default day, for tests about ordering not cuts."""
    return Scheduler(constraints, get_strategy(StrategyName.PRIORITY_FIRST))


@pytest.fixture
def temp_save(tmp_path):
    """A throwaway JSON path so storage tests never touch data/pawpal_data.json."""
    return tmp_path / "state.json"


@pytest.fixture
def medical_history(today):
    """One chronic condition, one severe allergy, a due booster, two past visits."""
    return MedicalHistory(
        conditions=[
            Condition(
                name="Arthritis",
                diagnosed_on=today - timedelta(days=400),
                status=ConditionStatus.CHRONIC,
                severity=Severity.MODERATE,
                treatment="Daily anti-inflammatory",
            ),
            Condition(
                name="Ear infection",
                diagnosed_on=today - timedelta(days=200),
                status=ConditionStatus.RESOLVED,
                severity=Severity.MILD,
                resolved_on=today - timedelta(days=180),
            ),
        ],
        allergies=[
            Allergy(substance="Chicken", reaction="Itching", severity=Severity.SEVERE),
            Allergy(substance="Pollen", reaction="Sneezing", severity=Severity.MILD),
        ],
        vaccinations=[
            Vaccination(
                name="Rabies",
                given_on=today - timedelta(days=350),
                next_due_on=today + timedelta(days=10),
            ),
            Vaccination(
                name="DHPP",
                given_on=today - timedelta(days=100),
                next_due_on=today + timedelta(days=90),
            ),
        ],
        visits=[
            VetVisit(
                visit_date=today - timedelta(days=30),
                clinic="Bayside",
                reason="Stiffness",
                diagnosis="Arthritis flare",
                weight_kg=30.0,
                follow_up_on=today + timedelta(days=7),
            ),
            VetVisit(
                visit_date=today - timedelta(days=200),
                clinic="Bayside",
                reason="Ear scratching",
                diagnosis="Ear infection",
                weight_kg=31.0,
            ),
        ],
    )


@pytest.fixture
def grooming_log(today):
    """Three sessions six weeks apart, the last one now due again."""
    return [
        GroomingSession(
            session_date=today - timedelta(days=42),
            provider="Happy Paws",
            services=[GroomingService.BATH, GroomingService.NAIL_TRIM],
            duration_minutes=60,
            next_due_on=today,
        ),
        GroomingSession(
            session_date=today - timedelta(days=84),
            provider="Happy Paws",
            services=[GroomingService.BATH],
            duration_minutes=60,
            next_due_on=today - timedelta(days=42),
        ),
        GroomingSession(
            session_date=today - timedelta(days=126),
            provider="Happy Paws",
            services=[GroomingService.HAIRCUT],
            duration_minutes=90,
            next_due_on=today - timedelta(days=84),
        ),
    ]


@pytest.fixture
def bills(today):
    """A paid vet bill, an unpaid grooming bill, and one partially reimbursed."""
    return [
        Bill(
            id="b-vet",
            description="Wellness exam",
            category=BillCategory.VET,
            amount=150.0,
            billed_on=today - timedelta(days=30),
            status=PaymentStatus.PAID,
            amount_paid=150.0,
            paid_on=today - timedelta(days=30),
        ),
        Bill(
            id="b-groom",
            description="Full groom",
            category=BillCategory.GROOMING,
            amount=90.0,
            billed_on=today - timedelta(days=45),
            status=PaymentStatus.UNPAID,
        ),
        Bill(
            id="b-surgery",
            description="Dental surgery",
            category=BillCategory.VET,
            amount=300.0,
            billed_on=today - timedelta(days=5),
            status=PaymentStatus.CLAIMED,
            amount_paid=300.0,
            paid_on=today - timedelta(days=5),
            insurance_claimed=True,
            reimbursed_amount=200.0,
        ),
    ]


@pytest.fixture
def pet_with_records(sample_pet, medical_history, grooming_log, bills):
    """A fully populated pet: tasks, health history, grooming log and costs."""
    sample_pet.medical = medical_history
    sample_pet.grooming_sessions = list(grooming_log)
    sample_pet.bills = list(bills)
    sample_pet.add_task(
        CareTask(
            title="Evening play",
            category=TaskCategory.ENRICHMENT,
            duration_minutes=15,
            priority=Priority.MEDIUM,
            preferred_time=TimeOfDay.EVENING,
        )
    )
    return sample_pet


@pytest.fixture
def owner_with_records(pet_with_records):
    """An owner whose single pet carries the full record set."""
    owner = Owner(name="Jordan", phone="5551234567")
    owner.add_pet(pet_with_records)
    return owner


@pytest.fixture
def owner_with_contacts(sample_owner):
    """An owner with phone, email, an emergency contact and a preferred vet."""
    sample_owner.emergency_contact = Contact(
        name="Riley Chen", phone="5550142", relationship="neighbour"
    )
    sample_owner.preferred_vet = VetClinic(
        name="Dr. Rao",
        clinic_name="Bayside Animal Hospital",
        phone="5550177",
        is_emergency=True,
        hours="08:00-20:00",
    )
    return sample_owner
