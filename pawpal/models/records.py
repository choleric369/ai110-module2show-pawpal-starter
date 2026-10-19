"""Historical records: health, hospital visits, grooming, and money.

Records are the PAST (what happened); CareTask is the FUTURE (what to do).
They connect through services/reminders.py, which turns a due record into a task.
Money lives in one place: a Bill on the pet, referenced by id from the record
that caused it, so a vet visit and its invoice never drift apart.
"""

from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

from pawpal.models.enums import (
    BillCategory,
    ConditionStatus,
    GroomingService,
    PaymentStatus,
    Severity,
    VisitType,
)
from pawpal.utils.serialization import (
    enum_value,
    format_money,
    iso_date,
    parse_date,
    parse_enum,
)
from pawpal.utils.validation import (
    ValidationError,
    require_non_empty,
    require_non_negative,
    require_positive_int,
)

# A bill is only "overdue" once this many days have passed since it was billed.
BILL_GRACE_DAYS = 30
SEVERITY_ORDER = {Severity.SEVERE: 0, Severity.MODERATE: 1, Severity.MILD: 2}


def _new_id() -> str:
    """Short unique id used to cross-reference records and their bills."""
    return uuid4().hex[:8]


@dataclass
class Bill:
    """One cost: what it was for, how much, and whether it's actually been paid."""

    description: str = ""
    category: BillCategory = BillCategory.OTHER
    amount: float = 0.0
    billed_on: date | None = None
    status: PaymentStatus = PaymentStatus.UNPAID
    paid_on: date | None = None
    amount_paid: float = 0.0
    provider: str = ""
    invoice_ref: str = ""
    insurance_claimed: bool = False
    reimbursed_amount: float = 0.0
    linked_record_id: str = ""
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError on a negative amount or paid-before-billed date."""
        self.description = require_non_empty(self.description, "Bill description")
        self.amount = require_non_negative(self.amount, "Bill amount")
        self.amount_paid = require_non_negative(self.amount_paid, "Amount paid")
        self.reimbursed_amount = require_non_negative(
            self.reimbursed_amount, "Reimbursed amount"
        )
        if self.paid_on and self.billed_on and self.paid_on < self.billed_on:
            raise ValidationError("A bill cannot be paid before it was issued.")

    def outstanding(self) -> float:
        """Amount still owed: amount minus what's been paid, floored at zero."""
        return max(0.0, round(self.amount - self.amount_paid, 2))

    def net_cost(self) -> float:
        """True cost to the owner after any insurance reimbursement."""
        return max(0.0, round(self.amount - self.reimbursed_amount, 2))

    def is_settled(self) -> bool:
        """True when nothing is outstanding, whatever the status label says."""
        return self.outstanding() <= 0.0

    def is_overdue(self, today: date) -> bool:
        """True if still unpaid more than the grace period after billed_on."""
        if self.is_settled() or self.billed_on is None:
            return False
        return (today - self.billed_on).days > BILL_GRACE_DAYS

    def mark_paid(self, on: date, amount: float | None = None) -> None:
        """Record a payment; a partial amount sets PARTIAL instead of PAID."""
        payment = self.amount if amount is None else require_non_negative(amount, "Payment")
        self.amount_paid = round(min(self.amount, self.amount_paid + payment), 2)
        self.paid_on = on
        self.status = PaymentStatus.PAID if self.is_settled() else PaymentStatus.PARTIAL

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (dates become ISO strings)."""
        return {
            "id": self.id,
            "description": self.description,
            "category": enum_value(self.category),
            "amount": self.amount,
            "billed_on": iso_date(self.billed_on),
            "status": enum_value(self.status),
            "paid_on": iso_date(self.paid_on),
            "amount_paid": self.amount_paid,
            "provider": self.provider,
            "invoice_ref": self.invoice_ref,
            "insurance_claimed": self.insurance_claimed,
            "reimbursed_amount": self.reimbursed_amount,
            "linked_record_id": self.linked_record_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Bill":
        """Rebuild a Bill from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            description=data.get("description", ""),
            category=parse_enum(BillCategory, data.get("category"), BillCategory.OTHER),
            amount=float(data.get("amount", 0.0)),
            billed_on=parse_date(data.get("billed_on")),
            status=parse_enum(PaymentStatus, data.get("status"), PaymentStatus.UNPAID),
            paid_on=parse_date(data.get("paid_on")),
            amount_paid=float(data.get("amount_paid", 0.0)),
            provider=data.get("provider", ""),
            invoice_ref=data.get("invoice_ref", ""),
            insurance_claimed=bool(data.get("insurance_claimed", False)),
            reimbursed_amount=float(data.get("reimbursed_amount", 0.0)),
            linked_record_id=data.get("linked_record_id", ""),
            notes=data.get("notes", ""),
        )

    def __str__(self) -> str:
        """'Dental cleaning — $240.00 (unpaid)' for the bills table."""
        return f"{self.description} — {format_money(self.amount)} ({self.status.value})"


