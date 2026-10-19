"""JSON save/load. No database — these tests use tmp_path only."""

import json
from datetime import date, time

from pawpal.models.contact import VetClinic
from pawpal.models.enums import Species
from pawpal.models.owner import Owner
from pawpal.models.plan import DailyPlan, ScheduledTask
from pawpal.models.task import CareTask, MedicationTask
from pawpal.services import storage

DAY = date(2026, 6, 15)


def test_save_then_load_round_trips(owner_with_records, temp_save):
    """An owner saved and reloaded is equal to the original, pets and tasks included."""
    storage.save_state(owner_with_records, temp_save)
    restored = storage.load_state(temp_save)
    assert restored.to_dict() == owner_with_records.to_dict()


def test_round_trip_keeps_records(owner_with_records, temp_save):
    """Medical history, grooming log and bills all survive."""
    storage.save_state(owner_with_records, temp_save)
    pet = storage.load_state(temp_save).pets[0]
    original = owner_with_records.pets[0]
    assert len(pet.medical.visits) == len(original.medical.visits)
    assert len(pet.grooming_sessions) == len(original.grooming_sessions)
    assert len(pet.bills) == len(original.bills)


def test_task_subclasses_survive_the_round_trip(sample_owner, temp_save):
    """A MedicationTask loads back as a MedicationTask, not a bare CareTask."""
    sample_owner.pets[0].add_task(MedicationTask(title="Insulin", dosage="2 units"))
    storage.save_state(sample_owner, temp_save)
    restored_task = storage.load_state(temp_save).pets[0].tasks[0]
    assert isinstance(restored_task, MedicationTask)
    assert restored_task.dosage == "2 units"


def test_contacts_survive_the_round_trip(owner_with_contacts, temp_save):
    """A VetClinic reloads as a VetClinic with its emergency flag intact."""
    storage.save_state(owner_with_contacts, temp_save)
    restored = storage.load_state(temp_save)
    assert isinstance(restored.preferred_vet, VetClinic)
    assert restored.preferred_vet.is_emergency is True
    assert restored.emergency_contact.name == "Riley Chen"


def test_preferences_survive_the_round_trip(sample_owner, temp_save):
    """Times and the chosen strategy come back unchanged."""
    sample_owner.preferences.wake_time = time(6, 30)
    sample_owner.preferences.blocked_windows = [(time(9, 0), time(17, 0))]
    storage.save_state(sample_owner, temp_save)
    prefs = storage.load_state(temp_save).preferences
    assert prefs.wake_time == time(6, 30)
    assert prefs.blocked_windows == [(time(9, 0), time(17, 0))]


def test_missing_file_falls_back_to_seed(tmp_path):
    """load_state() on a nonexistent path returns demo data instead of raising."""
    owner = storage.load_state(tmp_path / "nothing.json")
    assert owner.pets
    assert owner.name


def test_corrupt_json_falls_back_to_seed(temp_save):
    """A malformed file is handled gracefully, not propagated as a crash."""
    temp_save.write_text("{not valid json", encoding="utf-8")
    owner = storage.load_state(temp_save)
    assert owner.pets


def test_save_is_atomic(sample_owner, temp_save):
    """No .tmp file is left behind and the target is valid JSON after a save."""
    storage.save_state(sample_owner, temp_save)
    assert not list(temp_save.parent.glob("*.tmp"))
    payload = json.loads(temp_save.read_text(encoding="utf-8"))
    assert payload["schema_version"] == storage.SCHEMA_VERSION


def test_legacy_payload_without_version_still_loads(temp_save):
    """A pre-versioning file stored the owner at the top level; _migrate handles it."""
    owner = Owner(name="Legacy")
    temp_save.write_text(json.dumps(owner.to_dict()), encoding="utf-8")
    assert storage.load_state(temp_save).name == "Legacy"


def test_history_appends_without_losing_past_days(tmp_path, sample_pet):
    """append_history() adds a day and keeps the earlier entries intact."""
    path = tmp_path / "history.json"
    for offset in range(3):
        plan = DailyPlan(day=date(2026, 6, 10 + offset), strategy_used="priority_first")
        plan.add_scheduled(
            ScheduledTask(
                task=CareTask(title="Walk", duration_minutes=20),
                pet=sample_pet,
                start_minute=420,
                end_minute=440,
            )
        )
        storage.append_history(plan, path)
    assert len(storage.load_history(path)) == 3


def test_history_replaces_the_same_day(tmp_path, sample_pet):
    """Re-logging the same date overwrites rather than duplicating it."""
    path = tmp_path / "history.json"
    for _ in range(2):
        storage.append_history(DailyPlan(day=DAY, strategy_used="x"), path)
    assert len(storage.load_history(path)) == 1


def test_load_history_of_missing_file_is_empty(tmp_path):
    """No history file yet means an empty list, not an error."""
    assert storage.load_history(tmp_path / "none.json") == []


def test_export_plan_writes_text(tmp_path, sample_pet):
    """export_plan() writes the text rendering for a .txt target."""
    plan = DailyPlan(day=DAY, strategy_used="priority_first")
    plan.add_scheduled(
        ScheduledTask(
            task=CareTask(title="Walk", duration_minutes=20),
            pet=sample_pet,
            start_minute=420,
            end_minute=440,
        )
    )
    path = storage.export_plan(plan, tmp_path / "plan.txt")
    assert "Walk" in path.read_text(encoding="utf-8")


def test_export_plan_writes_markdown(tmp_path, sample_pet):
    """A .md target gets the markdown table instead."""
    plan = DailyPlan(day=DAY, strategy_used="priority_first")
    plan.add_scheduled(
        ScheduledTask(
            task=CareTask(title="Walk", duration_minutes=20),
            pet=sample_pet,
            start_minute=420,
            end_minute=440,
        )
    )
    path = storage.export_plan(plan, tmp_path / "plan.md")
    assert "| Time |" in path.read_text(encoding="utf-8")


def test_saved_file_is_human_readable(sample_owner, temp_save):
    """The JSON is indented so a reader can diff it in git."""
    sample_owner.pets[0].species = Species.DOG
    storage.save_state(sample_owner, temp_save)
    assert "\n  " in temp_save.read_text(encoding="utf-8")
