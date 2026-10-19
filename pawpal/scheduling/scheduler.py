"""Scheduler: turns a pool of tasks plus constraints into a DailyPlan.

build_plan() is the single public entry point; everything prefixed with _ is a
numbered step of that pipeline and is tested through build_plan.
"""

from datetime import date

from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.plan import DailyPlan, ScheduledTask
from pawpal.models.preferences import DayConstraints
from pawpal.models.task import CareTask
from pawpal.scheduling import conflicts, explain
from pawpal.scheduling.strategies import SortStrategy
from pawpal.utils.timeutils import window_for


class Scheduler:
    """Builds a day plan: filter due tasks, rank them, place them, explain them."""

    def __init__(self, constraints: DayConstraints, strategy: SortStrategy) -> None:
        """Store the day's limits and the injected ranking strategy."""
        self.constraints = constraints
        self.strategy = strategy

    def build_plan(
        self, owner: Owner, day: date, pet: Pet | None = None, include_reminders: bool = True
    ) -> DailyPlan:
        """Main entry: plan for one pet, or the whole household when pet is None."""
        plan = DailyPlan(day=day, strategy_used=self.strategy.name.value)
        pairs = self._collect(owner, pet, day, include_reminders)
        due, not_due = self._filter_due(pairs, day)
        for task, owner_pet in not_due:
            plan.add_skipped(task, owner_pet, explain.explain_skip(task, "not_due", 0))
        self._place(self._rank(due), plan)
        return self._finalize(plan)

    def _collect(
        self, owner: Owner, pet: Pet | None, day: date, include_reminders: bool
    ) -> list[tuple[CareTask, Pet]]:
        """Step 1 — gather saved tasks plus, optionally, record-driven reminders.

        Reminders come from services.reminders (due boosters, vet follow-ups,
        overdue grooming) so medical history actually reaches the day's plan.
        """
        from pawpal.services import reminders

        pets = [pet] if pet is not None else list(owner.pets)
        pairs: list[tuple[CareTask, Pet]] = []
        for current in pets:
            pairs += [(task, current) for task in current.tasks]
            if include_reminders:
                pairs += [(task, current) for task in reminders.all_reminders(current, day)]
        return pairs

    def _filter_due(
        self, pairs: list[tuple[CareTask, Pet]], day: date
    ) -> tuple[list[tuple[CareTask, Pet]], list[tuple[CareTask, Pet]]]:
        """Step 2 — split into (due today, not due) using each task's recurrence."""
        due = [(t, p) for t, p in pairs if t.is_due(day)]
        not_due = [(t, p) for t, p in pairs if not t.is_due(day)]
        return due, not_due

    def _rank(self, pairs: list[tuple[CareTask, Pet]]) -> list[tuple[CareTask, Pet]]:
        """Step 3 — delegate ordering to the strategy, keeping pet pairings intact."""
        owners = {id(task): pet for task, pet in pairs}
        ordered = self.strategy.rank([task for task, _ in pairs])
        return [(task, owners[id(task)]) for task in ordered]

    def _place(self, ranked: list[tuple[CareTask, Pet]], plan: DailyPlan) -> DailyPlan:
        """Step 4 — anchors first, then walk the clock placing flexible tasks."""
        pets = {id(task): pet for task, pet in ranked}
        anchored, flexible = conflicts.split_anchored([task for task, _ in ranked])

        placed: list[ScheduledTask] = []
        anchor_items, rejected = conflicts.place_anchors(anchored, self.constraints)
        for item in anchor_items:
            item.pet = pets[id(item.task)]
            placed.append(item)
            plan.add_scheduled(item)
        for task, note in rejected:
            plan.add_skipped(task, pets[id(task)], note)

        used = sum(item.duration() for item in placed)
        day_length = self.constraints.day_end - self.constraints.day_start
        rank_of = {id(task): i + 1 for i, (task, _) in enumerate(ranked)}

        for task in flexible:
            remaining = self.constraints.available_minutes - used
            if task.duration_minutes > day_length:
                plan.add_skipped(task, pets[id(task)], explain.explain_skip(task, "too_long", 0))
                continue
            if task.skippable and task.duration_minutes > remaining:
                plan.add_skipped(
                    task, pets[id(task)], explain.explain_skip(task, "budget", remaining)
                )
                continue
            start = self._find_start(task, placed)
            if start is None or not self._fits(task, start, used):
                plan.add_skipped(task, pets[id(task)], self._skip_reason(task, used))
                continue
            if not conflicts.respects_medication_gap(task, start, placed):
                plan.add_skipped(task, pets[id(task)], explain.explain_skip(task, "med_gap", 0))
                continue
            item = ScheduledTask(
                task=task,
                pet=pets[id(task)],
                start_minute=start,
                end_minute=start + task.duration_minutes,
            )
            item.reason = explain.explain_placement(
                item, rank_of[id(task)], self.strategy.name.value
            )
            placed.append(item)
            plan.add_scheduled(item)
            used += task.duration_minutes
        return plan

    def _find_start(self, task: CareTask, placed: list[ScheduledTask]) -> int | None:
        """Prefer the task's time-of-day window, then fall back to any free gap.

        Each task searches the whole day from the start, so a task ranked late
        can still take an early slot that nothing else claimed.
        """
        padding = self.constraints.break_minutes
        if task.preferred_time.value != "any":
            low, high = window_for(task.preferred_time)
            start = conflicts.first_free_slot(
                task.duration_minutes, placed, self.constraints, low, padding
            )
            if start is not None and start + task.duration_minutes <= high:
                return start
        return conflicts.first_free_slot(
            task.duration_minutes, placed, self.constraints, self.constraints.day_start, padding
        )

    def _fits(self, task: CareTask, start: int, used_minutes: int) -> bool:
        """True if the task fits the remaining budget, the day window and no block.

        Non-skippable tasks (medication, appointments) bypass the budget check:
        running late is acceptable, missing a dose is not.
        """
        if start + task.duration_minutes > self.constraints.day_end:
            return False
        if not task.skippable:
            return True
        return used_minutes + task.duration_minutes <= self.constraints.available_minutes

    def _reserve_break(self, item: ScheduledTask) -> int:
        """Minutes of rest to insert after a task before the next one may start."""
        return item.end_minute + self.constraints.break_minutes

    def _skip_reason(self, task: CareTask, used_minutes: int) -> str:
        """Pick the honest reason a task was dropped: budget, window or conflict."""
        remaining = self.constraints.available_minutes - used_minutes
        if task.duration_minutes > self.constraints.day_end - self.constraints.day_start:
            return explain.explain_skip(task, "too_long", remaining)
        if task.duration_minutes > remaining:
            return explain.explain_skip(task, "budget", remaining)
        return explain.explain_skip(task, "no_slot", remaining)

    def _finalize(self, plan: DailyPlan) -> DailyPlan:
        """Step 5 — sort slots, attach reasoning text and unmet-need warnings."""
        plan.scheduled.sort(key=lambda s: (s.start_minute, s.end_minute))
        for item in plan.scheduled:
            if not item.reason and item.task:
                item.reason = explain.explain_placement(item, 0, self.strategy.name.value)
        plan.notes = plan.unmet_needs()
        return plan

    def explain(self, plan: DailyPlan) -> str:
        """Human summary of the whole plan; thin wrapper over scheduling.explain."""
        return explain.explain_plan(plan)
