"""Demo data so the app is never empty on first run or on a fresh clone.

Also doubles as the fixture source for tests and the README walkthrough.
Dates are relative to today so the demo never goes stale.
"""

from datetime import date, time, timedelta

from pawpal.models.contact import Contact, Groomer, VetClinic
from pawpal.models.enums import (
    BillCategory,
    ConditionStatus,
    EnergyLevel,
    GroomingService,
    PaymentStatus,
    Priority,
    Recurrence,
    Severity,
    Sex,
    Species,
    TaskCategory,
    TimeOfDay,
    VisitType,
)
from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.preferences import OwnerPreferences
from pawpal.models.records import (
    Allergy,
    Bill,
    Condition,
    GroomingSession,
    MedicalHistory,
    Vaccination,
    VetVisit,
)
from pawpal.models.task import (
    EnrichmentTask,
    FeedingTask,
    GroomingTask,
    MedicationTask,
    WalkTask,
)


def demo_owner() -> Owner:
    """A two-pet household (dog + cat) with contacts, records and costs filled in."""
    owner = Owner(
        name="Jordan Avery",
        phone="+1 555 0134",
        email="jordan@example.com",
        address="48 Harbour Lane, Bayside",
        emergency_contact=demo_emergency_contact(),
        preferred_vet=demo_vet(),
        preferences=OwnerPreferences(
            wake_time=time(7, 0),
            sleep_time=time(22, 0),
            available_minutes=180,
            break_minutes=5,
        ),
    )
    owner.pets = [demo_dog(), demo_cat()]
    return owner


def demo_dog() -> Pet:
    """Biscuit, a high-energy retriever: walks, training, grooming every 6 weeks."""
    today = date.today()
    pet = Pet(
        name="Biscuit",
        species=Species.DOG,
        breed="Golden Retriever",
        sex=Sex.MALE,
        date_of_birth=today - timedelta(days=int(3.5 * 365)),
        weight_kg=31.4,
        color="golden",
        microchip_id="985141000123456",
        is_neutered=True,
        energy_level=EnergyLevel.HIGH,
        vet=demo_vet(),
        groomer=demo_groomer(),
        insurance_provider="PetSecure",
        insurance_policy_no="PS-884213",
    )
    pet.tasks = [
        WalkTask(
            title="Morning walk",
            category=TaskCategory.WALK,
            duration_minutes=30,
            priority=Priority.HIGH,
            preferred_time=TimeOfDay.MORNING,
            distance_km=2.5,
        ),
        FeedingTask(
            title="Breakfast",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            fixed_time=time(8, 0),
            skippable=False,
            portion_grams=350,
        ),
        EnrichmentTask(
            title="Training session",
            category=TaskCategory.TRAINING,
            duration_minutes=15,
            priority=Priority.MEDIUM,
            indoor=True,
        ),
        WalkTask(
            title="Evening walk",
            category=TaskCategory.WALK,
            duration_minutes=40,
            priority=Priority.HIGH,
            preferred_time=TimeOfDay.EVENING,
            distance_km=3.2,
        ),
        FeedingTask(
            title="Dinner",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            fixed_time=time(18, 30),
            skippable=False,
            portion_grams=350,
        ),
        GroomingTask(
            title="Brush coat",
            category=TaskCategory.GROOMING,
            duration_minutes=15,
            priority=Priority.LOW,
            recurrence=Recurrence.WEEKLY,
            weekdays={5},
            tool="slicker brush",
        ),
    ]
    pet.medical = MedicalHistory(
        vaccinations=[
            Vaccination(
                name="Rabies",
                given_on=today - timedelta(days=350),
                next_due_on=today + timedelta(days=15),
                clinic="Bayside Animal Hospital",
                lot_number="RB-2291",
            ),
            Vaccination(
                name="DHPP",
                given_on=today - timedelta(days=180),
                next_due_on=today + timedelta(days=185),
                clinic="Bayside Animal Hospital",
            ),
        ],
        visits=[
            VetVisit(
                visit_date=today - timedelta(days=42),
                visit_type=VisitType.CHECKUP,
                clinic="Bayside Animal Hospital",
                vet_name="Dr. Rao",
                reason="Annual wellness check",
                diagnosis="Healthy, mild tartar buildup",
                treatment="Dental chew recommended",
                weight_kg=31.4,
                bill_id="bill-dog-1",
            )
        ],
    )
    pet.grooming_sessions = [
        GroomingSession(
            session_date=today - timedelta(days=44),
            provider="Happy Paws",
            services=[GroomingService.BATH, GroomingService.DE_SHEDDING, GroomingService.NAIL_TRIM],
            duration_minutes=75,
            next_due_on=today + timedelta(days=-2),
            bill_id="bill-dog-2",
        ),
        GroomingSession(
            session_date=today - timedelta(days=86),
            provider="Happy Paws",
            services=[GroomingService.BATH, GroomingService.HAIRCUT],
            duration_minutes=90,
            next_due_on=today - timedelta(days=44),
        ),
    ]
    pet.bills = [
        Bill(
            id="bill-dog-1",
            description="Annual wellness exam",
            category=BillCategory.VET,
            amount=145.00,
            billed_on=today - timedelta(days=42),
            status=PaymentStatus.PAID,
            paid_on=today - timedelta(days=42),
            amount_paid=145.00,
            provider="Bayside Animal Hospital",
            linked_record_id="visit-dog-1",
        ),
        Bill(
            id="bill-dog-2",
            description="Full groom + de-shed",
            category=BillCategory.GROOMING,
            amount=95.00,
            billed_on=today - timedelta(days=44),
            status=PaymentStatus.PAID,
            paid_on=today - timedelta(days=44),
            amount_paid=95.00,
            provider="Happy Paws",
        ),
        Bill(
            description="Large-breed kibble (15kg)",
            category=BillCategory.FOOD,
            amount=72.50,
            billed_on=today - timedelta(days=12),
            status=PaymentStatus.PAID,
            paid_on=today - timedelta(days=12),
            amount_paid=72.50,
        ),
    ]
    return pet


