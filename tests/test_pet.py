"""Pet behaviour: task CRUD and species/age-aware care needs."""

from datetime import date, timedelta

import pytest

from pawpal.models.enums import EnergyLevel, Species
from pawpal.models.pet import Pet
from pawpal.models.task import CareTask
from pawpal.utils.validation import ValidationError


def _dog(**kwargs) -> Pet:
    """A plain adult dog, overridable per test."""
    base = {"name": "Biscuit", "species": Species.DOG, "age_years": 4.0}
    return Pet(**{**base, **kwargs})


def test_add_task_appends(sample_pet):
    """add_task() puts the task in pet.tasks."""
    sample_pet.add_task(CareTask(title="Walk", duration_minutes=20))
    assert len(sample_pet.tasks) == 1


def test_add_task_validates(sample_pet):
    """An invalid task is rejected before it reaches the list."""
    with pytest.raises(ValidationError):
        sample_pet.add_task(CareTask(title="", duration_minutes=20))
    assert sample_pet.tasks == []


def test_remove_task_by_id(sample_pet):
    """remove_task() deletes the match and returns True."""
    task = CareTask(title="Walk", duration_minutes=20)
    sample_pet.add_task(task)
    assert sample_pet.remove_task(task.id) is True
    assert sample_pet.tasks == []


def test_remove_task_missing_returns_false(sample_pet):
    """Removing an unknown id is a no-op, not an exception."""
    assert sample_pet.remove_task("nope") is False


def test_get_task_finds_by_id(sample_pet):
    """get_task() resolves the task the UI is editing."""
    task = CareTask(title="Walk", duration_minutes=20)
    sample_pet.add_task(task)
    assert sample_pet.get_task(task.id) is task


def test_validate_rejects_blank_name():
    """A pet needs a name."""
    with pytest.raises(ValidationError):
        Pet(name="").validate()


def test_exercise_need_higher_for_high_energy_dog():
    """A high-energy dog needs more daily minutes than a low-energy one."""
    high = _dog(energy_level=EnergyLevel.HIGH).daily_exercise_need()
    low = _dog(energy_level=EnergyLevel.LOW).daily_exercise_need()
    assert high > low


def test_exercise_need_lower_for_senior():
    """A senior pet's target is reduced versus the same adult pet."""
    adult = _dog(age_years=4.0).daily_exercise_need()
    senior = _dog(age_years=12.0).daily_exercise_need()
    assert senior < adult


def test_cat_needs_less_than_dog():
    """Species changes the baseline, not just the modifiers."""
    dog = _dog().daily_exercise_need()
    cat = Pet(name="Mochi", species=Species.CAT, age_years=4.0).daily_exercise_need()
    assert cat < dog


def test_is_senior_uses_species_threshold():
    """A 10-year-old dog is senior; a 10-year-old cat is not."""
    assert _dog(age_years=10.0).is_senior()
    assert not Pet(name="Mochi", species=Species.CAT, age_years=10.0).is_senior()


def test_age_prefers_date_of_birth():
    """When a DOB is set it wins over the stored age_years number."""
    today = date(2026, 6, 15)
    pet = _dog(age_years=1.0, date_of_birth=today - timedelta(days=730))
    assert pet.age(today) == pytest.approx(2.0, abs=0.02)


def test_age_falls_back_to_age_years():
    """With no DOB the stored number is used unchanged."""
    assert _dog(age_years=5.0).age() == 5.0


def test_age_label_formats_young_animals():
    """Under a year reads in months, not '0y'."""
    today = date(2026, 6, 15)
    pet = _dog(date_of_birth=today - timedelta(days=120))
    assert "month" in pet.age_label(today)


def test_tasks_by_category_groups(sample_pet):
    """Tasks are bucketed by their category for the grouped view."""
    from pawpal.models.enums import TaskCategory

    sample_pet.add_task(CareTask(title="Walk", category=TaskCategory.WALK, duration_minutes=20))
    sample_pet.add_task(CareTask(title="Run", category=TaskCategory.WALK, duration_minutes=20))
    sample_pet.add_task(CareTask(title="Brush", category=TaskCategory.GROOMING, duration_minutes=5))
    grouped = sample_pet.tasks_by_category()
    assert len(grouped[TaskCategory.WALK]) == 2
    assert len(grouped[TaskCategory.GROOMING]) == 1
