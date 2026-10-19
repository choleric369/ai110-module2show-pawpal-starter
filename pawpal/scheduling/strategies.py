"""Pluggable ranking strategies — the 'tradeoff' the reflection asks about.

Each strategy only decides ORDER. Placement, budget and conflicts are the
Scheduler's job, so swapping strategies can never break the time rules.
"""

from abc import ABC, abstractmethod

from pawpal.models.enums import StrategyName
from pawpal.models.task import CareTask


class SortStrategy(ABC):
    """Interface every ranking strategy implements; injected into Scheduler."""

    name: StrategyName
    description: str

    @abstractmethod
    def rank(self, tasks: list[CareTask]) -> list[CareTask]:
        """Return the tasks in the order the scheduler should try to place them."""

    def explain(self) -> str:
        """One sentence on what this strategy optimises, shown under the plan."""
        return self.description


class PriorityFirstStrategy(SortStrategy):
    """Highest priority first, ties broken by shorter duration. The safe default."""

    name = StrategyName.PRIORITY_FIRST
    description = (
        "Most important tasks first. Guarantees the essentials happen, but a single "
        "long high-priority task can crowd out several smaller ones."
    )

    def rank(self, tasks: list[CareTask]) -> list[CareTask]:
        """Sort by (priority desc, duration asc)."""
        return sorted(tasks, key=lambda t: (-int(t.priority), t.duration_minutes, t.title))


class ShortestFirstStrategy(SortStrategy):
    """Shortest tasks first — maximises how MANY tasks fit, not how important."""

    name = StrategyName.SHORTEST_FIRST
    description = (
        "Shortest tasks first. Fits the largest number of tasks into the day, at the "
        "risk of pushing out one long but important task."
    )

    def rank(self, tasks: list[CareTask]) -> list[CareTask]:
        """Sort by (duration asc, priority desc)."""
        return sorted(tasks, key=lambda t: (t.duration_minutes, -int(t.priority), t.title))


class WeightedScoreStrategy(SortStrategy):
    """Value density: priority per minute, so cheap high-value tasks win."""

    name = StrategyName.WEIGHTED_SCORE
    description = (
        "Ranks by value per minute, so quick high-priority tasks come first. A good "
        "middle ground, but it can defer a long task indefinitely."
    )

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Store optional per-category weights that nudge the score."""
        self.weights = weights or {}

    def rank(self, tasks: list[CareTask]) -> list[CareTask]:
        """Sort by CareTask.score() descending."""
        return sorted(tasks, key=lambda t: (-t.score(self.weights), t.title))


class BalancedStrategy(SortStrategy):
    """Round-robins across pets and categories so one pet can't eat the whole day."""

    name = StrategyName.BALANCED
    description = (
        "Interleaves categories after a priority pass, so no single kind of care "
        "takes over the day. Fairer coverage, slightly less optimal ordering."
    )

    def rank(self, tasks: list[CareTask]) -> list[CareTask]:
        """Interleave tasks from different pets/categories after a priority pass."""
        by_priority = sorted(tasks, key=lambda t: (-int(t.priority), t.duration_minutes))
        buckets: dict[str, list[CareTask]] = {}
        for task in by_priority:
            buckets.setdefault(task.category.value, []).append(task)
        ordered: list[CareTask] = []
        while any(buckets.values()):
            for key in sorted(buckets):
                if buckets[key]:
                    ordered.append(buckets[key].pop(0))
        return ordered


# Registry so the UI dropdown and JSON prefs can name a strategy by string.
STRATEGIES: dict[StrategyName, type[SortStrategy]] = {
    StrategyName.PRIORITY_FIRST: PriorityFirstStrategy,
    StrategyName.SHORTEST_FIRST: ShortestFirstStrategy,
    StrategyName.WEIGHTED_SCORE: WeightedScoreStrategy,
    StrategyName.BALANCED: BalancedStrategy,
}


def get_strategy(name: StrategyName, weights: dict[str, float] | None = None) -> SortStrategy:
    """Build a strategy instance from its enum name; defaults to PriorityFirst."""
    target = STRATEGIES.get(name, PriorityFirstStrategy)
    if target is WeightedScoreStrategy:
        return WeightedScoreStrategy(weights)
    return target()