def demo_cat() -> Pet:
    """Mochi, a senior cat: fixed-time meals, daily medication, arthritis on file."""
    today = date.today()
    pet = Pet(
        name="Mochi",
        species=Species.CAT,
        breed="Domestic Shorthair",
        sex=Sex.FEMALE,
        date_of_birth=today - timedelta(days=int(12 * 365)),
        weight_kg=4.2,
        color="calico",
        is_neutered=True,
        energy_level=EnergyLevel.LOW,
        vet=demo_vet(),
    )
    pet.tasks = [
        FeedingTask(
            title="Morning meal",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            fixed_time=time(7, 30),
            skippable=False,
            portion_grams=60,
        ),
        MedicationTask(
            title="Arthritis medication",
            category=TaskCategory.MEDICATION,
            duration_minutes=5,
            priority=Priority.HIGH,
            dosage="1 tablet",
            min_hours_between_doses=12,
        ),
        EnrichmentTask(
            title="Wand play",
            category=TaskCategory.ENRICHMENT,
            duration_minutes=10,
            priority=Priority.MEDIUM,
            preferred_time=TimeOfDay.EVENING,
            indoor=True,
        ),
        FeedingTask(
            title="Evening meal",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            fixed_time=time(19, 0),
            skippable=False,
            portion_grams=60,
        ),
        GroomingTask(
            title="Brush + check for mats",
            category=TaskCategory.GROOMING,
            duration_minutes=10,
            priority=Priority.LOW,
            recurrence=Recurrence.WEEKLY,
            weekdays={2},
        ),
    ]
    pet.medical = demo_medical_history()
    pet.bills = [
        Bill(
            id="bill-cat-1",
            description="Senior blood panel + arthritis consult",
            category=BillCategory.VET,
            amount=310.00,
            billed_on=today - timedelta(days=21),
            status=PaymentStatus.CLAIMED,
            amount_paid=310.00,
            paid_on=today - timedelta(days=21),
            provider="Bayside Animal Hospital",
            insurance_claimed=True,
            reimbursed_amount=180.00,
        ),
        Bill(
            description="Arthritis tablets (90 day supply)",
            category=BillCategory.MEDICATION,
            amount=64.00,
            billed_on=today - timedelta(days=45),
            status=PaymentStatus.UNPAID,
            provider="Bayside Pharmacy",
        ),
    ]
    return pet


