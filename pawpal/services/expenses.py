"""Money rollups over Bill records. Read-only: never mutates a bill.

Every function here uses Bill.net_cost() (post-insurance) unless the name says
otherwise, so 'spend' always means what the owner actually paid.
"""

from datetime import date

from pawpal.models.enums import BillCategory
from pawpal.models.owner import Owner
from pawpal.models.pet import Pet
from pawpal.models.records import Bill


def _in_range(bill: Bill, start: date | None, end: date | None) -> bool:
    """True if the bill's date falls inside an optional window."""
    if start is None and end is None:
        return True
    if bill.billed_on is None:
        return False
    if start and bill.billed_on < start:
        return False
    if end and bill.billed_on > end:
        return False
    return True


def total_spend(bills: list[Bill], start: date | None = None, end: date | None = None) -> float:
    """Net total across the bills, optionally limited to a date range."""
    return round(sum(b.net_cost() for b in bills if _in_range(b, start, end)), 2)


def spend_by_category(bills: list[Bill]) -> dict[BillCategory, float]:
    """Spend grouped by category — vet vs grooming vs food, for the pie chart."""
    totals: dict[BillCategory, float] = {}
    for bill in bills:
        totals[bill.category] = round(totals.get(bill.category, 0.0) + bill.net_cost(), 2)
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def spend_by_month(bills: list[Bill]) -> dict[str, float]:
    """{'2026-03': 184.50, ...} ordered oldest first, for the trend chart."""
    totals: dict[str, float] = {}
    for bill in bills:
        if bill.billed_on is None:
            continue
        key = bill.billed_on.strftime("%Y-%m")
        totals[key] = round(totals.get(key, 0.0) + bill.net_cost(), 2)
    return dict(sorted(totals.items()))


def spend_by_pet(
    owner: Owner, start: date | None = None, end: date | None = None
) -> dict[str, float]:
    """Net spend per pet name, so the owner can see which pet costs what."""
    return {pet.name: pet.total_spent(start, end) for pet in owner.pets}


def outstanding_bills(owner: Owner) -> list[Bill]:
    """Unpaid and partial bills across the household, largest first."""
    unpaid = [b for b in owner.all_bills() if not b.is_settled()]
    return sorted(unpaid, key=lambda b: -b.outstanding())


def overdue_bills(owner: Owner, today: date) -> list[Bill]:
    """Bills past the grace period, which the dashboard flags in red."""
    return sorted(
        (b for b in owner.all_bills() if b.is_overdue(today)),
        key=lambda b: b.billed_on or today,
    )


def monthly_average(bills: list[Bill], months: int = 6) -> float:
    """Mean monthly spend over the trailing window, for budget context."""
    by_month = spend_by_month(bills)
    if not by_month:
        return 0.0
    recent = list(by_month.values())[-months:]
    return round(sum(recent) / len(recent), 2)


def projected_annual(bills: list[Bill], today: date) -> float:
    """Simple year-end projection from the run rate so far."""
    start_of_year = date(today.year, 1, 1)
    so_far = total_spend(bills, start_of_year, today)
    days_elapsed = max(1, (today - start_of_year).days + 1)
    return round(so_far / days_elapsed * 365, 2)


def insurance_summary(bills: list[Bill]) -> dict[str, float]:
    """Claimed vs reimbursed vs still-out-of-pocket totals."""
    claimed = sum(b.amount for b in bills if b.insurance_claimed)
    reimbursed = sum(b.reimbursed_amount for b in bills)
    return {
        "claimed": round(claimed, 2),
        "reimbursed": round(reimbursed, 2),
        "out_of_pocket": round(sum(b.net_cost() for b in bills), 2),
    }


def cost_of_visit(pet: Pet, visit_id: str) -> float:
    """Net cost of one vet visit by resolving its linked bill."""
    visit = next((v for v in pet.medical.visits if v.id == visit_id), None)
    if visit is None or not visit.bill_id:
        return 0.0
    bill = pet.get_bill(visit.bill_id)
    return bill.net_cost() if bill else 0.0


def grooming_spend(pet: Pet, start: date | None = None, end: date | None = None) -> float:
    """What grooming has cost for one pet, to compare against DIY."""
    bills = [b for b in pet.bills if b.category is BillCategory.GROOMING]
    return total_spend(bills, start, end)
