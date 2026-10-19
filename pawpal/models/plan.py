"""The scheduler's output: what got placed, what didn't, and why.

DailyPlan is deliberately dumb — it stores decisions and renders them.
All the deciding happens in pawpal.scheduling.
"""

from dataclasses import dataclass, field
from datetime import date

from pawpal.models.pet import ACTIVE_CATEGORIES, Pet
from pawpal.models.task import CareTask
from pawpal.utils.serialization import iso_date
from pawpal.utils.timeutils import format_minutes, format_range


@dataclass
class ScheduledTask:
    """One task placed at a real time slot, with the reason it landed there."""

    task: CareTask | None = None
    pet: Pet | None = None
    start_minute: int = 0
    end_minute: int = 0
    reason: str = ""

    def time_label(self) -> str:
        """'08:00-08:30' for the plan table."""
        return format_range(self.start_minute, self.end_minute)

    def duration(self) -> int:
        """Placed length in minutes; normally equals the task's duration."""
        return max(0, self.end_minute - self.start_minute)

    def to_dict(self) -> dict:
        """Serialize for history/export; stores the task id, not the whole task."""
        return {
            "task_id": self.task.id if self.task else "",
            "title": self.task.title if self.task else "",
            "category": self.task.category.value if self.task else "",
            "pet_id": self.pet.id if self.pet else "",
            "pet_name": self.pet.name if self.pet else "",
            "start_minute": self.start_minute,
            "end_minute": self.end_minute,
            "is_completed": bool(self.task and self.task.is_completed),
            "reason": self.reason,
        }


@dataclass
class SkippedTask:
    """A task that did not make the cut, paired with a human-readable reason."""

    task: CareTask | None = None
    pet: Pet | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        """Serialize for the 'what got dropped' section of an exported plan."""
        return {
            "task_id": self.task.id if self.task else "",
            "title": self.task.title if self.task else "",
            "category": self.task.category.value if self.task else "",
            "pet_id": self.pet.id if self.pet else "",
            "pet_name": self.pet.name if self.pet else "",
            "reason": self.reason,
        }


@dataclass
class DailyPlan:
    """A finished day: ordered slots, dropped tasks, and summary metrics."""

    day: date | None = None
    scheduled: list[ScheduledTask] = field(default_factory=list)
    skipped: list[SkippedTask] = field(default_factory=list)
    strategy_used: str = ""
    notes: list[str] = field(default_factory=list)

    def add_scheduled(self, item: ScheduledTask) -> None:
        """Append a placed task, keeping the list sorted by start time."""
        self.scheduled.append(item)
        self.scheduled.sort(key=lambda s: (s.start_minute, s.end_minute))

    def add_skipped(self, task: CareTask, pet: Pet, reason: str) -> None:
        """Record a dropped task plus why, so the UI can always explain itself."""
        self.skipped.append(SkippedTask(task=task, pet=pet, reason=reason))

    def total_minutes(self) -> int:
        """Sum of scheduled durations, shown against the owner's budget."""
        return sum(item.duration() for item in self.scheduled)

    def utilization(self, budget_minutes: int) -> float:
        """Fraction of the available budget actually used, 0.0-1.0."""
        if budget_minutes <= 0:
            return 0.0
        return round(min(1.0, self.total_minutes() / budget_minutes), 4)

    def completion_rate(self) -> float:
        """Share of scheduled tasks already marked complete, for the progress bar."""
        if not self.scheduled:
            return 0.0
        done = sum(1 for s in self.scheduled if s.task and s.task.is_completed)
        return round(done / len(self.scheduled), 4)

    def minutes_for_pet(self, pet_id: str) -> int:
        """Scheduled minutes for one pet, used by the unmet-needs warning."""
        return sum(s.duration() for s in self.scheduled if s.pet and s.pet.id == pet_id)

    def active_minutes_for_pet(self, pet_id: str) -> int:
        """Scheduled minutes that count as exercise (walks, training, enrichment)."""
        return sum(
            s.duration()
            for s in self.scheduled
            if s.pet and s.pet.id == pet_id and s.task and s.task.category in ACTIVE_CATEGORIES
        )

    def pets(self) -> list[Pet]:
        """Every distinct pet appearing in this plan, scheduled or skipped."""
        seen: dict[str, Pet] = {}
        for item in [*self.scheduled, *self.skipped]:
            if item.pet and item.pet.id not in seen:
                seen[item.pet.id] = item.pet
        return list(seen.values())

    def unmet_needs(self) -> list[str]:
        """Warnings like 'Mochi needs 60 active min, only 25 scheduled'."""
        warnings = []
        for pet in self.pets():
            needed = pet.daily_exercise_need()
            got = self.active_minutes_for_pet(pet.id)
            if got < needed:
                warnings.append(
                    f"{pet.name} needs {needed} active min/day, only {got} scheduled"
                )
        return warnings

    def is_empty(self) -> bool:
        """True when nothing was scheduled, so the UI shows an empty state."""
        return not self.scheduled

    def to_text(self) -> str:
        """Plain-text plan — this is what gets pasted into the README sample output."""
        header = f"Daily plan for {self._pet_label()}"
        if self.day:
            header += f" — {self.day.isoformat()}"
        lines = [header, "=" * len(header)]
        if self.is_empty():
            lines.append("  (nothing scheduled)")
        for item in self.scheduled:
            task = item.task
            lines.append(
                f"  {format_minutes(item.start_minute)} — {task.title}"
                f" ({item.duration()} min) [priority: {task.priority.label}]"
            )
        lines.append("")
        lines.append(f"Total: {self.total_minutes()} min across {len(self.scheduled)} tasks")
        if self.skipped:
            lines.append("")
            lines.append("Skipped:")
            for drop in self.skipped:
                lines.append(f"  - {drop.task.title}: {drop.reason}")
        for warning in self.unmet_needs():
            lines.append(f"  ! {warning}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Markdown table version for copy-to-clipboard / download."""
        lines = [
            f"### Daily plan — {self.day.isoformat() if self.day else 'today'}",
            "",
            "| Time | Pet | Task | Duration | Priority |",
            "|------|-----|------|----------|----------|",
        ]
        for item in self.scheduled:
            task = item.task
            pet_name = item.pet.name if item.pet else ""
            lines.append(
                f"| {item.time_label()} | {pet_name} | {task.icon()} {task.title} "
                f"| {item.duration()} min | {task.priority.label} |"
            )
        if self.skipped:
            lines += ["", "**Skipped:**"]
            lines += [f"- {d.task.title} — {d.reason}" for d in self.skipped]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize the plan so history (C2) can store past days as JSON."""
        return {
            "day": iso_date(self.day),
            "strategy_used": self.strategy_used,
            "scheduled": [s.to_dict() for s in self.scheduled],
            "skipped": [s.to_dict() for s in self.skipped],
            "total_minutes": self.total_minutes(),
            "completion_rate": self.completion_rate(),
            "notes": list(self.notes),
        }

    def _pet_label(self) -> str:
        """'Biscuit (dog)' for one pet, or 'the household' when several appear."""
        pets = self.pets()
        if len(pets) == 1:
            pet = pets[0]
            return f"{pet.name} ({pet.breed or pet.species.value})"
        return "the household"