def demo_vet() -> VetClinic:
    """Bayside Animal Hospital, with an emergency flag and phone number."""
    return VetClinic(
        name="Dr. Priya Rao",
        clinic_name="Bayside Animal Hospital",
        phone="+1 555 0177",
        email="care@baysidevet.example",
        address="12 Marine Parade, Bayside",
        is_emergency=True,
        hours="08:00-20:00",
        relationship="veterinarian",
    )


def demo_groomer() -> Groomer:
    """Happy Paws salon, linked from Biscuit's grooming sessions."""
    return Groomer(
        name="Sam Ortega",
        salon_name="Happy Paws",
        phone="+1 555 0190",
        typical_cost=95.00,
        relationship="groomer",
    )


def demo_emergency_contact() -> Contact:
    """A neighbour who can take the pets if the owner is away."""
    return Contact(
        name="Riley Chen",
        phone="+1 555 0142",
        email="riley@example.com",
        relationship="neighbour",
        notes="Has a spare key and knows Mochi's medication schedule.",
    )


def demo_medical_history() -> MedicalHistory:
    """A realistic history: one chronic condition, an allergy, shots, two visits."""
    today = date.today()
    return MedicalHistory(
        conditions=[
            Condition(
                name="Osteoarthritis (hips)",
                diagnosed_on=today - timedelta(days=400),
                status=ConditionStatus.CHRONIC,
                severity=Severity.MODERATE,
                treatment="Daily anti-inflammatory",
                notes="Monitor mobility; avoid high jumps.",
            ),
            Condition(
                name="Ear infection",
                diagnosed_on=today - timedelta(days=200),
                status=ConditionStatus.RESOLVED,
                severity=Severity.MILD,
                resolved_on=today - timedelta(days=186),
            ),
        ],
        allergies=[
            Allergy(
                substance="Chicken protein",
                reaction="Itching and ear inflammation",
                severity=Severity.SEVERE,
                noted_on=today - timedelta(days=500),
            )
        ],
        vaccinations=[
            Vaccination(
                name="FVRCP",
                given_on=today - timedelta(days=400),
                next_due_on=today - timedelta(days=35),
                clinic="Bayside Animal Hospital",
            )
        ],
        visits=[
            VetVisit(
                visit_date=today - timedelta(days=21),
                visit_type=VisitType.CHECKUP,
                clinic="Bayside Animal Hospital",
                vet_name="Dr. Rao",
                reason="Stiffness in hind legs",
                diagnosis="Arthritis flare-up",
                treatment="Increased anti-inflammatory dose",
                prescriptions=["Meloxicam 0.5mg"],
                weight_kg=4.2,
                follow_up_on=today + timedelta(days=7),
                bill_id="bill-cat-1",
            ),
            VetVisit(
                visit_date=today - timedelta(days=200),
                visit_type=VisitType.EMERGENCY,
                clinic="Bayside Animal Hospital",
                vet_name="Dr. Nwosu",
                reason="Head shaking, scratching at ear",
                diagnosis="Bacterial ear infection",
                treatment="Ear drops, 14 days",
                weight_kg=4.4,
            ),
        ],
        blood_type="A",
    )


def starter_tasks_for(pet: Pet) -> list:
    """Suggested task list for a new pet, based on its species and age."""
    if pet.species is Species.DOG:
        return [
            WalkTask(
                title="Morning walk",
                category=TaskCategory.WALK,
                duration_minutes=30,
                priority=Priority.HIGH,
                preferred_time=TimeOfDay.MORNING,
            ),
            FeedingTask(
                title="Breakfast",
                category=TaskCategory.FEEDING,
                duration_minutes=10,
                priority=Priority.HIGH,
                skippable=False,
            ),
            FeedingTask(
                title="Dinner",
                category=TaskCategory.FEEDING,
                duration_minutes=10,
                priority=Priority.HIGH,
                skippable=False,
            ),
        ]
    return [
        FeedingTask(
            title="Morning meal",
            category=TaskCategory.FEEDING,
            duration_minutes=10,
            priority=Priority.HIGH,
            skippable=False,
        ),
        EnrichmentTask(
            title="Play session",
            category=TaskCategory.ENRICHMENT,
            duration_minutes=10,
            priority=Priority.MEDIUM,
        ),
    ]
