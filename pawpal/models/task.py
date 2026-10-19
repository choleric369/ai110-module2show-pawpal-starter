"""CareTask and its subclasses: the things the scheduler places on a day.

The base class carries everything the scheduler needs; subclasses add
category-specific fields and override score() where the ranking should differ.
"""

from dataclasses import dataclass, field
from datetime import date, time
from uuid import uuid4

from pawpal.models.enums import Priority, Recurrence, TaskCategory, TimeOfDay
from pawpal.utils.serialization import (
    enum_value,
    iso_date,
    iso_time,
    parse_date,
    parse_enum,
    parse_time,
)
from pawpal.utils.validation import require_non_empty, require_positive_int

MAX_TASK_MINUTES = 480

# Multiplier applied to a task's base score, by subclass. See reasoning.txt.
CATEGORY_ICONS = {
    TaskCategory.WALK: "\U0001f6b6",
    TaskCategory.FEEDING: "\U0001f37d️",
    TaskCategory.MEDICATION: "\U0001f48a",
    TaskCategory.GROOMING: "\U0001f9fc",
    TaskCategory.ENRICHMENT: "\U0001f9e9",
    TaskCategory.TRAINING: "\U0001f393",
    TaskCategory.VET: "\U0001f3e5",
    TaskCategory.OTHER: "\U0001f43e",
}


def _new_id() -> str:
    """Short unique id so the UI can edit/delete a specific task row."""
    return uuid4().hex[:8]


