"""Pet: identity, care tasks, health history, grooming log and costs.

The Pet is the hub — tasks are what's planned, records are what happened,
bills are what it cost. Everything else hangs off this one object.
"""

from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

from pawpal.models.contact import Groomer, VetClinic, contact_from_dict
from pawpal.models.enums import EnergyLevel, Sex, Species, TaskCategory
from pawpal.models.records import Bill, GroomingSession, MedicalHistory
from pawpal.models.task import CareTask, task_from_dict
from pawpal.utils.serialization import enum_value, iso_date, parse_date, parse_enum
from pawpal.utils.validation import (
    require_in_range,
    require_non_empty,
    require_non_negative,
)

# Baseline active minutes per day, before age and energy modifiers.
BASE_EXERCISE_MINUTES = {
    Species.DOG: 60,
    Species.CAT: 20,
    Species.RABBIT: 30,
    Species.BIRD: 15,
    Species.OTHER: 20,
}
ENERGY_MULTIPLIER = {EnergyLevel.LOW: 0.7, EnergyLevel.MEDIUM: 1.0, EnergyLevel.HIGH: 1.4}
SENIOR_AGE = {
    Species.DOG: 8.0,
    Species.CAT: 11.0,
    Species.RABBIT: 5.0,
    Species.BIRD: 10.0,
    Species.OTHER: 8.0,
}
YOUNG_AGE = {Species.DOG: 1.0, Species.CAT: 1.0}
SENIOR_FACTOR = 0.6
YOUNG_FACTOR = 0.8
# Categories that count toward a pet's daily activity target.
ACTIVE_CATEGORIES = {TaskCategory.WALK, TaskCategory.TRAINING, TaskCategory.ENRICHMENT}


