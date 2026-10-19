"""Turns scheduling decisions into sentences a pet owner would actually read.

Kept separate from Scheduler so wording can change without touching logic,
and so the explanation text itself can be unit-tested.
"""

from pawpal.models.plan import DailyPlan, ScheduledTask, SkippedTask
from pawpal.models.task import CareTask
from pawpal.utils.timeutils import format_duration, format_minutes

# Loud categories: dropping one of these is a real problem, not a nice-to-have.
CRITICAL_CATEGORIES = {"medication", "feeding", "vet"}


def explain_placement(item: ScheduledTask, rank: int, strategy_name: str) -> str:
    """Why this task sits at this time: priority, anchor, or preferred window."""
    task = item.task
    if task is None:
        return ""
    when = format_minutes(item.start_minute)
    if task.is_anchored():
        return f"Fixed appointment — pinned to {when}."
    reason = f"Ranked #{rank} by {strategy_name.replace('_', ' ')} ({task.priority.label} priority"
    reason += f", {format_duration(task.duration_minutes)})"
    if task.preferred_time.value != "any":
        reason += f"; placed at {when} inside your preferred {task.preferred_time.value}"
    else:
        reason += f"; earliest free slot was {when}"
    return reason + "."


def explain_skip(task: CareTask, reason_code: str, remaining_minutes: int) -> str:
    """Why a task was dropped, phrased concretely ('needs 30 min, 10 left')."""
    needs = format_duration(task.duration_minutes)
    messages = {
        "budget": f"needs {needs} but only {format_duration(max(0, remaining_minutes))} of your budget is left",
        "too_long": f"needs {needs}, which is longer than your whole available day",
        "no_slot": f"needs {needs} and there is no free gap left in the day",
        "window": f"could not fit inside your waking hours ({needs} required)",
        "not_due": "is not scheduled for this day",
        "med_gap": "would fall too close to another dose of the same medication",
        "completed": "is already marked complete",
    }
    return messages.get(reason_code, f"could not be scheduled ({reason_code})")


def explain_strategy(strategy_name: str) -> str:
    """One line on what the chosen strategy optimises and what it gives up."""
    from pawpal.scheduling.strategies import STRATEGIES

    for name, cls in STRATEGIES.items():
        if name.value == strategy_name:
            return cls.description
    return "Tasks were ordered by priority."


def explain_plan(plan: DailyPlan) -> str:
    """Full narrative: strategy, how time was spent, what was cut and why."""
    lines = [f"Strategy: {explain_strategy(plan.strategy_used)}"]
    if plan.is_empty():
        lines.append("Nothing could be scheduled today.")
    else:
        lines.append(
            f"Scheduled {len(plan.scheduled)} task(s) totalling "
            f"{format_duration(plan.total_minutes())}, running from "
            f"{format_minutes(plan.scheduled[0].start_minute)} to "
            f"{format_minutes(plan.scheduled[-1].end_minute)}."
        )
    if plan.skipped:
        lines.append(f"{len(plan.skipped)} task(s) did not fit:")
        lines += [f"  - {d.task.title} {d.reason}" for d in plan.skipped if d.task]
    for warning in plan.unmet_needs():
        lines.append(f"Warning: {warning}.")
    tradeoff = summarize_tradeoff(plan)
    if tradeoff:
        lines.append(tradeoff)
    return "\n".join(lines)


def summarize_tradeoff(plan: DailyPlan) -> str:
    """Name the main tradeoff this plan made — feeds section 2b of reflection.md."""
    if not plan.skipped or not plan.scheduled:
        return ""
    dropped = max(
        (d for d in plan.skipped if d.task), key=lambda d: int(d.task.priority), default=None
    )
    if dropped is None:
        return ""
    kept = len(plan.scheduled)
    return (
        f"Tradeoff: kept {kept} task(s) that fit the budget and deferred "
        f"'{dropped.task.title}' ({dropped.task.priority.label} priority)."
    )


def warnings_for(plan: DailyPlan) -> list[SkippedTask]:
    """Skipped items worth surfacing loudly (medication, feeding) vs. quietly."""
    return [
        drop
        for drop in plan.skipped
        if drop.task
        and (drop.task.category.value in CRITICAL_CATEGORIES or not drop.task.skippable)
    ]