@dataclass
class CareTask:
    """One unit of pet care: what to do, how long it takes, how badly it's needed."""

    title: str = ""
    category: TaskCategory = TaskCategory.OTHER
    duration_minutes: int = 15
    priority: Priority = Priority.MEDIUM
    recurrence: Recurrence = Recurrence.DAILY
    weekdays: set[int] = field(default_factory=set)
    due_date: date | None = None
    preferred_time: TimeOfDay = TimeOfDay.ANY
    fixed_time: time | None = None
    skippable: bool = True
    notes: str = ""
    is_completed: bool = False
    id: str = field(default_factory=_new_id)

    def validate(self) -> None:
        """Raise ValidationError if title is blank or duration is out of range."""
        self.title = require_non_empty(self.title, "Task title")
        self.duration_minutes = require_positive_int(
            self.duration_minutes, "Task duration", maximum=MAX_TASK_MINUTES
        )

    def score(self, weights: dict[str, float] | None = None) -> float:
        """Rank value for the scheduler; higher sorts earlier. Subclasses may override."""
        weights = weights or {}
        base = int(self.priority) * 100
        density = base / max(1, self.duration_minutes)
        return round(density * float(weights.get(self.category.value, 1.0)), 4)

    def is_due(self, day: date) -> bool:
        """True if this task's recurrence means it should appear on that date."""
        if self.recurrence is Recurrence.DAILY:
            return True
        if self.recurrence is Recurrence.WEEKDAYS:
            return day.weekday() < 5
        if self.recurrence is Recurrence.WEEKLY:
            wanted = self.weekdays or {0}
            return day.weekday() in wanted
        # ONCE: due on its date, or any day until done when no date was given.
        if self.is_completed:
            return False
        return self.due_date is None or self.due_date == day

    def is_anchored(self) -> bool:
        """True if fixed_time is set, meaning the scheduler must not move it."""
        return self.fixed_time is not None

    def mark_complete(self) -> None:
        """Flip is_completed so the progress bar and stats pick it up."""
        self.is_completed = True

    def reset(self) -> None:
        """Clear completion, used when rolling over to a new day."""
        self.is_completed = False

    def icon(self) -> str:
        """Emoji for this task's category, used in the plan table."""
        return CATEGORY_ICONS.get(self.category, CATEGORY_ICONS[TaskCategory.OTHER])

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict, including a 'type' key for from_dict.

        Subclass-only fields (distance_km, dosage, ...) are picked up
        automatically, so a new CareTask subclass needs no extra to_dict.
        """
        data = {
            "type": type(self).__name__,
            "id": self.id,
            "title": self.title,
            "category": enum_value(self.category),
            "duration_minutes": self.duration_minutes,
            "priority": int(self.priority),
            "recurrence": enum_value(self.recurrence),
            "weekdays": sorted(self.weekdays),
            "due_date": iso_date(self.due_date),
            "preferred_time": enum_value(self.preferred_time),
            "fixed_time": iso_time(self.fixed_time),
            "skippable": self.skippable,
            "notes": self.notes,
            "is_completed": self.is_completed,
        }
        for name in type(self).__dataclass_fields__:
            if name not in CareTask.__dataclass_fields__:
                data[name] = getattr(self, name)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CareTask":
        """Rebuild this exact class from a dict; see task_from_dict for dispatch."""
        data = dict(data or {})
        data.pop("type", None)
        base = {
            "id": data.get("id", _new_id()),
            "title": data.get("title", ""),
            "category": parse_enum(TaskCategory, data.get("category"), TaskCategory.OTHER),
            "duration_minutes": int(data.get("duration_minutes", 15)),
            "priority": parse_enum(Priority, data.get("priority"), Priority.MEDIUM),
            "recurrence": parse_enum(Recurrence, data.get("recurrence"), Recurrence.DAILY),
            "weekdays": set(data.get("weekdays", []) or []),
            "due_date": parse_date(data.get("due_date")),
            "preferred_time": parse_enum(TimeOfDay, data.get("preferred_time"), TimeOfDay.ANY),
            "fixed_time": parse_time(data.get("fixed_time")),
            "skippable": bool(data.get("skippable", True)),
            "notes": data.get("notes", ""),
            "is_completed": bool(data.get("is_completed", False)),
        }
        subclass_only = {
            k: v
            for k, v in data.items()
            if k in cls.__dataclass_fields__ and k not in CareTask.__dataclass_fields__
        }
        return cls(**base, **subclass_only)

    def __str__(self) -> str:
        """'Morning walk (30 min) [high]' — used in text exports and tests."""
        return f"{self.title} ({self.duration_minutes} min) [{self.priority.label}]"


@dataclass
class WalkTask(CareTask):
    """An outdoor walk; distance feeds exercise totals and weather can bump it."""

    distance_km: float = 0.0
    weather_sensitive: bool = True

    def score(self, weights: dict[str, float] | None = None) -> float:
        """Base score lifted 20%: missed exercise drives most behaviour problems."""
        return round(super().score(weights) * 1.2, 4)


@dataclass
class FeedingTask(CareTask):
    """A meal; these are usually anchored to a fixed_time and rarely skippable."""

    portion_grams: int = 0

    def score(self, weights: dict[str, float] | None = None) -> float:
        """Meals outrank same-priority tasks because missing one is worse."""
        return round(super().score(weights) * 1.5, 4)


@dataclass
class MedicationTask(CareTask):
    """A dose; never dropped for time and spaced by min_hours_between_doses."""

    dosage: str = ""
    min_hours_between_doses: int = 8
    skippable: bool = False

    def score(self, weights: dict[str, float] | None = None) -> float:
        """Always returns the top band so medication is placed before anything else."""
        return round(10_000 + super().score(weights), 4)

    def conflicts_with(self, other: "MedicationTask", gap_minutes: int) -> bool:
        """True if two doses of the same med land closer than the safe gap."""
        if self.title.strip().lower() != other.title.strip().lower():
            return False
        return gap_minutes < self.min_hours_between_doses * 60


@dataclass
class GroomingTask(CareTask):
    """Brushing, nails, bath; low urgency but tracked so it does not slip forever."""

    tool: str = ""


@dataclass
class EnrichmentTask(CareTask):
    """Play, puzzle feeders, training games; counts toward mental-stimulation needs."""

    indoor: bool = True


@dataclass
class VetAppointment(CareTask):
    """A real appointment; always anchored and acts as a fixed point in the day."""

    clinic: str = ""
    skippable: bool = False

    def is_anchored(self) -> bool:
        """Always True — the whole day is arranged around the appointment."""
        return True

    def score(self, weights: dict[str, float] | None = None) -> float:
        """Just below medication: an appointment outranks all routine care."""
        return round(5_000 + super().score(weights), 4)


# Maps the 'type' key written by to_dict() back to the class that wrote it.
TASK_TYPES: dict[str, type[CareTask]] = {
    "CareTask": CareTask,
    "WalkTask": WalkTask,
    "FeedingTask": FeedingTask,
    "MedicationTask": MedicationTask,
    "GroomingTask": GroomingTask,
    "EnrichmentTask": EnrichmentTask,
    "VetAppointment": VetAppointment,
}

# Which subclass the UI builds when the user picks a category.
CATEGORY_TO_TYPE: dict[TaskCategory, type[CareTask]] = {
    TaskCategory.WALK: WalkTask,
    TaskCategory.FEEDING: FeedingTask,
    TaskCategory.MEDICATION: MedicationTask,
    TaskCategory.GROOMING: GroomingTask,
    TaskCategory.ENRICHMENT: EnrichmentTask,
    TaskCategory.TRAINING: EnrichmentTask,
    TaskCategory.VET: VetAppointment,
    TaskCategory.OTHER: CareTask,
}


def task_from_dict(data: dict) -> CareTask:
    """Polymorphic loader: read data['type'] and build the right CareTask subclass."""
    target = TASK_TYPES.get((data or {}).get("type", "CareTask"), CareTask)
    return target.from_dict(data)


def make_task(category: TaskCategory, **kwargs) -> CareTask:
    """Factory used by the UI: pick the subclass that matches the chosen category."""
    target = CATEGORY_TO_TYPE.get(category, CareTask)
    kwargs.setdefault("category", category)
    allowed = {k: v for k, v in kwargs.items() if k in target.__dataclass_fields__}
    return target(**allowed)
