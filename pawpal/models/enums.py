"""Fixed vocabularies shared across the app.

These are filled in (not stubs) because every other module imports these names.
"""

from enum import Enum, IntEnum


class Priority(IntEnum):
    """How badly a task needs to happen today; higher int wins when ranking."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_label(cls, label: str) -> "Priority":
        """Turn a UI string like 'high' into a Priority member."""
        try:
            return cls[str(label).strip().upper()]
        except KeyError:
            raise ValueError(f"Unknown priority: {label!r}") from None

    @property
    def label(self) -> str:
        """Lowercase display name used by the Streamlit widgets."""
        return self.name.lower()


class Species(str, Enum):
    """Pet species; drives the default care needs in Pet.daily_exercise_need()."""

    DOG = "dog"
    CAT = "cat"
    RABBIT = "rabbit"
    BIRD = "bird"
    OTHER = "other"


class TaskCategory(str, Enum):
    """What kind of care a task is; used for icons, grouping and balance rules."""

    WALK = "walk"
    FEEDING = "feeding"
    MEDICATION = "medication"
    GROOMING = "grooming"
    ENRICHMENT = "enrichment"
    TRAINING = "training"
    VET = "vet"
    OTHER = "other"


class Recurrence(str, Enum):
    """How often a task repeats; CareTask.is_due() reads this to filter a day."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    WEEKDAYS = "weekdays"


class TimeOfDay(str, Enum):
    """Soft placement hint; the scheduler prefers but does not guarantee it."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    ANY = "any"


class EnergyLevel(str, Enum):
    """Pet energy, used to scale exercise needs and pick high-intensity slots."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyName(str, Enum):
    """Selectable scheduling strategies, surfaced as a dropdown in the UI."""

    PRIORITY_FIRST = "priority_first"
    SHORTEST_FIRST = "shortest_first"
    WEIGHTED_SCORE = "weighted_score"
    BALANCED = "balanced"


class Sex(str, Enum):
    """Pet sex; shown on the profile and relevant to some health records."""

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class VisitType(str, Enum):
    """What a hospital/clinic visit was for; drives icons and cost grouping."""

    CHECKUP = "checkup"
    VACCINATION = "vaccination"
    EMERGENCY = "emergency"
    SURGERY = "surgery"
    DENTAL = "dental"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class ConditionStatus(str, Enum):
    """Where a diagnosed condition stands today."""

    ACTIVE = "active"
    CHRONIC = "chronic"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class Severity(str, Enum):
    """Severity shared by conditions and allergies; orders the health summary."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class GroomingService(str, Enum):
    """Individual services performed in one grooming session."""

    BATH = "bath"
    HAIRCUT = "haircut"
    NAIL_TRIM = "nail_trim"
    EAR_CLEANING = "ear_cleaning"
    TEETH_BRUSHING = "teeth_brushing"
    DE_SHEDDING = "de_shedding"
    FLEA_TREATMENT = "flea_treatment"
    OTHER = "other"


class BillCategory(str, Enum):
    """What a cost was for; the grouping key for every spending breakdown."""

    VET = "vet"
    MEDICATION = "medication"
    GROOMING = "grooming"
    FOOD = "food"
    SUPPLIES = "supplies"
    INSURANCE = "insurance"
    TRAINING = "training"
    BOARDING = "boarding"
    OTHER = "other"


class PaymentStatus(str, Enum):
    """Whether a bill is settled; UNPAID bills surface as outstanding."""

    PAID = "paid"
    UNPAID = "unpaid"
    PARTIAL = "partial"
    CLAIMED = "claimed"
    REIMBURSED = "reimbursed"
