"""Medical history, vet visits and grooming sessions."""

from datetime import timedelta

import pytest

from pawpal.models.enums import ConditionStatus, GroomingService, Severity, VisitType
from pawpal.models.records import (
    Allergy,
    Condition,
    GroomingSession,
    MedicalHistory,
    Vaccination,
    VetVisit,
)
from pawpal.utils.validation import ValidationError


# --- conditions & allergies ---
def test_active_conditions_excludes_resolved(medical_history):
    """A RESOLVED condition drops out of active_conditions()."""
    names = [c.name for c in medical_history.active_conditions()]
    assert "Arthritis" in names
    assert "Ear infection" not in names


def test_chronic_condition_stays_active(today):
    """CHRONIC counts as active even years after diagnosis."""
    condition = Condition(
        name="Arthritis",
        diagnosed_on=today - timedelta(days=2000),
        status=ConditionStatus.CHRONIC,
    )
    assert condition.is_active()


def test_active_conditions_sorted_by_severity(today):
    """The severest condition is listed first for the banner."""
    history = MedicalHistory(
        conditions=[
            Condition(name="Mild thing", severity=Severity.MILD),
            Condition(name="Bad thing", severity=Severity.SEVERE),
        ]
    )
    assert history.active_conditions()[0].name == "Bad thing"


