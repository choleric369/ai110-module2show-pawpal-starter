"""Bills and the spending rollups built on them."""

from datetime import timedelta

import pytest

from pawpal.models.enums import BillCategory, PaymentStatus
from pawpal.models.records import Bill
from pawpal.services import expenses
from pawpal.utils.validation import ValidationError


def test_negative_amount_is_rejected():
    """A Bill with a negative amount fails validate()."""
    with pytest.raises(ValidationError):
        Bill(description="Vet", amount=-10.0).validate()


def test_blank_description_is_rejected():
    """Every cost needs a label."""
    with pytest.raises(ValidationError):
        Bill(description="", amount=10.0).validate()


def test_outstanding_is_amount_minus_paid():
    """A $200 bill with $50 paid leaves $150 outstanding."""
    assert Bill(description="X", amount=200.0, amount_paid=50.0).outstanding() == 150.0


def test_outstanding_never_goes_negative():
    """Overpaying floors outstanding at zero, it does not go negative."""
    assert Bill(description="X", amount=100.0, amount_paid=150.0).outstanding() == 0.0


def test_partial_payment_sets_partial_status(today):
    """mark_paid() with less than the full amount sets PARTIAL, not PAID."""
    bill = Bill(description="X", amount=200.0, billed_on=today)
    bill.mark_paid(today, 50.0)
    assert bill.status is PaymentStatus.PARTIAL
    assert bill.outstanding() == 150.0


def test_full_payment_sets_paid_status(today):
    """Paying it all marks the bill settled."""
    bill = Bill(description="X", amount=200.0, billed_on=today)
    bill.mark_paid(today)
    assert bill.status is PaymentStatus.PAID
    assert bill.is_settled()


def test_net_cost_subtracts_reimbursement():
    """A $300 bill reimbursed $200 has a net cost of $100."""
    bill = Bill(description="Surgery", amount=300.0, reimbursed_amount=200.0)
    assert bill.net_cost() == 100.0


def test_paid_before_billed_is_rejected(today):
    """A payment date earlier than the invoice date is a data error."""
    bill = Bill(description="X", amount=10.0, billed_on=today, paid_on=today - timedelta(days=1))
    with pytest.raises(ValidationError):
        bill.validate()


def test_overdue_only_after_grace_period(today):
    """An unpaid bill inside the grace window is not yet overdue."""
    fresh = Bill(description="X", amount=10.0, billed_on=today - timedelta(days=5))
    stale = Bill(description="Y", amount=10.0, billed_on=today - timedelta(days=45))
    assert not fresh.is_overdue(today)
    assert stale.is_overdue(today)


def test_paid_bill_is_never_overdue(today):
    """A settled bill is excluded regardless of age."""
    bill = Bill(
        description="X",
        amount=10.0,
        amount_paid=10.0,
        billed_on=today - timedelta(days=400),
    )
    assert not bill.is_overdue(today)


def test_spend_by_category_groups_correctly(bills):
    """Vet and grooming bills land in separate buckets with correct totals."""
    totals = expenses.spend_by_category(bills)
    assert totals[BillCategory.VET] == 250.0  # 150 + (300 - 200 reimbursed)
    assert totals[BillCategory.GROOMING] == 90.0


def test_spend_by_month_is_chronological(bills):
    """Keys come back oldest-first as 'YYYY-MM'."""
    months = list(expenses.spend_by_month(bills))
    assert months == sorted(months)


def test_spend_by_pet_splits_the_household(owner_with_records):
    """Each pet's bills are reported under its own name."""
    per_pet = expenses.spend_by_pet(owner_with_records)
    assert per_pet["Biscuit"] == 340.0


def test_date_range_filter_excludes_outside_bills(bills, today):
    """A bill before the start date is left out of the range total."""
    recent = expenses.total_spend(bills, today - timedelta(days=10), today)
    assert recent == 100.0


def test_total_spend_of_empty_list_is_zero():
    """No bills means 0.0, not a crash."""
    assert expenses.total_spend([]) == 0.0


def test_outstanding_bills_sorted_largest_first(owner_with_records):
    """The biggest debt is listed first."""
    unpaid = expenses.outstanding_bills(owner_with_records)
    assert [b.description for b in unpaid] == ["Full groom"]


def test_overdue_bills_only_lists_stale_ones(owner_with_records, today):
    """A 45-day-old unpaid grooming bill is overdue."""
    overdue = expenses.overdue_bills(owner_with_records, today)
    assert [b.description for b in overdue] == ["Full groom"]


def test_insurance_summary_totals(bills):
    """Claimed, reimbursed and out-of-pocket are reported separately."""
    summary = expenses.insurance_summary(bills)
    assert summary["claimed"] == 300.0
    assert summary["reimbursed"] == 200.0
    assert summary["out_of_pocket"] == 340.0


def test_cost_of_visit_resolves_the_linked_bill(pet_with_records):
    """A visit's bill_id resolves to that bill's net cost."""
    visit = pet_with_records.medical.visits[0]
    visit.bill_id = "b-surgery"
    assert expenses.cost_of_visit(pet_with_records, visit.id) == 100.0


def test_cost_of_visit_without_a_bill_is_zero(pet_with_records):
    """An unbilled visit costs nothing, it does not raise."""
    visit = pet_with_records.medical.visits[1]
    assert expenses.cost_of_visit(pet_with_records, visit.id) == 0.0


def test_grooming_spend_only_counts_grooming(pet_with_records):
    """Vet bills are excluded from the grooming total."""
    assert expenses.grooming_spend(pet_with_records) == 90.0


def test_monthly_average_of_empty_list_is_zero():
    """No bills means no average, not a division error."""
    assert expenses.monthly_average([]) == 0.0


def test_projected_annual_scales_the_run_rate(today):
    """Spend so far this year is extrapolated across 365 days."""
    bill = Bill(description="X", amount=100.0, billed_on=today.replace(month=1, day=1))
    assert expenses.projected_annual([bill], today) > 100.0


def test_outstanding_total_rolls_up_the_household(owner_with_records):
    """Owner-level outstanding matches the sum of the pets'."""
    assert owner_with_records.outstanding_total() == 90.0