@dataclass
class Condition:
    """A diagnosed condition, e.g. arthritis; chronic ones never leave the summary."""

    name: str = ""
    diagnosed_on: date | None = None
    status: ConditionStatus = ConditionStatus.ACTIVE
    severity: Severity = Severity.MILD
    treatment: str = ""
    resolved_on: date | None = None
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError on a blank name or resolution before diagnosis."""
        self.name = require_non_empty(self.name, "Condition name")
        if self.resolved_on and self.diagnosed_on and self.resolved_on < self.diagnosed_on:
            raise ValidationError("A condition cannot resolve before it was diagnosed.")

    def is_active(self) -> bool:
        """True for ACTIVE, CHRONIC and MONITORING — anything not resolved."""
        return self.status is not ConditionStatus.RESOLVED

    def duration_days(self, today: date) -> int:
        """How long the pet has had this, for the health timeline."""
        if self.diagnosed_on is None:
            return 0
        end = self.resolved_on or today
        return max(0, (end - self.diagnosed_on).days)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "name": self.name,
            "diagnosed_on": iso_date(self.diagnosed_on),
            "status": enum_value(self.status),
            "severity": enum_value(self.severity),
            "treatment": self.treatment,
            "resolved_on": iso_date(self.resolved_on),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Condition":
        """Rebuild a Condition from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", ""),
            diagnosed_on=parse_date(data.get("diagnosed_on")),
            status=parse_enum(ConditionStatus, data.get("status"), ConditionStatus.ACTIVE),
            severity=parse_enum(Severity, data.get("severity"), Severity.MILD),
            treatment=data.get("treatment", ""),
            resolved_on=parse_date(data.get("resolved_on")),
            notes=data.get("notes", ""),
        )


@dataclass
class Allergy:
    """Something the pet reacts to; severe ones are shown as a red banner."""

    substance: str = ""
    reaction: str = ""
    severity: Severity = Severity.MILD
    noted_on: date | None = None
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError if the substance is blank."""
        self.substance = require_non_empty(self.substance, "Allergy substance")

    def is_critical(self) -> bool:
        """True for SEVERE, which the UI surfaces above everything else."""
        return self.severity is Severity.SEVERE

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "substance": self.substance,
            "reaction": self.reaction,
            "severity": enum_value(self.severity),
            "noted_on": iso_date(self.noted_on),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Allergy":
        """Rebuild an Allergy from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            substance=data.get("substance", ""),
            reaction=data.get("reaction", ""),
            severity=parse_enum(Severity, data.get("severity"), Severity.MILD),
            noted_on=parse_date(data.get("noted_on")),
            notes=data.get("notes", ""),
        )