@dataclass
class Pet:
    """A single animal: who it is, what it needs, and its full care record."""

    # --- identity ---
    name: str = ""
    species: Species = Species.DOG
    breed: str = ""
    sex: Sex = Sex.UNKNOWN
    date_of_birth: date | None = None
    age_years: float = 1.0
    weight_kg: float = 0.0
    color: str = ""
    microchip_id: str = ""
    is_neutered: bool = False
    photo_path: str = ""
    notes: str = ""

    # --- care planning ---
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    tasks: list[CareTask] = field(default_factory=list)

    # --- records ---
    medical: MedicalHistory = field(default_factory=MedicalHistory)
    grooming_sessions: list[GroomingSession] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)

    # --- contacts & cover ---
    vet: VetClinic | None = None
    groomer: Groomer | None = None
    insurance_provider: str = ""
    insurance_policy_no: str = ""

    id: str = field(default_factory=lambda: uuid4().hex[:8])

    # ------------------------------------------------------------------ identity
    def validate(self) -> None:
        """Raise ValidationError on a blank name or a negative age/weight."""
        self.name = require_non_empty(self.name, "Pet name")
        self.age_years = require_in_range(self.age_years, "Age", 0.0, 40.0)
        self.weight_kg = require_non_negative(self.weight_kg, "Weight")

    def age(self, today: date | None = None) -> float:
        """Age in years, computed from date_of_birth when set, else age_years."""
        if self.date_of_birth is None:
            return float(self.age_years)
        today = today or date.today()
        return max(0.0, round((today - self.date_of_birth).days / 365.25, 2))

    def age_label(self, today: date | None = None) -> str:
        """Human age for the profile header, e.g. '3y 4m' or '7 weeks'."""
        years = self.age(today)
        if years < 0.25:
            return f"{int(years * 52)} weeks"
        if years < 1:
            return f"{int(years * 12)} months"
        whole = int(years)
        months = int(round((years - whole) * 12))
        if months == 12:
            whole, months = whole + 1, 0
        return f"{whole}y" if months == 0 else f"{whole}y {months}m"

    def is_senior(self) -> bool:
        """True past the species' senior threshold; lowers the exercise target."""
        return self.age() >= SENIOR_AGE.get(self.species, 8.0)

    def is_puppy_or_kitten(self) -> bool:
        """True for young animals, which need more frequent short sessions."""
        return self.age() < YOUNG_AGE.get(self.species, 0.5)

    # ------------------------------------------------------------------ tasks
    def add_task(self, task: CareTask) -> None:
        """Validate then append a task to this pet's list."""
        task.validate()
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        """Delete a task by id; returns False if nothing matched."""
        remaining = [t for t in self.tasks if t.id != task_id]
        if len(remaining) == len(self.tasks):
            return False
        self.tasks = remaining
        return True

    def get_task(self, task_id: str) -> CareTask | None:
        """Look up one task by id, for the edit form."""
        return next((t for t in self.tasks if t.id == task_id), None)

    def tasks_by_category(self) -> dict:
        """Group this pet's tasks by TaskCategory for the grouped UI view."""
        grouped: dict[TaskCategory, list[CareTask]] = {}
        for task in self.tasks:
            grouped.setdefault(task.category, []).append(task)
        return grouped

    def daily_exercise_need(self) -> int:
        """Recommended active minutes per day from species, age and energy."""
        base = BASE_EXERCISE_MINUTES.get(self.species, 20)
        minutes = base * ENERGY_MULTIPLIER.get(self.energy_level, 1.0)
        if self.is_senior():
            minutes *= SENIOR_FACTOR
        elif self.is_puppy_or_kitten():
            minutes *= YOUNG_FACTOR
        return max(5, int(round(minutes / 5.0) * 5))

    # ------------------------------------------------------------------ grooming
    def add_grooming_session(self, session: GroomingSession) -> None:
        """Validate and log a grooming session, newest first."""
        session.validate()
        self.grooming_sessions.append(session)
        self.grooming_sessions.sort(key=lambda s: s.session_date or date.min, reverse=True)

    def remove_grooming_session(self, session_id: str) -> bool:
        """Delete a logged session by id; False if nothing matched."""
        remaining = [s for s in self.grooming_sessions if s.id != session_id]
        if len(remaining) == len(self.grooming_sessions):
            return False
        self.grooming_sessions = remaining
        return True

    def last_grooming(self) -> GroomingSession | None:
        """Most recent session, or None if this pet has never been groomed."""
        dated = [s for s in self.grooming_sessions if s.session_date]
        return max(dated, key=lambda s: s.session_date) if dated else None

    def grooming_due(self, today: date, lookahead_days: int = 14) -> bool:
        """True when the last session's next_due_on is near or past."""
        last = self.last_grooming()
        return bool(last and last.is_due_again(today, lookahead_days))

    def grooming_interval_days(self) -> int | None:
        """Average gap between past sessions, used to suggest the next due date."""
        dates = sorted(s.session_date for s in self.grooming_sessions if s.session_date)
        if len(dates) < 2:
            return None
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        return int(round(sum(gaps) / len(gaps)))

    # ------------------------------------------------------------------ money
    def add_bill(self, bill: Bill) -> None:
        """Validate and attach a cost to this pet."""
        bill.validate()
        self.bills.append(bill)

    def remove_bill(self, bill_id: str) -> bool:
        """Delete a bill by id; False if nothing matched."""
        remaining = [b for b in self.bills if b.id != bill_id]
        if len(remaining) == len(self.bills):
            return False
        self.bills = remaining
        return True

    def get_bill(self, bill_id: str) -> Bill | None:
        """Resolve the bill a visit or grooming session points at."""
        return next((b for b in self.bills if b.id == bill_id), None)

    def total_spent(self, start: date | None = None, end: date | None = None) -> float:
        """Net spend on this pet, optionally limited to a date range."""
        total = 0.0
        for bill in self.bills:
            if start and (bill.billed_on is None or bill.billed_on < start):
                continue
            if end and (bill.billed_on is None or bill.billed_on > end):
                continue
            total += bill.net_cost()
        return round(total, 2)

    def outstanding_total(self) -> float:
        """Sum still owed across this pet's unpaid and partial bills."""
        return round(sum(b.outstanding() for b in self.bills), 2)

    # ------------------------------------------------------------------ health
    def health_alerts(self, today: date) -> list[str]:
        """Warnings worth showing now: severe allergies, overdue shots, follow-ups."""
        alerts = []
        for allergy in self.medical.critical_allergies():
            alerts.append(f"Severe allergy: {allergy.substance} ({allergy.reaction})")
        for vaccine in self.medical.due_vaccinations(today):
            days = vaccine.days_until_due(today)
            if days is None:
                continue
            alerts.append(
                f"{vaccine.name} booster overdue by {abs(days)} days"
                if days < 0
                else f"{vaccine.name} booster due in {days} days"
            )
        for visit in self.medical.upcoming_follow_ups(today):
            days = (visit.follow_up_on - today).days
            when = "today" if days == 0 else f"in {days} days"
            alerts.append(f"Follow-up at {visit.clinic or 'the vet'} {when}")
        if self.grooming_due(today):
            alerts.append("Grooming is due")
        return alerts

    def needs_vet_attention(self, today: date) -> bool:
        """True if a follow-up or booster is due, driving the profile badge."""
        return bool(
            self.medical.due_vaccinations(today) or self.medical.upcoming_follow_ups(today)
        )

    # ------------------------------------------------------------------ io
    def to_dict(self) -> dict:
        """Serialize the pet with its tasks, history, grooming log and bills."""
        return {
            "id": self.id,
            "name": self.name,
            "species": enum_value(self.species),
            "breed": self.breed,
            "sex": enum_value(self.sex),
            "date_of_birth": iso_date(self.date_of_birth),
            "age_years": self.age_years,
            "weight_kg": self.weight_kg,
            "color": self.color,
            "microchip_id": self.microchip_id,
            "is_neutered": self.is_neutered,
            "photo_path": self.photo_path,
            "notes": self.notes,
            "energy_level": enum_value(self.energy_level),
            "tasks": [t.to_dict() for t in self.tasks],
            "medical": self.medical.to_dict(),
            "grooming_sessions": [s.to_dict() for s in self.grooming_sessions],
            "bills": [b.to_dict() for b in self.bills],
            "vet": self.vet.to_dict() if self.vet else None,
            "groomer": self.groomer.to_dict() if self.groomer else None,
            "insurance_provider": self.insurance_provider,
            "insurance_policy_no": self.insurance_policy_no,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pet":
        """Rebuild a Pet and every nested record from JSON."""
        data = data or {}
        vet = contact_from_dict(data.get("vet"))
        groomer = contact_from_dict(data.get("groomer"))
        return cls(
            id=data.get("id", uuid4().hex[:8]),
            name=data.get("name", ""),
            species=parse_enum(Species, data.get("species"), Species.OTHER),
            breed=data.get("breed", ""),
            sex=parse_enum(Sex, data.get("sex"), Sex.UNKNOWN),
            date_of_birth=parse_date(data.get("date_of_birth")),
            age_years=float(data.get("age_years", 1.0)),
            weight_kg=float(data.get("weight_kg", 0.0)),
            color=data.get("color", ""),
            microchip_id=data.get("microchip_id", ""),
            is_neutered=bool(data.get("is_neutered", False)),
            photo_path=data.get("photo_path", ""),
            notes=data.get("notes", ""),
            energy_level=parse_enum(EnergyLevel, data.get("energy_level"), EnergyLevel.MEDIUM),
            tasks=[task_from_dict(t) for t in data.get("tasks", [])],
            medical=MedicalHistory.from_dict(data.get("medical", {})),
            grooming_sessions=[
                GroomingSession.from_dict(s) for s in data.get("grooming_sessions", [])
            ],
            bills=[Bill.from_dict(b) for b in data.get("bills", [])],
            vet=vet if isinstance(vet, VetClinic) else None,
            groomer=groomer if isinstance(groomer, Groomer) else None,
            insurance_provider=data.get("insurance_provider", ""),
            insurance_policy_no=data.get("insurance_policy_no", ""),
        )

    def __str__(self) -> str:
        """'Mochi (cat, 3y)' — used in headings and the pet picker."""
        return f"{self.name} ({self.species.value}, {self.age_label()})"