def test_condition_cannot_resolve_before_diagnosis(today):
    """A resolved_on earlier than diagnosed_on is rejected."""
    condition = Condition(
        name="X", diagnosed_on=today, resolved_on=today - timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        condition.validate()


def test_critical_allergies_only_returns_severe(medical_history):
    """A mild allergy is not surfaced as critical."""
    assert [a.substance for a in medical_history.critical_allergies()] == ["Chicken"]


def test_allergy_requires_a_substance():
    """A blank substance fails validation."""
    with pytest.raises(ValidationError):
        Allergy(substance="").validate()


# --- vaccinations ---
def test_vaccination_due_inside_lookahead(today):
    """A booster due in 10 days is due with a 30-day lookahead."""
    vaccine = Vaccination(name="Rabies", next_due_on=today + timedelta(days=10))
    assert vaccine.is_due(today, lookahead_days=30)


def test_vaccination_not_due_outside_lookahead(today):
    """A booster due in 90 days is not yet due."""
    vaccine = Vaccination(name="Rabies", next_due_on=today + timedelta(days=90))
    assert not vaccine.is_due(today, lookahead_days=30)


def test_overdue_vaccination_reports_negative_days(today):
    """days_until_due() goes negative once the date has passed."""
    vaccine = Vaccination(name="Rabies", next_due_on=today - timedelta(days=5))
    assert vaccine.days_until_due(today) == -5
    assert vaccine.is_overdue(today)


def test_vaccination_without_due_date_is_never_due(today):
    """No next_due_on means nothing to remind about."""
    vaccine = Vaccination(name="Rabies", given_on=today)
    assert vaccine.days_until_due(today) is None
    assert not vaccine.is_due(today)


def test_adding_same_vaccine_supersedes_the_old_record(today):
    """Logging a new rabies shot replaces the previous rabies entry."""
    history = MedicalHistory()
    history.add_vaccination(Vaccination(name="Rabies", given_on=today - timedelta(days=365)))
    history.add_vaccination(Vaccination(name="Rabies", given_on=today))
    assert len(history.vaccinations) == 1
    assert history.vaccinations[0].given_on == today


def test_booster_before_shot_is_rejected(today):
    """A next_due_on earlier than given_on is a data-entry error."""
    vaccine = Vaccination(
        name="Rabies", given_on=today, next_due_on=today - timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        vaccine.validate()


# --- vet visits ---
def test_visit_requires_a_date():
    """A VetVisit with no date fails validate()."""
    with pytest.raises(ValidationError):
        VetVisit(clinic="Bayside").validate()


def test_follow_up_before_visit_is_rejected(today):
    """A follow_up_on earlier than visit_date raises ValidationError."""
    visit = VetVisit(visit_date=today, follow_up_on=today - timedelta(days=1))
    with pytest.raises(ValidationError):
        visit.validate()


def test_upcoming_follow_ups_sorted_soonest_first(today):
    """Pending follow-ups come back in date order."""
    history = MedicalHistory(
        visits=[
            VetVisit(visit_date=today, follow_up_on=today + timedelta(days=30)),
            VetVisit(visit_date=today, follow_up_on=today + timedelta(days=5)),
        ]
    )
    pending = history.upcoming_follow_ups(today)
    assert pending[0].follow_up_on < pending[1].follow_up_on


def test_past_follow_ups_are_not_upcoming(today):
    """A follow-up that already happened is not pending."""
    history = MedicalHistory(
        visits=[VetVisit(visit_date=today, follow_up_on=today - timedelta(days=1))]
    )
    assert history.upcoming_follow_ups(today) == []


def test_last_visit_returns_most_recent(medical_history, today):
    """last_visit() ignores insertion order and uses the dates."""
    assert medical_history.last_visit().visit_date == today - timedelta(days=30)


def test_last_visit_of_empty_history_is_none():
    """A pet that has never been seen returns None."""
    assert MedicalHistory().last_visit() is None


def test_emergency_visit_is_flagged():
    """EMERGENCY and SURGERY read as emergencies; a checkup does not."""
    assert VetVisit(visit_type=VisitType.EMERGENCY).is_emergency()
    assert VetVisit(visit_type=VisitType.SURGERY).is_emergency()
    assert not VetVisit(visit_type=VisitType.CHECKUP).is_emergency()


def test_weight_history_tracks_visits_over_time(medical_history):
    """Weights recorded at visits come back as ordered (date, kg) pairs."""
    history = medical_history.weight_history()
    assert len(history) == 2
    assert history[0][0] < history[1][0]


def test_visits_in_range_filters_by_date(medical_history, today):
    """Only visits inside the window are returned."""
    recent = medical_history.visits_in_range(today - timedelta(days=60), today)
    assert len(recent) == 1


def test_empty_history_is_empty():
    """A fresh MedicalHistory reports is_empty() True."""
    assert MedicalHistory().is_empty()


def test_summary_line_mentions_conditions_and_boosters(medical_history, today):
    """The one-liner names what actually needs attention."""
    summary = medical_history.summary_line(today)
    assert "active condition" in summary
    assert "Rabies" in summary


def test_summary_line_of_clean_history():
    """Nothing on file reads as a clean bill of health."""
    assert "No health issues" in MedicalHistory().summary_line()


def test_remove_deletes_across_every_list(medical_history):
    """remove() finds a record whichever list it lives in."""
    target = medical_history.visits[0].id
    assert medical_history.remove(target) is True
    assert medical_history.remove("missing") is False


# --- grooming ---
def test_grooming_session_requires_services(today):
    """An empty service list fails validate()."""
    with pytest.raises(ValidationError):
        GroomingSession(session_date=today, services=[]).validate()


def test_grooming_session_requires_a_date():
    """A session with no date fails validate()."""
    with pytest.raises(ValidationError):
        GroomingSession(services=[GroomingService.BATH]).validate()


def test_grooming_due_when_next_due_passed(today):
    """A session whose next_due_on is yesterday marks the pet as due."""
    session = GroomingSession(
        session_date=today - timedelta(days=50), next_due_on=today - timedelta(days=1)
    )
    assert session.is_due_again(today)


def test_grooming_not_due_when_far_off(today):
    """A session due in two months is not yet due."""
    session = GroomingSession(session_date=today, next_due_on=today + timedelta(days=60))
    assert not session.is_due_again(today, lookahead_days=14)


def test_grooming_interval_averages_past_sessions(pet_with_records):
    """Three sessions six weeks apart yield a ~42 day interval."""
    assert pet_with_records.grooming_interval_days() == 42


def test_grooming_interval_needs_two_sessions(sample_pet, today):
    """One session is not enough to infer a cadence."""
    sample_pet.add_grooming_session(
        GroomingSession(session_date=today, services=[GroomingService.BATH])
    )
    assert sample_pet.grooming_interval_days() is None


def test_last_grooming_returns_most_recent_session(pet_with_records, today):
    """last_grooming() uses session_date, not list position."""
    assert pet_with_records.last_grooming().session_date == today - timedelta(days=42)


def test_days_since_grooming_is_correct(today):
    """days_since() counts calendar days from the session date."""
    session = GroomingSession(session_date=today - timedelta(days=47))
    assert session.days_since(today) == 47


def test_service_labels_are_human_readable():
    """Enum values are rendered without underscores."""
    session = GroomingSession(services=[GroomingService.NAIL_TRIM, GroomingService.BATH])
    assert session.service_labels() == ["nail trim", "bath"]


def test_records_round_trip_through_dict(medical_history):
    """A full history survives to_dict/from_dict unchanged."""
    assert MedicalHistory.from_dict(medical_history.to_dict()).to_dict() == (
        medical_history.to_dict()
    )