@dataclass
class Vaccination:
    """A shot given, plus when the next one is due so it can become a reminder."""

    name: str = ""
    given_on: date | None = None
    next_due_on: date | None = None
    clinic: str = ""
    lot_number: str = ""
    bill_id: str = ""
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError on a blank name or a booster before the shot."""
        self.name = require_non_empty(self.name, "Vaccine name")
        if self.next_due_on and self.given_on and self.next_due_on < self.given_on:
            raise ValidationError("A booster cannot be due before the shot was given.")

    def is_due(self, today: date, lookahead_days: int = 30) -> bool:
        """True if the booster falls within the lookahead window (or is overdue)."""
        days = self.days_until_due(today)
        return days is not None and days <= lookahead_days

    def is_overdue(self, today: date) -> bool:
        """True once next_due_on has passed with no newer record."""
        days = self.days_until_due(today)
        return days is not None and days < 0

    def days_until_due(self, today: date) -> int | None:
        """Days to the booster; negative when overdue, None when not scheduled."""
        if self.next_due_on is None:
            return None
        return (self.next_due_on - today).days

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "name": self.name,
            "given_on": iso_date(self.given_on),
            "next_due_on": iso_date(self.next_due_on),
            "clinic": self.clinic,
            "lot_number": self.lot_number,
            "bill_id": self.bill_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Vaccination":
        """Rebuild a Vaccination from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            name=data.get("name", ""),
            given_on=parse_date(data.get("given_on")),
            next_due_on=parse_date(data.get("next_due_on")),
            clinic=data.get("clinic", ""),
            lot_number=data.get("lot_number", ""),
            bill_id=data.get("bill_id", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class VetVisit:
    """One hospital/clinic visit: why they went, what was found, what it cost."""

    visit_date: date | None = None
    visit_type: VisitType = VisitType.CHECKUP
    clinic: str = ""
    vet_name: str = ""
    reason: str = ""
    diagnosis: str = ""
    treatment: str = ""
    prescriptions: list[str] = field(default_factory=list)
    weight_kg: float = 0.0
    follow_up_on: date | None = None
    bill_id: str = ""
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError on a missing date or a follow-up before the visit."""
        if self.visit_date is None:
            raise ValidationError("A vet visit needs a date.")
        if self.follow_up_on and self.follow_up_on < self.visit_date:
            raise ValidationError("A follow-up cannot be scheduled before the visit.")
        self.weight_kg = require_non_negative(self.weight_kg, "Weight")

    def has_follow_up(self) -> bool:
        """True if a return visit is booked, which reminders turns into a task."""
        return self.follow_up_on is not None

    def is_emergency(self) -> bool:
        """True for EMERGENCY or SURGERY; these headline the health timeline."""
        return self.visit_type in (VisitType.EMERGENCY, VisitType.SURGERY)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (dates become ISO strings)."""
        return {
            "id": self.id,
            "visit_date": iso_date(self.visit_date),
            "visit_type": enum_value(self.visit_type),
            "clinic": self.clinic,
            "vet_name": self.vet_name,
            "reason": self.reason,
            "diagnosis": self.diagnosis,
            "treatment": self.treatment,
            "prescriptions": list(self.prescriptions),
            "weight_kg": self.weight_kg,
            "follow_up_on": iso_date(self.follow_up_on),
            "bill_id": self.bill_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VetVisit":
        """Rebuild a VetVisit from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            visit_date=parse_date(data.get("visit_date")),
            visit_type=parse_enum(VisitType, data.get("visit_type"), VisitType.CHECKUP),
            clinic=data.get("clinic", ""),
            vet_name=data.get("vet_name", ""),
            reason=data.get("reason", ""),
            diagnosis=data.get("diagnosis", ""),
            treatment=data.get("treatment", ""),
            prescriptions=list(data.get("prescriptions", [])),
            weight_kg=float(data.get("weight_kg", 0.0)),
            follow_up_on=parse_date(data.get("follow_up_on")),
            bill_id=data.get("bill_id", ""),
            notes=data.get("notes", ""),
        )

    def __str__(self) -> str:
        """'2026-03-04 checkup at Bayside Vet — ear infection' for the timeline."""
        when = iso_date(self.visit_date) or "undated"
        detail = self.diagnosis or self.reason
        head = f"{when} {self.visit_type.value} at {self.clinic or 'unknown clinic'}"
        return f"{head} — {detail}" if detail else head


@dataclass
class GroomingSession:
    """One grooming appointment: what was done, by whom, and when it's due again."""

    session_date: date | None = None
    provider: str = ""
    groomer_id: str = ""
    services: list[GroomingService] = field(default_factory=list)
    duration_minutes: int = 60
    next_due_on: date | None = None
    bill_id: str = ""
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError on a missing date or an empty service list."""
        if self.session_date is None:
            raise ValidationError("A grooming session needs a date.")
        if not self.services:
            raise ValidationError("A grooming session needs at least one service.")
        self.duration_minutes = require_positive_int(
            self.duration_minutes, "Grooming duration", maximum=480
        )
        if self.next_due_on and self.next_due_on < self.session_date:
            raise ValidationError("The next session cannot be due before this one.")

    def service_labels(self) -> list[str]:
        """Human names of the services performed, for the session card."""
        return [service.value.replace("_", " ") for service in self.services]

    def is_due_again(self, today: date, lookahead_days: int = 14) -> bool:
        """True when next_due_on falls inside the lookahead window or has passed."""
        if self.next_due_on is None:
            return False
        return (self.next_due_on - today).days <= lookahead_days

    def days_since(self, today: date) -> int:
        """Days since this session, powering 'last groomed 47 days ago'."""
        if self.session_date is None:
            return 0
        return max(0, (today - self.session_date).days)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "session_date": iso_date(self.session_date),
            "provider": self.provider,
            "groomer_id": self.groomer_id,
            "services": [enum_value(s) for s in self.services],
            "duration_minutes": self.duration_minutes,
            "next_due_on": iso_date(self.next_due_on),
            "bill_id": self.bill_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroomingSession":
        """Rebuild a GroomingSession from JSON."""
        data = data or {}
        return cls(
            id=data.get("id", _new_id()),
            session_date=parse_date(data.get("session_date")),
            provider=data.get("provider", ""),
            groomer_id=data.get("groomer_id", ""),
            services=[
                parse_enum(GroomingService, s, GroomingService.OTHER)
                for s in data.get("services", [])
            ],
            duration_minutes=int(data.get("duration_minutes", 60)),
            next_due_on=parse_date(data.get("next_due_on")),
            bill_id=data.get("bill_id", ""),
            notes=data.get("notes", ""),
        )

    def __str__(self) -> str:
        """'2026-02-11 — bath, nail trim (Happy Paws)' for the grooming log."""
        when = iso_date(self.session_date) or "undated"
        services = ", ".join(self.service_labels()) or "grooming"
        return f"{when} — {services}" + (f" ({self.provider})" if self.provider else "")


@dataclass
class MedicalHistory:
    """Everything health-related for one pet, in one place the UI can render."""

    conditions: list[Condition] = field(default_factory=list)
    allergies: list[Allergy] = field(default_factory=list)
    vaccinations: list[Vaccination] = field(default_factory=list)
    visits: list[VetVisit] = field(default_factory=list)
    blood_type: str = ""
    notes: str = ""

    def add_condition(self, condition: Condition) -> None:
        """Validate and record a new diagnosis."""
        condition.validate()
        self.conditions.append(condition)

    def add_allergy(self, allergy: Allergy) -> None:
        """Record a new allergy."""
        allergy.validate()
        self.allergies.append(allergy)

    def add_vaccination(self, vaccination: Vaccination) -> None:
        """Record a shot, replacing an earlier record of the same vaccine name."""
        vaccination.validate()
        key = vaccination.name.strip().lower()
        self.vaccinations = [v for v in self.vaccinations if v.name.strip().lower() != key]
        self.vaccinations.append(vaccination)

    def add_visit(self, visit: VetVisit) -> None:
        """Record a hospital visit, keeping the list newest-first."""
        visit.validate()
        self.visits.append(visit)
        self.visits.sort(key=lambda v: v.visit_date or date.min, reverse=True)

    def remove(self, record_id: str) -> bool:
        """Delete any record by id across all four lists; False if not found."""
        for attr in ("conditions", "allergies", "vaccinations", "visits"):
            records = getattr(self, attr)
            remaining = [r for r in records if r.id != record_id]
            if len(remaining) != len(records):
                setattr(self, attr, remaining)
                return True
        return False

    def active_conditions(self) -> list[Condition]:
        """Unresolved conditions, severest first, for the health banner."""
        active = [c for c in self.conditions if c.is_active()]
        return sorted(active, key=lambda c: SEVERITY_ORDER.get(c.severity, 9))

    def critical_allergies(self) -> list[Allergy]:
        """Severe allergies that must be visible before any medication is given."""
        return [a for a in self.allergies if a.is_critical()]

    def due_vaccinations(self, today: date, lookahead_days: int = 30) -> list[Vaccination]:
        """Boosters due soon or already overdue."""
        due = [v for v in self.vaccinations if v.is_due(today, lookahead_days)]
        return sorted(due, key=lambda v: v.next_due_on or date.max)

    def upcoming_follow_ups(self, today: date) -> list[VetVisit]:
        """Visits with a future follow_up_on date, sorted soonest first."""
        pending = [v for v in self.visits if v.follow_up_on and v.follow_up_on >= today]
        return sorted(pending, key=lambda v: v.follow_up_on or date.max)

    def last_visit(self) -> VetVisit | None:
        """Most recent visit, or None if the pet has never been seen."""
        dated = [v for v in self.visits if v.visit_date]
        return max(dated, key=lambda v: v.visit_date) if dated else None

    def visits_in_range(self, start: date, end: date) -> list[VetVisit]:
        """Visits between two dates, for the year-in-review and cost reports."""
        return [v for v in self.visits if v.visit_date and start <= v.visit_date <= end]

    def weight_history(self) -> list[tuple[date, float]]:
        """(date, weight) pairs recorded at visits, for the weight trend chart."""
        points = [(v.visit_date, v.weight_kg) for v in self.visits if v.visit_date and v.weight_kg]
        return sorted(points)

    def is_empty(self) -> bool:
        """True when nothing has been recorded, so the UI shows an empty state."""
        return not (self.conditions or self.allergies or self.vaccinations or self.visits)

    def summary_line(self, today: date | None = None) -> str:
        """One-line health status, e.g. '2 active conditions · rabies due in 9 days'."""
        today = today or date.today()
        parts = []
        active = self.active_conditions()
        if active:
            parts.append(f"{len(active)} active condition{'s' if len(active) != 1 else ''}")
        critical = self.critical_allergies()
        if critical:
            parts.append(f"{len(critical)} severe allerg{'ies' if len(critical) != 1 else 'y'}")
        for vaccine in self.due_vaccinations(today):
            days = vaccine.days_until_due(today)
            if days is None:
                continue
            when = f"overdue by {abs(days)}d" if days < 0 else f"due in {days}d"
            parts.append(f"{vaccine.name} {when}")
            break
        return " · ".join(parts) if parts else "No health issues on file"

    def to_dict(self) -> dict:
        """Serialize every record list to a JSON-safe dict."""
        return {
            "conditions": [c.to_dict() for c in self.conditions],
            "allergies": [a.to_dict() for a in self.allergies],
            "vaccinations": [v.to_dict() for v in self.vaccinations],
            "visits": [v.to_dict() for v in self.visits],
            "blood_type": self.blood_type,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MedicalHistory":
        """Rebuild the full history from JSON."""
        data = data or {}
        return cls(
            conditions=[Condition.from_dict(c) for c in data.get("conditions", [])],
            allergies=[Allergy.from_dict(a) for a in data.get("allergies", [])],
            vaccinations=[Vaccination.from_dict(v) for v in data.get("vaccinations", [])],
            visits=[VetVisit.from_dict(v) for v in data.get("visits", [])],
            blood_type=data.get("blood_type", ""),
            notes=data.get("notes", ""),
        )
